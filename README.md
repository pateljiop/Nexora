# Nexora — Virtual Hariom

**PLAN. ACT. VERIFY.**

Nexora is the local-first personal AI workstation for Hariom's Windows laptop. Its identity is **Virtual Hariom**: a persistent assistant that will plan work, explain what it is doing, ask before sensitive actions, execute through controlled tools, and verify outcomes.

## Current milestone: local desktop workspace

- Desktop-first workspace UI.
- Local Python HTTP server bound to `127.0.0.1` by default.
- SQLite persistence for tasks and a bounded activity trail.
- Task creation, completion/reopening, deletion, and one-time import of existing browser-local tasks.
- Host and Origin checks, request-body limit, parameterized SQL, path traversal protection, and restrictive response headers.
- JavaScript and Python automated tests in GitHub Actions.
- Windows launcher: `run-local.bat`.

## Run on Windows

1. Install Python 3.10+ and Node.js 22+.
2. Download/clone this repository to your laptop.
3. Double-click `run-local.bat`.
4. The local workspace opens at `http://127.0.0.1:8765`.
5. Keep the server terminal open while using Nexora. Press Ctrl+C in that window to stop it.

Or start it manually from the repository directory:

    python server.py

The SQLite database is created at `data/nexora.sqlite3`. Keep the `data` directory if you want to retain local tasks. It is runtime data and should not be committed.

## Verify the project

Requires Node.js 22+ and Python 3.10+.

    npm run check

This runs JavaScript syntax checks, JavaScript unit tests, and Python tests for SQLite/API behavior and local request protections.

## Honest current limitations

This is a working local-storage foundation, **not yet a working AI agent**.

- No LLM provider or structured task planner is connected.
- No model-generated tool execution, browser automation, Windows screen/mouse/keyboard control, or voice wake-word.
- No background orchestration, checkpoints, or crash recovery yet.
- Marking a task complete is a manual list update, not evidence of AI execution or verification.
- If the local server is unavailable, the UI falls back to browser storage; the connection panel explains which mode is active.

## Privacy and safety

- Runtime binds to loopback; it is not intended to be accessed from another device.
- No cloud runtime or Supabase project is required.
- No API keys are used or stored by this milestone.
- The server does not execute shell commands or control the computer.
- Task and activity data remain in the local SQLite file, except legacy data intentionally imported from browser storage on first successful connection.
- Back up the `data` directory before deleting or reinstalling the project.

## Architecture and project record

- `docs/DESKTOP_FIRST_SPEC.md`: desktop scope and intended assistant behavior.
- `docs/LOCAL_FIRST_ARCHITECTURE.md`: local hosting and security decisions.
- `DEVELOPMENT_LOG.md`: chronological record of changes, decisions, verification, known issues, and next steps.

Website/mobile access is deferred until the desktop experience is built and tested. GitHub is used for source control and CI, not runtime hosting.
