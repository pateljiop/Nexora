"""Bounded sequential runner for explicitly requested read-only tool plans."""
from __future__ import annotations

import json
import uuid

from planner import validate_plan
from tool_registry import ToolExecutionError, execute_read_only_tool

MAX_EXECUTION_STEPS = 8


class ExecutionError(ValueError):
    pass


def validate_execution_plan(plan_id, store):
    if not isinstance(plan_id, str) or not plan_id:
        raise ExecutionError("A saved plan id is required.")
    plan = store.get_plan(plan_id)
    if not plan:
        raise ExecutionError("Plan not found.")
    try:
        validate_plan(plan)
    except ValueError as exc:
        raise ExecutionError(f"Saved plan is invalid: {exc}") from None
    steps = plan.get("steps", [])
    if plan.get("source") not in {"local_model", "remote_model"}:
        raise ExecutionError("Only model-generated plans with explicit read-only tool calls can run.")
    if not 1 <= len(steps) <= MAX_EXECUTION_STEPS:
        raise ExecutionError("Plan exceeds the execution step limit.")
    if any(step.get("tool") in (None, "none") for step in steps):
        raise ExecutionError("Every step must select an allowlisted read-only tool before running.")
    return plan, steps


def run_plan_execution(plan_id, store, workspace, execution_id=None):
    plan, steps = validate_execution_plan(plan_id, store)
    execution = store.get_execution(execution_id) if execution_id else store.start_execution(plan, steps)
    if not execution or execution["planId"] != plan["id"]:
        raise ExecutionError("Execution record does not match the saved plan.")
    for index, step in enumerate(steps):
        if store.is_execution_cancel_requested(execution["id"]):
            for remaining in steps[index:]:
                store.set_execution_step_status(execution["id"], remaining["id"], "skipped")
            store.finish_execution(execution["id"], "cancelled")
            store.add_activity("Read-only run cancelled", plan["goal"])
            return store.get_execution(execution["id"])
        store.set_execution_step_status(execution["id"], step["id"], "running")
        try:
            output = execute_read_only_tool(step["tool"], step.get("arguments", {}), workspace, store)
            store.finish_execution_step(execution["id"], step["id"], "completed", output=output)
        except (ToolExecutionError, ValueError) as exc:
            store.finish_execution_step(execution["id"], step["id"], "failed", error=str(exc)[:500])
            store.finish_execution(execution["id"], "failed")
            store.add_activity("Read-only run failed", plan["goal"])
            return store.get_execution(execution["id"])
        except Exception:
            store.finish_execution_step(execution["id"], step["id"], "failed", error="Unexpected tool failure.")
            store.finish_execution(execution["id"], "failed")
            store.add_activity("Read-only run failed", plan["goal"])
            return store.get_execution(execution["id"])
    store.finish_execution(execution["id"], "completed")
    store.add_activity("Read-only run completed; goal not verified", plan["goal"])
    return store.get_execution(execution["id"])
