# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This repository contains **playbooks for [Maestro](https://github.com/pedramamini/Maestro) Auto Run**. Playbooks automate multi-step code improvement workflows through looping document chains processed by AI agents.

## What is Maestro Auto Run?

Auto Run is Maestro's file-system-based task automation system that batch-processes markdown checklists through AI agents. Key characteristics:

- **Document-driven**: Each markdown file contains task checkboxes (`- [ ]`) that agents complete
- **Session isolation**: Each task executes in a fresh AI session with clean context
- **Loop support**: Playbooks can cycle back to the first document after completion
- **Reset on Completion**: Documents can auto-uncheck their tasks for repeatable execution

For more information, see the [Maestro documentation](https://github.com/pedramamini/Maestro).

## Playbook Design Philosophy

**Playbook design is context engineering.** Each document in a playbook chain is a carefully crafted prompt that provides exactly the right context at the right time.

### Progressive Disclosure

The core principle: **reveal information incrementally, not all at once.**

AI agents perform best when given focused, relevant context rather than overwhelming amounts of information. Playbooks implement progressive disclosure by:

1. **Staged discovery**: Document 1 surveys broadly, Document 2 identifies specifics, Document 3 evaluates priorities
2. **Generated artifacts**: Each stage produces files that the next stage reads, carrying forward only what's relevant
3. **Loop-scoped context**: Each iteration works with a focused subset (one item from the plan), not the entire backlog
4. **Fresh sessions**: Session isolation prevents context pollution—each task starts clean and loads only what it needs

### Front-Load the Hard Work

The expensive token-consuming work—exploring the codebase, gathering context, making decisions—happens in the **early documents** (1-3). These produce detailed, well-separated task documents that later stages can execute cheaply.

**The two-phase pattern:**

```
Phase 1: Discovery & Planning (token-heavy)
├── Document 1: Broad survey, identify scope
├── Document 2: Deep investigation, find specifics
├── Document 3: Evaluate and prioritize candidates
└── Output: LOOP_N_PLAN.md with detailed implementation steps

Phase 2: Execution (token-light)
├── Document 4: Execute ONE item from the plan
└── Document 5: Check progress, loop if needed
```

When looping, the cycle returns to Phase 1, which re-surveys the (now changed) codebase and produces a fresh plan for the next iteration. Each loop is self-contained: discover → plan → execute → check.

**Why this matters:**
- Execution tasks read pre-computed context from `LOOP_N_*.md` files instead of re-exploring
- Each implementation step has clear, specific instructions written during planning
- Failed or blocked items don't pollute the next iteration—fresh discovery catches the current state

### Why This Matters

Without progressive disclosure, agents face:
- **Context overload**: Too much information degrades decision quality
- **Attention diffusion**: Important details get lost in noise
- **Token waste**: Irrelevant context consumes capacity that could be used for reasoning

With progressive disclosure:
- **Focused attention**: Each document addresses one concern with relevant context
- **Better decisions**: Agents reason more effectively with curated information
- **Efficient execution**: Less context = faster processing, lower costs

### Designing for Progressive Disclosure

When creating or editing playbooks:
- **Front-load discovery, back-load action**: Early documents gather and filter; later documents execute
- **Use intermediate files**: Write `LOOP_N_*.md` files to pass curated context between stages
- **One decision per document**: Don't combine analysis with implementation
- **Explicit context sections**: Each document's Context block should state exactly what the agent needs to know
- **Detailed task artifacts**: Planning documents should produce specific, actionable implementation steps—not vague directives

## How Auto Run Playbooks Work

### Execution Flow

1. Maestro processes documents in order (1 -> 2 -> 3 -> 4 -> 5)
2. Each document's tasks run in isolated AI sessions
3. Document 5 (progress gate) evaluates exit conditions
4. If work remains, document 5 resets documents 1-4 and the loop continues
5. If exit conditions are met, document 5 does NOT reset, and the pipeline exits

### The Reset Mechanism

The loop control relies on selective resetting:
- **Documents 1-4**: `Reset: OFF` - They stay completed unless explicitly reset
- **Document 5**: `Reset: ON` - Always resets itself, conditionally resets 1-4

When document 5 checks its reset tasks:
- If reset tasks are checked -> Documents 1-4 get reset -> Loop continues
- If reset tasks are unchecked -> Nothing resets -> Pipeline exits

### Template Variables

Maestro substitutes these at runtime:

| Variable | Description |
|----------|-------------|
| `{{AGENT_NAME}}` | Name of the Maestro agent |
| `{{AGENT_PATH}}` | Root path of the target project |
| `{{AUTORUN_FOLDER}}` | Path to the Auto Run folder |
| `{{LOOP_NUMBER}}` | Current loop iteration (1, 2, 3...) |
| `{{DATE}}` | Today's date (YYYY-MM-DD) |
| `{{CWD}}` | Current working directory |
| `{{GIT_BRANCH}}` | Current git branch |

## Working with Playbooks

When editing playbooks:
- Preserve the markdown task checkbox format (`- [ ]`) as it drives automation
- Keep the Context section with `{{VARIABLE}}` placeholders intact
- Maintain document chain references (e.g., `LOOP_{{LOOP_NUMBER}}_PLAN.md`)
- Each playbook's README.md contains specific configuration details

### Assets Folder Convention

Playbooks can include non-markdown assets in an `assets/` subfolder:
- Configuration templates (YAML, JSON, TOML)
- Dockerfiles and container configurations
- Helper scripts
- Schema definitions (OpenAPI, JSON Schema)
- Reference data files

Reference assets using `{{AUTORUN_FOLDER}}/assets/filename`. Maestro copies the entire playbook folder (including assets/) when installing from the Exchange.

**Exchange-only feature.** The `assets/` folder is bundled only for playbooks PR'd to this repository and installed via the in-app Playbook Exchange. Maestro's user-share / peer-to-peer flows transport only the markdown documents and drop `assets/`. If a playbook depends on bundled files, it must be contributed here via PR (see [CONTRIBUTING.md](CONTRIBUTING.md)).

### Outer Prompt Convention

The manifest's `prompt` field pre-fills the Auto Run panel when a user installs a playbook from the Exchange. Use it to surface per-run configuration variables (thresholds, targets, scopes, URLs) instead of hardcoding them in task documents.

**When to lift a variable:** lift values the user would reasonably tune per run AND that are not auto-detectable. Don't lift values inferable from the codebase or workflow constants that define the playbook's shape.

**Keep the configuration lines machine-readable.** Each value is one line, `**VAR_NAME:** `value``, and Maestro's Launch flow rewrites the value inside the backticks with the user's answer (see "Launch Support" in CONTRIBUTING.md). Do not split a value over lines or put a backtick inside it. When a playbook has a `launch` block, every input in it must match one of these lines. Run `node scripts/validate-manifest.mjs` after any manifest change.

**Template structure:**

```markdown
# {Playbook Name} Agent Prompt

**IMPORTANT: Configure the placeholders below before running this playbook.**

## Configuration

### {Group}

<!-- CONFIGURE: {description} -->
**{VARIABLE_NAME}:** `{default}`

<!-- Examples:
- {example}
-->

## Agent Instructions
{Generic context.}
```

**Naming and references:**

- `UPPER_SNAKE_CASE` variable names — `AUTO_FIX_SEVERITY`, `COVERAGE_TARGET`, `PR_URL`
- In task docs, use `[VARIABLE_NAME]` (square brackets) as the substitution placeholder
- Add an early task in each consuming doc: "Read the agent prompt for [VAR_X] and [VAR_Y]"

`Research/Market` is the canonical reference implementation.

### Critical Design Considerations

1. **One task per document step**: Each document should do ONE thing, then stop. This allows proper loop iteration.

2. **Session isolation awareness**: Each task runs in a fresh session. Don't rely on information from previous tasks being "remembered" - read it from generated files instead.

3. **Exit condition clarity**: Document 5 must have unambiguous logic for when to reset vs. when to exit.

4. **Incremental progress**: Playbooks should make small, verifiable changes per loop iteration rather than large batch changes.

### Common Pitfalls to Avoid

These patterns cause subtle bugs that are hard to diagnose:

#### 1. Early Exit on Empty States

**Problem:** If a discovery step finds nothing, downstream steps have nothing to process, and the progress gate may exit prematurely—even when more discovery work remains.

**Solution:** Track exhaustion explicitly. Use markers like `## ALL_TACTICS_EXHAUSTED` to signal when discovery is truly complete. The progress gate should check BOTH:
- Are there pending items to process?
- Is discovery complete?

Only exit when both conditions indicate no work remains.

#### 2. Wasteful Re-Analysis

**Problem:** When loops reset documents 1-4, document 1 re-runs its full analysis even though artifacts from the previous iteration still exist.

**Solution:** Add skip logic to discovery tasks:
```markdown
- [ ] **Survey codebase (if needed)**: First check if `GAME_PLAN.md`
      already exists with content. If yes, skip this task. If no,
      perform the survey...
```

#### 3. Missing Graceful Empty-State Handling

**Problem:** Tasks assume their input files exist and have content. When a previous step produced nothing, the task fails or behaves unexpectedly.

**Solution:** Every task should handle the "nothing to do" case explicitly:
```markdown
- [ ] **Evaluate one candidate (or skip if empty)**: Read CANDIDATES.md.
      If it contains no findings OR all findings are already evaluated,
      mark this task complete without changes. Otherwise...
```

#### 4. Progress Gate Checks Only One Condition

**Problem:** The progress gate checks for PENDING items but ignores whether discovery is complete. If a tactic finds nothing, there are no PENDING items, so the loop exits—leaving other tactics unexecuted.

**Solution:** The progress gate should continue if EITHER:
- There are PENDING items to implement, OR
- Discovery is not yet exhausted (more tactics/searches to run)

```
CONTINUE if: PENDING items exist OR discovery not exhausted
EXIT if: No PENDING items AND discovery is exhausted
```

#### 5. Ambiguous Loop State in Filenames

**Problem:** Using `LOOP_{{LOOP_NUMBER}}_*.md` creates new files each loop iteration. If the design intent is to accumulate state across loops, this orphans previous work. If the intent is fresh-analysis-each-loop, this is fine but wasteful.

**Recommendation:** Be explicit about the design choice:
- **Accumulate across loops**: Use static names like `PERF_PLAN.md`
- **Fresh each loop**: Use `LOOP_{{LOOP_NUMBER}}_*.md` but ensure document 1 always creates new content

See README.md for available playbooks and usage instructions.
