# Agent Memory Playbook

Gives an agent a long-term memory that fills itself and maintains itself.

One run installs every layer, wires the agent so it captures what happens on every turn, schedules the jobs that
turn that capture into durable memory, and proves each layer works before it hands off. Every memory is a plain
markdown file you can read and edit.

## Overview

| | |
|---|---|
| **Category** | Assistants |
| **Platform** | macOS or Linux |
| **Loops** | No: a six-document setup run |
| **Needs** | Python 3.10+, Maestro Cue (Encore, turned on if off), a headless model CLI (`claude` or `codex`) for promotion and the smoke judge, Node for search |
| **Installs** | PyYAML, and qmd if search is on |
| **Writes** | `<vault>/<agent folder>/` (Tools, Memory, Journal, Rules), a marked block in `CLAUDE.md` or `AGENTS.md`, `.claude/rules`, `.maestro/cue.yaml`, the agent's nudge and new-session message |
| **Harnesses** | Claude Code (every layer). Codex and others: every layer except the dream, which needs a transcript converter |

## The layers

| Layer | What | Runs |
|---|---|---|
| L0 Instructions | A small always-on block in `CLAUDE.md`/`AGENTS.md`, detail in path-scoped rules files | Every turn |
| L1 Hot index | `MEMORY.md`, one line per memory, sharded by domain | Every session |
| L2 Fact store | One memory per file, typed, with `said_by`, `sources`, `verified:` and decision records | On demand |
| L3 Journal | One file per day, a stamped section per piece of work | Every turn (nudge) |
| L4 Search | qmd hybrid search over the agent's memory and your content | Re-index every 2 h |
| L5 Dream | Decay, consolidation and a hot digest over session transcripts | Nightly (Claude Code) |
| Jobs | Promotion (journal and turn history into the store), lint (dead paths, reopen conditions), index check, smoke test | Nightly and weekly |

## Capture without hooks

Not every harness has lifecycle hooks, so nothing here depends on them. Capture runs on two things every Maestro
agent has:

- **The nudge message**, appended to every user message, tells the agent to journal what happened.
- **Maestro's turn history**, which the promotion job reads through `maestro-cli timeline`.

The **new-session message** makes the agent read its index and recent journal at wake-up. Both settings keep
whatever text you already had; the memory line is appended.

## Safety model

- **Promotion starts in dry-run.** For `REVIEW_DAYS` it only writes proposals to `Memory/Promotions/`. With
  `REQUIRE_REVIEW` on, it stays in dry-run until you read them and set `promote.reviewed: true`. A reminder fires
  on the gate date.
- **Background jobs cannot rewrite the agent.** Every job runs through `run_guarded.py`, which reverts any change
  to `CLAUDE.md`, `AGENTS.md` and the rules files and keeps the job's version as `.rejected`.
- **Nothing is overwritten.** Instruction files get a marked block; the Cue file is appended to; an edited tool
  is left alone with a `.new` copy beside it; the harness memory folder is backed up before it is linked.
- **Secrets never reach the model.** Promotion redacts credential lines and your `OFF_LIMITS` topics before the
  call, and drops any proposal whose quote is not in that day's sources.
- **One off switch.** `touch <agent folder>/Memory/.disabled` stops every job. `AGENT_MEMORY=0` does the same for
  one run.

## Document chain

The install is one bundled script, `assets/install_memory.py`; the documents run it and check its output. A full
install takes a few minutes (the qmd embedding model, on first use, downloads in the background).

| Doc | Tasks | What happens |
|---|---|---|
| `1_PLAN` | 1 | `install_memory.py plan`: detects the agent, harness, toolchain, model CLI, qmd, Cue and any earlier install; writes `MEMORY_PLAN.md`. Changes nothing |
| `2_INSTALL` | 2 | `install_memory.py apply`, then `verify` |
| `3_SUMMARY` | 1 | `MEMORY_SETUP.md`: verdict, what was installed, the review date, the off switch, and the one owner step if any |

