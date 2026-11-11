# Changelog

Spec versions are release dates, `YYYY-MM-DD`. A second release on the same day adds a suffix: `.2`, `.3`.
Newest first. Each version lists what changed, the new files, and the **breaking** changes an existing install
must apply. Find the version you run in `spec_version` in your configs (see `README.md`, Upgrading).

## 2026-11-10.7

Two bugs found by the agent that packaged this spec as an Auto Run playbook.

### Changed

| # | File | Change | Breaking? |
|---|---|---|---|
| G21 | `memory_promote.py` | `"model": null` in the promote config now means the default model. Before, `null` reached the model call as `None` and crashed the extraction step (`replace() argument 2 must be str`), so the night was lost | No |
| G22 | `memory_promote.py` | The Promotions log no longer ends with a hardcoded tag from the reference install's own vault conventions | No (cosmetic) |

### New tests

`test_memory_jobs.py` grows from 37 to 39: `test_g21_null_model_falls_back_to_the_default` and
`test_g22_promotions_log_carries_no_vault_tag`. Mutation check: both fail against the `.6` `memory_promote.py`.

### Breaking

None. Copy `memory_promote.py` and `test_memory_jobs.py`, then **set `spec_version: "2026-11-10.7"`** in both configs
after `test_memory_jobs.py` (39) and `test_memory.py` (11) pass.

## 2026-11-10.6

One secret-filter gap (G19) and one documentation fix (G20), both from an implementer's `.5` run.

### Changed

| # | File | Change | Breaking? |
|---|---|---|---|
| G19 | `memstore.py` | New pattern `authorization` in `SECRET_PATTERNS`: an authorization header or assignment, case-insensitive, `:` or `=`, any scheme (`Basic`, `Token`, `Digest`, ...) or none, optional quotes as in JSON. Before, only `Bearer` values were caught, so `Authorization: Basic ...`, `Authorization: Token ...` and bare values reached the model | **Yes, can reduce promotions.** More source lines are redacted before the model, and more candidates are dropped as "contains a secret" |
| G20 | `README.md` | The timeline source needs Maestro CLI `1.1.1-RC` or later. Older versions such as `1.1.0-RC` have no `timeline` command and log `skipped (exit 1: ...)` | No (docs) |

### New tests

`test_memory_jobs.py` grows from 36 to 37: `test_g19_every_authorization_form_is_redacted` covers `Basic`, `Token`,
a bare value with `:`, a bare value with `=` and a quoted JSON header, plus three ordinary sentences that must not
match. The credential-coverage test gains an `authorization` sample. Values are filler assembled at run time.
Mutation check: removing the pattern, or narrowing it to `Bearer` only, fails both tests.

### Breaking

1. **G19:** no config change. Copy `memstore.py` and `test_memory_jobs.py`. Expect a few more
   `[redacted: secret]` lines in the first week's Promotions logs.
2. **Set `spec_version: "2026-11-10.6"`** in both configs after `test_memory_jobs.py` (37) and `test_memory.py`
   (11) pass and one nightly promotion, lint and smoke have run.

## 2026-11-10.5

Three defects (G16 to G18) from an implementer's `.4` run. G16 is a privacy fix and can reduce promotions.

### Changed

