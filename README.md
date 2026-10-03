# Nexora — Virtual Hariom

**PLAN. ACT. VERIFY.**

Nexora is a desktop-first personal AI workspace built around the idea of **Virtual Hariom**: a personal assistant experience that helps Hariom capture goals, organize work, and eventually run approved tasks through a transparent execution engine. The web interface is responsive so it can also be used from a phone browser.

## Current foundation

- Responsive dark workspace UI for desktop and mobile browsers.
- Task creation, completion/reopening, deletion, and task history.
- Local browser persistence with basic validation of restored data.
- Activity trail for task changes.
- Quick-start prompts for daily planning, project breakdown, and debugging.
- Clear preview-mode messaging: no fake AI responses, cloud sync, or device execution.
- Unit tests for task validation, transitions, deletion, summaries, and persisted-data normalization.
- GitHub Actions checks for JavaScript syntax and unit tests.

## Current limitations

This branch is a **frontend foundation**, not a connected AI agent yet.

- Tasks are stored in the current browser only; they do not sync across devices.
- Supabase is not configured in this repository and no Supabase project is connected.
- OpenRouter, Gemini, and Grok providers are not wired up.
- No browser agent, laptop mouse/keyboard control, voice wake word, or Windows companion is connected.
- The interface does not claim a task has executed; task status currently means only that Hariom marked it complete.

## Local development

Requires Node.js 22 or later. There are no npm dependencies in the current foundation.

```bash
npm run check
```

For a local static preview, use any static file server from the repository root and open `index.html`. Opening the file directly may work, but a local server is the recommended approach for ES modules.

## Product direction

1. Connect Supabase for authenticated, persistent task data and realtime updates, with row-level security.
2. Add a server-side provider adapter for OpenRouter/Gemini/Grok; keep secrets out of browser code.
3. Build structured planning, bounded execution, visible logs, and approval gates.
4. Add a secure Windows companion for actual laptop screen/mouse/keyboard actions.
5. Add verification, recovery/checkpoints, and audit history before expanding autonomous execution.

The goal is a useful personal workspace—not a pretend assistant that reports work as done when it has not run.
