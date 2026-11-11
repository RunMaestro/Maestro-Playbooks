# Document 3: Install the Memory Layers

## Context

- **Playbook**: Agent Memory
- **Agent**: {{AGENT_NAME}}
- **Project**: {{AGENT_PATH}}
- **Date**: {{DATE}}
- **Working Folder**: {{AUTORUN_FOLDER}}

## Purpose

Put every file in place: tools, configs, store, journal, instructions, rules and search. Nothing here is
scheduled yet and the agent's settings are not touched; document 4 does that. Promotion stays in dry-run.

Execute `{{AUTORUN_FOLDER}}/MEMORY_PLAN.md` as written. If a planned path no longer exists, stop and say so
rather than substituting a guess. Append every command and its exit status to
`{{AUTORUN_FOLDER}}/MEMORY_INSTALL_LOG.md` as you go.

**Every task runs in a fresh session.** Before each task, read `{{AUTORUN_FOLDER}}/MEMORY_PLAN.md` for the real
value of every `<PLACEHOLDER>` in it (paths, ids, slug, commands). Never run a command with a placeholder left in.

## Tasks

### Task 1: Dependencies

- [ ] **Read `{{AUTORUN_FOLDER}}/MEMORY_PLAN.md`.** Then install PyYAML if detection found it missing:

      ```bash
      python3 -m pip install --user pyyaml || python3 -m pip install --user --break-system-packages pyyaml
      python3 -c "import yaml; print('pyyaml', yaml.__version__)"
      ```

      Use the same `python3` the plan names for the schedules. If both installs fail, record the error verbatim,
      finish the file placement, and let document 5 report `PARTIAL`.

### Task 2: Tools and spec

- [ ] **Create the folders and copy the tools**, without overwriting a tool the user has changed:

      ```bash
      mkdir -p "<TOOLS>" "<STORE>" "<JOURNAL>" "<RULES>" "<SPEC>" "<MEMDIR>/Promotions" "<STATE>"
      cd "{{AUTORUN_FOLDER}}/assets"
      for f in memstore.py memory_promote.py memory_lint.py memory_smoke.py protected_files.py run_guarded.py \
               memory_index_check.py claude_md_audit.py link_store.py memory.py cc_sessions.py \
               test_memory.py test_memory_jobs.py qmd-update.sh; do
        if [ -f "<TOOLS>/$f" ] && ! cmp -s "$f" "<TOOLS>/$f"; then cp "$f" "<TOOLS>/$f.new"; echo "kept $f, new copy at $f.new"
        else cp "$f" "<TOOLS>/$f"; echo "installed $f"; fi
      done
      chmod +x "<TOOLS>"/*.py "<TOOLS>/qmd-update.sh"
      cp ARCHITECTURE.md CHANGELOG.md SESSION-FORMAT.md SPEC-README.md harness-memory-format.md \
         memory-record.schema.json "<SPEC>/"
      ```

      A `.new` file means the user edited that tool. Record it; document 6 asks them to diff it. Do not replace
      their version.

- [ ] **Run the shipped tests** before anything depends on the tools:

      ```bash
      cd "<TOOLS>" && python3 test_memory_jobs.py 2>&1 | tail -3 && python3 test_memory.py 2>&1 | tail -3
      ```

      Both must print `all passed`. The tests use temporary folders and stub models; they touch nothing real. A
      failure here is a blocker for scheduling: record it verbatim, and document 4 installs the schedules
      disabled.

### Task 3: Configs, store and seed

- [ ] **Write `<MEMDIR>/config.json`** exactly as planned. In `UPDATE` mode, do not replace the file: add only
      the keys the plan lists as missing, keep every existing value (above all `promote.reviewed` and
      `promote.apply_after`), and leave `spec_version` alone until document 5 has passed. Validate:

      ```bash
      python3 -c "import json,sys; json.load(open(sys.argv[1])); print('config OK')" "<MEMDIR>/config.json"
      ```

- [ ] **Create the store.** Write `<STORE>/MEMORY.md` if it does not exist (a `# Memory Index` heading, then the
      planned pointer lines), `<STORE>/index_promoted.md`, the three seed memories, and `<MEMDIR>/smoke.json`.
      In `UPDATE` mode, append only the missing pointer lines. Check the index:

      ```bash
      python3 "<TOOLS>/memory_index_check.py" "<STORE>"; echo "exit=$?"
      ```

      It must exit 0.