| # | File | Change | Breaking? |
|---|---|---|---|
| G16 | `memstore.py` | `SECRET_RE` is now built from a named list, `SECRET_PATTERNS`. Added: GitHub fine-grained tokens (`github_pat_`), **secret gist URLs** (`gist.github.com` and `gist.githubusercontent.com` with a 20 to 40 hex id), `ASIA` cloud key ids, chat webhooks, Google API keys, payment keys (`sk_live_`, `rk_test_` style), GitLab tokens (`glpat-`), npm tokens (`npm_`), JWTs, and credentials inside URLs (`scheme://user:pass@`). Kept and now tested one by one: `sk-` (covers `sk-ant-`, `sk-proj-`), `ghp_`/`gho_`/`ghs_`/`ghu_`/`ghr_`, `AKIA`, `xox[abposr]-`, PEM private-key headers, `Bearer` headers, `password=`/`token=` assignments | **Yes, can reduce promotions.** More source lines are redacted before the model, and more candidates are dropped as "contains a secret". A journal line that shares a gist link is now redacted |
| G17 | `memory_promote.py` | The timeline command's exit code is checked before its output is read. Non-zero: the source is logged as `skipped (exit N: <first stderr line>)` and not parsed. Exit 0 with output that is not JSON: `skipped (timeline output is not JSON: ...)`. The README names the command and the CLI version it was built against | No. A broken timeline was already lost; now the log says why |
| G18 | `memstore.py`, `memory_promote.py` | Config `store_dir` (top level): the fact store folder that holds `MEMORY.md`, relative to `Memory/` or absolute, default `Store`, `"."` = flat. Never auto-detected. The default promoted shard follows it (`<store_dir>/index_promoted.md`), so `promote.promoted_shard` is only needed for a shard outside the store folder. A missing store folder or `MEMORY.md` makes apply mode exit 2 with `no core index at ... (check config store_dir)` | **Yes, for a flat layout that relied on a local fallback**: set `store_dir: "."` or the jobs read an empty `Memory/Store/`. Default layouts are unaffected |

### New tests

`test_memory_jobs.py` grows from 28 to 36: 3 for G16 (one assertion per named pattern and every listed prefix,
ordinary text that must not match, and an end-to-end run where a fine-grained token and a secret gist URL never
reach the model), 2 for G17 (a stub CLI that exits 1 with `unknown command 'timeline'`, and one that prints
non-JSON), 3 for G18 (flat layout, no silent fallback, missing store folder). Every credential value in the tests
is synthetic and assembled at run time, so the file holds nothing token-shaped. Each new guard was
mutation-checked: removing a pattern, weakening one, dropping the exit-code check, ignoring `store_dir`, adding a
silent fallback, or pinning the shard default each fails its own test.

### Breaking

1. **G18, flat layout:** set `"store_dir": "."` at the top level of `Memory/config.json`, remove any local
   fallback in `memstore.py`, and remove `promote.promoted_shard` if it only pointed at `Memory/index_promoted.md`
   (the default now resolves there). `MEMORY.md` keeps its `(index_promoted.md)` pointer.
2. **G16:** no config change. Expect more `[redacted: secret]` lines and some "contains a secret" drops; read the
   counts in the first week's Promotions logs.
3. **Set `spec_version: "2026-11-10.5"`** in both configs after `test_memory_jobs.py` (36) and `test_memory.py`
   (11) pass and one nightly promotion, lint and smoke have run.

## 2026-11-10.4

Portability and privacy. Four defects (G12 to G15) found by an implementer running on Linux with Codex and a
different journal layout. G13 is a privacy fix and can reduce promotions.

### Changed

