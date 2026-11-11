# Document 1: Detect the Agent, the Harness and the Toolchain

## Context

- **Playbook**: Agent Memory
- **Agent**: {{AGENT_NAME}}
- **Project**: {{AGENT_PATH}}
- **Date**: {{DATE}}
- **Working Folder**: {{AUTORUN_FOLDER}}

## Purpose

Find every fact the plan needs, and every blocker, before anything is installed. Nothing in this document
writes outside `{{AUTORUN_FOLDER}}`.

The memory system has seven layers (`{{AUTORUN_FOLDER}}/assets/ARCHITECTURE.md`, section 1). Each one depends
on something on this machine: Python and PyYAML for the jobs, a headless model CLI for promotion and the smoke
judge, Node for search, Maestro Cue for the schedules, and the agent's own Maestro settings for capture.

## Tasks

### Task 1: Read the configuration

- [ ] **Read the agent prompt** and record every configured value: `[OWNER_NAME]`, `[VAULT_PATH]`,
      `[AGENT_FOLDER]`, `[OWNER_CONTENT_FOLDERS]`, `[TIMEZONE]`, `[NIGHTLY_TIME]`, `[WEEKLY_SLOT]`,
      `[REVIEW_DAYS]`, `[REQUIRE_REVIEW]`, `[OFF_LIMITS]`, `[ENABLE_DREAM]`, `[SEARCH]`,
      `[UPDATE_AGENT_MESSAGES]`. Expand `~` and record absolute paths.

      If `[OWNER_NAME]` is still `Owner`, record it as unset; document 2 asks for it in the summary rather than
      blocking. If `[VAULT_PATH]` is not `{{AGENT_PATH}}` and not inside it, record a conflict: the agent can
      only write inside its working directory.

- [ ] **Confirm the bundled assets arrived**:

      ```bash
      ls "{{AUTORUN_FOLDER}}/assets/"
      ```

      Expect, among others, `memstore.py`, `memory_promote.py`, `memory_lint.py`, `memory_smoke.py`,
      `memory.py`, `run_guarded.py`, `cue-memory.yaml` and `CLAUDE.md.fragment.md`. If the folder is missing,
      the playbook arrived through a share link, which drops `assets/`. Halt (Task 8) with the reason
      `assets folder missing: install this playbook from the Playbook Exchange`.

### Task 2: Identify this agent in Maestro

- [ ] **Resolve this agent's id, harness and settings**:

      ```bash
      maestro-cli --version || {{MAESTRO_CLI_PATH}} --version
      maestro-cli list agents --json || {{MAESTRO_CLI_PATH}} list agents --json
      ```

      Find the entry whose name is `{{AGENT_NAME}}`; if several match, narrow by working directory
      `{{AGENT_PATH}}`. Then read it in full:

      ```bash
      maestro-cli show agent <id> --json || {{MAESTRO_CLI_PATH}} show agent <id> --json
      ```

      Record:

      - the agent **id**
      - the **harness** (`toolType`: `claude-code`, `codex`, `opencode`, ...)
      - the **current nudge message** and **new-session message**, verbatim. Document 4 appends to them; it must
        never replace them.
      - **SSH remote**: whether `sessionSshRemoteConfig.enabled` is true. A remote agent runs its shell on the
        remote host, so this install happens there, and Cue schedules must use prompt actions (document 2).
      - `CLAUDE_CONFIG_DIR` from the agent's environment, if set (Claude Code only). Default `~/.claude`.

      Record the Maestro CLI version. The promotion job's turn-history source needs `1.1.1-RC` or later; an older
      CLI only means that source is skipped, not a blocker.

### Task 3: Check the platform and toolchain

- [ ] **Probe every tool the jobs need**:

      ```bash
      uname -a
      command -v python3 && python3 -c "import sys; print(sys.version)"
      python3 -c "import yaml; print('pyyaml', yaml.__version__)" 2>&1
      command -v node && node --version
      command -v npx
      command -v claude codex opencode 2>/dev/null
      ls -l /opt/homebrew/bin/node /usr/local/bin/node 2>/dev/null
      ```

      Record absolute paths for `python3`, `node`, `npx` and each model CLI. Cue command actions run with a
      minimal `PATH`, so every schedule uses absolute paths.

      Python 3.10 or later is required. If it is missing or older, halt (Task 8) with
      `python3 3.10+ not found`. A missing PyYAML is not a blocker: document 3 installs it.

- [ ] **Pick the model CLI for the jobs.** Promotion, the smoke judge and the dream each make headless model
      calls, with the prompt on stdin and the answer on stdout. The jobs do not have to use the agent's own
      harness. Choose in this order and record the choice with its reason:

      | Found | `model_cmd` | Models |
      |---|---|---|
      | `claude` | `["<abs claude>", "-p", "--model", "{model}"]` | `sonnet` for promotion, `haiku` for smoke and dream |
      | `codex` only | `["<abs codex>", "exec", "--skip-git-repo-check", "-"]` | none (no `{model}`); check `codex exec --help` |
      | neither | none | promotion, smoke and dream are installed switched off; lint and search still run |

      Prove the chosen CLI answers headless, with a 60 second limit (`perl` stands in for `timeout`, which macOS
      lacks):

      ```bash
      echo "Reply with the single word OK." | perl -e 'alarm 60; exec @ARGV' <model_cmd, {model} replaced by haiku or left out> 2>&1 | tail -3
      ```

      Record `MODEL: OK`, or `MODEL: FAILED` with the output.

