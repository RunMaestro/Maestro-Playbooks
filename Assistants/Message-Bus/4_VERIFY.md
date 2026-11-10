# Document 4: Verify

## Context

- **Playbook**: Message Bus
- **Agent**: {{AGENT_NAME}}
- **Project**: {{AGENT_PATH}}
- **Date**: {{DATE}}
- **Working Folder**: {{AUTORUN_FOLDER}}

## Purpose

Prove the bus works **without sending anything**.

The scanner stays in dry-run whenever `MAESTRO_HANDLER_AGENT_ID` is unset, so
the entire detection path — read the live database, byte-match the marker in the
blob, decode the text, resolve the thread — can be exercised end to end while
dispatch is structurally impossible.

**This document is re-runnable on its own.** After granting a permission or
installing `imsg`, the user should re-run this one document and get a real
verdict, not restart the playbook.

## Tasks

### Task 1: Read the install log

- [ ] **Read `{{AUTORUN_FOLDER}}/BUS_INSTALL_LOG.md` and
      `{{AUTORUN_FOLDER}}/BUS_DETECT.md`** for the resolved paths, the handler
      id, and the intended arming state. If the log is absent, this document is
      running standalone — recover the paths from `BUS_INSTALL_PLAN.md` or from
      the Cue subscription itself.

### Task 2: Verify the pieces exist

- [ ] **Check every file and tool**:

      ```bash
      ls -la "<INSTALL_DIR>/maestro_message_scanner.py"
      ls -la "<WORK_DIR>/automation/Maestro-Message-Channel.md"
      ls -la "<WORK_DIR>/automation/state/message_bus_watermark.json"
      command -v imsg || echo "imsg: MISSING"
      /usr/bin/python3 -c "import ast; ast.parse(open('<INSTALL_DIR>/maestro_message_scanner.py').read()); print('SYNTAX OK')"
      ```

      The spec document is the one people forget. If it is missing, the handler
      dispatches without its voice and reply-contract rules — the bus will
      "work" and behave wrongly, which is the worse failure.

### Task 3: Verify the live read

- [ ] **Confirm the database read still works, with the WAL**:

      ```bash
      /usr/bin/python3 -c "
      import sqlite3, pathlib
      db = pathlib.Path.home()/'Library/Messages/chat.db'
      con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
      print('max rowid:', con.execute('select max(rowid) from message').fetchone()[0])
      "
      ```

      Compare the max rowid against the seeded watermark in
      `message_bus_watermark.json`. They should be close. A watermark far below
      the current max means the seed did not take, and the bus would replay a
      backlog the moment it is armed.

### Task 4: The end-to-end dry run

- [ ] **Ask the user to send one test message, then detect it.** This is the
      only step that needs a human, and it takes ten seconds:

      > **Send yourself a test.** Open Messages, text **yourself** (or any
      > thread) the line:
      >
      > `<TRIGGER_MARKER> test one two`
      >
      > Then say "sent" and I will confirm the bus can see it.

      Use the in-app notification so the ask is not buried in scrollback:

      ```bash
      maestro-cli notify toast "Message bus: send yourself '<TRIGGER_MARKER> test one two' to verify" \
        || {{MAESTRO_CLI_PATH}} notify toast "Message bus: send a test message"
      ```

      If this playbook is running unattended and no reply is possible, skip this
      task, record `NO-TEST-MESSAGE`, and let the verdict be `INSTALLED-UNPROVEN`.
      Do not block an unattended run waiting for an answer that cannot come.

- [ ] **Run the scanner in dry-run and read what it found**:

      ```bash
      VAULT_DIR="<WORK_DIR>" /usr/bin/python3 "<INSTALL_DIR>/maestro_message_scanner.py" 2>&1 \
        | tee "{{AUTORUN_FOLDER}}/bus-verify.out"
      ```

      `MAESTRO_HANDLER_AGENT_ID` is deliberately absent. Dispatch is impossible.

      Classify the output:

      | Output | Means |
      |---|---|
      | Found the candidate, decoded the text, reports dry-run / no handler | **Working.** This is the pass condition. |
      | `no new commands` after a test was sent | The marker did not byte-match. Check `MARKER` in the header against what was actually typed — including case and any autocorrect substitution. |
      | Database error | The read is failing under this process. TCC, not code. |
      | Found the candidate but could not resolve text | `imsg` is missing or failing. |

      **The decoded command text is the evidence.** A scanner that reports
      "1 candidate" without resolving it to readable text has not proven the
      thing that matters — the `attributedBody` decode is the hard part of this
      whole design.

### Task 5: Verify the subscription

- [ ] **Confirm the subscription exists and its state**:

      ```bash
      maestro-cli cue list --json | head -60
      grep -n -A8 "maestro-message-bus" "{{AGENT_PATH}}/.maestro/cue.yaml"
      ```

      Check four things: it exists, `agent_id` matches the resolved handler id,
      `interval_minutes` matches `[POLL_MINUTES]`, and the shell line carries
      `MAESTRO_HANDLER_AGENT_ID`, `VAULT_DIR`, and an absolute interpreter path.
      Record its `enabled` state.

      A subscription whose shell line is missing `MAESTRO_HANDLER_AGENT_ID` will
      run forever in dry-run and never reply. That is a silent failure with every
      light green — call it out specifically if you see it.

### Task 6: Confirm there is exactly one bus

- [ ] **Check for duplicates**: list all subscriptions and confirm exactly one
      scans the message database. Two heartbeats on the same database
      double-dispatch every command the user sends.

### Task 7: Write the verdict

- [ ] **Write `{{AUTORUN_FOLDER}}/BUS_VERIFY.md`** with each check, the evidence
      that produced it, and one verdict:

      | Verdict | Meaning |
      |---|---|
      | `VERIFIED-DISARMED` | Everything installed, the dry run detected and decoded a real test command, subscription present and disabled. **This is the expected clean result.** |
      | `VERIFIED-ARMED` | As above, and the subscription is enabled |
      | `INSTALLED-UNPROVEN` | Everything installed, but no test message was available to prove detection |
      | `PARTIAL` | Something concrete failed — name it and name the fix |
      | `FAILED` | The scanner cannot read the database or cannot decode |

      For anything other than `VERIFIED-*`, state the single next action that
      would change the verdict.
