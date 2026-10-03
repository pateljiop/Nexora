"""Small read-only tool registry for the first execution milestone."""
from __future__ import annotations

import re

from planner import ALLOWED_READ_ONLY_TOOLS
from workspace_tools import WorkspaceError

MAX_TOOL_OUTPUT_CHARS = 12_000
SECRET_PATTERNS = (
    (re.compile(r"""(?i)(["']?\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|client_secret|secret)\b["']?\s*[:=]\s*)(["']?)([^"']*?)(?=["']|[,}\s]|$)"""), r"\1\2[REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "[REDACTED_KEY]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}"), "Bearer [REDACTED]")
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "[REDACTED_SLACK_TOKEN]"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{25,}\b"), "[REDACTED_GOOGLE_KEY]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "[REDACTED_JWT]")
)


class ToolExecutionError(ValueError):
    pass


def redact_text(value):
    text = str(value)
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def execute_read_only_tool(name, arguments, workspace, store):
    if name not in ALLOWED_READ_ONLY_TOOLS or name == "none":
        raise ToolExecutionError("Tool is not enabled for execution.")
    if not isinstance(arguments, dict):
        raise ToolExecutionError("Tool arguments must be an object.")
    try:
        if name == "workspace.list":
            if set(arguments) - {"path"}:
                raise ToolExecutionError("workspace.list received unsupported arguments.")
            result = workspace.list_files(arguments.get("path", "."))
            entries = result["entries"][:50]
            return {"tool": name, "readOnly": True,
                    "summary": f"Listed {len(entries)} entries in {result['relativePath']}.",
                    "data": {"rootName": result["rootName"], "relativePath": result["relativePath"],
                             "entries": entries, "truncated": result["truncated"] or len(result["entries"]) > 50}}
        if name == "workspace.read":
            if set(arguments) != {"path"}:
                raise ToolExecutionError("workspace.read requires only a relative path.")
            result = workspace.read_file(arguments["path"])
            safe_content = redact_text(result["content"])
            truncated = len(safe_content) > MAX_TOOL_OUTPUT_CHARS
            return {"tool": name, "readOnly": True, "summary": f"Read text file {result['path']}.",
                    "data": {"path": result["path"], "content": safe_content[:MAX_TOOL_OUTPUT_CHARS],
                             "bytes": result["bytes"], "truncated": truncated}}
        if name == "tasks.list":
            if arguments:
                raise ToolExecutionError("tasks.list does not accept arguments.")
            tasks = store.list_tasks()[:20]
            return {"tool": name, "readOnly": True, "summary": f"Retrieved {len(tasks)} saved tasks.",
                    "data": {"tasks": tasks, "truncated": len(store.list_tasks()) > 20}}
    except WorkspaceError as exc:
        raise ToolExecutionError(str(exc)) from None
    raise ToolExecutionError("Tool is not enabled for execution.")
