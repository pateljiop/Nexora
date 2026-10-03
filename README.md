# Nexora — Virtual Hariom

**PLAN. ACT. VERIFY.**

Nexora is the local-first personal AI workstation for Hariom's Windows laptop. Its identity is **Virtual Hariom**: a persistent assistant that plans work, explains what it is doing, asks before sensitive actions, executes through controlled tools, and verifies outcomes.

## Scope decision

**Desktop computer first.** Build and test the complete desktop experience on Hariom's own laptop before spending time on mobile layouts, phone access, or a separate public website. Those are explicitly deferred.

## Current foundation

- Desktop-first dark workspace UI foundation.
- Task creation, completion/reopening, deletion, and activity trail.
- Browser-local persistence in the current frontend prototype.
- Clear preview-mode messaging; no fake AI responses or claims of device execution.
- Unit tests for task validation, state transitions, deletion, summaries, and persisted-data normalization.
- GitHub Actions CI for JavaScript syntax and unit tests.
- Local-first architecture and desktop-first product scope documented under `docs/`.
- A chronological development record in `DEVELOPMENT_LOG.md` to capture decisions, implementation steps, tests, known issues, and next actions after each meaningful session.

## Current limitations

This is not yet a working AI agent. The current UI is a foundation only.

- No local HTTP backend or SQLite persistence yet.
- No connected AI model provider or structured planner.
- No actual browser automation, Windows screen/mouse/keyboard control, or voice wake-word.
- Task status means a task was marked complete in the UI; it does not mean the assistant executed or verified it.

## Local development

Requires Node.js 22 or later. The current frontend foundation has no npm dependencies.

    npm run check

Serve the repository root using a local static HTTP server and open `index.html`. The next implementation milestone is a local-only backend, not cloud deployment.

## Architecture principles

- Laptop is the runtime host; local disk is the source of truth.
- Start services on `127.0.0.1` and do not expose the runtime to the network by default.
- SQLite for durable tasks, conversations, audit events, and checkpoints.
- Optional local inference and optional external providers; secrets never go in frontend code or Git.
- Explicit permissions, approval gates, bounded retries, cancellation, audit trails, and post-action verification.
- Desktop-first UI with a plan panel, task timeline, approvals, tool output, screenshots/evidence, and runtime status.

See `docs/DESKTOP_FIRST_SPEC.md` for the product scope and phase order, `docs/LOCAL_FIRST_ARCHITECTURE.md` for local-hosting and security decisions, and `DEVELOPMENT_LOG.md` for the running implementation record.

Supabase, Vercel, and Render are not required runtime dependencies for this personal local setup. GitHub remains useful for source control and CI.