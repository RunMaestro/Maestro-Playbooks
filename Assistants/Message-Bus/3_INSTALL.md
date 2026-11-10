# Document 3: Install

## Context

- **Playbook**: Message Bus
- **Agent**: {{AGENT_NAME}}
- **Project**: {{AGENT_PATH}}
- **Date**: {{DATE}}
- **Working Folder**: {{AUTORUN_FOLDER}}

## Purpose

Execute the plan and land in a **disarmed but complete** state.

Everything is installed. The scanner works. The subscription exists. It is
switched off. Nothing this document does can cause a message to be sent.

Arming is document 5's job, and only after document 4 has produced evidence.

## Tasks

### Task 1: Read the plan

- [ ] **Read `{{AUTORUN_FOLDER}}/BUS_INSTALL_PLAN.md`.** Execute it as written.
      If a resolved path no longer exists, stop and say so rather than
      substituting a guess.

### Task 2: Install `imsg`

- [ ] **Install the decoder if the plan calls for it**:

      ```bash
      brew install steipete/tap/imsg
      command -v imsg && imsg --help 2>&1 | head -3
      ```

      This is a hard requirement, not an optional extra. If it fails, record the
      error verbatim and stop after finishing the file placement in Task 4 — the
      verify in document 4 will report `FAILED` and document 5 will hand the user
      the install command. Do not create the Cue subscription without a working
      `imsg`.

### Task 3: Enable Maestro Cue

- [ ] **Turn on the Encore feature if the plan calls for it**:

      ```bash
      maestro-cli settings set encoreFeatures.maestroCue true \
        || {{MAESTRO_CLI_PATH}} settings set encoreFeatures.maestroCue true
      maestro-cli settings get encoreFeatures.maestroCue
      ```

      Read the value back to confirm. Record that you enabled it — document 5
      tells the user, because a feature that switched itself on without
      explanation is worse than one that stayed off.

### Task 4: Place the files

- [ ] **Create the directories and copy both assets**:

      ```bash
      mkdir -p "<INSTALL_DIR>" "<WORK_DIR>/automation/state"
      cp "{{AUTORUN_FOLDER}}/assets/maestro_message_scanner.py" "<INSTALL_DIR>/"
      cp "{{AUTORUN_FOLDER}}/assets/Maestro-Message-Channel.md" "<WORK_DIR>/automation/"
      chmod +x "<INSTALL_DIR>/maestro_message_scanner.py"
      ls -la "<INSTALL_DIR>" "<WORK_DIR>/automation"
      ```

      The spec document must land at
      `<WORK_DIR>/automation/Maestro-Message-Channel.md` exactly. The scanner
      references it by that relative path in every dispatch payload, resolved
      from the handler agent's working directory. A spec the handler cannot find
      means an agent replying without its voice or reply-contract rules.

      If `{{AUTORUN_FOLDER}}/assets/` is missing, the playbook arrived through a
      channel that drops assets. Say so plainly and point at the source gists
      rather than failing silently:
      `https://gist.github.com/pedramamini/5470bde338cd27d0ce4acff04a199661` (scanner)
      and `https://gist.github.com/pedramamini/123b0dbe02ded0c47aadfa5e3f2fca0a` (spec).

### Task 5: Apply the config edits

- [ ] **Edit only what the plan says to edit** in the scanner's header block:
      `MARKER` and, if and only if the plan explicitly calls for it,
      `ALLOWED_SENDERS`. Everything else — `VAULT_DIR`, the handler id, the
      `node` path, the `maestro-cli` path — travels through the environment in
      the Cue command line and must not be patched into the source.

      After editing, confirm the file still parses:

      ```bash
      /usr/bin/python3 -c "import ast; ast.parse(open('<INSTALL_DIR>/maestro_message_scanner.py').read()); print('SYNTAX OK')"
      ```

- [ ] **Announce a widened sender scope**: if `ALLOWED_SENDERS` was changed away
      from `None`, record in the install log, in plain words, that people other
      than the user can now trigger this agent, and list the handles. This must
      appear in document 5's summary too.

### Task 6: Seed the watermark

- [ ] **Run the scanner once with no flags** to draw the line in the sand:

      ```bash
      VAULT_DIR="<WORK_DIR>" /usr/bin/python3 "<INSTALL_DIR>/maestro_message_scanner.py" 2>&1 | tee "{{AUTORUN_FOLDER}}/bus-seed.out"
      ```

      Note the absence of `MAESTRO_HANDLER_AGENT_ID` — the scanner stays in
      dry-run and cannot dispatch.

      Expect output saying it seeded the watermark and processed nothing. Confirm
      the state file now exists:

      ```bash
      cat "<WORK_DIR>/automation/state/message_bus_watermark.json"
      ```

      If this is an update and a watermark already existed, re-draw the line
      instead so a stale position cannot replay a backlog:

      ```bash
      VAULT_DIR="<WORK_DIR>" /usr/bin/python3 "<INSTALL_DIR>/maestro_message_scanner.py" --reseed
      ```

      **If the seeding run reports zero messages visible**, the read is failing
      under this process even though document 1's probe passed. Record it and
      stop creating the subscription — document 4 will report the failure.

### Task 7: Create the Cue subscription, disabled

- [ ] **Add the subscription in the disabled state**, using
      `{{AUTORUN_FOLDER}}/assets/cue-subscription.yaml` as the shape and
      substituting every placeholder from the plan.

      Check for a create/import verb first:

      ```bash
      maestro-cli cue --help
      ```

      If one exists, use it. Otherwise append the block to
      `{{AGENT_PATH}}/.maestro/cue.yaml` by hand — **read the file first, append
      to the existing subscription list, preserve everything already there.**
      Never write that file from scratch; it may hold the user's other pipelines.

- [ ] **Replace, do not duplicate**: if detection found an existing message-bus
      subscription, remove it as part of this edit. Two heartbeats scanning the
      same database double-dispatch every command.

- [ ] **Confirm what landed, and confirm it is off**:

      ```bash
      maestro-cli cue list --json | head -60
      grep -n -A6 "maestro-message-bus" "{{AGENT_PATH}}/.maestro/cue.yaml"
      ```

      The subscription must be present and `enabled: false`. If it is enabled,
      disable it now — arming before verification is the one thing this document
      must not do.

### Task 8: Write the install log

- [ ] **Write `{{AUTORUN_FOLDER}}/BUS_INSTALL_LOG.md`**: every command in order
      with its exit status, whether Cue was enabled by this run, the files placed
      and their paths, the config edits applied, the seeding output, the exact
      subscription block written, its enabled state, and any failure with its
      error text verbatim.