| # | File | Change | Breaking? |
|---|---|---|---|
| G12 | `memory_promote.py` | The Maestro CLI is resolved in this order: env `MAESTRO_CLI`, config `promote.maestro_cli`, `maestro-cli` on `PATH`, the macOS app bundle. A `.js` path runs under `node`. When none is found, or the timeline command fails, the source is logged as **skipped** with the reason (Promotions log, "Sources:" line), never reported as an empty source | No. macOS installs resolve as before. A Linux install that silently got 0 chars now sees why |
| G13 | `memory_promote.py`, `memstore.py` | **Every source is redacted before the model call.** A line that matches `promote.off_limits` or a credential pattern (`memstore.SECRET_RE`: API keys, cloud and chat tokens, private-key headers, bearer tokens, `password=`/`token=` style assignments) is replaced by `[redacted: off-limits]` or `[redacted: secret]`. Counts go on the log's "Sources:" line. The candidate filter keeps its off-limits check and gains the secret check. The G10 quote check runs on the redacted text, so a quote of a redacted line is dropped as `unquoted` | **Yes, can reduce promotions.** Memories that used to come from a line naming an off-limits topic, or a line holding a credential, are no longer proposed |
| G14 | `memory_promote.py` | Config `promote.journal_glob`: the journal files of a day, relative to the agent folder (`..` allowed) or absolute, `{date}` = `YYYY-MM-DD`. Default `Journal/{date}.md`, which is the old layout. Several files for one day are read in name order, each under a `### file:` header | No |
| G15 | `memory.py`, `memstore.py`, `memory_promote.py`, `memory_smoke.py` | Config `model_cmd`: the argv of any headless model CLI, prompt on **stdin**, answer on stdout, `{model}` replaced by the job's model. Absent or `null` means `["claude", "-p", "--model", "{model}"]`: the requested `["claude", "-p"]` plus the model name, so the per-job model choice is kept. Used by the L5 dream, promotion and the gist's smoke judge. L5 gains a `model` config key (default `haiku`); `MEMORY_MODEL` still wins. A Codex example is in the README, marked untested by the spec author | **Yes, for code that called the gist's `memstore.run_claude()`**: it is gone; call `memstore.model_call(prompt, model)`. A local patch of `_claude()` or of the `claude -p` line should be replaced by `model_cmd`. The default call now sends the prompt on stdin instead of as an argument (verified with Claude Code; same answers) |

### New tests

`test_memory_jobs.py` grows from 18 to 28 tests (3 for G12, 2 for G13, 2 for G14, 3 for G15). `test_memory.py`
grows from 10 to 11 (G15 for L5). Every new guard was mutation-checked: disabling it fails its own test. Model
stubs print a channel label and a token footer around the answer, the way Codex does.

### Breaking

1. **G15: replace local model patches.** Delete any patch of `memory.py`'s `_claude()` or of the `claude -p` call
   in `memstore.py` or `memory_promote.py`. Set `model_cmd` in BOTH configs instead (the L5 `config.json` and
   `Memory/config.json`). Code that imports `memstore.run_claude` must call `memstore.model_call(prompt, model)`.
2. **G13: expect fewer promotions.** No config change. For the first week, read the "redacted before the model"
   counts and the `(N unquoted)` count in each Promotions log.
3. **G12 / G14: replace local path patches** with `promote.maestro_cli` and `promote.journal_glob`.
4. **Set `spec_version: "2026-11-10.4"`** in both configs after `test_memory_jobs.py` (28) and `test_memory.py`
   (11) pass and one nightly promotion, lint and smoke have run.

## 2026-11-10.3

Seven open defects (G5 to G11) found while implementing `.2`, fixed. Each item says whether it breaks an existing
install. G7, G8 and G10 can change what an existing install promotes.

### Changed

