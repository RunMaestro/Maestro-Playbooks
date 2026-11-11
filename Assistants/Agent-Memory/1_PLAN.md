# Document 1: Plan the Install

## Context

- **Playbook**: Agent Memory
- **Agent**: {{AGENT_NAME}}
- **Project**: {{AGENT_PATH}}
- **Date**: {{DATE}}
- **Working Folder**: {{AUTORUN_FOLDER}}

<!-- MAESTRO:MODEL tier="low" effort="low" reason="The installer script detects and plans; the agent only runs it and reads its report, which needs no deep reasoning." -->

## Tasks

- [ ] **Plan the install.** Find the installer and run its `plan` step with every configured value (the flag
      table is in the agent prompt). It detects the agent, the harness, Python, Node, the model CLI, qmd, Maestro
      Cue and any earlier install, and writes `{{AUTORUN_FOLDER}}/MEMORY_PLAN.md` and `MEMORY_PLAN.json`. It
      changes nothing.

      ```bash
      INSTALLER="$(find "{{AUTORUN_FOLDER}}" -maxdepth 3 -path '*/assets/install_memory.py' | head -1)"
      python3 "$INSTALLER" plan --owner "[OWNER_NAME]" --vault "[VAULT_PATH]" --agent-folder "[AGENT_FOLDER]" \
        --content-folders "[OWNER_CONTENT_FOLDERS]" --timezone "[TIMEZONE]" --nightly "[NIGHTLY_TIME]" \
        --weekly "[WEEKLY_SLOT]" --review-days "[REVIEW_DAYS]" --require-review "[REQUIRE_REVIEW]" \
        --off-limits "[OFF_LIMITS]" --dream "[ENABLE_DREAM]" --search "[SEARCH]" \
        --update-messages "[UPDATE_AGENT_MESSAGES]" --agent-name "{{AGENT_NAME}}" --out "{{AUTORUN_FOLDER}}"
      echo "exit=$?"
      ```

      Read `MEMORY_PLAN.md`. If it says **BLOCKED**, write `<!-- maestro:halt: <the blocker> -->` into this
      document and stop. Otherwise check the plan makes sense for this agent (owner name, vault path, layers,
      schedule times). If a value is wrong, run the command again with the corrected flag. Note in this task
      what the plan will do, in one or two lines.