### Task 4: Check search

- [ ] **If `[SEARCH]` is `qmd`**, probe it:

      ```bash
      npx --yes @tobilu/qmd --version 2>&1 | tail -1
      npx --yes @tobilu/qmd collection list 2>&1 | head -60
      ```

      Record the version (or `qmd: not installed`) and **every existing collection name**. qmd collections are
      global to this user account, not per project, so another agent may already own `agent-journal`.
      Document 2 picks collision-free names.

      If Node is missing, record `SEARCH: BLOCKED (no node)`. Search is then skipped; it does not block the
      rest of the install.

### Task 5: Check Maestro Cue

- [ ] **Cue runs every schedule.** Check it:

      ```bash
      maestro-cli settings get encoreFeatures.maestroCue || {{MAESTRO_CLI_PATH}} settings get encoreFeatures.maestroCue
      ls -l "{{AGENT_PATH}}/.maestro/cue.yaml" 2>/dev/null || echo "no cue.yaml yet"
      maestro-cli cue list --json 2>/dev/null | head -80
      ```

      If Cue is off, do not enable it here. Record the state; document 2 plans the opt-in and document 6 says it
      was turned on. Record any existing subscription for this agent whose name contains `memory`, `dream`,
      `qmd` or `promote`. Those make this an update, and document 4 replaces them by name.

### Task 6: Survey the vault

- [ ] **Look at what already exists** under `[VAULT_PATH]`:

      ```bash
      cd "[VAULT_PATH]"
      ls -la
      ls -la "[AGENT_FOLDER]" "[AGENT_FOLDER]/Journal" "[AGENT_FOLDER]/Memory" "[AGENT_FOLDER]/Rules" 2>&1 | head -60
      cat "[AGENT_FOLDER]/Memory/config.json" 2>/dev/null | head -5
      ls -la CLAUDE.md AGENTS.md .claude .claude/rules 2>&1
      find . -name "*.md" -not -path "./[AGENT_FOLDER]/*" -not -path "*/node_modules/*" -not -path "*/.git/*" \
        | awk -F/ 'NF>2{print $2}' | sort | uniq -c | sort -rn | head -10
      ```

      Record:

      - **Install mode**: `FRESH`, or `UPDATE` when `[AGENT_FOLDER]/Memory/config.json` exists. Record its
        `spec_version` and compare with `Spec version:` in `{{AUTORUN_FOLDER}}/assets/ARCHITECTURE.md`.
      - Whether a journal already exists, and its file naming (`YYYY-MM-DD.md` or other). A different layout is
        kept, and document 2 sets `promote.journal_glob` to match it.
      - The instruction file for this harness: `CLAUDE.md` for Claude Code, `AGENTS.md` for the others. Whether
        it exists, its size, and whether it already holds an `agent-memory:begin` block.
      - Whether `.claude/rules` exists, and whether it is a real folder or a symlink.
      - The top markdown folders outside `[AGENT_FOLDER]` (candidates for `[OWNER_CONTENT_FOLDERS]` = `auto`).

- [ ] **Claude Code only: find the harness memory folder.** The harness keys memory on the project path:
      `<CLAUDE_CONFIG_DIR>/projects/<slug>/memory/`, where `<slug>` is the absolute working directory with
      every `/` and `.` turned into `-`.

      ```bash
      ls -la "<CLAUDE_CONFIG_DIR>/projects/" | grep -- "<slug>"
      ls -la "<CLAUDE_CONFIG_DIR>/projects/<slug>/memory" 2>&1 | head -20
      ```

      Record whether it exists, whether it is already a symlink, and how many memory files it holds. Document 3
      moves them into the vault store with `link_store.py`, which backs up first and never overwrites.

### Task 7: Resolve the time zone

- [ ] **If `[TIMEZONE]` is `auto`**, read it from the machine:

      ```bash
      readlink /etc/localtime | sed 's#.*/zoneinfo/##'
      python3 -c "import zoneinfo,sys; zoneinfo.ZoneInfo(sys.argv[1]); print('valid')" "<zone>"
      ```

      Record a valid IANA zone. If none can be read, record `UTC` and say so.

### Task 8: Halt on blockers, or write the report

- [ ] **If a blocker was recorded** (assets missing, no Python 3.10+, vault outside the working directory), write
      a **halt marker** into this document directly below this task: an HTML comment whose whole body is
      `maestro:halt: <reason>`. The marker is described here, not shown, because a literal one in this file
      would halt the playbook as soon as the document is read. Leave this task unchecked and make your final
      message the reason and the one action that clears it.

- [ ] **Write `{{AUTORUN_FOLDER}}/MEMORY_DETECT.md`** with sections: **Agent** (id, harness, SSH remote,
      config dir, current nudge and new-session message verbatim), **Toolchain** (absolute paths, versions,
      PyYAML, Maestro CLI version), **Model** (chosen `model_cmd`, models, `MODEL: OK|FAILED`), **Search**
      (qmd version, existing collections), **Cue** (enabled, file path, existing memory subscriptions),
      **Vault** (install mode, spec versions, journal layout, instruction file, rules folder, content folder
      candidates, harness memory folder), **Time zone**, and a one-line **DETECT SUMMARY**:
      `READY | READY-WITH-GAPS: <list> | BLOCKED: <reason>`.
