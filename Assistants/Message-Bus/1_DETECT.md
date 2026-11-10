# Document 1: Detect Environment, Permissions, and Gates

## Context

- **Playbook**: Message Bus
- **Agent**: {{AGENT_NAME}}
- **Project**: {{AGENT_PATH}}
- **Date**: {{DATE}}
- **Working Folder**: {{AUTORUN_FOLDER}}

## Purpose

Find every blocker **before** installing anything. This playbook has four
independent ways to fail, and three of them are invisible until runtime:

1. Full Disk Access denied → the scanner reads an empty database and silently
   never fires.
2. Maestro Cue not enabled → the subscription cannot be created, so nothing
   schedules the scanner.
3. `imsg` missing → the scanner finds candidate messages but cannot decode them.
4. Wrong or unresolvable handler agent id → dispatch goes nowhere.

Each is probed here with evidence, not assumption.

## Tasks

### Task 1: Read the configuration

- [ ] **Read the agent prompt** and record `[HANDLER_AGENT_ID]`,
      `[TRIGGER_MARKER]`, `[ALLOWED_SENDERS]`, `[ARM_ON_INSTALL]`,
      `[POLL_MINUTES]`, `[WORK_DIR]`, and `[INSTALL_DIR]`. Expand `~` and record
      absolute paths.

- [ ] **Validate the marker**: `[TRIGGER_MARKER]` must be plain ASCII with no
      spaces. The scanner byte-matches it inside a binary blob, so a marker with
      an emoji or a non-ASCII character will never match. If it fails this check,
      halt as in Task 3 with the reason `TRIGGER_MARKER must be plain ASCII`.

### Task 2: Confirm the platform

- [ ] **Check macOS, Python, and Messages**:

      ```bash
      sw_vers
      /usr/bin/python3 --version
      ls -l "$HOME/Library/Messages/chat.db" 2>&1 | head -2
      command -v node || ls -l /opt/homebrew/bin/node 2>/dev/null || echo "node: MISSING"
      ls -l /Applications/Maestro.app/Contents/Resources/maestro-cli.js 2>/dev/null || echo "maestro-cli.js: not at default path"
      ```

      This is macOS-only — it reads Apple's local message store directly. If
      `sw_vers` fails, or `chat.db` does not exist at all, this machine cannot
      run the bus. Halt as in Task 3.

      Record the absolute `node` path. The Cue command node runs with a minimal
      `PATH`, so the scanner needs an absolute interpreter, not a bare `node`.

### Task 3: Probe the privileged read — the one that matters

- [ ] **Attempt to read `chat.db`, and catch the failure**:

      ```bash
      /usr/bin/python3 -c "
      import sqlite3, pathlib
      db = pathlib.Path.home()/'Library/Messages/chat.db'
      try:
          con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
          n = con.execute('select count(*) from message').fetchone()[0]
          m = con.execute('select count(*) from message where is_from_me=1 and attributedBody is not null').fetchone()[0]
          print(f'TCC: GRANTED — {n} messages, {m} of yours carry attributedBody')
      except Exception as e:
          print(f'TCC: DENIED — {type(e).__name__}: {e}')
      "
      ```

      Note `mode=ro` and **not** `immutable=1`. `chat.db` is live and WAL-backed;
      `immutable` ignores the `-wal` file and goes blind to messages that just
      arrived, which would make the bus miss fresh commands until macOS happened
      to checkpoint. Use this exact connection string everywhere.

      Record **`TCC: GRANTED`** or **`TCC: DENIED`**.

      If DENIED, do this:

      Write a **halt marker** into this document, directly below this
      task: an HTML comment whose entire body is

      ```text
      maestro:halt: Full Disk Access denied. Grant it to Maestro, then re-run.
      ```

      The marker is described rather than shown, because a literal one sitting
      in this file would halt the playbook the moment the document is read.

      Leave the task unchecked, open the settings pane, and make your final
      message the grant instructions and nothing else:

      ```bash
      open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
      ```

      > **Nothing was installed.** This agent cannot read your message database.
      >
      > The Full Disk Access pane is now open. Click **+**, add **Maestro**,
      > toggle it on, then **quit and reopen Maestro** — the grant only takes
      > effect on relaunch. Add your terminal too if you want to test by hand.
      >
      > Then delete the `maestro:halt` marker from `1_DETECT.md` and run this
      > playbook again.

      Do not proceed. Every later document depends on this read working.

