# Document 4: Fan In — Index and Synthesize

## Context

- **Playbook**: Corpus Synthesis
- **Agent**: {{AGENT_NAME}}
- **Project**: {{AGENT_PATH}}
- **Date**: {{DATE}}
- **Working Folder**: {{AUTORUN_FOLDER}}
- **Loop**: {{LOOP_NUMBER}}

## Purpose

Two jobs, and which one you do depends on whether the corpus is exhausted:

- **Every loop** — keep `INDEX.md` current so a half-finished corpus is still
  navigable. Cheap, incremental, mechanical.
- **Final loop only** — the cross-cutting synthesis: thematic tracks, the
  metrics table, the curated shortlist. This is the reason the corpus was built
  and it is the one part that genuinely needs to see everything at once.

## Tasks

### Task 1: Read state

- [ ] **Read `{{AUTORUN_FOLDER}}/CORPUS_MANIFEST.md`.** Count `PENDING`,
      `PROCESSED`, `FAILED`, `SKIP`. Record whether any `PENDING` items remain —
      that single fact decides which half of this document runs.

### Task 2: Update the running index (every loop)

- [ ] **Write or update `[OUTPUT_FOLDER]/INDEX.md`** with one row per
      `PROCESSED` item: number, wiki-linked title, author/speaker, and a
      one-line key point lifted from that synopsis's Thesis section.

      Keep a coverage line at the top: `N of M processed · K skipped · J failed`.
      Someone opening this file mid-run should be able to tell instantly how far
      along it is.

### Task 3: Stop here if work remains

- [ ] **Defer the synthesis if the corpus is not exhausted**: if any items are
      still `PENDING`, mark the remaining tasks in this document complete without
      doing them and stop. The synthesis is expensive and it is wrong when it
      runs on a partial corpus — themes drawn from the first sixteen of sixty
      items are an artifact of manifest order, not a finding.

### Task 4: Write the synthesis (final loop only)

- [ ] **Read every synopsis in `[OUTPUT_FOLDER]`** — the synopses, not the raw
      transcripts. That is the whole economy of this playbook: the expensive
      reading already happened once, in parallel, and produced these files.

- [ ] **Write `[OUTPUT_FOLDER]/SYNTHESIS.md`** through the lens of
      `[ANALYTICAL_LENS]` (read it from `CORPUS_CONFIG.md`):

      ```markdown
      ---
      type: synthesis
      corpus: "<corpus name>"
      items: <n>
      created: {{DATE}}
      ---

      # <Corpus name>: Synthesis

      ## The through-line
      One paragraph. If the whole corpus is making one argument, state it. If it
      is not, say that instead — a forced thesis is worse than an honest "these
      are three unrelated conversations."

      ## Themes
      3-8 themes. Each: a claim, the items that support it (wiki-linked), and
      the strongest single piece of evidence. A theme backed by one item is not
      a theme; call it an outlier and move on.

      ## By the numbers
      | What | Number | Source |
      Every figure wiki-linked to the item that stated it. No number appears
      here that you cannot point at in a synopsis.

      ## Disagreements
      Where items contradict each other. This section is usually the most
      valuable one and it is the one a per-item pass structurally cannot produce.

      ## What to read first
      A ranked shortlist of 5, each with one line on why.

      ## Gaps
      What the corpus does not cover, and what was skipped or failed (from the
      manifest). State it plainly — a corpus with holes that names them is more
      useful than one that reads as complete.
      ```

- [ ] **Link the synthesis from the index**: add a prominent link to
      `SYNTHESIS.md` at the top of `INDEX.md`.

### Task 5: Surface the result

- [ ] **Open the synthesis in Maestro** so the user sees it without hunting for
      a path:

      ```bash
      maestro-cli open-file "<OUTPUT_FOLDER>/SYNTHESIS.md" || \
        {{MAESTRO_CLI_PATH}} open-file "<OUTPUT_FOLDER>/SYNTHESIS.md"
      ```

      If neither command is available, skip this quietly — it is a convenience,
      not a requirement. Either way, print the absolute path to `SYNTHESIS.md`
      and to `INDEX.md` in your final message.