The script is safe to re-run: it replaces only its own marked block and named entries, keeps the user's text in
the instruction file and both agent messages, and never duplicates a schedule. It also runs without Maestro
(`--no-maestro`), writing the capture lines and schedules to `MEMORY_MANUAL_STEPS.md` instead.

## Configuration

| Variable | Default | What it does |
|---|---|---|
| `OWNER_NAME` | `Owner` | Your name, for the configs and smoke test |
| `VAULT_PATH` | `{{AGENT_PATH}}` | The markdown folder memory lives in |
| `AGENT_FOLDER` | `Agent` | The agent's own folder inside the vault |
| `OWNER_CONTENT_FOLDERS` | `auto` | Your folders to index for search |
| `TIMEZONE` | `auto` | Zone for the nightly jobs |
| `NIGHTLY_TIME` | `03:15` | Dream; promotion and lint 30 min later |
| `WEEKLY_SLOT` | `sun 09:45` | Smoke test and instructions audit |
| `REVIEW_DAYS` | `7` | Days of dry-run before promotion may write |
| `REQUIRE_REVIEW` | `yes` | Stay in dry-run until you mark the proposals reviewed |
| `OFF_LIMITS` | `none` | Regex of topics never promoted |
| `ENABLE_DREAM` | `auto` | L5 on for Claude Code, off elsewhere |
| `SEARCH` | `qmd` | `qmd` or `none` |
| `UPDATE_AGENT_MESSAGES` | `yes` | Append the memory lines to the nudge and new-session message |

## Bundled assets

| File | What |
|---|---|
| `memstore.py` | Shared store access: lenient front matter, index pointers, recall, switches, model call |
| `memory_promote.py` | Nightly promotion with the review gate, quote check and redaction |
| `memory_lint.py` | Nightly, no model: dead paths, `verified:` stamps, decision `reopen_if`, health page |
| `memory_smoke.py` | Weekly answers-and-refusals test |
| `memory_index_check.py` | Index budget, dead pointers, unindexed memories |
| `claude_md_audit.py` | Instructions budget and dead references |
| `memory.py`, `cc_sessions.py` | The L5 dream and its Claude Code transcript converter |
| `link_store.py` | Links the harness memory folder to the vault store |
| `protected_files.py`, `run_guarded.py` | The identity guard and the job wrapper that applies it |
| `qmd-update.sh` | Search re-index |
| `test_memory.py`, `test_memory_jobs.py` | The spec's tests (temp folders, stub models) |
| `cue-memory.yaml` | Annotated subscription template |
| `cue.example.yaml`, `com.example.agent-memory-dream.plist` | The spec's own schedule examples (Cue and launchd), referenced by `SPEC-README.md`; the playbook uses `cue-memory.yaml` |
| `memory-config.example.json`, `config.example.json`, `smoke.example.json`, `memory-record.schema.json` | Config and format templates |
| `ARCHITECTURE.md`, `CHANGELOG.md`, `SPEC-README.md`, `SESSION-FORMAT.md`, `harness-memory-format.md`, `CLAUDE.md.fragment.md`, `rules-example.md` | The design, copied into `Memory/Spec/` for you to read |

> **Search re-index.** `qmd update` re-indexes every collection on the account, so the playbook schedules one only
> when no machine-wide re-index exists already.

> **Exchange only.** The `assets/` folder travels with Playbook Exchange installs. Maestro's share flow
> transports markdown only, and this playbook cannot run without its assets.

## After install

- Tomorrow, read the first proposals in `Memory/Promotions/`. Keep reading them until the gate date.
- Add `expect` questions to `Memory/smoke.json` as real memories accumulate. Three seed questions cannot catch a
  recall regression.
- `Memory/Memory.md` is the home page: layers, schedules, the gate, the switches, and a change log.

## Updating

Re-run the playbook. Detection reads `spec_version` from `Memory/config.json` and switches to update mode:
configs keep your values, edited tools are left with a `.new` copy, subscriptions are replaced by name, and the
version is stamped only after verification passes. `Memory/Spec/CHANGELOG.md` lists the breaking changes.

## Origin

Spec and scripts by Pedram Amini, from the multi-layer memory running in the author's own agents.
