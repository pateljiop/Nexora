# Virtual Hariom — Desktop-first product specification

## Decision

Build and test the full computer experience on Hariom's Windows laptop first. Do not spend implementation time on mobile layouts, mobile navigation, phone access, or a public website during this phase. A separate website can be built after the desktop application works reliably.

## Intended experience

Virtual Hariom is a personal assistant for one Windows user, not a generic multi-user SaaS dashboard. It should feel like a persistent desktop companion and a practical AI workstation.

### Main desktop workspace

- Left rail: identity/avatar, Home, Chat, Tasks, Projects, Memory, Activity, Tools, Settings.
- Main conversation: user requests, assistant replies, streaming/working state, structured plans, and follow-up prompts.
- Execution inspector: current step, completed steps, pending approvals, tool output, timestamps, retries, and verification results.
- Evidence area: screenshots and artifacts produced during a real task, clearly distinguished from illustrative content.
- Global status: local runtime health, selected model/provider, privacy mode, and whether execution is enabled.

### Core assistant loop

1. Accept a user request and clarify only when required.
2. Build a validated, structured plan with a bounded step count.
3. Classify risk and permissions before executing any side effect.
4. Show the plan and request approval when policy requires it.
5. Execute through a controlled tool registry, one bounded step at a time.
6. Stream visible progress and append tool inputs/outputs to a local audit trail with secrets redacted.
7. Verify each meaningful result using independent evidence where possible.
8. Retry or repair only within configured limits; stop safely when uncertain.
9. Save task state and checkpoints locally so interrupted tasks can be resumed or diagnosed.

## Local Windows architecture

- Desktop UI: begin with a full-width desktop workspace served locally; choose a native shell only after the local core is stable.
- Backend: lightweight local process bound to 127.0.0.1 by default.
- Persistence: SQLite on local disk for tasks, conversations, settings, audit events, and checkpoints.
- Model router: local model endpoint optional; external APIs optional and visibly labelled. API keys stay server-side / in an OS-protected secret store.
- Tool runtime: explicit allowlisted tools; workspace-scoped file operations; shell execution disabled or approval-gated; timeouts and output limits.
- Computer control: separate Windows companion/adapter for screenshots, mouse, keyboard, and window/app controls. Start read-only, then introduce individually permissioned actions.
- Reliability: structured errors, health checks, bounded queues, cancellation, restart recovery, and tests for failure paths.

## Safety and trust requirements

- No automatic access to the entire disk; start with an explicitly selected workspace.
- Never execute model-generated shell commands directly without policy validation.
- Sensitive actions such as deleting files, sending messages, purchases, credential access, commits, pushes, or system settings require explicit approval.
- Revalidate policy after approval and immediately before execution.
- Treat webpage text, files, screenshots, and model outputs as untrusted data.
- Redact credentials and personal secrets from logs.
- Keep an append-only local audit trail for actions and approvals.
- Show the difference between planned, running, completed, failed, blocked, and verified. Never claim success from a tool call alone.
- Include a global pause/stop control and per-task cancellation.

## Hardware target

Initial target: Windows laptop, 12 GB RAM, approximately 200 GB free SSD space, Intel Core i5 6th generation. Prefer a lightweight local server and SQLite. Benchmark local inference before choosing a model; local model size and speed depend on exact CPU, GPU, quantization, and memory availability. Remote inference, if enabled, must be opt-in and disclose that selected data leaves the laptop.

## Phase order

1. Desktop-only UX: chat, plan panel, execution timeline, task list, inspector, local runtime status.
2. Local API + SQLite; remove browser localStorage as the source of truth for durable state.
3. Provider adapter and structured planner; start with dry-run plans and fake/test tools.
4. Secure tool registry, approvals, audit logs, cancellation, timeouts, bounded retries, and verification.
5. Browser automation with screenshots and evidence, isolated from unrestricted system access.
6. Windows computer-control adapter with read-only observation first, then approved actions.
7. Background task recovery, end-to-end tests, threat review, and local installer/launcher.
8. Only after desktop testing is successful: package a separate website/mobile-access experience if still desired.

## Explicitly deferred

- Mobile-specific UI and phone access.
- Public website, public deployment, accounts for other users, and cloud-hosted runtime.
- Supabase as a required dependency.
- Always-on voice/wake-word until core task execution is reliable.
- Unrestricted autonomous computer control.