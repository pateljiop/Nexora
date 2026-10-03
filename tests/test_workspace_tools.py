import os
import tempfile
import unittest
from pathlib import Path

from workspace_tools import Workspace, WorkspaceError


class WorkspaceToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "workspace"
        self.root.mkdir()
        (self.root / "notes.txt").write_text("hello workspace", encoding="utf-8")
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_text("print('safe')", encoding="utf-8")
        (self.root / ".env").write_text("API_KEY=secret", encoding="utf-8")
        (self.root / "data").mkdir()
        (self.root / "data" / "private.txt").write_text("private", encoding="utf-8")
        self.workspace = Workspace(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_lists_relative_files_and_excludes_private_paths(self):
        listing = self.workspace.list_files()
        paths = {item["path"] for item in listing["entries"]}
        self.assertIn("notes.txt", paths)
        self.assertIn("src/main.py", paths)
        self.assertNotIn(".env", paths)
        self.assertFalse(any(path.startswith("data/") for path in paths))

    def test_reads_utf8_text_with_read_only_metadata(self):
        result = self.workspace.read_file("src/main.py")
        self.assertEqual(result["content"], "print('safe')")
        self.assertTrue(result["readOnly"])

    def test_rejects_traversal_absolute_and_secret_paths(self):
        for path in ("../outside.txt", str(self.root / "notes.txt"), ".env", "data/private.txt", "src\\main.py"):
            with self.assertRaises(WorkspaceError):
                self.workspace.read_file(path)

    def test_rejects_oversized_and_binary_files(self):
        (self.root / "large.txt").write_bytes(b"x" * (256 * 1024 + 1))
        (self.root / "binary.bin").write_bytes(b"\xff\x00\xfe")
        with self.assertRaises(WorkspaceError):
            self.workspace.read_file("large.txt")
        with self.assertRaises(WorkspaceError):
            self.workspace.read_file("binary.bin")

    def test_preview_write_shows_diff_without_modifying_file(self):
        original = (self.root / "notes.txt").read_text(encoding="utf-8")
        result = self.workspace.preview_write("notes.txt", "hello updated workspace")
        self.assertTrue(result["readOnly"])
        self.assertFalse(result["created"])
        self.assertIn("-hello workspace", result["diff"])
        self.assertIn("+hello updated workspace", result["diff"])
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), original)

    def test_preview_new_file_and_reject_unsafe_or_oversized_proposals(self):
        result = self.workspace.preview_write("src/new.py", "print('preview only')")
        self.assertTrue(result["created"])
        self.assertIn("+print('preview only')", result["diff"])
        self.assertFalse((self.root / "src" / "new.py").exists())
        for path in ("../outside.txt", ".env", "missing/new.py"):
            with self.subTest(path=path), self.assertRaises(WorkspaceError):
                self.workspace.preview_write(path, "content")
        with self.assertRaises(WorkspaceError):
            self.workspace.preview_write("notes.txt", "x" * (64 * 1024 + 1))

    def test_rejects_symlink_outside_root(self):
        outside = Path(self.temp.name) / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        link = self.root / "outside-link.txt"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks are unavailable on this runner.")
        with self.assertRaises(WorkspaceError):
            self.workspace.read_file("outside-link.txt")


if __name__ == "__main__":
    unittest.main()
