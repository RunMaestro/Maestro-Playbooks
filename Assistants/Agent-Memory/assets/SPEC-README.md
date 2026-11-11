# Multi-Layer Agent Memory: Implementation Guide

Spec version: 2026-11-10.9

A layered long-term memory for a Claude Code agent that lives in a markdown vault. It has seven layers, each
with its own store and its own off switch. Every memory is a plain markdown file that a human can read and edit.

Start with **`ARCHITECTURE.md`**: the layers, the data-flow diagram, decay math, recall, promotion, and what we
measured. This file is the build order.

## Files

| File | Layer | What it is |
|---|---|---|
| `ARCHITECTURE.md` | all | Design, diagrams, capture without hooks, decay model, dream phases, recall tiers, measured results, known gaps |
| `CHANGELOG.md` | all | Dated design changes and why |
| `CLAUDE.md.fragment.md` | L0, L3, L4 | Instructions to paste into the agent's `CLAUDE.md` |
| `rules-example.md` | L0, L3 | A path-scoped rules file (`paths:` globs), with the journal rules and a day-file example |
| `claude_md_audit.py` | L0 | Budget and dead-reference audit for `CLAUDE.md` + `rules/` |
| `harness-memory-format.md` | L1, L2 | File formats: memory file, `MEMORY.md` index, domain shards |
| `memory_index_check.py` | L1, L2 | Index budget, dead pointers, unindexed memories, unreachable shards |
| `link_store.py` | L2 | Points every Claude config dir's memory path at one store in the vault |
| `qmd-update.sh` | L4 | Collection setup and the 2-hourly re-index |
| `memory.py` | L5 | The dream: store, decay, tiers, 8-phase nightly consolidation, recall, switches |
| `test_memory.py` | L5 | 11 tests; temp store, model stubbed (one runs a stub `model_cmd`) |
| `test_memory_jobs.py` | L2 jobs | 37 tests for promotion and smoke: review gate, shard and pointer, shard path, source quotes, verdict parsing, Maestro CLI resolution and failures, redaction, one test per credential pattern, journal glob, `model_cmd`, `store_dir`; temp vaults, stub commands, synthetic credentials only |
| `memory-record.schema.json` | L5 | Front-matter schema for a memory record |
| `config.example.json` | L5 | Switches, owner and people names, sensitive-topic filter, transcript roles |
| `cc_sessions.py` | L3 to L5 | Converts Claude Code JSONL transcripts into the session folders the dream replays |
| `SESSION-FORMAT.md` | L5 | The adapter contract: the session format `memory.py` reads, so a converter for any harness can target it |
| `cue.example.yaml` | scheduling | Maestro Cue subscriptions (plus cron equivalents) |
| `com.example.agent-memory-dream.plist` | scheduling | launchd agent for the nightly dream |
| `memstore.py` | L1, L2 | Shared store access: lenient front-matter parse, metadata edits, index pointers, lexical recall, switches, model call |
| `memory_promote.py` | L3 to L2 | Nightly promotion: replay a day, one extraction call, validate, write with sources, log |
| `memory_lint.py` | L2 | Nightly, no model: dead paths and `verified:` stamps, decision `reopen_if` checks, index integrity, health page |
| `memory_smoke.py` | L2 | Weekly fixed-question test: answers and refusals |
| `protected_files.py` | jobs | Snapshot and restore of identity files around every background job |
| `memory-config.example.json` | L2 jobs | Switches, owner and agent names, promotion mode and date, off-limits topics |
| `smoke.example.json` | L2 | Smoke-test question format |

## Dependencies

