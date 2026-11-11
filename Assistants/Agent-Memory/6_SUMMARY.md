# Document 6: Hand Off

## Context

- **Playbook**: Agent Memory
- **Agent**: {{AGENT_NAME}}
- **Project**: {{AGENT_PATH}}
- **Date**: {{DATE}}
- **Working Folder**: {{AUTORUN_FOLDER}}

## Purpose

Give the owner one page that says what now runs, where it lives, what they owe, and how to switch it off. Also
leave that page inside the agent's own folder, so the memory system has a home the owner can find later.

This is the last document. The playbook does not loop.

**Every task runs in a fresh session.** Before each task, read `{{AUTORUN_FOLDER}}/MEMORY_PLAN.md` for the real
value of every `<PLACEHOLDER>` in it (paths, ids, slug, commands). Never run a command with a placeholder left in.

## Tasks

### Task 1: Reconcile

- [ ] **Read `MEMORY_DETECT.md`, `MEMORY_PLAN.md`, `MEMORY_INSTALL_LOG.md`, `MEMORY_WIRE_LOG.md` and
      `MEMORY_VERIFY.md`** in `{{AUTORUN_FOLDER}}`. Where the plan and a log disagree, the log wins.

### Task 2: Write the memory home page

- [ ] **Write `<MEMDIR>/Memory.md`** (in `UPDATE` mode, update it and keep its change log). It is the page the
      owner opens to "pull the thread" on memory. Sections:

      - **The system today**: a table, one row per layer: what it is, where it lives (path), who writes it, when
        it runs, and ON, OFF or SKIPPED.
      - **Capture**: the nudge line and the new-session line as installed, and Maestro turn history.
      - **Schedules**: each `<slug>-memory-*` subscription with its time.
      - **Review gate**: the date promotion may start writing, whether your review is required, and the one edit
        that opens it (`promote.reviewed: true` in `<MEMDIR>/config.json`).
      - **Switches**: `AGENT_MEMORY=0`; `touch <MEMDIR>/.disabled`; `"enabled": false` per job in the config;
        `maestro-cli cue disable <name>`.
      - **Design**: links to `Spec/ARCHITECTURE.md`, `Spec/CHANGELOG.md`, `Spec/harness-memory-format.md`.
      - **Change log**: `{{DATE}}`: installed by the Agent Memory playbook, spec version, verdict.

      Do not add it to `MEMORY.md`: the index holds memories only. The instruction block already points at this
      page (document 2, Task 5).

### Task 3: Write the setup summary

- [ ] **Write `{{AUTORUN_FOLDER}}/MEMORY_SETUP.md`**:

      - **Status**: the verdict from `MEMORY_VERIFY.md`, in plain words, on the first line.
      - **What runs now**: capture on every turn (nudge), wake-up reads (new-session message), and each schedule
        with its time and job.
      - **What you owe**: read `<MEMDIR>/Promotions/` before `<apply_after>`; then set `promote.reviewed: true`
        (only if review is required). A reminder fires that morning. Also: add `expect` questions to
        `<MEMDIR>/smoke.json` as real memories accumulate; three seed questions cannot catch a recall regression.
      - **What changed on this machine**: every folder created, the instruction file and its `agent-memory`
        block, the rules files and `.claude/rules`, the harness memory link and its backup folder, the two
        agent settings (before and after), the Cue subscriptions, whether **Maestro Cue was turned on by this
        run**, the qmd collections, PyYAML and qmd if installed, and every `.new` tool copy left for a diff.
      - **What was skipped, and why**: each OFF or SKIPPED layer, with the one step that would turn it on.
      - **How to switch it off**: one line for everything (`touch <MEMDIR>/.disabled`), and the Cue line per
        job. State this before the details, not after.

### Task 4: Name the next step

- [ ] **Give the single next action for the verdict:**

      | Verdict | Next step |
      |---|---|
      | `VERIFIED` | Work as usual. Tomorrow, open `<MEMDIR>/Promotions/` and read the first proposals |
      | any, Claude Code, residency `OWNER` | First: paste `! <the apply command from MEMORY_INSTALL_LOG.md>` into this agent's chat, so the harness loads the same `MEMORY.md` the jobs maintain |
      | `VERIFIED-WITH-GAPS` | The step that turns on the most useful skipped layer (usually: install a model CLI, then re-run `5_VERIFY.md`) |
      | `PARTIAL` | The fix named in `MEMORY_VERIFY.md`, then re-run only `5_VERIFY.md` |
      | `FAILED` | The fix named in `MEMORY_VERIFY.md`, re-run `5_VERIFY.md`, then `maestro-cli cue enable` each `<slug>-memory-*` subscription |

### Task 5: Surface it

- [ ] **Notify and open**, best effort, in the background:

      ```bash
      maestro-cli notify toast "Agent memory: <verdict>. Review gate: <apply_after>." \
        || {{MAESTRO_CLI_PATH}} notify toast "Agent memory: <verdict>"
      maestro-cli open-file "<MEMDIR>/Memory.md" --background \
        || {{MAESTRO_CLI_PATH}} open-file "<MEMDIR>/Memory.md" --background
      ```

### Task 6: Print the handoff

- [ ] **Output the contents of `MEMORY_SETUP.md`** as your final message, ending with a `▶ Next step` block that
      holds the next action and the one-line off switch.
