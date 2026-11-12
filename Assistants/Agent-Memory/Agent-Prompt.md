# Agent Memory Agent Prompt

**IMPORTANT: Configure the placeholders below before running this playbook.**

This playbook installs a layered long-term memory into the agent that runs it: a journal, a fact store with a
hot index, local search, nightly promotion and lint, a weekly smoke test, an optional nightly "dream", the
schedules that run them, and the agent settings that make the agent use them.

---

## Configuration

### Identity

<!-- CONFIGURE: Your first name, as the agent should refer to you. It goes into the memory configs and the
     smoke test. -->
**OWNER_NAME:** `Owner`

<!-- Examples: Alex, Sam, Jo -->

### Layout

<!-- CONFIGURE: The folder of markdown files that becomes the memory's home ("the vault"). Usually the agent's
     own working directory. Must be inside, or equal to, the agent's working directory. -->
**VAULT_PATH:** `{{AGENT_PATH}}`

<!-- CONFIGURE: The folder inside the vault that the agent owns. Journal, Memory, Rules and Tools go here. -->
**AGENT_FOLDER:** `Agent`

<!-- Examples: Agent, Claude, .agent, Assistant -->

<!-- CONFIGURE: Folders inside the vault that hold YOUR content (notes, docs) to index for search, comma
     separated, relative to the vault. `auto` picks the largest markdown folders outside the agent folder.
     `none` indexes only the agent's own memory. -->
**OWNER_CONTENT_FOLDERS:** `auto`

<!-- Examples: auto, none, Notes, docs,Notes,Meetings -->

### Schedule

<!-- CONFIGURE: IANA time zone for the nightly jobs. `auto` reads it from this machine. -->
**TIMEZONE:** `auto`

<!-- Examples: auto, America/Chicago, Europe/Berlin -->

<!-- CONFIGURE: Local time for the nightly jobs (24 h). Pick a time after your last work of the day and before
     you start the next day. The dream runs here; promotion and lint run 30 minutes later. -->
**NIGHTLY_TIME:** `03:15`

<!-- CONFIGURE: Day and time of the weekly smoke test and instructions audit. -->
**WEEKLY_SLOT:** `sun 09:45`

<!-- Examples: sun 09:45, mon 08:00 -->

### Promotion

<!-- CONFIGURE: Days that nightly promotion runs in dry-run (proposals only) before it may write to the
     store. -->
**REVIEW_DAYS:** `7`

<!-- CONFIGURE: `no` (the default) lets promotion start writing on its own when REVIEW_DAYS have passed. `yes`
     keeps it in dry-run after REVIEW_DAYS until you read the proposals and set promote.reviewed to true. -->
**REQUIRE_REVIEW:** `no`

<!-- CONFIGURE: A regular expression of topics that must never be promoted into memory (matching lines are
     redacted before the model call). `none` for no extra topics. Credentials are always redacted. -->
**OFF_LIMITS:** `none`

<!-- Examples: none, \b(old-employer|side-project)\b, \b(lawsuit|medical)\b -->

### Layers

<!-- CONFIGURE: The nightly dream (L5: decay, consolidation, a hot digest). `auto` turns it on for Claude Code
     agents, where a transcript converter exists, and off for other harnesses. -->
**ENABLE_DREAM:** `auto`

<!-- Valid values: auto, yes, no -->

<!-- CONFIGURE: Local search. `qmd` installs qmd (Node) and indexes the memory and your content. `none` skips
     search. -->
**SEARCH:** `qmd`

<!-- Valid values: qmd, none -->

<!-- CONFIGURE: `yes` appends the journal nudge and the memory wake-up line to this agent's Maestro nudge
     message and new-session message. Existing text is kept. `no` leaves both settings alone. -->
**UPDATE_AGENT_MESSAGES:** `yes`

---

## Agent Instructions

You are installing a layered memory into the agent you are running as. One bundled script does the work:
`install_memory.py`, in this playbook's `assets/` folder. An Exchange import puts the playbook in a subfolder of
`{{AUTORUN_FOLDER}}`, so find the script instead of assuming its path:

```bash
INSTALLER="$(find "{{AUTORUN_FOLDER}}" -maxdepth 3 -path '*/assets/install_memory.py' | head -1)"
```

Pass the configuration above to it as flags, mapped like this:

| Prompt value | Flag |
|---|---|
| `[OWNER_NAME]` | `--owner` |
| `[VAULT_PATH]` | `--vault` |
| `[AGENT_FOLDER]` | `--agent-folder` |
| `[OWNER_CONTENT_FOLDERS]` | `--content-folders` |
| `[TIMEZONE]` | `--timezone` |
| `[NIGHTLY_TIME]` | `--nightly` |
| `[WEEKLY_SLOT]` | `--weekly` |
| `[REVIEW_DAYS]` | `--review-days` |
| `[REQUIRE_REVIEW]` | `--require-review` |
| `[OFF_LIMITS]` | `--off-limits` |
| `[ENABLE_DREAM]` | `--dream` |
| `[SEARCH]` | `--search` |
| `[UPDATE_AGENT_MESSAGES]` | `--update-messages` |

Always add `--agent-name "{{AGENT_NAME}}" --out "{{AUTORUN_FOLDER}}"`. Quote every value.

Rules that hold for every document:

1. **The script does the mechanics; you check its output.** Do not redo by hand what the script does.
2. **Never overwrite what the user already has.** The script appends or replaces only its own marked blocks and
   named entries. If its plan shows a conflict, stop and report it rather than forcing it.
3. **Never write outside the working directory yourself.** The one step that needs to (linking the harness
   memory folder) is handed to the owner as a command.
4. **Evidence, not assumption.** Report what the script printed, not what you expect it did.

---

## Your Task Now

This prompt replaces Maestro's default Auto Run prompt, so it names the document itself.

Process tasks from this document: **{{DOCUMENT_PATH}}**

Read it, do the **first unchecked task** (`- [ ]`) only, then check it off (`- [x]`) in that file with a short
note of what you did. Then stop: a fresh session does the next task. If there are no unchecked tasks left, say
so and stop.
