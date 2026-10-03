"""Approval-gated, reversible workspace file changes.

This manager is separate from the read-only agent tool registry. A proposal never
mutates a workspace; apply and rollback require explicit approval calls.
"""
from __future__ import annotations

import hashlib
import json
import uuid

from planner import now_iso
from workspace_tools import MAX_WRITE_BYTES, WorkspaceError

MAX_PROPOSALS = 50


class WorkspaceChangeError(ValueError):
    pass


class WorkspaceChangeManager:
    def __init__(self, store, workspace, backup_root=None):
        self.store = store
        self.workspace = workspace
        self.backup_root = backup_root
        with self.store.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS workspace_changes (
                id TEXT PRIMARY KEY, path TEXT NOT NULL, diff TEXT NOT NULL,
                original_exists INTEGER NOT NULL, original_content BLOB,
                original_sha256 TEXT, proposed_content BLOB NOT NULL,
                proposed_sha256 TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','applying','applied','rolled_back','stale','failed')),
                created_at TEXT NOT NULL, applied_at TEXT, rolled_back_at TEXT,
                error TEXT, receipt_json TEXT
            )""")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(workspace_changes)").fetchall()}
            if "receipt_json" not in columns:
                db.execute("ALTER TABLE workspace_changes ADD COLUMN receipt_json TEXT")

    @staticmethod
    def _sha(content):
        return hashlib.sha256(content).hexdigest()

    def _metadata(self, row):
        return {
            "id": row["id"], "path": row["path"], "diff": row["diff"],
            "created": not bool(row["original_exists"]),
            "originalSha256": row["original_sha256"],
            "proposedSha256": row["proposed_sha256"],
            "status": row["status"], "createdAt": row["created_at"],
            "appliedAt": row["applied_at"], "rolledBackAt": row["rolled_back_at"],
            "error": row["error"],
        }

    def preview(self, relative, content):
        try:
            preview = self.workspace.preview_write(relative, content)
            original_exists = not preview["created"]
            original_content = None
            original_sha = None
            if original_exists:
                current = self.workspace.read_file(preview["path"])
                original_content = current["content"].encode("utf-8")
                if len(original_content) > MAX_WRITE_BYTES:
                    raise WorkspaceChangeError("Files over 64 KiB cannot be changed in this approval-gated milestone.")
                original_sha = self._sha(original_content)
            proposed = content.encode("utf-8")
            proposal_id = str(uuid.uuid4())
            created_at = now_iso()
            with self.store.connect() as db:
                db.execute(
                    """INSERT INTO workspace_changes
                       (id,path,diff,original_exists,original_content,original_sha256,
                        proposed_content,proposed_sha256,status,created_at)
                       VALUES(?,?,?,?,?,?,?,?,'pending',?)""",
                    (proposal_id, preview["path"], preview["diff"], int(original_exists),
                     original_content, original_sha, proposed, self._sha(proposed), created_at)
                )
                db.execute("""DELETE FROM workspace_changes
                              WHERE id IN (SELECT id FROM workspace_changes
                                           WHERE status IN ('applied','rolled_back','stale','failed')
                                           ORDER BY created_at DESC LIMIT -1 OFFSET ?)""", (MAX_PROPOSALS,))
            self.store.add_activity("Workspace change proposed", preview["path"])
            return self.get(proposal_id)
        except WorkspaceError as exc:
            raise WorkspaceChangeError(str(exc)) from None

    def get(self, proposal_id):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM workspace_changes WHERE id=?", (proposal_id,)).fetchone()
        return self._metadata(row) if row else None

    def list(self):
        with self.store.connect() as db:
            rows = db.execute("SELECT * FROM workspace_changes ORDER BY created_at DESC LIMIT 20").fetchall()
        return [self._metadata(row) for row in rows]

    def apply(self, proposal_id, approved):
        if approved is not True:
            raise WorkspaceChangeError("Explicit approval is required before applying a file change.")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM workspace_changes WHERE id=?", (proposal_id,)).fetchone()
            if not row:
                raise WorkspaceChangeError("Change proposal not found.")
            if row["status"] != "pending":
                raise WorkspaceChangeError("Only a pending proposal can be applied.")
            db.execute("UPDATE workspace_changes SET status='applying',error=NULL WHERE id=?", (proposal_id,))
            record = dict(row)
        try:
            proposed = bytes(record["proposed_content"]).decode("utf-8")
            receipt = self.workspace.write_file(
                record["path"], proposed,
                expected_sha256=record["original_sha256"] if record["original_exists"] else "missing",
                backup_root=str(self.backup_root) if self.backup_root else None,
            )
            with self.store.connect() as db:
                db.execute("""UPDATE workspace_changes
                              SET status='applied',applied_at=?,error=NULL,receipt_json=?
                              WHERE id=? AND status='applying'""",
                           (now_iso(), json.dumps(receipt, ensure_ascii=False), proposal_id))
            self.store.add_activity("Approved workspace change applied", record["path"])
            result = self.get(proposal_id)
            result["appliedSha256"] = receipt["sha256"]
            result["backupCreated"] = bool(receipt.get("backupPath"))
            return result
        except WorkspaceError as exc:
            message = str(exc)
            status = "stale" if any(token in message.lower() for token in
                                    ("changed since", "changed during", "appeared after preview", "stale")) else "failed"
            with self.store.connect() as db:
                db.execute("UPDATE workspace_changes SET status=?,error=? WHERE id=? AND status='applying'",
                           (status, message[:500], proposal_id))
            raise WorkspaceChangeError(message) from None
        except Exception:
            with self.store.connect() as db:
                db.execute("""UPDATE workspace_changes SET status='failed',
                              error='Apply failed unexpectedly; inspect the file and backup before retrying.'
                              WHERE id=? AND status='applying'""", (proposal_id,))
            raise

    def rollback(self, proposal_id, approved):
        if approved is not True:
            raise WorkspaceChangeError("Explicit approval is required before rolling back a file change.")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM workspace_changes WHERE id=?", (proposal_id,)).fetchone()
            if not row:
                raise WorkspaceChangeError("Change proposal not found.")
            if row["status"] != "applied":
                raise WorkspaceChangeError("Only an applied change can be rolled back.")
            if not row["receipt_json"]:
                raise WorkspaceChangeError("Write receipt is missing; rollback is unavailable.")
            db.execute("UPDATE workspace_changes SET status='applying',error=NULL WHERE id=?", (proposal_id,))
            record = dict(row)
        try:
            receipt = json.loads(record["receipt_json"])
            result = self.workspace.rollback_write(receipt, backup_root=str(self.backup_root) if self.backup_root else None)
            with self.store.connect() as db:
                db.execute("""UPDATE workspace_changes SET status='rolled_back',rolled_back_at=?,error=NULL
                              WHERE id=? AND status='applying'""", (now_iso(), proposal_id))
            self.store.add_activity("Approved workspace change rolled back", record["path"])
            return {**self.get(proposal_id), "rollback": result}
        except (WorkspaceError, WorkspaceChangeError) as exc:
            with self.store.connect() as db:
                db.execute("UPDATE workspace_changes SET status='applied',error=? WHERE id=? AND status='applying'",
                           (str(exc)[:500], proposal_id))
            raise WorkspaceChangeError(str(exc)) from None

    def recover_interrupted_changes(self):
        """Mark uncertain applies as failed for human inspection; never retry automatically."""
        with self.store.connect() as db:
            rows = db.execute("SELECT id,path FROM workspace_changes WHERE status='applying'").fetchall()
            for row in rows:
                db.execute("""UPDATE workspace_changes SET status='failed',
                              error='Server restarted during apply/rollback. Inspect the target and backup; no retry was attempted.'
                              WHERE id=? AND status='applying'""", (row["id"],))
        for row in rows:
            self.store.add_activity("Interrupted file change requires review", row["path"])
        return len(rows)
