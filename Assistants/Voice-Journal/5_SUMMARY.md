# Document 5: Summarize and Hand Off

## Context

- **Playbook**: Voice Memo Journal
- **Agent**: {{AGENT_NAME}}
- **Project**: {{AGENT_PATH}}
- **Date**: {{DATE}}
- **Working Folder**: {{AUTORUN_FOLDER}}

## Purpose

Write the one thing the user actually reads, and reduce whatever they still owe
to the smallest possible action.

If the run ended `DISARMED`, the user owes exactly two clicks and one uncomment.
Say that in those terms. Do not hand them a tutorial.

This is the last document; the playbook does not loop.

## Tasks

### Task 1: Reconcile the artifacts

- [ ] **Read `VOICE_DETECT.md`, `VOICE_INSTALL_PLAN.md`, `VOICE_INSTALL_LOG.md`,
      and `VOICE_VERIFY.md`.** Reconcile them into one story: what was found,
      what was decided, what ran, what was proven. Where the log and the plan
      disagree, the log is authoritative — it records what actually happened.

### Task 2: Write the summary

- [ ] **Write `{{AUTORUN_FOLDER}}/VOICE_JOURNAL_SETUP.md`** with:

      - **Status** — the verdict from `VOICE_VERIFY.md` in plain language.
      - **What was installed** — both scripts and where, the Whisper fallback or
        its absence, the schedule and whether it is live or commented.
      - **How it works, in three lines** — long-press Voice Memos on the lock
        screen, talk, stop. iCloud syncs to the Mac. The scheduled job reads
        Apple's on-device transcript, titles the memo, and appends it to
        `<JOURNAL_DIR>/YYYY-MM-DD.md`. Nothing leaves the machine.
      - **What it costs** — up to one scheduling interval of latency, and Apple's
        transcription is asynchronous, so a memo may land on the following run.
      - **Your next step** — from the table in Task 3.

### Task 3: State the next step precisely

- [ ] **Give the exact next action for the verdict**:

      | Verdict | Next step |
      |---|---|
      | `ACTIVE` | Nothing. Record a memo and check `<JOURNAL_DIR>/{{DATE}}.md` after the next tick. Add Voice Memos to your iPhone lock screen so capture is one long-press. |
      | `ACTIVE-NO-DATA` | Record a ten-second memo now, wait for the next scheduled run, then open `<JOURNAL_DIR>/{{DATE}}.md`. |
      | `DISARMED` | Two clicks and one uncomment — see Task 4. |
      | `PARTIAL` | The one named failure from `VOICE_VERIFY.md`, with its fix. |
      | `FAILED` | Read `VOICE_INSTALL_LOG.md` and `voice-dryrun.out`. Nothing was scheduled; your prior crontab is backed up at `{{AUTORUN_FOLDER}}/crontab.backup`. |

### Task 4: Make the permission grant a two-click job

- [ ] **If the verdict is `DISARMED` (or `TCC_CRON` is anything but granted),
      open the settings pane for them** rather than describing where it lives:

      ```bash
      open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
      ```

      Then give exactly this block, with the real paths substituted:

      > **You owe this two clicks.** The Full Disk Access pane is now open.
      >
      > 1. Click **+**, press **⌘⇧G**, type `/usr/sbin/cron`, press Enter, click **Open**
      > 2. Toggle **cron** on
      >
      > Then arm the job:
      >
      > ```bash
      > crontab -e     # delete the leading "# " from the three voice_memo lines
      > ```
      >
      > To confirm it worked, re-run **just** `4_VERIFY.md` from this playbook —
      > it is written to be run on its own and will tell you `ACTIVE` or name
      > what is still wrong.

      The reason macOS makes you do this by hand: Voice Memos data is
      TCC-protected and no script can grant itself access. State that in one
      sentence so it reads as a platform constraint, not a defect in the install.

### Task 5: Surface it

- [ ] **Notify and open**, so the handoff does not depend on the user reading
      scrollback. Best effort — if `maestro-cli` is not on `PATH`, try the
      bundled path, and if that fails, skip quietly:

      ```bash
      maestro-cli notify toast "Voice journal: <VERDICT> — <one-line next step>" \
        || {{MAESTRO_CLI_PATH}} notify toast "Voice journal: <VERDICT>"
      maestro-cli open-file "{{AUTORUN_FOLDER}}/VOICE_JOURNAL_SETUP.md" \
        || {{MAESTRO_CLI_PATH}} open-file "{{AUTORUN_FOLDER}}/VOICE_JOURNAL_SETUP.md"
      ```

### Task 6: Print the handoff

- [ ] **Output the contents of `VOICE_JOURNAL_SETUP.md`** as your final message
      so the result is visible without opening a file.

- [ ] **End with a `▶ Next step` block** containing the literal, copy-pasteable
      commands for the verdict. For `DISARMED`, that block must contain the
      literal strings `/usr/sbin/cron`, `crontab -e`, and `4_VERIFY.md` — do not
      paraphrase them away. For `ACTIVE`, it is one line: the path to today's
      journal file.
