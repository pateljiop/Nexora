import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from server import Store
from workspace_changes import WorkspaceChangeError, WorkspaceChangeManager
from workspace_tools import Workspace, WorkspaceError


class WorkspaceChangeManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.root = base / "workspace"
        self.root.mkdir()
        (self.root / "notes.txt").write_text("original text\n", encoding="utf-8")
        self.store = Store(base / "state.sqlite3")
        self.backups = base / "backups"
        self.manager = WorkspaceChangeManager(self.store, Workspace(self.root), self.backups)

    def tearDown(self):
        self.temp.cleanup()

    def test_preview_is_persistent_but_never_mutates_file(self):
        proposal = self.manager.preview("notes.txt", "proposed text\n")
        self.assertEqual(proposal["status"], "pending")
        self.assertIn("-original text", proposal["diff"])
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), "original text\n")
        self.assertEqual(self.manager.get(proposal["id"])["proposedSha256"], proposal["proposedSha256"])

    def test_apply_requires_explicit_approval_and_rollback_restores_backup(self):
        proposal = self.manager.preview("notes.txt", "updated text\n")
        with self.assertRaises(WorkspaceChangeError):
            self.manager.apply(proposal["id"], False)
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), "original text\n")
        applied = self.manager.apply(proposal["id"], True)
        self.assertEqual(applied["status"], "applied")
        self.assertTrue(applied["backupCreated"])
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), "updated text\n")
        rolled_back = self.manager.rollback(proposal["id"], True)
        self.assertEqual(rolled_back["status"], "rolled_back")
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), "original text\n")

    def test_created_file_can_be_rolled_back_only_by_its_receipt(self):
        proposal = self.manager.preview("generated.txt", "generated\n")
        applied = self.manager.apply(proposal["id"], True)
        self.assertTrue(applied["created"])
        self.assertTrue((self.root / "generated.txt").exists())
        self.manager.rollback(proposal["id"], True)
        self.assertFalse((self.root / "generated.txt").exists())

    def test_stale_proposal_never_overwrites_a_newer_edit(self):
        proposal = self.manager.preview("notes.txt", "AI proposed text\n")
        (self.root / "notes.txt").write_text("human edit\n", encoding="utf-8")
        with self.assertRaises(WorkspaceChangeError):
            self.manager.apply(proposal["id"], True)
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), "human edit\n")
        self.assertEqual(self.manager.get(proposal["id"])["status"], "stale")

    def test_rollback_refuses_to_overwrite_edits_made_after_apply(self):
        proposal = self.manager.preview("notes.txt", "approved text\n")
        self.manager.apply(proposal["id"], True)
        (self.root / "notes.txt").write_text("edit after apply\n", encoding="utf-8")
        with self.assertRaises(WorkspaceChangeError):
            self.manager.rollback(proposal["id"], True)
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), "edit after apply\n")
        self.assertEqual(self.manager.get(proposal["id"])["status"], "stale")

    def test_secret_like_proposals_are_rejected_and_saved_diffs_are_redacted(self):
        with self.assertRaises(WorkspaceChangeError):
            self.manager.preview("notes.txt", "API_KEY=supersecret123\n")
        (self.root / "notes.txt").write_text("API_KEY=supersecret123\n", encoding="utf-8")
        proposal = self.manager.preview("notes.txt", "safe content\n")
        self.assertNotIn("supersecret123", proposal["diff"])
        self.assertIn("[REDACTED]", proposal["diff"])

    def test_reconciles_interrupted_apply_and_recovers_rollback_without_receipt(self):
        proposal = self.manager.preview("notes.txt", "new content\n")
        with self.store.connect() as db:
            db.execute("UPDATE workspace_changes SET status='applying',operation='apply' WHERE id=?", (proposal["id"],))
        self.manager.workspace.write_file(
            "notes.txt", "new content\n",
            expected_sha256=proposal["originalSha256"], backup_root=str(self.backups)
        )
        self.assertEqual(self.manager.recover_interrupted_changes(), 1)
        recovered = self.manager.get(proposal["id"])
        self.assertEqual(recovered["status"], "applied")
        rolled_back = self.manager.rollback(proposal["id"], True)
        self.assertEqual(rolled_back["status"], "rolled_back")
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), "original text\n")

    def test_unexpected_exception_after_apply_write_reconciles_and_keeps_rollback_available(self):
        proposal = self.manager.preview("notes.txt", "durable new version\n")
        original_write = self.manager.workspace.write_file

        def write_then_interrupt(*args, **kwargs):
            original_write(*args, **kwargs)
            raise RuntimeError("simulated failure after atomic replace")

        with patch.object(self.manager.workspace, "write_file", side_effect=write_then_interrupt):
            with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                self.manager.apply(proposal["id"], True)

        recovered = self.manager.get(proposal["id"])
        self.assertEqual(recovered["status"], "applied")
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), "durable new version\n")
        rolled_back = self.manager.rollback(proposal["id"], True)
        self.assertEqual(rolled_back["status"], "rolled_back")
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), "original text\n")

    def test_unexpected_exception_after_rollback_write_reconciles_status(self):
        proposal = self.manager.preview("notes.txt", "durable new version\n")
        self.manager.apply(proposal["id"], True)
        original_rollback = self.manager.workspace.rollback_write

        def rollback_then_interrupt(*args, **kwargs):
            original_rollback(*args, **kwargs)
            raise RuntimeError("simulated failure after rollback replace")

        with patch.object(self.manager.workspace, "rollback_write", side_effect=rollback_then_interrupt):
            with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                self.manager.rollback(proposal["id"], True)

        self.assertEqual(self.manager.get(proposal["id"])["status"], "rolled_back")
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), "original text\n")

    def test_rollback_rechecks_created_file_before_deleting(self):
        proposal = self.manager.preview("generated.txt", "generated\n")
        self.manager.apply(proposal["id"], True)
        target = self.root / "generated.txt"
        real_read = Path.read_bytes
        reads = {"target": 0}

        def race_on_second_read(path):
            if path == target:
                reads["target"] += 1
                if reads["target"] == 2:
                    target.write_text("human edit\n", encoding="utf-8")
            return real_read(path)

        with patch.object(Path, "read_bytes", new=race_on_second_read):
            with self.assertRaises(WorkspaceChangeError):
                self.manager.rollback(proposal["id"], True)
        self.assertEqual(target.read_text(encoding="utf-8"), "human edit\n")
        self.assertEqual(self.manager.get(proposal["id"])["status"], "stale")

    def test_recovery_marks_unknown_new_file_state_stale_not_missing(self):
        proposal = self.manager.preview("generated.txt", "generated\n")
        with self.store.connect() as db:
            db.execute(
                "UPDATE workspace_changes SET status='applying',operation='rollback' WHERE id=?",
                (proposal["id"],),
            )
        with patch.object(self.manager.workspace, "file_sha256_or_missing",
                          side_effect=WorkspaceError("target state could not be read")):
            self.manager.recover_interrupted_changes()
        self.assertEqual(self.manager.get(proposal["id"])["status"], "stale")

    def test_concurrent_proposals_for_same_file_do_not_overwrite_each_other(self):
        first = self.manager.preview("notes.txt", "first approved version\n")
        second = self.manager.preview("notes.txt", "second approved version\n")

        def apply(proposal_id):
            try:
                return self.manager.apply(proposal_id, True)["status"]
            except WorkspaceChangeError:
                return self.manager.get(proposal_id)["status"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(apply, (first["id"], second["id"])))

        self.assertEqual(statuses.count("applied"), 1)
        self.assertEqual(statuses.count("stale"), 1)
        current = (self.root / "notes.txt").read_text(encoding="utf-8")
        self.assertIn(current, {"first approved version\n", "second approved version\n"})

    def test_pending_proposals_are_bounded(self):
        for index in range(50):
            self.manager.preview("notes.txt", f"proposal number {index}\n")
        with self.assertRaises(WorkspaceChangeError):
            self.manager.preview("notes.txt", "one too many\n")

    def test_backup_failure_does_not_mutate_target(self):
        blocked_backup_path = Path(self.temp.name) / "not-a-directory"
        blocked_backup_path.write_text("not a directory", encoding="utf-8")
        manager = WorkspaceChangeManager(self.store, Workspace(self.root), blocked_backup_path)
        proposal = manager.preview("notes.txt", "must not be written\n")
        with self.assertRaises(WorkspaceChangeError):
            manager.apply(proposal["id"], True)
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), "original text\n")
        self.assertEqual(manager.get(proposal["id"])["status"], "failed")


if __name__ == "__main__":
    unittest.main()
