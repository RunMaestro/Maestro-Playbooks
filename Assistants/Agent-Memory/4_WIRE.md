# Document 4: Wire Capture and Schedules

## Context

- **Playbook**: Agent Memory
- **Agent**: {{AGENT_NAME}}
- **Project**: {{AGENT_PATH}}
- **Date**: {{DATE}}
- **Working Folder**: {{AUTORUN_FOLDER}}

## Purpose

Make the memory run without anyone remembering to run it:

- **Capture**: the nudge message makes the agent journal every turn; the new-session message makes it read its
  memory at wake-up. Neither needs a harness hook.
- **Processing**: Cue schedules run search, the dream, promotion, lint, the index check and the smoke test.

Append every command and its result to `{{AUTORUN_FOLDER}}/MEMORY_WIRE_LOG.md` as you go.

**Every task runs in a fresh session.** Before each task, read `{{AUTORUN_FOLDER}}/MEMORY_PLAN.md` for the real
value of every `<PLACEHOLDER>` in it (paths, ids, slug, commands). Never run a command with a placeholder left in.

## Tasks

### Task 1: Read the plan and the install log

- [ ] **Read `{{AUTORUN_FOLDER}}/MEMORY_PLAN.md` and `{{AUTORUN_FOLDER}}/MEMORY_INSTALL_LOG.md`.** If the
      shipped tests failed in document 3, every subscription in Task 4 is written with `enabled: false`, and the
      log says why.

### Task 2: Agent capture settings

- [ ] **Set the nudge and new-session message** (only if `[UPDATE_AGENT_MESSAGES]` is `yes`). Read both current
      values again first; the user may have changed them since detection:

      ```bash
      maestro-cli show agent <id> --json || {{MAESTRO_CLI_PATH}} show agent <id> --json
      ```

      If a current value differs from the one in the plan, rebuild the final string from the current value plus
      the planned memory line, so nothing the user wrote is lost. If the memory line is already present, skip
      that setting. Then write both, quoting each string as one shell argument:

      ```bash
      maestro-cli update-agent <id> --nudge "<final nudge>" \
        || {{MAESTRO_CLI_PATH}} update-agent <id> --nudge "<final nudge>"
      maestro-cli update-agent <id> --new-session-message "<final new-session message>" \
        || {{MAESTRO_CLI_PATH}} update-agent <id> --new-session-message "<final new-session message>"
      ```

      Read both back with `show agent <id> --json` and confirm each one contains the earlier text unchanged and
      the memory line once. Report success on what you read back, not on the exit code.

### Task 3: Turn on Maestro Cue

- [ ] **Enable Cue if the plan calls for it**, then read the value back:

      ```bash
      maestro-cli settings set encoreFeatures.maestroCue true || {{MAESTRO_CLI_PATH}} settings set encoreFeatures.maestroCue true
      maestro-cli settings get encoreFeatures.maestroCue || {{MAESTRO_CLI_PATH}} settings get encoreFeatures.maestroCue
      ```

      Record that this run turned it on. Document 6 tells the user.

### Task 4: Write the subscriptions

- [ ] **Add the planned subscriptions to `{{AGENT_PATH}}/.maestro/cue.yaml`.** `cue schedule` can only send
      prompts or start Auto Runs, so command subscriptions are written into the file. Rules:

      1. Read the file first. Create it with a `subscriptions:` list only if it does not exist.
      2. Remove any subscription whose `name` matches a planned one (`<slug>-memory-*`), and any older memory
         subscription for this agent that detection listed. Replace, never duplicate: two promotion jobs on one
         day race on the same store.
      3. Append the planned blocks under `subscriptions:`. Keep every other subscription, comment and key
         exactly as it was.

      Then check the file still parses and Maestro sees the subscriptions:

      ```bash
      python3 -c "import yaml,sys; d=yaml.safe_load(open(sys.argv[1])); print(len(d.get('subscriptions') or []), 'subscriptions')" "{{AGENT_PATH}}/.maestro/cue.yaml"
      maestro-cli cue list --json | grep -- "<slug>-memory-" || {{MAESTRO_CLI_PATH}} cue list --json | grep -- "<slug>-memory-"
      ```

      Every planned name must appear. If the YAML does not parse, restore the file from your read in step 1
      before you do anything else.

### Task 5: Schedule the review reminder

- [ ] **Create the one-shot reminder** for the gate date, as planned:

      ```bash
      maestro-cli cue schedule --at "<apply_after> 09:00" --agent <id> --notify "<planned text>" \
        || {{MAESTRO_CLI_PATH}} cue schedule --at "<apply_after> 09:00" --agent <id> --notify "<planned text>"
      maestro-cli cue schedule --list --agent <id>
      ```

      Record the task name it prints.

### Task 6: Run each job once, now

- [ ] **Fire the cheap jobs once through Cue**, so the first real run is not at 3 a.m. with nobody watching:

      ```bash
      maestro-cli cue trigger <slug>-memory-index-check --source-agent-id <id>
      maestro-cli cue trigger <slug>-memory-promote-lint --source-agent-id <id>
      sleep 60
      maestro-cli cue activity -n 10
      ```

      Promotion runs in dry-run for yesterday (or reports no sources on a fresh install); the lint writes
      `<MEMDIR>/🎛️ Memory Health.md`. Record each run's status and last output line. A command subscription that
      fails here because of `PATH` or a relative path is the most likely wiring bug: fix the shell line in
      `cue.yaml` and trigger it again.

### Task 7: Log

- [ ] **Finish `{{AUTORUN_FOLDER}}/MEMORY_WIRE_LOG.md`**: the nudge and new-session message before and after
      (verbatim), whether Cue was turned on by this run, each subscription name with its schedule and enabled
      state, the reminder task name, each triggered run's result, and every failure verbatim. End with
      `WIRE: COMPLETE` or `WIRE: PARTIAL: <what failed>`.
