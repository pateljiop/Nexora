# Nexora local-first architecture

## Product decision

Nexora / Virtual Hariom is intended to run on Hariom's own Windows laptop. Cloud hosting and Supabase are not prerequisites. GitHub is for source control and CI only; it is not the runtime host.

## Target topology

Phone browser (same trusted Wi-Fi, optional later) -> explicit secure access -> Windows laptop running the Nexora local server.

The local server will host the responsive web UI, local API, task orchestrator, SQLite database, event logs/checkpoints, optional model router, and later a permission-gated Windows companion.

## Local-first rules

- The laptop is the runtime host and local disk is the default source of truth.
- Start bound to 127.0.0.1; do not expose the API to a LAN or public internet by default.
- Do not add a public tunnel or router port-forwarding as a shortcut.
- Phone access from the same Wi-Fi is a separate feature requiring authentication, origin/host validation, and explicit opt-in before listening on a LAN interface.
- Use SQLite for persistent local task state, event logs, and checkpoints. Keep backups and logs on the laptop.
- Keep provider credentials in environment variables or an OS-protected local secret store; never in frontend files, Git, browser localStorage, or task logs.
- Local model inference is optional. The app should remain usable without a downloaded model or external API.
- External model APIs send selected prompt data outside the laptop. Clearly disclose this and make provider use configurable.
- No device control until a Windows companion has least-privilege permissions, bounded operations, audit logs, approval gates for sensitive actions, and post-action verification.
- Never mark a task executed merely because it was added, planned, or sent to a model. Separate task lifecycle states from verified execution outcomes.

## Hardware fit

The target machine has 12 GB RAM, about 200 GB free SSD space, and a 6th-generation Intel Core i5. Keep the base stack lightweight and dependency-minimal. Begin with the UI, a small local HTTP server, and SQLite. Treat local language models as optional experiments: choose model size after checking available RAM, GPU, Windows build, and measured response speed. Disk capacity alone does not guarantee acceptable model performance.

## Milestones

1. Serve the existing responsive UI from a local-only server.
2. Move task persistence from browser-only storage to local SQLite with validated API operations.
3. Add structured planning and provider routing behind the local API.
4. Add visible task events, bounded retries, checkpoints, and explicit approval records.
5. Add secure optional phone-on-LAN access after authentication and network threat review.
6. Build a separate Windows companion for screen/mouse/keyboard control, initially disabled and approval-gated.
7. Add end-to-end tests, recovery tests, and a security audit before enabling real execution.

## Explicitly out of scope for the initial local version

- Supabase or another hosted database as a required dependency.
- Required Vercel/Render runtime hosting.
- Automatic public exposure of the laptop.
- Silent computer control or unverified claims of completion.