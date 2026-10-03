import tempfile
import unittest
from pathlib import Path

from server import Store
from tool_registry import ToolExecutionError, execute_read_only_tool, redact_text
from workspace_tools import Workspace


class ReadOnlyToolRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "workspace"
        self.root.mkdir()
        (self.root / "sample.txt").write_text("API_KEY=supersecret123\nnormal text", encoding="utf-8")
        self.workspace = Workspace(self.root)
        self.store = Store(Path(self.temp.name) / "state.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def test_workspace_list_and_read_are_read_only(self):
        listing = execute_read_only_tool("workspace.list", {"path": "."}, self.workspace, self.store)
        self.assertTrue(listing["readOnly"])
        self.assertIn("sample.txt", [item["path"] for item in listing["data"]["entries"]])
        preview = execute_read_only_tool("workspace.read", {"path": "sample.txt"}, self.workspace, self.store)
        self.assertTrue(preview["readOnly"])
        self.assertIn("[REDACTED]", preview["data"]["content"])
        self.assertIn("normal text", preview["data"]["content"])

    def test_task_list_and_unknown_tools(self):
        self.store.create_task("Keep safe", task_id="task-1")
        result = execute_read_only_tool("tasks.list", {}, self.workspace, self.store)
        self.assertEqual(result["data"]["tasks"][0]["title"], "Keep safe")
        with self.assertRaises(ToolExecutionError):
            execute_read_only_tool("shell.run", {"command": "whoami"}, self.workspace, self.store)

    def test_rejects_unsupported_arguments_and_path_escape(self):
        with self.assertRaises(ToolExecutionError):
            execute_read_only_tool("workspace.list", {"path": ".", "extra": "bad"}, self.workspace, self.store)
        with self.assertRaises(ToolExecutionError):
            execute_read_only_tool("workspace.read", {"path": "../outside"}, self.workspace, self.store)

    def test_redacts_common_token_patterns(self):
        result = redact_text("token=abcdefghijklmno and Bearer abcdefghijklmnop")
        self.assertNotIn("abcdefghijklmno", result)
        self.assertIn("[REDACTED]", result)

    def test_redacts_json_and_quoted_secret_assignments(self):
        samples = [
            '{"api_key": "json-super-secret-value"}',
            "{'client_secret': 'quoted-secret-value'}",
            'PASSWORD = "env-secret-value"',
        ]
        for sample, secret in zip(samples, ("json-super-secret-value", "quoted-secret-value", "env-secret-value")):
            with self.subTest(sample=sample):
                result = redact_text(sample)
                self.assertNotIn(secret, result)
                self.assertIn("[REDACTED]", result)


if __name__ == "__main__":
    unittest.main()
