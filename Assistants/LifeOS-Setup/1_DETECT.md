# Document 1: Detect Harness and Probe Environment

## Context

- **Playbook**: LifeOS Setup
- **Agent**: {{AGENT_NAME}}
- **Project**: {{AGENT_PATH}}
- **Date**: {{DATE}}
- **Working Folder**: {{AUTORUN_FOLDER}}

## Purpose

Identify the harness this agent is running inside, resolve the **config root** LifeOS will install into, and probe the prerequisites the LifeOS installer needs. Write everything to `LIFEOS_DETECT.md` for the planning document to read.

LifeOS v6 is **harness-agnostic and additive**. It ships as one self-contained skill that drops into your skills directory and never clobbers your other files. The old PAI model (clone a full `~/.claude/` tree and run a wizard) is gone. So detection has two jobs now:

1. **Which harness** — Claude Code gets the full always-on experience (native hooks); Cursor / Cline / Codex / Gemini / other get a real but degraded install (skill + USER tree + Pulse + per-session context, but always-on hooks are not wired yet). Chat-only assistants with no filesystem/command access fail the capability gate.
2. **Which config root** — LifeOS resolves this from the environment (`~/.claude`, `~/.config/claude`, or a project-local `.claude/`). **Do not assume `~/.claude`.** The authoritative resolver is `bun Tools/DetectEnv.ts`, which ships inside the skill and runs in document 3 after the skill is dropped. This document does a lightweight manual probe so document 2 can plan.

For Maestro agents, expected `toolType` values are `claude-code`, `opencode`, `codex`, `factory-droid`, `copilot-cli`, `gemini-cli`, `qwen3-coder`.

## Tasks

### Task 1: Self-identify

- [ ] **State your harness**: You are running inside an AI coding harness right now. Without checking files, name the harness you are running inside (Claude Code, Codex, OpenCode/OpenClaw, Cursor, Cline, Factory Droid, GitHub Copilot CLI, Gemini CLI, Qwen3 Coder, or other). If you are uncertain, say so explicitly — do not guess.

### Task 2: Cross-check via Maestro

- [ ] **Look up your Maestro `toolType`**: The agent name is `{{AGENT_NAME}}`. Use the first command that works:

  ```bash
  maestro-cli list agents --json
  ```

  Fallback if `maestro-cli` is not on `PATH` (Maestro fills in the bundled CLI path):

  ```bash
  {{MAESTRO_CLI_PATH}} list agents --json
  ```

  Find the entry whose `name` matches `{{AGENT_NAME}}`. If multiple agents share the name, narrow by `cwd` matching `{{AGENT_PATH}}`. Read the matching record's `toolType` field. Record the value (or `unavailable` if both commands failed).

### Task 3: Cross-check via binary on PATH

- [ ] **Confirm the harness binary**: Check which harness CLIs are actually on `PATH` — `command -v claude`, `command -v codex`, `command -v cursor`, `command -v gemini`, etc. Record what you find. If Task 1, Task 2, and Task 3 disagree, note the conflict; the `toolType` from Maestro (Task 2) is authoritative for planning.

### Task 4: Probe prerequisites

- [ ] **Check the install prerequisites**: LifeOS's bootstrap needs `curl`, `bash`, and `tar`. Its install Tools run under **`bun`** (they are TypeScript, not shell), so `bun` is the hard requirement. Record the result of each:

  ```bash
  for c in curl bash tar bun git claude; do
    if command -v "$c" >/dev/null 2>&1; then echo "$c: $(command -v "$c")"; else echo "$c: MISSING"; fi
  done
  bun --version 2>/dev/null || echo "bun --version: FAILED"
  ```

  `bun` is the one that blocks the install if missing — the bootstrap only auto-installs it when stdin is a TTY, which a Maestro Bash subprocess is not. Document 3 installs `bun` first if it is missing. Note whether `bun` is present.

### Task 5: Resolve config root and existing state

- [ ] **Find the config root and any existing LifeOS install**: Determine where LifeOS would install. Probe, in order:

  ```bash
  for d in "$HOME/.claude" "$HOME/.config/claude" "{{AGENT_PATH}}/.claude"; do
    if [ -d "$d" ]; then echo "config-root candidate: $d"; fi
  done
  ls -d "$HOME/.claude/skills/LifeOS" 2>/dev/null && echo "EXISTING LifeOS skill found" || echo "no existing LifeOS skill"
  ls -d "$HOME/.claude/LIFEOS" 2>/dev/null && echo "EXISTING LIFEOS runtime found" || echo "no existing LIFEOS runtime"
  ```

  Record the resolved config-root candidate(s), whether a LifeOS skill or `LIFEOS/` runtime already exists (→ this becomes an **update**, not a fresh install), and whether `{{AGENT_PATH}}` looks like the **LifeOS source repo** itself (a `danielmiessler/LifeOS` git remote, or a `LifeOS/SKILL.md` with the maintenance skill present). The installer **refuses to run inside the LifeOS source tree** (`isDevTree`) — flag it if detected.

### Task 6: Write the detection report

- [ ] **Write `{{AUTORUN_FOLDER}}/LIFEOS_DETECT.md`** with:
  - **Harness** (self-report + `toolType` + binary-on-PATH), and the harness **capability tier**: `claude-code-full` (native hooks), `other-degraded` (skill + USER + Pulse + context, no always-on hooks yet), or `chat-only-blocked` (no file/command access → fails the capability gate).
  - **Config root**: the resolved candidate LifeOS will target, and whether a project-local `.claude/` under `{{AGENT_PATH}}` is available (relevant if the user wants single-agent isolation — see document 2).
  - **Prerequisites**: `curl` / `bash` / `tar` / `bun` / `git` / `claude` presence, with `bun` called out as the blocker.
  - **Existing state**: fresh install vs. update; whether the config root already has a LifeOS skill/runtime; whether this is the LifeOS source tree (→ must abort).
  - A one-line **DETECT SUMMARY** the planning document can read at a glance.
