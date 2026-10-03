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
