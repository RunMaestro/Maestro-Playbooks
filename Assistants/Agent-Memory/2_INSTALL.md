# Document 2: Install and Verify

## Context

- **Playbook**: Agent Memory
- **Agent**: {{AGENT_NAME}}
- **Project**: {{AGENT_PATH}}
- **Date**: {{DATE}}
- **Working Folder**: {{AUTORUN_FOLDER}}

<!-- MAESTRO:MODEL tier="low" effort="low" reason="The installer applies and verifies the plan itself; the agent runs two commands and reports their output." -->

## Tasks

- [ ] **Install.** Apply the plan. This copies the tools, writes the store, configs, instruction block and rules,
      starts the journal, adds the qmd collections (the embedding model downloads in the background), sets the
      nudge and new-session message (the agent's own text is kept), writes the Cue schedules and the review
      reminder, and runs the first lint. Re-running it is safe.

      ```bash
      INSTALLER="$(find "{{AUTORUN_FOLDER}}" -maxdepth 3 -path '*/assets/install_memory.py' | head -1)"
      python3 "$INSTALLER" apply --plan "{{AUTORUN_FOLDER}}/MEMORY_PLAN.json" --out "{{AUTORUN_FOLDER}}"
      echo "exit=$?"
      ```

      It must exit 0. Its log is `{{AUTORUN_FOLDER}}/MEMORY_INSTALL_LOG.md`. If it fails, read the log, fix the
      cause it names (a missing tool, a permission), and run it once more.

- [ ] **Verify.** Run the checks: index, instruction block, lint, off switch, review gate, smoke test, search,
      capture wiring, schedules and the protected-files guard.

      ```bash
      INSTALLER="$(find "{{AUTORUN_FOLDER}}" -maxdepth 3 -path '*/assets/install_memory.py' | head -1)"
      python3 "$INSTALLER" verify --plan "{{AUTORUN_FOLDER}}/MEMORY_PLAN.json" --out "{{AUTORUN_FOLDER}}"
      echo "exit=$?"
      ```

      Exit 0 is `VERIFIED`. On exit 1, read the failing row in `{{AUTORUN_FOLDER}}/MEMORY_VERIFY.md`, fix what it
      names, and run `verify` again once. Record the final verdict here.
