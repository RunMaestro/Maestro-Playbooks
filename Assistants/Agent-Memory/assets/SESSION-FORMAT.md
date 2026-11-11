# Session Format: the Adapter Contract for L5

Spec version: 2026-11-10.8

`memory.py dream` reads conversations in one plain-text format. It does not know which harness produced them.
`cc_sessions.py` converts Claude Code transcripts. For any other harness (Codex, an orchestrator's turn history,
a voice app, a chat bridge), write a converter that produces this format. Nothing else in L5 changes.

## 1. Layout

```
$MEMORY_SESSIONS/
├── 2026-11-09-081502-3f9a1c2e/
│   └── transcript.md
└── 2026-11-09-140233-b71d04aa/
    └── transcript.md
```

- One folder per session. The folder name starts with the session's local start date and time,
  `YYYY-MM-DD-HHMMSS`. An optional `-<id>` suffix keeps names unique.
- **The first 10 characters decide the day** the session belongs to. A session that runs past midnight stays on
  its start day.
- The folder name is the session's identity. Do not rename a folder after it has been replayed, or it replays
  again under the new name.

## 2. The File

UTF-8 Markdown. **One turn per line.** A line that does not match the turn grammar is ignored, so headings and
blank lines are allowed.

```
- `HH:MM:SS` **<Label>:** <text>
```

The exact pattern `memory.py` applies:

```
^- `(\d\d:\d\d(?::\d\d)?)` \*\*(<Label>):\*\* (.*)$
```

| Part | Rule |
|---|---|
| Time | Local time of the turn, `HH:MM` or `HH:MM:SS` |
| Label | One of the keys of `roles` in the L5 `config.json` |
| Text | The turn on one line. Turn every newline into a space. Never empty. Cap long turns (2,000 characters is a good limit) |

Example:

```markdown
# session 3f9a1c2e

- `08:15:02` **User:** From now on, book client calls in the afternoon only.
- `08:15:09` **Assistant:** Understood. Afternoons only for client calls.
- `08:20:40` **Task:** Moved the Thursday client call to 14:00.
```

## 3. Labels and What They Mean

`roles` in the L5 `config.json` maps each label to the speaker that REPLAY gives the extractor:

| Default label | Replays as | Put here |
|---|---|---|
| `User` | `OWNER` | What the owner typed |
| `Typed` | `OWNER (typed)` | Typed input on a second surface (a screen, a form) |
| `Texted` | `OWNER (text)` | The owner's text messages |
| `Phone` | `OWNER (call)` | The owner's words on a call, from a transcript that attributes speakers |
| `Task` | `TASK RESULT` | One-line outcome of a job the agent ran |
| `Assistant` | `ASSISTANT` | The agent's visible reply text |

Rules for the right-hand side, which the extractor depends on:

- A value that starts with `OWNER` is the owner's own words. **Only these turns, and `TASK RESULT` turns, can
  support a memory.** Each candidate must quote 3 or more words from one of them, or the whole turn if it is
  shorter. A candidate quoting anything else is dropped (spec `2026-11-10.2`).
- `TASK RESULT` must be exactly that string. Memories supported only by a task quote are stored with
  `said_by: task`, which ranks below `owner` in contradictions.
- `ASSISTANT` is context for the extractor. It can never support a memory.
- **Any label not in `roles` is dropped before the model sees it.** Use that on purpose: give unattributed audio,
  other people in a room, or pasted documents a label of their own (`Heard`, `Pasted`) and leave it out of
  `roles`.

You can add labels. Map them in `roles`, with values that follow the rules above.

## 4. What a Converter Must Leave Out

| Leave out | Why |
|---|---|
| Tool calls, tool results, file contents | The extractor would memorize file dumps |
| Hidden reasoning ("thinking") | Not something anyone said |
| System prompts, injected reminders, harness wrappers | Not the owner's words. In Claude Code these are user records whose text starts with `<` |
| Text the owner pasted from elsewhere, if your harness can tell | Someone else's words under the owner's label become false memories. Label it `Pasted` and leave it out of `roles` |
| Secrets (keys, tokens, passwords) | The store is plain files. Scrub before writing |
| Sub-agent or side-chain turns | Not the owner talking to this agent |

Mapping a harness: for each record type it writes, decide one of `User`, `Assistant`, `Task`, or "drop". When in
doubt, drop. A missed memory costs little; a false one is recalled with confidence.

## 5. Re-runs and Idempotency

- `memory.py` remembers each replayed session by folder name and **file size**. A file whose size changed
  replays again in full.
- So rewrite a transcript only when its content changed (compare first, write atomically). Appending new turns
  to a live session is fine: the next dream replays the whole session, and memories restated from it count as
  "same" (at most one reinforcement per memory per day).
- Running the converter twice in a row must change nothing.

## 6. Acceptance Checks for a New Converter

```bash
export MEMORY_SESSIONS=/tmp/sessions-test MEMORY_DIR=/tmp/memory-test AGENT_MEMORY_LLM=0
your_converter --out "$MEMORY_SESSIONS"           # 1. produce sessions
your_converter --out "$MEMORY_SESSIONS"           # 2. second run: no file changes
python3 - <<'PY'                                  # 3. what REPLAY will hand the extractor
import os, re, sys, collections; sys.path.insert(0, ".")
import memory
from pathlib import Path
s = sorted(p.parent for p in Path(os.environ["MEMORY_SESSIONS"]).glob("*/transcript.md"))
txt = memory.replay(s)
print(len(s), "sessions", collections.Counter(l.split(": ")[0] for l in txt.splitlines() if ": " in l))
PY
python3 memory.py dream --dry-run                  # 4. "N session(s), M chars"; nothing written
```

Pass when:

1. The session count matches the conversations you converted.
2. The second run reports no changes.
3. Every owner message you spot-check appears under an `OWNER` speaker, and **no assistant text, tool output or
   injected text appears under `OWNER`**. This check is the one that matters: L5 trusts that label.
4. The dry run reports more than zero characters. With `AGENT_MEMORY_LLM=0` it then reports "extract call
   failed": expected, nothing is marked replayed, and the real run will read the same sessions.

Delete the test folders afterwards.