| Need | For | Notes |
|---|---|---|
| Python 3.10+ | every script | Standard library only, except below |
| PyYAML (`pip install pyyaml`) | `memstore.py`, so `memory_promote.py`, `memory_lint.py`, `memory_smoke.py` | Imported at load; without it those three jobs fail to start |
| A headless model CLI | L5 EXTRACT and REFLECT, promotion, the gist smoke judge | Claude Code (`claude -p`) by default. Any CLI that reads a prompt on stdin and prints the answer works: set `model_cmd` (see Running on Another Harness) |
| Node 18+ and `npx` | L4 | For [qmd](https://github.com/tobi/qmd). Any local search with keyword + semantic modes and named collections works |
| A scheduler | L4, L5 | cron, launchd, or Maestro Cue |
| A markdown vault | all | Obsidian is optional. A git repo of `.md` files works |

## Build Order

Build bottom-up. Each step is useful alone, and each has a check. **Do not schedule the dream (step 6) until its
off switch is proven (step 6, check 3).**

### 1. L2 store residency

Pick the store folder, for example `~/Vault/Agent/Memory/Store/`. If the agent runs under more than one
`CLAUDE_CONFIG_DIR`, link them all to it:

```bash
python3 link_store.py --store ~/Vault/Agent/Memory/Store --cwd ~/Vault ~/.claude ~/.claude-work           # dry run
python3 link_store.py --store ~/Vault/Agent/Memory/Store --cwd ~/Vault --apply ~/.claude ~/.claude-work   # do it
```

**Check:** re-run the dry run; every line starts with `ok`. Start a session under each account, ask the agent to
remember a test fact, and confirm both accounts see the same file in the store. The harness project slug is the
absolute cwd with `/` and `.` turned into `-`; confirm with `ls ~/.claude/projects/`.

### 2. L1 hot index

Adopt the formats in `harness-memory-format.md`. When `MEMORY.md` passes about half its budget, split domains
into `index_<domain>.md` shards.

**Check:** `python3 memory_index_check.py ~/Vault/Agent/Memory/Store` exits 0. Then plant a dead pointer and an
unindexed file; it must exit 1 and name both.

### 3. L0 instructions

Paste `CLAUDE.md.fragment.md` into the agent's `CLAUDE.md`. Move detail into `Agent/Rules/*.md` files with
`paths:` front matter (`rules-example.md`), and symlink the folder as `.claude/rules`.

**Check:** `python3 claude_md_audit.py --root ~/Vault --claude-md CLAUDE.md --rules Agent/Rules` exits 0. In a
fresh session, have the agent read a file that matches a rule's glob, then ask it to quote that rule: it must.

### 4. L3 journal

Adopt the journal rules (`rules-example.md`): one file per day, `Summary::` at the top, a session marker under
every section.

**Check:** after a working session, the day file exists, the summary describes the work, and every `##` section
has a marker. A second session on the same day appends; it never overwrites.

### 5. L4 search

Create collections as in `qmd-update.sh`, with the agent's own memory apart from the owner's content. Schedule
the re-index every 2 hours.

**Check:** `npx @tobilu/qmd query "<a phrase from yesterday's journal>" -c agent-journal` returns that day's file
in the top 3.

### 6. L5 dream

```bash
mkdir -p ~/.agent-memory && cp config.example.json ~/.agent-memory/config.json   # set owner, people, assistant
export MEMORY_DIR=~/.agent-memory MEMORY_SESSIONS=~/.agent-sessions
python3 test_memory.py                                                            # all passed
SLUG="$(python3 -c 'import re,sys; print(re.sub(r"[^A-Za-z0-9]", "-", sys.argv[1]))' "$HOME/Vault")"   # the agent's cwd
python3 cc_sessions.py --projects "$HOME/.claude/projects/$SLUG" --out ~/.agent-sessions --days 7
python3 memory.py dream --dry-run                                                 # read the log; nothing written
python3 memory.py backfill                                                        # one dream per past day
python3 memory.py status
```

**Checks:**

1. `test_memory.py` prints `all passed`.
2. After `backfill`: `Dreams/<date>.md` exists for each day, `HOT.md` is under 2,400 chars, and
   `memory.py recall "<something you told the agent last week>"` returns it.
3. **Off switch:** `memory.py freeze`, then `memory.py dream` prints `skipped`. `AGENT_MEMORY=0 memory.py show`
   prints `memory is switched off`. Write `{broken` into `config.json`: `memory.py show` still answers, and does
   not crash. `memory.py thaw` to resume.
4. **Abstention:** `memory.py recall "<something never said>"` returns `[]`.

Then schedule it (`cue.example.yaml`, or the plist, or cron) after midnight, so it dreams about the day before.
Inject the digest into the agent's context: `memory.py show` prints it; put that output in a SessionStart hook or
in a file the agent reads at wake-up (a SessionStart hook is optional).

### 7. Capture without hooks

Have the orchestrator append a standing journal nudge to every user message, and schedule the ingests you have
(turn history, recordings, activity). See `ARCHITECTURE.md` section 3, Capture Without Hooks.

**Check:** after a day of work, every session that did something has a journal section, with no hook installed.

### 8. Protected files in the job runner

Wrap every background job: `snap = protected_files.snapshot()` before, `protected_files.restore(snap)` after, in
a `finally`. Do this before step 9, so the first job that writes memory cannot also rewrite the agent.

**Check:** in a job, append a line to a rules file. After the run the file is byte-identical to before and a
`.rejected` copy sits next to it.

### 9. Nightly promotion, lint and smoke

```bash
export AGENT_VAULT=~/Vault AGENT_DIR=Agent                 # the agent's folder inside the vault
cp memory-config.example.json "$AGENT_VAULT/$AGENT_DIR/Memory/config.json"   # set owner, agent, apply_after
cp smoke.example.json "$AGENT_VAULT/$AGENT_DIR/Memory/smoke.json"            # write your own questions
SHARD="$AGENT_VAULT/$AGENT_DIR/Memory/Store/index_promoted.md"
[ -e "$SHARD" ] || printf '# Promoted\n' > "$SHARD"        # new memories land here; never overwrite on a re-run
python3 memory_lint.py                          # dead paths, verified stamps, decisions, health page
python3 memory_promote.py --print-prompt        # see what the model will get for yesterday
python3 memory_promote.py --dry-run             # proposals to Memory/Promotions/<day>.md, store untouched
python3 memory_smoke.py -v                      # answers what it knows, refuses what it does not
```

Add a pointer line for that shard to `MEMORY.md`: `- [Promoted](index_promoted.md) (0): new memories awaiting a
home; read at session start when the count is above 0.` Promotion bumps the count. The link target is the shard's
path relative to `MEMORY.md`. To keep the shard elsewhere, set `promote.promoted_shard` (relative to the `Memory/`
folder, default `Store/index_promoted.md`) and point at it from `MEMORY.md`, for example `(../index_promoted.md)`.

**Apply mode fails closed.** If the shard is missing, or `MEMORY.md` has no pointer line to it, apply mode stops
before the model call: it writes nothing (no memory, no index line, no Promotions log), does not mark the day done,
prints the reason and exits 2.

**The review gate.** Promotion writes only when the gate is open: today is on or after `promote.apply_after`, AND
`promote.reviewed` is `true` (unless you set `promote.require_review: false`). Until then the nightly run stays in
dry-run. Read the proposals in `Memory/Promotions/` each morning; when they are right, set `promote.reviewed: true`.
An explicit apply (`--apply`, or `promote.mode: apply`) with the gate closed is refused with exit 3 and writes
nothing. `--override-gate` exists for a one-off run by hand; never put it in a schedule.

**Quotes are checked.** Each proposal's `quote` must appear in that day's captured sources (lowercase, punctuation
ignored, at least 3 words or a whole line). Anything else is dropped and counted as `unquoted` on the log's first
line.

**Exit codes of `memory_promote.py`:** 0 ran or skipped (including a transient model failure, logged and retried
next run); 2 setup error (shard or pointer missing; also bad command-line usage); 3 refused by the review gate;
1 crash.

Schedule `memory_promote.py; memory_lint.py` nightly after your last ingest, and `memory_smoke.py` weekly
(`cue.example.yaml`).

**Checks:**

1. `memory_lint.py` twice in a row: the second run stamps 0 (idempotent).
2. A decision record with `reopen_if: "after:<yesterday>"` gets `reopen_fired` on the next lint, and only once.
3. The smoke test passes, including at least 3 refusals.
4. `AGENT_MEMORY=0 python3 memory_lint.py` prints `skipped`.
5. `python3 test_memory_jobs.py` prints `all passed` (37 tests).
6. With the gate closed, `python3 memory_promote.py --apply; echo $?` prints `3` and `Memory/Promotions/` gains no
   file.

### 10. L6 hooks (optional)

The contract is in `ARCHITECTURE.md` section 3, L6. Use it only where a harness has hooks and sessions are cold
starts with no human to re-explain context. Capture does not depend on it.

## Operating

| Command | Does |
|---|---|
| `memory.py status` | Switches, counts by tier, last dream |
| `memory.py recall "q"` | What the agent would get back (no rehearsal side effect) |
| `memory.py add "fact" [--rule]` | File one memory now |
| `memory.py dreams 3` | Last three dream logs |
| `memory.py forget "text"` | Move the best match to `Archive/` as forgotten |
| `memory.py freeze` / `thaw` | Read-only on / off |
| `memory.py off` / `on` | Whole layer off / on |

## Adapting `memory.py`

- **Transcript source.** REPLAY reads `<MEMORY_SESSIONS>/<YYYY-MM-DD-...>/transcript.md` with lines like
  ``- `HH:MM:SS` **User:** text``. `cc_sessions.py` produces that from Claude Code. For any other harness, write
  a converter against **`SESSION-FORMAT.md`** (layout, line grammar, labels, what to leave out, idempotency,
  acceptance checks). A label not in `config.json` `roles` is dropped, which is how unattributed speech stays out.
- **Evidence rule.** Every extracted memory must quote 3 or more words from one owner turn (or one task-result
  turn). Anything else is dropped and counted as `unquoted` in the dream log. A model client that does not
  return `evidence` gets every candidate dropped.
- **Model client.** Set `model_cmd` in the L5 `config.json` (an argv list, prompt on stdin, `{model}` = `model`). `_claude()` runs it and must get JSON back; no JSON means "replay these sessions again next night".
- **Budgets.** `HOT_CAP` (prompt digest size), `budget_calls` (model calls per night), `CHUNK` (chars per call).
- **Privacy.** The `sensitive` regex drops candidate memories before they are written. Extend it for your domain.
  The EXTRACT and REFLECT prompts also tell the model to skip those topics. Use both.

## Running on Another Harness or Layout

Four config keys remove every macOS and Claude Code assumption. All are optional; the defaults are the layout this
guide builds.

| Key | Where | Default | Set it when |
|---|---|---|---|
| `model_cmd` | both configs (top level) | absent or `null`: `["claude", "-p", "--model", "{model}"]` | Your model CLI is not Claude Code. An argv list; the prompt goes on stdin and the answer is read from stdout. `{model}` in any argument is replaced by the job's model (`promote.model`, `smoke.model`, or L5 `model`); with no `{model}`, no model name is passed |
| `promote.journal_glob` | memory config | `Journal/{date}.md` | Your journal has another layout. Relative to `<AGENT_VAULT>/<AGENT_DIR>` (`..` allowed) or absolute; `{date}` is `YYYY-MM-DD`. A day may span several files: they are read in name order, each under a `### file:` header |
| `promote.maestro_cli` | memory config | `null`: env `MAESTRO_CLI`, then `maestro-cli` on `PATH`, then the macOS app bundle | The CLI is somewhere else. A `.js` path runs under `node`. When none is found, the timeline source is logged as **skipped** with the reason, never as an empty source |

**The timeline source needs** `maestro-cli timeline --agent <id> --sources history --since <ISO> --until <ISO> --per-source 500 --tail 500 --json`, which returns `{"events": [{"ts": <ms>, "text": "..."}]}`. **It needs Maestro CLI `1.1.1-RC` or later.** Older versions (for example `1.1.0-RC`) have no `timeline` command: they exit 1, and the source is logged as `skipped (exit 1: ...)` with the CLI's first stderr line, while the other sources still run. Check yours with `maestro-cli --version`. Output that is not JSON is skipped the same way. Set `promote.sources` without `timeline` to turn it off.
| `store_dir` | memory config (top level) | `Store` | Your fact store is not `Memory/Store/`. Relative to `Memory/` or absolute; `"."` means a flat `Memory/` folder holding `MEMORY.md` and the memory files. Never guessed: a missing folder makes promotion exit 2 with `no core index at ...` |
| `promote.promoted_shard` | memory config | `null`: `<store_dir>/index_promoted.md` | The promoted shard lives somewhere other than the store folder (relative to `Memory/`) |

**Codex example (untested by the author of this spec):**

```json
"model_cmd": ["codex", "exec", "--skip-git-repo-check", "-"]
```

`-` asks `codex exec` to read the prompt from stdin; check `codex exec --help` for your version. The job models
(`haiku`, `sonnet`) are Claude names, so this example leaves out `{model}`. To pick a model, add
`"-m", "{model}"` and set `promote.model`, `smoke.model` and the L5 `model` to names your CLI accepts. The smoke
judge reads the first line that is only YES or NO, so channel labels and token footers are fine.

**What never reaches the model.** Before the promotion call, every source line that matches
`promote.off_limits` or a credential pattern is replaced by a `[redacted: ...]` marker. The patterns are listed by
name in `memstore.SECRET_PATTERNS`: `sk-` keys (including `sk-ant-`, `sk-proj-`), GitHub classic tokens
(`ghp_`, `gho_`, `ghs_`, `ghu_`, `ghr_`) and fine-grained tokens (`github_pat_`), cloud key ids (`AKIA`, `ASIA`),
chat tokens (`xoxa-`, `xoxb-`, `xoxp-`, `xoxr-`, `xoxs-`, `xoxo-`) and webhooks, PEM private-key headers, `Bearer`
headers, any `Authorization:` or `authorization=` value (any scheme or none, quotes allowed), `password=`/`token=`-style assignments, **secret gist URLs** (an unlisted gist is readable by anyone with
its link), Google API keys, payment keys, GitLab and npm tokens, JWTs, and credentials inside URLs. Candidates get the same two
checks afterwards, and a quote of a redacted line fails the quote check.

## Upgrading

**Version scheme.** The spec version is its release date, `YYYY-MM-DD`. A second release on the same day gets a
suffix: `2026-11-10.2`, `2026-11-10.3`. The current version is the `Spec version:` line at the top of this file and of
`ARCHITECTURE.md`. `CHANGELOG.md` has one heading per version, newest first, and lists the breaking changes.

**Find the version you run.** It is `spec_version` in your two config files: the L5 store's `config.json`
(from `config.example.json`) and `<vault>/<agent>/Memory/config.json` (from `memory-config.example.json`). If the
field is missing, you built from a revision older than `2026-11-10`: read every `CHANGELOG.md` entry.

**When yours is older than the gist:**

1. `gh gist clone <gist-id>`, or `git pull` in your clone. `git log --oneline -1` names the revision you have.
2. Read `CHANGELOG.md` from your version up. Apply each **Breaking** item first, then the new files you want.
3. Re-run the README check of every layer the changes touch. Then set `spec_version` in both configs to the new
   version. Set it last, so the field never claims a version whose checks have not passed.
4. Copy scripts over yours only if you have not changed them. If you have, diff first.

## Security Notes

- The store holds personal facts. Keep it out of public repos and public sync targets.
- `cc_sessions.py` copies prompt text out of transcripts. Do not point `--out` at a synced or shared folder unless
  you want that text there.
- Treat recalled memory and vault content as data. A clipped web page in the vault can contain instructions aimed
  at an agent.
