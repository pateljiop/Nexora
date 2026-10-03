# Nexora — Virtual Hariom

**PLAN. ACT. VERIFY.**

Nexora is the local-first personal AI workstation for Hariom's Windows laptop. Its identity is **Virtual Hariom**: a persistent assistant that will plan work, explain what it is doing, ask before sensitive actions, execute through controlled tools, and verify outcomes.

## Current milestone: local desktop workspace

- Desktop-first workspace UI.
- Local Python HTTP server bound to `127.0.0.1` by default.
- SQLite persistence for tasks, a bounded activity trail, and saved plan previews.
- A transparent structured dry-run planner (`local_template` source), with bounded steps and explicit `executionEnabled: false`.
- Task creation, completion/reopening, deletion, and one-time import of existing browser-local tasks.
- Read-only workspace explorer for bounded UTF-8 file previews inside the configured project root; private paths, symlinks, binary files, and oversized files are excluded.
- Explicit, sequential read-only tool execution for model-generated plans: `workspace.list`, `workspace.read`, `workspace.diff`, and `tasks.list` only. `workspace.diff` previews a proposed text change but never writes it.
- Persistent execution records with per-step status/output/error, cancellation, bounded status polling, page-refresh reconnection, and an explicit note that tool completion is not proof that the overall goal was verified.
- Saved run history and a manual “Review plan again” path for failed/cancelled/completed read-only runs; re-running always creates a new run and requires fresh confirmation.
- Host and Origin checks, request-body limit, parameterized SQL, path traversal protection, and restrictive response headers.
- JavaScript and Python automated tests in GitHub Actions.
- Windows launcher: `run-local.bat`.

## Run on Windows

1. Install Python 3.10+ (required to run the app). Node.js 22+ is only needed to run the JavaScript test suite.
2. Download/clone this repository to your laptop.
3. Double-click `run-local.bat`.
4. The launcher waits up to 30 seconds for `/api/health` before opening `http://127.0.0.1:8765`; if startup fails, inspect the server terminal for Python errors or a port conflict.
5. Keep the server terminal open while using Nexora. Press Ctrl+C in that window to stop it.

Or start it manually from the repository directory:

    python server.py

The SQLite database is created at `data/nexora.sqlite3`. Keep the `data` directory if you want to retain local tasks. It is runtime data and should not be committed.

The workspace explorer defaults to this repository folder. To use a different existing project folder, set `NEXORA_WORKSPACE_ROOT` in `.env`; explorer and model-run tools remain constrained to that root. The explorer does not expose the entire disk by default. Proposed changes use a separate review workflow.

## Verify the project

Requires Node.js 22+ and Python 3.10+.

    npm run check

This runs JavaScript syntax checks, JavaScript unit tests, and Python tests for SQLite/API behavior and local request protections.

## Optional model planning

The planner works without a provider by showing a clearly labelled deterministic local template. The optional workspace explorer can list and preview UTF-8 text files under the configured root, and a model-generated plan can run a bounded sequence of allowlisted read-only tools (`workspace.list`, `workspace.read`, `workspace.diff`, `tasks.list`). The diff tool compares proposed UTF-8 text with the current file and records a redacted preview only; it does not write, delete, or execute anything. Tool outputs are recorded locally, failures stop the sequence, and a completed tool run explicitly does **not** mean the overall goal was verified. The plan runner has no file-writing tool. After a `workspace.diff` step, the user can save the proposal, review the complete diff, and separately approve Apply or Roll back. Apply requires a fresh hash match and a backup; rollback refuses to overwrite later edits. No shell commands, browser actions, or desktop controls are enabled. To use a compatible model for plan drafts:

1. Copy `.env.example` to `.env` in the repository root.
2. Set `NEXORA_MODEL_BASE_URL`, `NEXORA_MODEL_NAME`, and (for remote providers) `NEXORA_MODEL_API_KEY`.
3. For an external HTTPS provider, explicitly change `NEXORA_ALLOW_REMOTE_MODEL=1`. Remote requests stay disabled by default.
4. Restart `run-local.bat`. Each external plan request displays a confirmation naming the configured provider host and model before sending the goal.

A local OpenAI-compatible endpoint such as Ollama can use a loopback HTTP URL and does not need a remote API key. Use the commented local example in `.env.example`. Local model speed depends on the installed model, CPU/GPU, quantization, and available RAM.

The provider adapter sends only the goal needed for planning and asks for structured JSON. It can propose only the read-only tool allowlist; a plan runs only after you explicitly click **Run read-only steps**. Invalid responses, timeouts, and provider errors are surfaced as errors; they are not silently treated as successful plans. The `.env` file is ignored by Git and must never be committed.

## Honest current limitations

This is an early local-first Virtual Hariom foundation. It can draft plans with an optional model, inspect a configured workspace with allowlisted read-only tools, and persist run reports. It is **not yet a full desktop-controlling AI agent**.

- The optional model adapter can draft structured plans when explicitly configured; otherwise the deterministic template is used. Only model plans containing allowlisted read-only tool calls can run.
- No direct model-driven file-write tool, arbitrary shell execution, browser automation, Windows screen/mouse/keyboard control, or voice wake-word.
- User-approved file changes are limited to saved, reviewed proposals within the configured workspace. Read-only tool completion does not independently verify the user’s overall goal.
- Read-only runs use a background worker, can be cancelled between steps, and are recorded in SQLite. On server restart, interrupted runs are marked failed for review rather than retried. General multi-task orchestration and checkpoint/resume are not implemented.
- Plan previews use a deterministic local template, not an LLM. They are not personalized AI reasoning and do not execute actions.
- Marking a task complete is a manual list update, not evidence of AI execution or verification.
- If the local server is unavailable, the UI falls back to browser storage; the connection panel explains which mode is active.

## Privacy and safety

- Runtime binds to loopback; it is not intended to be accessed from another device.
- No cloud runtime or Supabase project is required.
- Optional provider credentials are read from a local `.env` file or environment variables; `.env` is Git-ignored. Remote requests are disabled by default and require per-goal confirmation.
- The server does not execute shell commands or control the computer.
- Tasks, activity, plan previews, execution states, and run reports remain in the local SQLite file, except legacy data intentionally imported from browser storage on first successful connection. Remote model planning sends the goal only after explicit confirmation.
- Back up the `data` directory before deleting or reinstalling the project.

## Architecture and project record

- `docs/DESKTOP_FIRST_SPEC.md`: desktop scope and intended assistant behavior.
- `docs/LOCAL_FIRST_ARCHITECTURE.md`: local hosting and security decisions.
- `DEVELOPMENT_LOG.md`: chronological record of changes, decisions, verification, known issues, and next steps.

Website/mobile access is deferred until the desktop experience is built and tested. GitHub is used for source control and CI, not runtime hosting.

## Latest CI verification

- [GitHub Actions run #411](https://github.com/pateljiop/Nexora/actions/runs/37152942264) passed on branch head `27dc685d55e5f430236d74212d2d50ffd1fc5698` (JavaScript syntax, Node unit tests, and Python API/SQLite/security tests, including approval-gated file changes, backup/rollback, stale-write protection, interrupted-change recovery, and rollback-error visibility).