| # | File | Change | Breaking? |
|---|---|---|---|
| G5 | `README.md` | Describes the G4 behavior: apply mode with no shard writes nothing, does not mark the day done, exits 2 | No (docs) |
| G6 | `memory_promote.py`, `README.md`, `ARCHITECTURE.md` | The docstring, README and architecture list the real exit codes: 0 ran or skipped (a transient model failure is logged and retried), 2 setup error (shard or pointer missing; also bad usage), 3 refused by the review gate, 1 crash | No (docs; exit 3 is new with G7) |
| G7 | `memory_promote.py`, `memory-config.example.json` | **Every path to apply obeys the review gate**: `promote.apply_after` reached AND `promote.reviewed: true` (skip the second part with `promote.require_review: false`). The nightly switch from dry-run to apply happens only when the gate is open. An explicit apply (`--apply` or `promote.mode: apply`) against a closed gate is refused: nothing written, day not marked, exit 3. `--override-gate` is the only bypass; no scheduler example uses it | **Yes.** An install past its `apply_after` stops applying until `reviewed: true` is set. `--apply` before the date now exits 3 instead of writing |
| G8 | `memory_promote.py`, `memstore.py` | Apply mode also fails closed (exit 2, nothing written, day not marked) when the shard exists but `MEMORY.md` has no pointer line to it | **Yes**, if your `MEMORY.md` lacks the pointer: apply stops until you add it |
| G9 | `memory_smoke.py` | The judge's reply is read for the first line that is only YES or NO (markdown, quotes and a full stop allowed). Channel labels, preambles and footers are ignored. No such line counts as a miss for answer AND abstain questions. The judge prompt asks for the verdict on its own line | **Yes, for installs that use the gist's judge**: a reply such as "Yes, they do" passed before and is now a miss. A custom `judge()` that returns a float is unaffected; it may now return `None` for "no verdict" |
| G10 | `memory_promote.py`, `memstore.py` | Each proposal's `quote` must appear in that day's captured source text, as the model saw it, normalized with the G1 rules (lowercase, punctuation as spaces, whole words, within one line, at least 3 words or a whole line). Anything else is dropped and counted as `unquoted` on the Promotions log's first line | **Yes.** Paraphrased or invented quotes were accepted before; those proposals are now dropped, so fewer memories are promoted |
| G11 | `memstore.py`, `memory_promote.py`, `memory-config.example.json` | Optional `promote.promoted_shard`: the shard path relative to the `Memory/` folder (or absolute). Default unchanged, `Store/index_promoted.md`. G4 and G8 use the resolved path; the `MEMORY.md` pointer is the shard's path relative to `MEMORY.md` | No. A local patch that moved the shard can be replaced by the key |

### New files

| File | What it is |
|---|---|
| `test_memory_jobs.py` | 18 tests for promotion and smoke, one or more per item above; temp vaults, model stubbed. Each guard was mutation-checked: disabling it fails its own test |

### Breaking

