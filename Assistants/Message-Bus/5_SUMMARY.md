# Document 5: Arm and Hand Off

## Context

- **Playbook**: Message Bus
- **Agent**: {{AGENT_NAME}}
- **Project**: {{AGENT_PATH}}
- **Date**: {{DATE}}
- **Working Folder**: {{AUTORUN_FOLDER}}

## Purpose

Make the arming decision real, then hand the user a summary they can act on in
one line.

This is the only document that can switch the bus on, it can only do so under
`[ARM_ON_INSTALL]: auto` **and** a clean verify, and it always says plainly
which state it left things in.

This is the last document; the playbook does not loop.

## Tasks

### Task 1: Reconcile the artifacts

- [ ] **Read `BUS_DETECT.md`, `BUS_INSTALL_PLAN.md`, `BUS_INSTALL_LOG.md`, and
      `BUS_VERIFY.md`.** Reconcile into one story. Where plan and log disagree,
      the log wins — it records what happened.

### Task 2: Arm, or explain why not

- [ ] **Apply the arming rule, exactly**:

      | `[ARM_ON_INSTALL]` | Verdict | Action |
      |---|---|---|
      | `auto` | `VERIFIED-DISARMED` | Enable the subscription now |
      | `auto` | anything else | **Do not enable.** Report the verdict and its fix. |
      | `manual` | any | **Do not enable.** Give the user the one-line arm command. |

      To arm:

      ```bash
      maestro-cli cue --help          # find the enable verb on this build
      # then enable the 'maestro-message-bus' subscription, or set
      # enabled: true in {{AGENT_PATH}}/.maestro/cue.yaml
      ```

      Read the state back and confirm it took. Do not report armed on the basis
      of having run a command; report it on the basis of having read `true`.

      "Verified but not armed" is a good place to leave someone. "Armed but
      unverified" is not. If those two ever conflict, choose disarmed.

### Task 3: Write the summary

- [ ] **Write `{{AUTORUN_FOLDER}}/MESSAGE_BUS_SETUP.md`** with:

      - **Status** — armed or disarmed, in the first line, in plain words.
      - **How to use it** — drop `<TRIGGER_MARKER>` into any iMessage thread,
        solo or group, on any device. The agent picks it up within
        `[POLL_MINUTES]` minutes, does the work, and replies once into that same
        thread prefixed `🎶 Maestro:`.
      - **Who can drive it** — say this explicitly. Default is one master: the
        user, and only the user. `is_from_me = 1` is enforced in SQL, so nobody
        else in a thread can trigger the agent, even in a group chat where they
        can watch it reply. **If `ALLOWED_SENDERS` was widened, name every handle
        that can now drive this agent.**
      - **What it costs** — up to `[POLL_MINUTES]` minutes of latency; commands
        drain one at a time, not in parallel; macOS only; Full Disk Access
        required.
      - **What was changed on this machine** — the two file locations, the Cue
        subscription, whether **Maestro Cue was enabled by this run**, and where
        state lives (`<WORK_DIR>/automation/state/`).
      - **How to stop it** — disable the `maestro-message-bus` subscription. One
        line, stated up front, not buried. Anyone installing this should know how
        to turn it off before they turn it on.

### Task 4: State the next step

- [ ] **Give the exact next action for the verdict**:

      | Verdict / state | Next step |
      |---|---|
      | Armed | Text yourself `<TRIGGER_MARKER> what time is it` and wait up to `[POLL_MINUTES]` minutes for the reply. |
      | `VERIFIED-DISARMED`, `manual` | One line to arm it (Task 2's command), then the text-yourself test. |
      | `INSTALLED-UNPROVEN` | Send yourself `<TRIGGER_MARKER> test`, then re-run **just** `4_VERIFY.md`. |
      | `PARTIAL` / `FAILED` | The single named fix from `BUS_VERIFY.md`, then re-run **just** `4_VERIFY.md`. |

      Where the fix is a Full Disk Access grant, open the pane rather than
      describing it:

      ```bash
      open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
      ```

      > Click **+**, add **Maestro**, toggle it on, then **quit and reopen
      > Maestro** — the grant only takes effect on relaunch. Then re-run
      > `4_VERIFY.md`.

### Task 5: Point at the voice contract

- [ ] **Tell the user where the behavior lives and that it is theirs to edit**:
      `<WORK_DIR>/automation/Maestro-Message-Channel.md` is the spec the handler
      reads on every dispatch — reply voice, one-message rule, what happens when
      a request is ambiguous. The voice section is written in one person's
      texting style and is meant to be rewritten in the user's.

      Mention the two rules worth knowing without reading it: the agent always
      replies, success or failure, exactly once; and it cannot ask questions, so
      when something is ambiguous it makes the best call, does the work, and
      states the assumption in the reply.

### Task 6: Surface it

- [ ] **Notify and open**, best effort — skip quietly if `maestro-cli` is
      unavailable:

      ```bash
      maestro-cli notify toast "Message bus: <ARMED|DISARMED> — <one-line next step>" \
        || {{MAESTRO_CLI_PATH}} notify toast "Message bus: <ARMED|DISARMED>"
      maestro-cli open-file "{{AUTORUN_FOLDER}}/MESSAGE_BUS_SETUP.md" \
        || {{MAESTRO_CLI_PATH}} open-file "{{AUTORUN_FOLDER}}/MESSAGE_BUS_SETUP.md"
      ```

### Task 7: Print the handoff

- [ ] **Output the contents of `MESSAGE_BUS_SETUP.md`** as your final message.

- [ ] **End with a `▶ Next step` block** holding the literal commands. It must
      always contain the disable line — `maestro-cli cue` disable for
      `maestro-message-bus`, or `enabled: false` in
      `{{AGENT_PATH}}/.maestro/cue.yaml` — because the first thing anyone should
      know about a bus that texts on their behalf is how to switch it off.
