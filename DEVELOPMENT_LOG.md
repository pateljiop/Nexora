# Virtual Hariom — Development Log

> Update this file on every meaningful development session and after significant implementation/test milestones. Record facts, not intentions as completed work. Include commit SHA or PR/run link where available. Never record API keys, passwords, tokens, or secrets.

## Product direction
- Project: Nexora — Virtual Hariom.
- Goal: a personal AI assistant/workstation running on Hariom's own Windows laptop.
- Principle: PLAN. ACT. VERIFY.
- Order: finish and test the desktop computer experience first. Website and mobile access come later.
- Target machine: Windows, Intel Core i5 6th generation, 12 GB RAM, approximately 200 GB free SSD.
- Local-first runtime. GitHub is for source control and CI, not runtime hosting.
- Do not require Supabase, Vercel, Render, public cloud hosting, or Docker for the first local version.

## Intended assistant loop
1. Accept a user request and clarify only when required.
2. Build a structured, validated plan with a bounded number of steps.
3. Classify risk and permissions before side effects.
4. Show the plan and ask for approval where required.
5. Execute one bounded step at a time through an allowlisted tool registry.
6. Show progress, tool output, timestamps, approvals, and redacted audit records.
7. Verify meaningful results using evidence; a successful tool call alone is not proof of success.
8. Retry or repair only within configured limits; stop safely when uncertain.
9. Persist tasks, conversations, audit events, and checkpoints locally.
10. Recover interrupted tasks safely or explain why recovery is blocked.

## Safety and reliability decisions
- Bind the local service to 127.0.0.1 by default; no LAN/public exposure by default.
- Do not implement phone access until desktop behavior is tested and LAN authentication/origin protections are designed.
- Keep API keys out of browser code, Git, localStorage, and logs. Store secrets server-side or in OS-protected storage.
- Disclose when an external model provider receives prompt/context data.
- Start file access inside an explicitly selected workspace; avoid unrestricted disk access.
- Never execute model-generated shell commands without validation and policy enforcement.
- Require explicit approval for sensitive/destructive actions and revalidate policy immediately before execution.
- Treat webpages, documents, screenshots, and model outputs as untrusted inputs.
- Use bounded retries, timeouts, output limits, cancellation, structured errors, and audit logs.
- Distinguish planned, running, completed, failed, blocked, and verified states. Never fake execution or verification.

## Repository state — 2026-10-03
### Branch and PR
- Branch: feat/desktop-web-foundation
- Draft PR: https://github.com/pateljiop/Nexora/pull/1
- PR targets main and has not been merged.
- Latest known branch commit at this entry: 41f61b8ea564f5ac08d399ef78b77f91e12bfb51 (README desktop-first update).
- Product specification commit: d4c0ff7a31dc403e9e72a98d7a30a586a4a31006.

### Existing files and responsibilities
- index.html and styles.css: desktop-first workspace UI foundation.
- src/main.js: browser-side interactions, task operations, activity list, navigation, quick prompts, notifications/dialogs, and browser localStorage persistence.
- src/task-state.js: task validation, normalization, and state helper functions.
- tests/task-state.test.js: task-state unit tests.
- package.json: check/test scripts without npm runtime dependencies.
- .github/workflows/ci.yml: GitHub Actions syntax and unit-test workflow.
- docs/LOCAL_FIRST_ARCHITECTURE.md: local-first architecture and security constraints.
- docs/DESKTOP_FIRST_SPEC.md: desktop-first product experience, assistant loop, safety, hardware assumptions, phases, and deferred scope.

### Current capabilities
- Create tasks and display them.
- Mark tasks complete/reopen them and delete them.
- Show a basic activity trail.
- Persist prototype task data in browser localStorage.
- Run task-state tests and GitHub Actions checks.

### Not implemented yet
- Local HTTP backend or SQLite-backed durable storage.
- Connected LLM/provider routing or structured planner.
- Real tool execution or task orchestration.
- Actual browser automation or Windows screen/mouse/keyboard control.
- Persistent background queue, checkpoints, and recovery.
- Voice/wake-word assistant.
- Secure phone-on-Wi-Fi access or a separate website.

Important: marking a task complete in the current UI is a manual UI state change. It is not proof that an AI agent performed or verified the work.

## Recent work log