- [ ] **Link the harness memory folder (Claude Code only).** Dry run first, read it, then apply:

      ```bash
      python3 "<TOOLS>/link_store.py" --store "<STORE>" --cwd "{{AGENT_PATH}}" "<CLAUDE_CONFIG_DIR>"
      python3 "<TOOLS>/link_store.py" --store "<STORE>" --cwd "{{AGENT_PATH}}" --apply --backup "<STATE>/backup" "<CLAUDE_CONFIG_DIR>"
      python3 "<TOOLS>/link_store.py" --store "<STORE>" --cwd "{{AGENT_PATH}}" "<CLAUDE_CONFIG_DIR>"
      ```

      The last dry run must print only `ok` lines. Existing memories are backed up, then merged into the store;
      a name clash keeps the store copy and reports the other. After the merge, run the index check again and
      add a pointer line to `MEMORY.md` for every unindexed memory it names.

- [ ] **Create the dream store (L5 ON only):**

      ```bash
      mkdir -p "<DREAM_DIR>" "<SESSIONS>"
      # write <DREAM_DIR>/config.json as planned, then:
      MEMORY_DIR="<DREAM_DIR>" MEMORY_SESSIONS="<SESSIONS>" python3 "<TOOLS>/memory.py" status
      ```

### Task 4: Instructions and rules

- [ ] **Write the instruction block** into `<INSTRUCTIONS>`. Read the file first. If it holds an
      `agent-memory:begin` block, replace the text between the two markers. Otherwise append a blank line and the
      block at the end. Create the file if it does not exist. Then confirm exactly one block exists:

      ```bash
      grep -c "agent-memory:begin" "<INSTRUCTIONS>"
      ```

- [ ] **Write the rules files** `<RULES>/journal.md` and `<RULES>/memory.md` as planned. Then apply the
      rules-folder decision: create the `.claude/rules` symlink, or copy the two files into an existing
      `.claude/rules` folder. Never replace an existing folder with a symlink.

      ```bash
      ls -la "{{AGENT_PATH}}/.claude/rules/"
      python3 "<TOOLS>/claude_md_audit.py" --root "<VAULT>" --claude-md "<INSTRUCTIONS relative to VAULT>" --rules "<AGENT_DIR>/Rules"; echo "exit=$?"
      ```

      A non-zero audit that names only content the user wrote before this install is not a failure of this
      install: record what it found and move on. A finding inside the `agent-memory` block must be fixed now.

- [ ] **Start today's journal**, so the first promotion has something to read and the format has an example.
      Create `<JOURNAL>/{{DATE}}.md` if it does not exist, with a `Summary::` line and one stamped section
      (format in `<RULES>/journal.md`) that records this install: what was installed, where, and that promotion
      is in dry-run until the gate date. If the file exists, append the section and rewrite the `Summary::`
      line; never remove earlier sections.

### Task 5: Search

- [ ] **Install qmd and add the collections (L4 ON only):**

      ```bash
      export PATH="<node dir>:$PATH"; unset BUN_INSTALL
      npx --yes @tobilu/qmd --version || npm install -g @tobilu/qmd
      npx --yes @tobilu/qmd collection add "<JOURNAL>" --name "<slug>-journal"
      npx --yes @tobilu/qmd collection add "<MEMDIR>"  --name "<slug>-memory"
      npx --yes @tobilu/qmd collection add "<TOOLS>"   --name "<slug>-tools"
      # one line per planned content folder:
      npx --yes @tobilu/qmd collection add "<VAULT>/<folder>" --name "<slug>-notes-<folder slug>"
      npx --yes @tobilu/qmd collection list | grep -- "<slug>-"
      ```

      A collection that already exists with the same name and folder is fine. One with the same name and a
      different folder belongs to someone else: stop and record it, because the plan's collision check missed it.

- [ ] **Build the first index:**

      ```bash
      /bin/bash "<TOOLS>/qmd-update.sh" 2>&1 | tail -5
      npx --yes @tobilu/qmd search "memory" -c "<slug>-memory" 2>&1 | head -8
      ```

      The first `embed` downloads local models; allow it several minutes. If it fails, record the error; keyword
      search still works and document 5 reports search as `PARTIAL`.

### Task 6: Log

- [ ] **Finish `{{AUTORUN_FOLDER}}/MEMORY_INSTALL_LOG.md`**: every command in order with its exit status, every
      file created or changed (with "appended", "replaced block" or "new"), every `.new` tool copy, the test
      results, the `link_store.py` output, the index-check result, the audit result, the qmd collections, and
      every failure with its error text verbatim. End with one line: `INSTALL: COMPLETE` or
      `INSTALL: PARTIAL: <what failed>`.
