import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from execution_engine import ExecutionError, run_plan_execution
from planner import build_remote_plan
from server import Store
from workspace_tools import Workspace


class ExecutionEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "workspace"
        self.root.mkdir()
        (self.root / "readme.txt").write_text("hello", encoding="utf-8")
        self.store = Store(Path(self.temp.name) / "state.sqlite3")
        self.workspace = Workspace(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_runs_read_only_tools_and_does_not_claim_goal_verified(self):
        plan = build_remote_plan("Inspect workspace", [
            {"title": "List files", "detail": "Read-only list.", "tool": "workspace.list", "arguments": {"path": "."}},
            {"title": "Read readme", "detail": "Read-only preview.", "tool": "workspace.read", "arguments": {"path": "readme.txt"}},
            {"title": "List tasks", "detail": "Read-only task list.", "tool": "tasks.list", "arguments": {}}
        ])
        self.store.save_plan(plan)
        result = run_plan_execution(plan["id"], self.store, self.workspace)
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["goalVerified"])
        self.assertEqual(len(result["steps"]), 3)
        self.assertTrue(all(step["status"] == "completed" for step in result["steps"]))
        self.assertIn("goal has not been independently verified", result["verificationNote"])

    def test_cancellation_is_checked_between_steps(self):
        plan = build_remote_plan("Inspect workspace", [
            {"title": "List files", "detail": "Read-only list.", "tool": "workspace.list", "arguments": {"path": "."}},
            {"title": "Read readme", "detail": "Should be skipped after cancellation.", "tool": "workspace.read", "arguments": {"path": "readme.txt"}},
            {"title": "List tasks", "detail": "Should not run.", "tool": "tasks.list", "arguments": {}}
        ])
        self.store.save_plan(plan)
        original_list = self.workspace.list_files

        def list_and_request_cancel(path="."):
            result = original_list(path)
            active = self.store.list_executions()[0]
            self.store.request_execution_cancel(active["id"])
            return result

        self.workspace.list_files = list_and_request_cancel
        result = run_plan_execution(plan["id"], self.store, self.workspace)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["steps"][0]["status"], "completed")
        self.assertEqual(result["steps"][1]["status"], "skipped")
        self.assertEqual(result["steps"][2]["status"], "skipped")
        self.assertTrue(result["steps"][1]["finishedAt"])
        self.assertIn("cancellation was requested", result["steps"][1]["error"])

    def test_cancel_requested_during_final_step_is_not_reported_as_completed(self):
        plan = build_remote_plan("Inspect tasks", [
            {"title": "List files", "detail": "Read-only list.", "tool": "workspace.list", "arguments": {"path": "."}},
            {"title": "Read readme", "detail": "Read-only preview.", "tool": "workspace.read", "arguments": {"path": "readme.txt"}},
            {"title": "List tasks", "detail": "Request cancellation while final tool is in progress.", "tool": "tasks.list", "arguments": {}}
        ])
        self.store.save_plan(plan)
        original_list_tasks = self.store.list_tasks

        def list_tasks_and_cancel():
            result = original_list_tasks()
            active = self.store.list_executions()[0]
            self.store.request_execution_cancel(active["id"])
            return result

        self.store.list_tasks = list_tasks_and_cancel
        result = run_plan_execution(plan["id"], self.store, self.workspace)
        self.assertEqual(result["status"], "cancelled")
        self.assertTrue(all(step["status"] == "completed" for step in result["steps"]))
        self.assertIn("final read-only step", result["verificationNote"])

    def test_failed_step_marks_remaining_steps_skipped(self):
        plan = build_remote_plan("Inspect workspace", [
            {"title": "List files", "detail": "First read.", "tool": "workspace.list", "arguments": {"path": "."}},
            {"title": "Read readme", "detail": "Must be skipped.", "tool": "workspace.read", "arguments": {"path": "readme.txt"}},
            {"title": "List tasks", "detail": "Must also be skipped.", "tool": "tasks.list", "arguments": {}},
        ])
        self.store.save_plan(plan)
        with patch("execution_engine.execute_read_only_tool", side_effect=ValueError("simulated invalid result")):
            result = run_plan_execution(plan["id"], self.store, self.workspace)

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["goalVerified"])
        self.assertEqual([step["status"] for step in result["steps"]], ["failed", "skipped", "skipped"])
        self.assertTrue(all(step["finishedAt"] for step in result["steps"]))

    def test_execution_state_transitions_are_one_way(self):
        plan = build_remote_plan("Inspect workspace", [
            {"title": "List files", "detail": "Read-only list.", "tool": "workspace.list", "arguments": {"path": "."}},
            {"title": "Read readme", "detail": "Read-only preview.", "tool": "workspace.read", "arguments": {"path": "readme.txt"}},
            {"title": "List tasks", "detail": "Read-only tasks.", "tool": "tasks.list", "arguments": {}},
        ])
        self.store.save_plan(plan)
        execution = self.store.start_execution(plan, plan["steps"])
        step_id = plan["steps"][0]["id"]
        self.store.set_execution_step_status(execution["id"], step_id, "running")
        with self.assertRaises(ValueError):
            self.store.set_execution_step_status(execution["id"], step_id, "running")
        self.store.finish_execution_step(execution["id"], step_id, "completed", output={"ok": True})
        with self.assertRaises(ValueError):
            self.store.finish_execution_step(execution["id"], step_id, "failed", error="must not overwrite")
        with self.assertRaises(ValueError):
            self.store.finish_execution(execution["id"], "completed")
        self.assertEqual(self.store.get_execution(execution["id"])["steps"][0]["status"], "completed")
        self.assertFalse(self.store.get_execution(execution["id"])["goalVerified"])

    def test_rejects_local_template_plan(self):
        from planner import build_dry_run_plan
        plan = build_dry_run_plan("Make progress")
        self.store.save_plan(plan)
        with self.assertRaises(ExecutionError):
            run_plan_execution(plan["id"], self.store, self.workspace)

    def test_rejects_invalid_path_before_execution(self):
        with self.assertRaises(ValueError):
            build_remote_plan("Inspect workspace", [
                {"title": "List files", "detail": "Read-only list.", "tool": "workspace.list", "arguments": {"path": "."}},
                {"title": "Read path", "detail": "Must be rejected before saving.", "tool": "workspace.read", "arguments": {"path": "../outside"}},
                {"title": "List tasks", "detail": "Never reached.", "tool": "tasks.list", "arguments": {}}
            ])

    def test_restart_marks_running_execution_failed_without_retry(self):
        plan = build_remote_plan("Inspect workspace", [
            {"title": "List files", "detail": "Read-only list.", "tool": "workspace.list", "arguments": {"path": "."}},
            {"title": "Read readme", "detail": "Read-only preview.", "tool": "workspace.read", "arguments": {"path": "readme.txt"}},
            {"title": "List tasks", "detail": "Read-only task list.", "tool": "tasks.list", "arguments": {}}
        ])
        self.store.save_plan(plan)
        execution = self.store.start_execution(plan, plan["steps"])
        self.store.set_execution_step_status(execution["id"], plan["steps"][0]["id"], "running")
        recovered = self.store.recover_interrupted_executions()
        self.assertEqual(recovered, 1)
        result = self.store.get_execution(execution["id"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["steps"][0]["status"], "failed")
        self.assertEqual(result["steps"][1]["status"], "skipped")
        self.assertEqual(result["steps"][2]["status"], "skipped")
        self.assertFalse(result["goalVerified"])
        self.assertEqual(self.store.recover_interrupted_executions(), 0)

    def test_rejects_plan_with_no_tool_call(self):
        plan = build_remote_plan("Do something", [
            {"title": f"Step {i}", "detail": "No tool.", "tool": "none", "arguments": {}} for i in range(1, 4)
        ])
        self.store.save_plan(plan)
        with self.assertRaises(ExecutionError):
            run_plan_execution(plan["id"], self.store, self.workspace)


if __name__ == "__main__":
    unittest.main()