- [ ] **Sanity-check the `attributedBody` assumption**: the probe above counts
      your outbound messages that carry an `attributedBody` blob. If that count
      is zero on a machine with message history, record it as an anomaly — the
      whole design rests on your own messages being readable from that blob, and
      a zero here means this macOS version stores them differently.

### Task 4: Check the Maestro Cue gate

- [ ] **Cue is an Encore feature and may be switched off.** Check it:

      ```bash
      maestro-cli settings get encoreFeatures.maestroCue \
        || {{MAESTRO_CLI_PATH}} settings get encoreFeatures.maestroCue
      ```

      If it returns `false`, **do not silently enable it.** Record the state and
      let document 2 plan the opt-in; document 3 will enable it only after the
      plan says to. The one-command opt-in is
      `settings set encoreFeatures.maestroCue true` — instant, no restart.

      Also record where the Cue config lives:

      ```bash
      ls -l "{{AGENT_PATH}}/.maestro/cue.yaml" 2>/dev/null || echo "no .maestro/cue.yaml yet"
      maestro-cli cue list --json 2>/dev/null | head -40 || echo "cue list unavailable"
      ```

      Note any **existing** subscription whose name or label mentions a message
      bus — that makes this an update, and document 3 must replace rather than
      duplicate it. Two heartbeats scanning the same database is a double-dispatch
      bug waiting to happen.

### Task 5: Check `imsg`

- [ ] **Probe the decoder**:

      ```bash
      command -v imsg && imsg --help 2>&1 | head -3 || echo "imsg: MISSING"
      command -v brew || echo "brew: MISSING"
      ```

      `imsg` is a hard requirement — the scanner byte-matches the marker in the
      raw blob, then hands off to `imsg` to decode readable text and thread
      context. Without it, commands are detected and cannot be read.

      If missing, record the install command
      (`brew install steipete/tap/imsg`) for document 3. If `brew` is also
      missing, halt as in Task 3 with the reason `imsg and Homebrew both missing`.

### Task 6: Resolve the handler agent id

- [ ] **Turn `[HANDLER_AGENT_ID]` into a real id**: if it is `self`, resolve it
      to this agent's own id. This agent is `{{AGENT_NAME}}` with working
      directory `{{AGENT_PATH}}`:

      ```bash
      maestro-cli list agents --json \
        || {{MAESTRO_CLI_PATH}} list agents --json
      ```

      Find the entry whose `name` matches `{{AGENT_NAME}}`; if several share the
      name, narrow by `cwd` matching `{{AGENT_PATH}}`. Record the resolved id.

      If `[HANDLER_AGENT_ID]` was given explicitly, **confirm it exists in that
      list**. A typo here produces an install that looks perfect and dispatches
      into nothing.

      If the id cannot be resolved or confirmed, halt as in Task 3 with the
      reason `handler agent id could not be resolved`.

### Task 7: Check the working directory

- [ ] **Confirm `[WORK_DIR]` is writable and note what the scanner will create
      there**: `<WORK_DIR>/automation/state/` for the watermark, dispatch log,
      and lock file, and `<WORK_DIR>/automation/Maestro-Message-Channel.md` for
      the handler spec.

      The scanner resolves `SPEC_DOC` **relative to the handler agent's working
      directory**, so `[WORK_DIR]` must be that agent's `cwd`, not an arbitrary
      folder. If the resolved handler agent's `cwd` differs from `[WORK_DIR]`,
      record the conflict — document 2 resolves it in favour of the agent's
      actual `cwd`.

### Task 8: Write the detection report

- [ ] **Write `{{AUTORUN_FOLDER}}/BUS_DETECT.md`** with:

      - **Platform**: macOS version, Python, absolute `node` path, `maestro-cli` path.
      - **Permissions**: `TCC: GRANTED|DENIED` with the evidence, plus the
        `attributedBody` sanity count.
      - **Cue**: `encoreFeatures.maestroCue` state, config file path, existing
        subscriptions, and whether this is an update.
      - **Toolchain**: `imsg`, `brew`.
      - **Identity**: resolved handler agent id, and the agent's real `cwd`.
      - **Config echo**: marker, sender scope, poll interval, install dir.
      - A one-line **DETECT SUMMARY**:
        `READY | READY-CUE-DISABLED | READY-NEEDS-IMSG | BLOCKED — <reason>`