Apply in this order (the README's Upgrading section has the general procedure):

1. **G7, review gate.** Add `"require_review": true` and `"reviewed": false` under `promote` in
   `<AGENT_VAULT>/<AGENT_DIR>/Memory/config.json`. Read the dry-run logs in `Memory/Promotions/`; set
   `"reviewed": true` only when they are right. If your design treats the dry-run period itself as the review, set
   `"require_review": false` instead and say so in your journal. Remove `--apply` from any schedule; the gate now
   decides.
2. **G8, pointer.** Make sure `MEMORY.md` links the shard by its path relative to `MEMORY.md`, for example
   `- [Promoted](index_promoted.md) (0): ...`.
3. **G10, quotes.** No config change. Expect fewer promotions: read the `(N unquoted)` count on each log's first
   line for the first week.
4. **G9, smoke judge.** If you use the gist's `judge()`, take the new one. If your model client wraps answers in
   labels or footers, the new parser handles that; a reply with no YES or NO line is now a miss.
5. **Set `spec_version: "2026-11-10.3"`** in both configs after `test_memory_jobs.py` and `test_memory.py` pass and
   one nightly promotion and lint have run.

## 2026-11-10.2

Four defects reported by an implementer on its first live run, fixed.

### Changed

- **G1, L5 evidence rule (`memory.py`).** The extraction prompt let a fact come from assistant text, and nothing
  checked the quote; on a first live run, assistant context was stored as something the owner said. Now every
  candidate must carry `evidence`: 3 or more words copied from ONE owner turn or ONE task-result turn (or that
  whole turn if it is shorter). Assistant lines never count. A candidate without a matching quote is dropped and
  counted as `unquoted` in the dream log and in `history.jsonl`. The quote, not the model's claim, now sets
  `said_by` (`owner` or `task`). New test: `test_extract_requires_a_quote_from_an_owner_turn`.
- **G2, adapter contract (`SESSION-FORMAT.md`, new).** The session format `memory.py` reads is now a written
  contract: layout, line grammar, labels and what each replays as, what a converter must leave out,
  idempotency, and acceptance checks. A Codex, orchestrator or voice-app converter targets it; `cc_sessions.py`
  is the Claude Code example.
- **G3, placeholders in the schedule examples.** `cue.example.yaml`, the launchd plist and the cron lines carried
  times from a real environment. Every time, ID, cwd slug and time zone is now a `<PLACEHOLDER>`.
  `memstore.py`'s default `AGENT_TZ` is now `UTC`.
- **G4, promotion fails closed (`memory_promote.py`).** Apply mode without `Memory/Store/index_promoted.md` used to
  write memory files it could not index and mark the day done. It now stops before the model call, writes
  nothing, leaves the day unmarked, prints the reason to stderr and exits 2.

### New files

| File | What it is |
|---|---|
| `SESSION-FORMAT.md` | The L5 input contract for converters |

### Breaking

1. **L5: candidates without `evidence` are now dropped.** Stored memories are not touched. But if you replaced
   `_claude()` with your own client, or your test stubs return candidates without `evidence`, every candidate is
   dropped from now on. Return the quote. Check: after one real dream, `unquoted` in `Dreams/<day>.md` must be
   lower than the number of candidates.
2. **L5: speaker values must follow the contract.** A memory can only be supported by a turn whose replayed
   speaker starts with `OWNER` or is exactly `TASK RESULT`. If you changed the right-hand values in `roles`
   (for example to your own name), change them back, or nothing will be extracted.
3. **L5: `said_by` comes from the quote.** A candidate the model labelled `owner` but that quotes a task-result
   turn is stored as `task`, and so ranks lower in contradictions.
4. **`AGENT_TZ` now defaults to `UTC`.** If you relied on the default, "yesterday" for
   promotion shifts. Set `AGENT_TZ` explicitly.
5. **Promotion now exits 2 when the promoted shard is missing.** A scheduler that alerts on a non-zero exit will
   alert. That is the intent: create the shard (see 2026-11-10, item 4).
6. **Schedule examples no longer load as-is.** The plist fails `plutil -lint` until `HOUR` and `MINUTE` are
   replaced. Installed schedules are not affected.
7. **Set `spec_version: "2026-11-10.2"`** in both configs after `test_memory.py` passes (10 tests) and one dream
   has run.

## 2026-11-10

The first versioned release. It covers every gist revision so far (`88396d4` first publish, `7716887`,
`72e02c5`) and this release. An install built from any of those revisions has no `spec_version` field. Treat it
as older than `2026-11-10` and apply the breaking items below.

### Changed

- **The owner's ask: implement the designed memory.** Until now promotion, lint, decisions and the smoke test
  existed only on paper. The items below are that build.
- **Capture no longer depends on hooks.** Not every harness has lifecycle hooks. L6 is now optional. Capture runs on a standing
  journal nudge appended to every user message, the orchestrator's turn history, and scheduled ingests. A
  comparison with a hook-based starter kit showed that its value was promotion, which we lacked, not capture,
  which we had. (`7716887`)
- **Promotion layer built: L3 journal to L2 store, nightly.** One extraction call per night, validated, written
  with `sources:` and `said_by:`, logged to `Memory/Promotions/<day>.md`. Dry-run until `promote.apply_after`.
  (`72e02c5`)
- **Lint, decisions and smoke test built.** `memory_lint.py` (no model): dead paths and `verified:` stamps,
  decision records with machine-checkable `reopen_if`, index integrity, a health page. `memory_smoke.py`: fixed
  questions, at least 3 of which must be refused. Five former known gaps closed. (`72e02c5`)
- **Protected files.** Every background job snapshots the agent's identity files (CLAUDE.md, rules) and restores
  them afterwards, so a job that writes memory cannot also rewrite the agent. (`72e02c5`)
- **Lenient front-matter parsing.** 5 of 230 real memories were invisible to strict YAML parsers because of an
  unquoted colon in `description`. `memstore.py` parses them. (`72e02c5`)
- **Versioning (this release).** `Spec version:` line in `README.md` and `ARCHITECTURE.md`, `spec_version` in
  both example configs, this dated changelog, and an Upgrading section in `README.md`.
- **Docs completed (this release).** `harness-memory-format.md` documents the new L2 metadata fields.
  `CLAUDE.md.fragment.md` names the nightly jobs and the version rule. `README.md` lists the PyYAML dependency and
  the `index_promoted.md` shard that promotion needs.

### New files

| File | Since | What it is |
|---|---|---|
| `CHANGELOG.md` | `7716887` | This file |
| `memstore.py` | `72e02c5` | Shared store access: lenient parse, metadata edits, index pointers, lexical recall, switches, model call |
| `memory_promote.py` | `72e02c5` | Nightly L3 to L2 promotion |
| `memory_lint.py` | `72e02c5` | Nightly lint and health page, no model |
| `memory_smoke.py` | `72e02c5` | Weekly answers-and-refusals test |
| `protected_files.py` | `72e02c5` | Snapshot and restore of identity files around background jobs |
| `memory-config.example.json` | `72e02c5` | Config for the four files above |
| `smoke.example.json` | `72e02c5` | Smoke-test question format |

The original 16 files did not change shape. `cue.example.yaml` gained two jobs. No L5 file changed:
`memory.py`, `test_memory.py`, `memory-record.schema.json` and `config.example.json` work as before
(`config.example.json` gained only `spec_version`).

### Breaking

For an install built from `88396d4` (or a partial build of a later revision):

1. **A second config file.** The new jobs read `<AGENT_VAULT>/<AGENT_DIR>/Memory/config.json`, copied from
   `memory-config.example.json`. It is not the L5 store's `config.json` (`$MEMORY_DIR/config.json`). Keep them
   apart. If the new file is missing or unreadable, the jobs treat memory as off and do nothing.
2. **New environment variables.** `AGENT_VAULT` (default `~/Vault`), `AGENT_DIR` (default `Agent`),
   `AGENT_MEMORY_STATE` (default `~/.config/agent-memory`), `AGENT_TZ` (set yours; the default is `UTC` since 2026-11-10.2).
   `AGENT_MEMORY=0` now stops the new jobs too.
3. **New dependency: PyYAML.** `memstore.py` imports it at load.
4. **Create the promoted shard before apply mode.** `Memory/Store/index_promoted.md`, plus a pointer line for it
   in `MEMORY.md`. Without it, apply mode writes memory files it cannot index.
5. **Wrap every background job with `protected_files` before you schedule promotion.** Order matters: the guard
   must exist before the first job that writes memory.
6. **The first lint run writes to existing memory files.** It adds `verified: <date>` to every memory whose paths
   all resolve. Expect one sync diff across most of the store. Run `memory_lint.py --no-write` first to see the
   report without changes.
7. **Set `spec_version: "2026-11-10"`** in both configs, after the README checks for steps 8 and 9 pass.

## Before versioning

Design history, from before the spec had versions. Kept for the reasons behind the design.

| Date | Change | Why |
|---|---|---|
| 2026-11-06 | L5 dream live in one agent | First production run of `memory.py` |
| 2026-11-05 | Added gaps: no `sources:`/`verified:` fields, no `said_by` on L2, no scheduled abstention test, no `reopen_if` decision records | Comparison with a plain-markdown "second brain" that traces every claim to a dated source |
| 2026-10-15 | L1 index split into domain shards | Index back over the load limit |
| 2026-09-09 | Static weighted recall replaced by lexical + adjacency, R as tie-breaker; abstention made a gate | Backtest: the weighted score lost to plain lexical search |
| 2026-09-04 | One store for every account via symlinks; external memory engine rejected | Account rotation forked memory; the engine wanted to be a second system of record |
| 2026-09-03 | Design written | Built-in index over its load limit and silently truncating |
