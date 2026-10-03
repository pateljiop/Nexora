import tempfile
import unittest
from pathlib import Path

from server import Store
from workspace_changes import WorkspaceChangeError, WorkspaceChangeManager
from workspace_tools import Workspace


class WorkspaceChangeManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.root = base / "workspace"
        self.root.mkdir()
        (self.root / "notes.txt").write_text("original content\n", encoding="utf-8")
        self.store = Store(base / "state.sqlite3")
        self.backups = base / "backups"
        self.workspace = Workspace(self.root)
        self.manager = WorkspaceChangeManager(self.store, self.workspace, self.backups)

    def tearDown(self):
        self.temp.cleanup()

    def test_preview_requires_approval_and_apply_can_be_rolled_back(self):
        original = (self.root / "notes.txt").read_text(encoding="utf-8")
        proposal = self.manager.preview("notes.txt", "reviewed content\n")
        self.assertEqual(proposal["status"], "pending")
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), original)
        with self.assertRaises(WorkspaceChangeError):
            self.manager.apply(proposal["id"], approved=False)
        applied = self.manager.apply(proposal["id"], approved=True)
        self.assertEqual(applied["status"], "applied")
        self.assertTrue(applied["backupCreated"])
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), "reviewed content\n")
        rolled_back = self.manager.rollback(proposal["id"], approved=True)
        self.assertEqual(rolled_back["status"], "rolled_back")
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), original)

    def test_new_file_apply_and_rollback(self):
        proposal = self.manager.preview("src/new.py", "print('approved')\n") if (self.root / "src").mkdir(exist_ok=True) is None else None
        self.assertIsNotNone(proposal)
        self.assertFalse((self.root / "src" / "new.py").exists())
        self.manager.apply(proposal["id"], approved=True)
        self.assertTrue((self.root / "src" / "new.py").is_file())
        result = self.manager.rollback(proposal["id"], approved=True)
        self.assertEqual(result["status"], "rolled_back")
        self.assertFalse((self.root / "src" / "new.py").exists())

    def test_stale_proposal_is_not_applied(self):
        proposal = self.manager.preview("notes.txt", "first proposal\n")
        (self.root / "notes.txt").write_text("manual edit\n", encoding="utf-8")
        with self.assertRaises(WorkspaceChangeError):
            self.manager.apply(proposal["id"], approved=True)
        self.assertEqual(self.manager.get(proposal["id"])["status"], "stale")
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), "manual edit\n")

    def test_rollback_refuses_to_overwrite_later_user_edit(self):
        proposal = self.manager.preview("notes.txt", "approved content\n")
        self.manager.apply(proposal["id"], approved=True)
        (self.root / "notes.txt").write_text("user edit after apply\n", encoding="utf-8")
        with self.assertRaises(WorkspaceChangeError):
            self.manager.rollback(proposal["id"], approved=True)
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), "user edit after apply\n")

    def test_backup_failure_prevents_apply(self):
        blocker = Path(self.temp.name) / "backup-blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        manager = WorkspaceChangeManager(self.store, self.workspace, blocker)
        proposal = manager.preview("notes.txt", "must not be applied\n")
        with self.assertRaises(WorkspaceChangeError):
            manager.apply(proposal["id"], approved=True)
        self.assertEqual(manager.get(proposal["id"])["status"], "failed")
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), "original content\n")


if __name__ == "__main__":
    unittest.main()
