# Document 5: Verify Every Layer

## Context

- **Playbook**: Agent Memory
- **Agent**: {{AGENT_NAME}}
- **Project**: {{AGENT_PATH}}
- **Date**: {{DATE}}
- **Working Folder**: {{AUTORUN_FOLDER}}

## Purpose

Prove each layer works, with a command and its output for every check. These are the spec's own acceptance
checks (`SPEC-README.md` in `ASSETS`, the folder recorded in `MEMORY_DETECT.md`), run against this install.

**This document can run on its own.** After a fix, re-run only this document. If the logs from documents 3 and
4 are absent, recover the paths from `MEMORY_PLAN.md`, or from `<MEMDIR>/config.json` and the Cue file.

Every check that plants a test record removes it afterwards. Record PASS, FAIL or SKIPPED (with the reason) for
each one.

**Every task runs in a fresh session.** Before each task, read `{{AUTORUN_FOLDER}}/MEMORY_PLAN.md` for the real
value of every `<PLACEHOLDER>` in it (paths, ids, slug, commands). Never run a command with a placeholder left in.

## Tasks

### Task 1: Read the logs

- [ ] **Read `MEMORY_PLAN.md`, `MEMORY_INSTALL_LOG.md` and `MEMORY_WIRE_LOG.md`** in `{{AUTORUN_FOLDER}}`. Export
      the environment the jobs use, and use it for every check below:

      ```bash
      export AGENT_VAULT="<VAULT>" AGENT_DIR="<AGENT_DIR>" AGENT_TZ="<TZ>" AGENT_MEMORY_STATE="<STATE>" MAESTRO_AGENT_ID="<id>"
      ```

### Task 2: Tools, store and instructions (L0 to L2)

- [ ] **Tests and index:**

      ```bash
      cd "<TOOLS>" && python3 test_memory_jobs.py 2>&1 | tail -1 && python3 test_memory.py 2>&1 | tail -1
      python3 memory_index_check.py "<STORE>"; echo "exit=$?"
      ```

      PASS: both print `all passed`; the index check exits 0.

- [ ] **The index check catches faults.** Plant a dead pointer and an unindexed file, run the check, remove both:

      ```bash
      echo "- [Ghost](ghost_test.md): planted" >> "<STORE>/MEMORY.md"
      printf -- "---\nname: orphan-test\ndescription: planted\nmetadata:\n  type: reference\n---\nx\n" > "<STORE>/orphan_test.md"
      python3 memory_index_check.py "<STORE>"; echo "exit=$?"
      sed -i '' '/ghost_test.md/d' "<STORE>/MEMORY.md" 2>/dev/null || sed -i '/ghost_test.md/d' "<STORE>/MEMORY.md"
      rm -f "<STORE>/orphan_test.md"
      python3 memory_index_check.py "<STORE>"; echo "exit=$?"
      ```

      PASS: exit 1 naming both, then exit 0 after cleanup.

- [ ] **Residency (Claude Code only; `OWNER` when the owner has not run the apply yet, which is not a failure):**
      the harness memory folder is a symlink to `<STORE>`:

      ```bash
      ls -la "<CLAUDE_CONFIG_DIR>/projects/<cwd-slug>/" | grep memory
      ```

- [ ] **Instructions:** exactly one `agent-memory:begin` block in `<INSTRUCTIONS>`; `.claude/rules` holds
      `journal.md` and `memory.md`, or links to `<RULES>`.

### Task 3: Lint and decisions (L2)

- [ ] **Lint is idempotent.** Run it twice:

      ```bash
      python3 memory_lint.py; python3 memory_lint.py
      ```

      PASS: the second run stamps 0. The health page `<MEMDIR>/🎛️ Memory Health.md` exists.

- [ ] **A decision fires once.** Write a test decision record with `decision: true`, `status: active` and
      `reopen_if: "after:<yesterday>"` as `<STORE>/decision_verify_test.md`, with a pointer line in `MEMORY.md`.
      Run `memory_lint.py` twice. PASS: the first run stamps `reopen_fired` on it, the second does not fire it
      again. Then delete the file and its pointer line, and run `memory_index_check.py` once more (exit 0).

- [ ] **The off switch holds:**

      ```bash
      AGENT_MEMORY=0 python3 memory_lint.py
      AGENT_MEMORY=0 python3 memory_promote.py --dry-run
      ```

      PASS: both print `skipped`.

### Task 4: Promotion (L3 to L2)

- [ ] **Dry-run writes a log, not memories:**

      ```bash
      ls "<STORE>" | wc -l
      python3 memory_promote.py --dry-run --date {{DATE}}; echo "exit=$?"
      ls "<STORE>" | wc -l
      ls "<MEMDIR>/Promotions/"
      ```

      PASS: exit 0, the same store file count before and after, and a `Promotions/{{DATE}}.md` log. Its
      `Sources:` line names each source read, with its size, and each one skipped, with the reason. Today's
      journal holds the install section, so `journal` must be read. A line `EXTRACT failed` means the model call
      failed: run the detection probe from `1_DETECT.md` Task 3 again. `timeline` may be skipped on Maestro CLI older than `1.1.1-RC`; that is not a
      failure. SKIPPED when the plan disabled promotion for lack of a model CLI.

