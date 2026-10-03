import unittest

from planner import build_dry_run_plan, validate_plan


class DryRunPlannerTests(unittest.TestCase):
    def test_builds_structured_preview_without_execution(self):
        plan = build_dry_run_plan("Organize my project")
        self.assertEqual(plan["goal"], "Organize my project")
        self.assertEqual(plan["mode"], "dry_run")
        self.assertEqual(plan["source"], "local_template")
        self.assertFalse(plan["executionEnabled"])
        self.assertEqual(len(plan["steps"]), 4)
        self.assertTrue(all(step["status"] == "not_started" and step["sideEffects"] is False for step in plan["steps"]))

    def test_rejects_empty_non_string_and_oversized_goals(self):
        for goal in ("", "   ", None, "x" * 1201):
            with self.assertRaises(ValueError):
                build_dry_run_plan(goal)

    def test_model_plan_accepts_only_read_only_tools(self):
        from planner import build_remote_plan
        safe = [{"title": f"Inspect {i}", "detail": "Read-only inspection.", "tool": "workspace.list", "arguments": {"path": "."}} for i in range(1, 4)]
        plan = build_remote_plan("Inspect project", safe)
        self.assertTrue(all(step["tool"] == "workspace.list" for step in plan["steps"]))
        unsafe = [dict(step) for step in safe]
        unsafe[0]["tool"] = "shell.run"
        with self.assertRaises(ValueError):
            build_remote_plan("Inspect project", unsafe)

    def test_diff_preview_plan_requires_safe_bounded_arguments(self):
        from planner import build_remote_plan
        steps = [
            {"title": "Inspect file", "detail": "Read the existing file.", "tool": "workspace.read", "arguments": {"path": "src/main.py"}},
            {"title": "Preview proposed change", "detail": "Show a diff only; do not write.", "tool": "workspace.diff", "arguments": {"path": "src/main.py", "content": "print('proposed')"}},
            {"title": "List tasks", "detail": "Read saved tasks.", "tool": "tasks.list", "arguments": {}}
        ]
        plan = build_remote_plan("Preview a code change", steps)
        self.assertEqual(plan["steps"][1]["tool"], "workspace.diff")
        self.assertEqual(plan["steps"][1]["arguments"]["content"], "print('proposed')")
        tampered = dict(plan)
        tampered["steps"] = [dict(step) for step in plan["steps"]]
        tampered["steps"][1]["arguments"] = {"path": "../outside.py", "content": "x"}
        with self.assertRaises(ValueError):
            validate_plan(tampered)
        with self.assertRaises(ValueError):
            build_remote_plan("Preview a code change", [
                dict(steps[0]), dict(steps[1], arguments={"path": "src/main.py", "content": "x" * 16001}), dict(steps[2])
            ])

    def test_validator_rejects_execution_enabled_plan(self):
        plan = build_dry_run_plan("Review a change")
        plan["executionEnabled"] = True
        with self.assertRaises(ValueError):
            validate_plan(plan)

    def test_validator_rejects_step_side_effects(self):
        plan = build_dry_run_plan("Review a change")
        plan["steps"][0]["sideEffects"] = True
        with self.assertRaises(ValueError):
            validate_plan(plan)

    def test_validator_rejects_too_many_steps(self):
        plan = build_dry_run_plan("Review a change")
        plan["steps"] *= 3
        with self.assertRaises(ValueError):
            validate_plan(plan)


if __name__ == "__main__":
    unittest.main()
