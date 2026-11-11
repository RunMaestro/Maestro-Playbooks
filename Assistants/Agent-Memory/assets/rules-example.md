---
paths:
  - "Agent/Journal/**"
  - "Agent/Tools/session_stamp.py"
---
<!-- Example path-scoped rules file (L0). Save as Agent/Rules/journal.md and symlink Agent/Rules to .claude/rules.
Claude Code loads this file only when the agent reads a file matching `paths`. The always-on summary lives in
CLAUDE.md; this file holds the full rule and its evidence. -->

# Journal Rules

- Keep a journal in `Agent/Journal/YYYY-MM-DD.md`. Read recent files at wake-up. Update it when you start or
  switch tasks. After each update, reread the whole entry and rewrite the `Summary::` line at the top (a few
  sentences). Run `date` before writing.
- **Every section you write gets its own session marker, on the line under its `##` heading.** Attribution is
  per section, not per day: one day file is written by several sessions, and a day-level "written by" line lost a
  write race in practice (one session's line ended up claiming another session's prose).
  - Format: an HTML comment, so a renderer shows nothing:
    `<!-- session-id: <stable session or tab UUID> cc: <transcript id> at: <ISO time> name: <session name> -->`
  - Optionally follow it on the same line with a deep link back into the session, if your orchestrator has one.
  - `session-id:` is a full UUID or it is absent. Do not invent one; a headless run with no session says so.
  - The transcript id is the durable way back (`claude --resume <id>`); session/tab ids die when tabs close.
- Do not start a journal until something tangible has happened. Waking up and browsing is not an entry.
- Never remove earlier entries for the same day. To shorten, condense without losing what was done.

## Example Day File

```markdown
Summary:: Fixed the nightly index rebuild (lock file never released on error). Wrote the Q1 launch checklist.

## Index rebuild fix (09:40)
<!-- session-id: 0c9e6a52-3d1f-4b7e-9a0c-2f5d8e1b7a44 cc: 7b2d9f10-8c4e-4a51-b3e6-1d0f9a2c5e88 at: 2026-11-10T09:40 name: Index Fix -->

- Cause: the rebuild script created `.lock` and exited on an exception without removing it.
- Fix: `try/finally` around the rebuild; verified by killing a run mid-way, the next run started clean.
```

#agent