- [ ] **The review gate refuses an explicit apply:**

      ```bash
      ls "<MEMDIR>/Promotions/" | wc -l
      python3 memory_promote.py --apply; echo "exit=$?"
      ls "<MEMDIR>/Promotions/" | wc -l
      ```

      PASS: exit 3 and no new Promotions file.

### Task 5: Smoke test (L2)

- [ ] **Run it verbose:**

      ```bash
      python3 memory_smoke.py -v; echo "exit=$?"
      ```

      PASS: every `expect` question answered by its seed memory and at least 3 correct refusals. If an `expect`
      question misses, the likely cause is wording: lexical recall needs shared words. Reword the question in
      `<MEMDIR>/smoke.json` with words from the memory's title and run again, once. Never weaken a refusal
      question to make it pass. SKIPPED when the plan disabled smoke.

### Task 6: Search (L4)

- [ ] **A journal phrase comes back** (L4 ON only):

      ```bash
      npx --yes @tobilu/qmd search "<a distinctive phrase from today's journal section>" -c "<slug>-journal" | head -10
      npx --yes @tobilu/qmd query "<the same idea in other words>" -c "<slug>-journal" | head -10
      ```

      PASS: today's journal file is in the top 3 of the keyword search. The `query` result is recorded; it needs
      the embeddings from document 3 and is `PARTIAL` if they failed.

### Task 7: Dream (L5)

- [ ] **Dry run, then the switches** (L5 ON only):

      ```bash
      export MEMORY_DIR="<DREAM_DIR>" MEMORY_SESSIONS="<SESSIONS>"
      python3 "<TOOLS>/cc_sessions.py" --projects "<PROJECTS>" --out "<SESSIONS>" --days 7
      python3 "<TOOLS>/memory.py" dream --dry-run | tail -5
      python3 "<TOOLS>/memory.py" freeze && python3 "<TOOLS>/memory.py" dream | tail -2; python3 "<TOOLS>/memory.py" thaw
      AGENT_MEMORY=0 python3 "<TOOLS>/memory.py" show
      python3 "<TOOLS>/memory.py" recall "the name of the owner's boat"
      ```

      PASS: the dry run writes nothing; the frozen dream prints `skipped`; the switched-off `show` prints
      `memory is switched off`; the recall returns `[]`. If all pass and `<SESSIONS>` holds past days, run
      `python3 "<TOOLS>/memory.py" backfill` once, so the first nightly dream does not start from nothing.

### Task 8: Capture and schedules

- [ ] **Capture is wired:** `show agent <id> --json` shows the memory line once in the nudge and once in the
      new-session message (or the plan recorded `[UPDATE_AGENT_MESSAGES]` = `no`).

- [ ] **Schedules are live:** `maestro-cli cue list --json` lists every planned `<slug>-memory-*` subscription,
      enabled, for this agent; `cue activity` shows the runs document 4 triggered, with no failure; the review
      reminder is in `cue schedule --list`.

- [ ] **The guard holds.** Prove the wrapper reverts an identity edit:

      ```bash
      python3 "<TOOLS>/run_guarded.py" -- /bin/sh -c 'echo "guard test" >> "<INSTRUCTIONS>"'
      tail -1 "<INSTRUCTIONS>"
      rm -f "<INSTRUCTIONS>.rejected"
      ```

      PASS: the wrapper prints `guard: ... edited by job; reverted`, and the last line of `<INSTRUCTIONS>` is
      not `guard test`.

### Task 9: Stamp the version and write the verdict

- [ ] **Stamp `spec_version`** in `<MEMDIR>/config.json` (and `<DREAM_DIR>/config.json`) to the version in
      `assets/ARCHITECTURE.md`, and only if Tasks 2 to 5 passed. Set it last, so it never claims a version whose
      checks did not pass.

- [ ] **Write `{{AUTORUN_FOLDER}}/MEMORY_VERIFY.md`**: one row per check with PASS, FAIL or SKIPPED, the command,
      and the output line that decided it. End with one verdict:

      | Verdict | Meaning |
      |---|---|
      | `VERIFIED` | Every check that applies passed |
      | `VERIFIED-WITH-GAPS` | Every check that ran passed; some layers SKIPPED by plan (name them and why) |
      | `PARTIAL` | A check failed. Name it and the single fix |
      | `FAILED` | Tests, the index check or the lint failed: the store is not safe to schedule against |

      On `FAILED`, disable every `<slug>-memory-*` subscription now (`maestro-cli cue disable <name>`) and say so.
