# Nexora — Virtual Hariom

**PLAN. ACT. VERIFY.**

Nexora is a personal AI workspace designed to run on Hariom's own Windows laptop. The experience is called **Virtual Hariom**: capture goals, organize work, and eventually execute approved tasks through a transparent local engine. The UI is responsive for desktop and phone browsers.

## Current foundation

- Responsive desktop-first dark workspace UI, with mobile browser layout.
- Task creation, completion/reopening, deletion, task list, and activity trail.
- Browser-local persistence for the current frontend prototype.
- Explicit preview-mode labels: no fake AI responses, cloud sync, or device execution.
- Unit tests for task validation, state transitions, deletion, summaries, and persisted-data normalization.
- GitHub Actions CI for syntax checks and unit tests.
- Local-first architecture decisions documented in docs/LOCAL_FIRST_ARCHITECTURE.md.

## Current limitations

This is still a **frontend foundation**, not a connected AI agent.

- Task data currently stays in the browser's local storage; SQLite-backed local persistence is a next milestone.
- No local HTTP backend or SQLite API is implemented yet.
- No AI provider is wired up; API keys must not be placed in frontend code.
- No browser agent, laptop mouse/keyboard control, wake-word voice, or Windows companion is connected.
- Task status means Hariom marked a task complete; it does not mean an AI executed or verified it.

## Local development

Requires Node.js 22 or later. The frontend foundation has no npm dependencies.

Run checks:

    npm run check

Serve the repository root with a static HTTP server and open index.html. A local-only backend will be added next so the application can run from the laptop rather than depending on cloud hosting.

## Local-first product direction

1. Add a lightweight local server bound to 127.0.0.1 by default.
2. Store tasks, audit events, and recovery checkpoints in local SQLite.
3. Add structured planning and optional provider routing behind the local server; keep secrets out of browser code.
4. Add bounded execution, visible logs, explicit approvals, and verification.
5. Add secure, opt-in phone-on-the-same-Wi-Fi access after authentication and network security checks.
6. Add a Windows companion for laptop screen/mouse/keyboard control only after permission gates, audit trails, and verification are in place.

Supabase, Vercel, and Render are not required runtime dependencies for this personal local setup. GitHub remains useful for source control and CI.

See docs/LOCAL_FIRST_ARCHITECTURE.md for the security rules and milestone plan.

The goal is a real personal assistant—not a pretend agent that claims an action happened when it did not.