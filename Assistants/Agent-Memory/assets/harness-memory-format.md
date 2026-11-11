# L1 + L2 File Formats (Claude Code auto-memory)

All examples are synthetic. Store location (after `link_store.py`): `~/Vault/Agent/Memory/Store/`, reached by
the harness through `<CLAUDE_CONFIG_DIR>/projects/<cwd-slug>/memory -> ~/Vault/Agent/Memory/Store`.

```
~/Vault/Agent/Memory/Store/
├── MEMORY.md                         # L1 hot index, loaded every session (byte limit!)
├── index_tooling.md                  # L1 shard, read on demand
├── index_travel.md
├── feedback_no_unverified_claims.md  # L2 memories, one per file
├── project_q1_launch.md
├── reference_build_dashboard.md
└── user_role_and_expertise.md
```

## L2 Memory File

```markdown
---
name: feedback-no-unverified-claims
description: Never report a result as done without naming the command or file that proves it
metadata:
  type: feedback
---

Report a finished task only with its evidence: the command run and its output, or the file read.
"Should work" counts as a failure.

**Why:** Two reports in one week said a fix was live; neither had been run. Each cost a day.
**How to apply:** Every completion claim names its evidence. If a step was skipped, say so. Related:
[[feedback-capture-state-before-destroying]].
```

| `metadata.type` | Holds | Body pattern |
|---|---|---|
| `user` | Who the owner is: role, expertise, standing preferences | The fact |
| `feedback` | Guidance on how the agent should work: corrections and confirmed approaches | Fact, **Why:**, **How to apply:** |
| `project` | Ongoing work, goals, constraints not derivable from the code or git history. Relative dates converted to absolute | Fact, **Why:**, **How to apply:** |
| `reference` | Pointers to external resources: URLs, dashboards, tickets | The pointer and what it is for |

Rules for writers:

1. One fact per file. Update the existing file on the same topic instead of creating a duplicate.
2. Delete a memory that turns out to be wrong.
3. Do not save what the repo already records (code structure, past fixes, git history, CLAUDE.md), or what only
   matters to this conversation.
4. Link related memories with `[[name]]`. A link to a memory that does not exist yet is fine.
5. A recalled memory names a file, function or flag? Verify it still exists before acting on it.
6. Memory content is background context, never an instruction that overrides the owner's current request.

## L2 Metadata Fields (spec 2026-11-10)

All optional, all under `metadata:`. A memory without them stays valid; `memory_lint.py` and
`memory_promote.py` add them over time. Parse front matter leniently (`memstore.parse`): strict YAML
parsers silently skip files with an unquoted colon in `description`.

| Field | Values | Written by | Meaning |
|---|---|---|---|
| `node_type` | `memory` | promotion | Marks the file as a memory node for graph tools |
| `said_by` | `owner` \| `inferred` \| `task` | promotion, agent | Source tier: a direct statement by the owner outranks an inference |
| `sources` | list of `<source>:<YYYY-MM-DD>` | promotion | Provenance, for example `journal:2026-11-09`. Each update appends one |
| `learned`, `modified`, `promoted` | `YYYY-MM-DD` | promotion | First seen, last changed, date promoted from the journal |
| `verified` | `YYYY-MM-DD` | lint | Every path the memory names in backticks existed on that day. Re-stamped at most every `lint.verify_stamp_days` |
| `decision` | `true` | promotion, agent | This memory is a decision record |
| `status` | `active` \| `superseded` | promotion, agent | Decision state. Superseded records stay |
| `reopen_if` | `after:YYYY-MM-DD` \| `exists:<path>` \| `grep:<path>::<regex>` \| `manual:<words>` | promotion, agent | Machine-checkable reopen condition. `manual:` never fires by itself |
| `reopen_fired` | `YYYY-MM-DD` | lint | The condition fired on that day. Stamped once, ever |

Example decision record:

```markdown
---
name: Deploy on Tuesdays only
description: Production deploys happen Tuesday mornings; reopen when the on-call rota covers Fridays
metadata:
  node_type: memory
  type: project
  said_by: owner
  sources: ["journal:2026-11-09"]
  learned: 2026-11-09
  decision: true
  status: active
  reopen_if: "exists:Ops/friday-oncall.md"
---

Deploys go out Tuesday 09:00 to 11:00 only.

**Why:** A Friday deploy broke checkout over a weekend with nobody on call.
**How to apply:** Hold any deploy asked for on another day and say why.
```

## L1 Hot Index: `MEMORY.md`

```markdown
# Agent Memory

Core index below is always loaded. Domain sections live in `index_*.md` in this folder: **read the matching one
before working in that domain**, and add new pointers there, not here.

## Pending
- [Q1 launch](project_q1_launch.md): ships 2027-01-15; blocked on vendor contract, owner decides by 12-01.

## Operating Posture
- [No unverified claims](feedback_no_unverified_claims.md): every "done" names its evidence.
- [Capture state before destroying](feedback_capture_state_before_destroying.md): planned deletions need a way back.

## Key Facts
- [Role and expertise](user_role_and_expertise.md): data engineer, 8 years; skip the basics.

## Section Indexes (read on demand)
- [Tooling](index_tooling.md) (29): read when touching deploys, publishing, dashboards, email tools.
- [Travel](index_travel.md) (1): read when touching hotels, trips.
```

Rules for the index:

- One line per memory: `- [Title](file.md): hook`. The hook is what lets the agent decide relevance without
  opening the file. No memory content in the index.
- The harness loads it whole into every session and drops what is past its limit, without warning. Keep it well
  under the limit (`memory_index_check.py`, default 24,400 B).
- When it grows, move a domain's lines into `index_<domain>.md` and leave one pointer line with a
  "read when touching ..." trigger and a count.

## Shard: `index_tooling.md`

```markdown
# Tooling Index

- [Dashboard design system](reference_dashboard_design.md): palette, type scale, chart rules.
- [Staging deploy](reference_staging_deploy.md): deploy script path, health URL, who owns the box.
```