### Entry: 2026-10-03 — local-first direction
**Why:** The assistant should run on Hariom's laptop rather than depend on a cloud runtime.
**Changes:** Documented local-first hosting, localhost-only defaults, SQLite as the intended durable store, optional model providers, secret handling, approval gates, and future Windows computer control in docs/LOCAL_FIRST_ARCHITECTURE.md. Updated README to clarify that Supabase/Vercel/Render are not required runtime dependencies.
**Verification:** An earlier GitHub Actions run passed on an earlier branch head. That result does not verify later commits.

### Entry: 2026-10-03 — desktop-first scope
**Why:** Hariom explicitly requested that mobile be ignored for now. Build and test the complete computer experience on the laptop first; consider a separate website/mobile experience only later.
**Changes:** Added docs/DESKTOP_FIRST_SPEC.md; updated README.md to make desktop-first scope and limitations explicit; updated draft PR #1 title and description.
**Verification:** GitHub Actions run #11 was queued and run #10 was in progress for commit 41f61b8ea564f5ac08d399ef78b77f91e12bfb51. Latest CI was not yet confirmed when this entry was written. Recheck https://github.com/pateljiop/Nexora/actions before reporting the branch as green.

## Planned implementation sequence

### Phase 1 — Desktop workspace
- Review current HTML/CSS/JS and improve the desktop interaction flow.
- Add clear chat, plan preview, task timeline, approvals, tool-output/evidence area, and local-runtime status.
- Include loading, empty, error, and cancellation states.

### Phase 2 — Local backend and durable state
- Add a lightweight local server bound to localhost by default.
- Add SQLite tables/APIs for tasks, conversations, activity/audit events, and checkpoints.
- Use parameterized SQL, bounded request bodies, safe error responses, and strict Host/Origin protections.
- Plan a deliberate migration/import path for existing browser-local tasks to avoid data loss.
- Add Windows launch scripts and setup instructions.

### Phase 3 — Planner and model adapter
- Define a structured task-plan schema and strict validation.
- Start with dry-run plans and test/fake tools before real side effects.
- Add optional provider adapters behind the local backend.
- Keep credentials out of frontend and source control; redact secrets from logs.
- Make external-data sharing explicit.

### Phase 4 — Execution and approvals
- Add allowlisted tools, risk classification, approval workflow, policy revalidation, cancellation, timeouts, and bounded retries.
- Persist task steps, tool results, audit events, and recovery checkpoints.
- Verify outcomes independently where possible and report uncertainty honestly.

### Phase 5 — Browser automation
- Add bounded navigation/observation/actions and screenshot evidence.
- Treat page content as untrusted input.
- Require approval for sensitive actions; test timeouts, unexpected pages, and failed actions.

### Phase 6 — Windows computer control
- Build a narrowly permissioned Windows adapter for screen observation, mouse, keyboard, and window/app actions.
- Start observation-only; introduce actions individually with permission gates, visible activity, stop control, and verification.

### Phase 7 — Testing and local release
- Add backend unit tests, API/security tests, planner/tool tests, UI checks, end-to-end scenarios, and failure/recovery tests.
- Test on Hariom's actual laptop for memory, responsiveness, restart behavior, and model speed.
- Package a repeatable local launcher after the core flow is reliable.

### Phase 8 — Website/mobile (deferred)
- Begin only after desktop testing succeeds.
- Treat remote access as a separate security milestone, not an automatic consequence of responsive design.
- Do not expose the local execution engine publicly without threat review and explicit user decision.

## Verification/change template

Append a dated entry for each meaningful session:

### Entry: YYYY-MM-DD — short title
**Goal:** What problem or milestone is being addressed?
**Inspection:** Which files, code paths, logs, or failures were inspected?
**Changes made:** Exact files and behaviors changed. Separate completed code from proposed work.
**Implementation approach:** Key design choices and why they fit the laptop/hardware constraints.
**Security/reliability impact:** Permissions, data handling, failure cases, retries, and risks considered.
**Tests run:** Exact commands or CI link and actual result. If not run, say so.
**Known issues:** Remaining bugs, uncertainty, or unverified behavior.
**Next step:** One concrete next action.
**Commit/PR:** Link or SHA when available.

## Current next action
Implement a local-only backend with SQLite and tests after inspecting existing UI/task-state contracts. Keep changes on feat/desktop-web-foundation, update this log in the same session, run CI, and do not merge the draft PR without Hariom's approval.