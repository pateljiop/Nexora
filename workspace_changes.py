"""Approval-gated, reversible workspace file changes.

This manager is separate from the read-only agent tool registry. A proposal never
mutates a workspace; apply and rollback require explicit approval calls.
"""
from __future__ import annotations

import hashlib
import json
import uuid

from planner import now_iso
from tool_registry import redact_text
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
                error TEXT, receipt_json TEXT, operation TEXT NOT NULL DEFAULT 'apply'
            )""")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(workspace_changes)").fetchall()}
            if "receipt_json" not in columns:
                db.execute("ALTER TABLE workspace_changes ADD COLUMN receipt_json TEXT")
            if "operation" not in columns:
                db.execute("ALTER TABLE workspace_changes ADD COLUMN operation TEXT NOT NULL DEFAULT 'apply'")

    @staticmethod
    def _sha(content):
        return hashlib.sha256(content).hexdigest()

    def _metadata(self, row):
        return {
            "id": row["id"], "path": row["path"], "diff": redact_text(row["diff"]),
            "created": not bool(row["original_exists"]),
            "originalSha256": row["original_sha256"],
            "proposedSha256": row["proposed_sha256"],
            "status": row["status"], "createdAt": row["created_at"],
            "appliedAt": row["applied_at"], "rolledBackAt": row["rolled_back_at"],
            "error": row["error"],
        }

    def preview(self, relative, content):
        try:
            if not isinstance(content, str):
                raise WorkspaceChangeError("Proposed content must be text.")
            if redact_text(content) != content:
                raise WorkspaceChangeError("Proposed content resembles a credential or token. Remove secrets before creating a change proposal.")
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
                pending = db.execute("SELECT COUNT(*) AS count FROM workspace_changes WHERE status IN ('pending','applying')").fetchone()["count"]
                if pending >= MAX_PROPOSALS:
                    raise WorkspaceChangeError("There are too many pending workspace proposals. Apply, roll back, or dismiss older proposals first.")
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
            db.execute("UPDATE workspace_changes SET status='applying',operation='apply',error=NULL WHERE id=?", (proposal_id,))
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
                                    ("changed since", "changed after preview", "changed during", "appeared after preview", "stale")) else "failed"
            with self.store.connect() as db:
                db.execute("UPDATE workspace_changes SET status=?,error=? WHERE id=? AND status='applying'",
                           (status, message[:500], proposal_id))
            raise WorkspaceChangeError(message) from None
        except Exception:
            # A low-level failure may happen after the atomic replace but before the
            # receipt/status commit. Observe disk and reconcile; never guess or replay.
            self.recover_interrupted_changes()
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
            db.execute("UPDATE workspace_changes SET status='applying',operation='rollback',error=NULL WHERE id=?", (proposal_id,))
            record = dict(row)
        try:
            if record["receipt_json"]:
                receipt = json.loads(record["receipt_json"])
                result = self.workspace.rollback_write(receipt, backup_root=str(self.backup_root) if self.backup_root else None)
            elif record["original_exists"]:
                original = bytes(record["original_content"]).decode("utf-8")
                self.workspace.write_file(
                    record["path"], original, expected_sha256=record["proposed_sha256"],
                    backup_root=str(self.backup_root) if self.backup_root else None,
                )
                result = {"path": record["path"], "rolledBack": True, "receiptRecoveredFromDatabase": True}
            else:
                result = self.workspace.rollback_write(
                    {"path": record["path"], "sha256": record["proposed_sha256"], "created": True},
                    backup_root=str(self.backup_root) if self.backup_root else None,
                )
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
        except Exception:
            # Rollback may have reached disk before a persistence failure. Reconcile
            # against the original/proposed hashes rather than leaving a false state.
            self.recover_interrupted_changes()
            raise

    def recover_interrupted_changes(self):
        """Reconcile disk state after interruption without repeating any mutation."""
        with self.store.connect() as db:
            rows = db.execute("SELECT * FROM workspace_changes WHERE status='applying'").fetchall()
        for row in rows:
            current_sha = None
            try:
                current = self.workspace.read_file(row["path"])
                current_sha = self._sha(current["content"].encode("utf-8"))
            except WorkspaceError:
                current_sha = None
            original_state = current_sha == row["original_sha256"] if row["original_exists"] else current_sha is None
            proposed_state = current_sha == row["proposed_sha256"]
            operation = row["operation"] if "operation" in row.keys() else "apply"
            if operation == "rollback" and original_state:
                status, note = "rolled_back", "Rollback reached disk before restart; status reconciled without retry."
            elif operation == "rollback" and proposed_state:
                status, note = "applied", "Rollback did not change the target before restart; review before retrying."
            elif operation == "apply" and proposed_state:
                status, note = "applied", "Proposed content reached disk before restart. The saved SQLite snapshot is available for rollback."
            elif operation == "apply" and original_state:
                status, note = "failed", "Server restarted before the proposal was applied; no automatic retry occurred."
            else:
                status, note = "stale", "Server restarted during the change and disk state matches neither snapshot; inspect manually."
            with self.store.connect() as db:
                db.execute("UPDATE workspace_changes SET status=?,error=? WHERE id=? AND status='applying'",
                           (status, note, row["id"]))
            self.store.add_activity("Interrupted file change reconciled", row["path"])
        return len(rows)
