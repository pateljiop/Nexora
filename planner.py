"""Transparent, deterministic plan previews. This module never executes actions."""
from __future__ import annotations

import uuid
from pathlib import PurePosixPath
from datetime import datetime, timezone

MAX_GOAL_LENGTH = 1200
MAX_PLAN_STEPS = 8
PLAN_MODE = "dry_run"
PLAN_SOURCE = "local_template"
ALLOWED_PLAN_SOURCES = {"local_template", "remote_model", "local_model"}
ALLOWED_READ_ONLY_TOOLS = {"workspace.list", "workspace.read", "workspace.diff", "tasks.list", "none"}


BLOCKED_WORKSPACE_PARTS = {
    ".git", ".env", ".env.local", ".env.production", ".ssh", "data",
    "node_modules", "__pycache__", ".venv", "venv", ".next", "dist",
    "build", "secrets", "credentials",
}


def _safe_relative_path(value, allow_dot=False):
    if not isinstance(value, str) or not value.strip() or len(value) > 1000:
        return False
    if "\x00" in value or "\\" in value or ":" in value:
        return False
    if allow_dot and value.strip() == ".":
        return True
    path = PurePosixPath(value)
    if path.is_absolute() or not all(part not in {"", ".", ".."} for part in path.parts):
        return False
    for part in path.parts:
        lowered = part.lower()
        if part.startswith(".") or lowered in BLOCKED_WORKSPACE_PARTS or lowered.endswith((".pem", ".key", ".p12", ".pfx")):
            return False
    return True


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
            if not _safe_relative_path(path):
                raise ValueError("workspace.read requires a safe relative path.")
            arguments = {"path": path.strip()}
        elif tool == "workspace.diff":
            path, content = arguments.get("path"), arguments.get("content")
            if not _safe_relative_path(path):
                raise ValueError("workspace.diff requires a safe relative path.")
            if not isinstance(content, str) or len(content) > 16000:
                raise ValueError("workspace.diff content must be text of at most 16000 characters.")
            arguments = {"path": path.strip(), "content": content}
        elif tool == "workspace.list":
            path = arguments.get("path", ".")
            if not _safe_relative_path(path, allow_dot=True):
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
            tool, arguments = step.get("tool"), step.get("arguments")
            if tool not in ALLOWED_READ_ONLY_TOOLS or not isinstance(arguments, dict):
                raise ValueError("Plan tool is outside the read-only allowlist.")
            if tool == "workspace.list":
                if set(arguments) - {"path"} or ("path" in arguments and not _safe_relative_path(arguments["path"], allow_dot=True)):
                    raise ValueError("workspace.list arguments are invalid.")
            elif tool == "workspace.read":
                if set(arguments) != {"path"} or not _safe_relative_path(arguments.get("path")):
                    raise ValueError("workspace.read arguments are invalid.")
            elif tool == "workspace.diff":
                if set(arguments) != {"path", "content"} or not _safe_relative_path(arguments.get("path")) or not isinstance(arguments.get("content"), str) or len(arguments["content"]) > 16000:
                    raise ValueError("workspace.diff arguments are invalid.")
            elif tool in {"tasks.list", "none"} and arguments:
                raise ValueError("This tool does not accept arguments.")
    return value
