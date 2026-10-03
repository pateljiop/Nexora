"""Transparent, deterministic plan previews. This module never executes actions."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

MAX_GOAL_LENGTH = 1200
MAX_PLAN_STEPS = 8
PLAN_MODE = "dry_run"
PLAN_SOURCE = "local_template"
ALLOWED_PLAN_SOURCES = {"local_template", "remote_model", "local_model"}
ALLOWED_READ_ONLY_TOOLS = {"workspace.list", "workspace.read", "tasks.list", "none"}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_dry_run_plan(goal, created_at=None):
    if not isinstance(goal, str):
        raise ValueError("Goal must be a string.")
    goal = goal.strip()
    if not goal:
        raise ValueError("Write a goal before requesting a plan.")
    if len(goal) > MAX_GOAL_LENGTH:
        raise ValueError(f"Goal must be {MAX_GOAL_LENGTH} characters or fewer.")
    created_at = created_at or now_iso()
    plan = {
        "id": str(uuid.uuid4()),
        "goal": goal,
        "mode": PLAN_MODE,
        "source": PLAN_SOURCE,
        "status": "preview",
        "createdAt": created_at,
        "executionEnabled": False,
        "steps": [
            {"id": "step-1", "title": "Define the expected outcome", "detail": "Turn the goal into observable success criteria before taking action.", "status": "not_started", "risk": "low", "sideEffects": False},
            {"id": "step-2", "title": "Identify required inputs and boundaries", "detail": "List relevant files, resources, and constraints. No resources are accessed in preview mode.", "status": "not_started", "risk": "low", "sideEffects": False},
            {"id": "step-3", "title": "Prepare a small, reversible action sequence", "detail": "Keep steps bounded. Any future sensitive action must be permission-gated before execution.", "status": "not_started", "risk": "low", "sideEffects": False},
            {"id": "step-4", "title": "Verify results against the goal", "detail": "Define evidence to inspect and report what succeeded, failed, or remains uncertain.", "status": "not_started", "risk": "low", "sideEffects": False}
        ]
    }
    return validate_plan(plan)


def build_remote_plan(goal, model_steps, created_at=None, source="remote_model"):
    if not isinstance(goal, str):
        raise ValueError("Goal must be a string.")
    goal = goal.strip()
    if not goal or len(goal) > MAX_GOAL_LENGTH:
        raise ValueError("Goal is invalid.")
    if not isinstance(model_steps, list) or not 3 <= len(model_steps) <= MAX_PLAN_STEPS:
        raise ValueError("Model plan must contain between 3 and 8 steps.")
    steps = []
    for index, item in enumerate(model_steps, start=1):
        if not isinstance(item, dict):
            raise ValueError("Model plan step must be an object.")
        title = item.get("title")
        detail = item.get("detail")
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 160:
            raise ValueError("Model plan step title is invalid.")
        if not isinstance(detail, str) or len(detail.strip()) > 500:
            raise ValueError("Model plan step detail is invalid.")
        tool = item.get("tool", "none")
        arguments = item.get("arguments", {})
        if not isinstance(tool, str) or tool not in ALLOWED_READ_ONLY_TOOLS:
            raise ValueError("Model plan requested a tool outside the read-only allowlist.")
        if not isinstance(arguments, dict):
            raise ValueError("Plan tool arguments must be an object.")
        if tool == "workspace.read":
            path = arguments.get("path")
            if not isinstance(path, str) or not path.strip() or len(path) > 1000:
                raise ValueError("workspace.read requires a relative path.")
            arguments = {"path": path.strip()}
        elif tool == "workspace.list":
            path = arguments.get("path", ".")
            if not isinstance(path, str) or len(path) > 1000:
                raise ValueError("workspace.list path is invalid.")
            arguments = {"path": path.strip() or "."}
        else:
            if arguments:
                raise ValueError("This tool does not accept arguments.")
            arguments = {}
        steps.append({"id": f"step-{index}", "title": title.strip(), "detail": detail.strip(),
                      "tool": tool, "arguments": arguments,
                      "status": "not_started", "risk": "low", "sideEffects": False})
    if source not in {"remote_model", "local_model"}:
        raise ValueError("Model plan source is invalid.")
    plan = {"id": str(uuid.uuid4()), "goal": goal, "mode": PLAN_MODE, "source": source,
            "status": "preview", "createdAt": created_at or now_iso(),
            "executionEnabled": False, "steps": steps}
    return validate_plan(plan)


def validate_plan(value):
    if not isinstance(value, dict):
        raise ValueError("Plan must be an object.")
    goal = value.get("goal")
    steps = value.get("steps")
    if not isinstance(goal, str) or not goal.strip() or len(goal) > MAX_GOAL_LENGTH:
        raise ValueError("Plan goal is invalid.")
    if value.get("mode") != PLAN_MODE or value.get("source") not in ALLOWED_PLAN_SOURCES:
        raise ValueError("Only local dry-run plans are supported.")
    if value.get("status") != "preview" or value.get("executionEnabled") is not False:
        raise ValueError("Plan must remain in preview mode.")
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_PLAN_STEPS:
        raise ValueError("Plan step count is invalid.")
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict) or step.get("id") != f"step-{index}":
            raise ValueError("Plan step identifiers are invalid.")
        if not isinstance(step.get("title"), str) or not step["title"].strip() or len(step["title"]) > 160:
            raise ValueError("Plan step title is invalid.")
        if not isinstance(step.get("detail"), str) or len(step["detail"]) > 500:
            raise ValueError("Plan step detail is invalid.")
        if step.get("status") != "not_started" or step.get("sideEffects") is not False or step.get("risk") != "low":
            raise ValueError("Dry-run steps cannot have side effects.")
        if "tool" in step:
            if step.get("tool") not in ALLOWED_READ_ONLY_TOOLS or not isinstance(step.get("arguments"), dict):
                raise ValueError("Plan tool is outside the read-only allowlist.")
    return value
