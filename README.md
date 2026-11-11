# Maestro-Playbooks

Playbooks for [RunMaestro.ai](https://github.com/pedramamini/Maestro) Agent Orchestrator.

## What Are Playbooks?

Playbooks are saved Auto Run configurations that automate multi-step workflows. Each playbook defines a sequence of markdown documents with task checkboxes that Maestro processes through AI agents, looping until exit conditions are met.

## Available Playbooks

### Assistants Playbooks

One-shot setup workflows that install personal-AI frameworks into a fresh agent.

| Playbook | Purpose | Exit Condition |
|----------|---------|----------------|
| `Assistants/LifeOS-Setup/` | Install Daniel Miessler's LifeOS (formerly PAI) — the AI-powered Life Operating System — onto a Claude Code or other agent | All 5 documents completed (no loop) |
| `Assistants/Message-Bus/` | Put your agent on the other end of your iMessage threads via a Cue-scheduled scanner (macOS) | All 5 documents completed (no loop) |
| `Assistants/Voice-Journal/` | Append Apple's on-device Voice Memos transcripts to a daily markdown journal (macOS) | All 5 documents completed (no loop) |
| `Assistants/Agent-Memory/` | Give an agent a self-maintaining long-term memory: per-turn journal capture via the nudge message, a fact store, qmd search, nightly promotion and lint, a weekly smoke test, scheduled with Cue | All 6 documents completed (no loop) |

### Development Playbooks

Code improvement workflows that work with Maestro's **default agent prompt**.

| Playbook | Purpose | Exit Condition |
|----------|---------|----------------|
| `Development/Best-PR/` | Compare two competing PRs, pick winner, extract gems | All 5 documents completed (no loop) |
| `Development/Documentation/` | Achieve 90% doc coverage | Coverage >=90% or no HIGH importance gaps |
| `Development/Mobile-Polish/` | Make React sites mobile-friendly | No PENDING items remain |
| `Development/Performance/` | Find and fix performance issues | No PENDING items remain |
| `Development/Refactor/` | Simplify code, eliminate duplication | No LOW risk + HIGH benefit items |
| `Development/Security/` | Audit and remediate vulnerabilities | No CRITICAL/HIGH severity issues |
| `Development/Testing/` | Achieve 80% test coverage | Coverage >=80% or no auto-testable work |
| `Development/Usage/` | Update README to match actual features | No CRITICAL/HIGH importance gaps |

### Research Playbooks

Knowledge-building workflows that require **custom agent prompts** with user configuration.

| Playbook | Purpose | Exit Condition |
|----------|---------|----------------|
| `Research/Corpus/` | Turn a playlist, folder, or URL list into an interlinked knowledge base with a cross-cutting synthesis | Nothing pending, extraction complete, and synthesis written |
| `Research/Market/` | Build Obsidian-style knowledge vault about a market | Coverage targets met or no HIGH importance entities remain |

## Design Philosophy: Context Engineering

**Playbook design is context engineering.** Each document is a prompt engineered to provide exactly the right information at the right time.

### Progressive Disclosure

The core principle: **reveal information incrementally, not all at once.**

AI agents perform best with focused, relevant context—not information overload. Playbooks achieve this through staged discovery, where each document produces artifacts that carry forward only what's relevant to the next stage.

### Front-Load the Hard Work

The expensive token-consuming work happens **upfront** in the early documents. These produce detailed, well-separated task documents that later stages execute cheaply.

```
Phase 1: Discovery & Planning (token-heavy)
├── Documents 1-3: Explore, investigate, evaluate
└── Output: LOOP_N_PLAN.md with detailed implementation steps

Phase 2: Execution (token-light)
├── Document 4: Execute ONE item from the plan
└── Document 5: Check progress, loop if needed
        ↓
    (loop back to Phase 1 if work remains)
```

**Each loop iteration is self-contained:** discover → plan → execute → check. When looping, Phase 1 re-surveys the (now changed) codebase and produces a fresh plan. Failed items don't pollute the next iteration.

### Why This Matters

- **Focused attention** beats scattered attention
- **Curated context** produces better decisions than raw dumps
- **Less context** = faster execution, lower costs, better reasoning
- **Detailed task artifacts** enable cheap execution—agents read pre-computed context instead of re-exploring

When creating playbooks, design each document to answer: *"What is the minimum context this agent needs to complete this specific task?"*

## Playbook Architecture

Each playbook follows a 5-document chain pattern (with optional initialization):

```
0_INITIALIZE.md  -> (Optional) One-time setup, create folder structure/agents
1_ANALYZE.md     -> Survey target, identify what to research/fix
2_FIND_*.md      -> Find specific issues/gaps/entities
3_EVALUATE.md    -> Rate candidates by priority criteria
4_IMPLEMENT.md   -> Execute one item (fix code or research entity)
5_PROGRESS.md    -> Loop gate: resets 1-4 if work remains, exits if done
```

### Loop Control Mechanism

- Document 0 (if present) has `Reset: OFF` and runs once at the start
- Documents 1-4 have `Reset: OFF` (don't auto-reset when completed)
- Document 5 has `Reset: ON` and controls the loop by conditionally resetting 1-4
- Each loop iteration creates `LOOP_N_*` working files with incremented loop number

### Agent Prompt Requirements

- **Development playbooks**: Use Maestro's default agent prompt
- **Research playbooks**: Require custom `Agent-Prompt.md` with user configuration (see playbook README)

### Assets Folder Convention

> **Exchange-only feature.** Bundled `assets/` are supported only for playbooks submitted to this repository and installed via the in-app Playbook Exchange. They are **not** carried by Maestro's peer-to-peer share links or copy-between-machines flows—those only transport the markdown documents. If your playbook needs supporting files, contribute it here via PR (see [CONTRIBUTING.md](CONTRIBUTING.md)).

Playbooks can include non-markdown assets (config files, YAML, Dockerfiles, templates, etc.) in an `assets/` subfolder:

```
Category/
└── YourPlaybook/
    ├── README.md
    ├── 1_ANALYZE.md
    ├── ...
    └── assets/           # Optional: bundled configuration files (Exchange installs only)
        ├── config.yaml
        ├── Dockerfile
        └── template.json
```

When installing playbooks from the Exchange, Maestro copies the entire playbook folder—including the `assets/` subfolder. Reference assets in your playbook documents using the `{{AUTORUN_FOLDER}}/assets/` path:

```markdown
- [ ] Read the config template from `{{AUTORUN_FOLDER}}/assets/config.yaml`
```

Use cases for assets:
- **Configuration templates**: Pre-configured YAML, JSON, or TOML files
- **Docker/container files**: Dockerfiles, docker-compose.yml
- **Scripts**: Helper shell scripts, Python utilities
- **Schema definitions**: OpenAPI specs, JSON schemas
- **Reference data**: Lookup tables, mapping files

## Status Values

Items in `LOOP_N_PLAN.md` use these statuses:

| Status | Meaning |
|--------|---------|
| `PENDING` | Ready for automated implementation/research |
| `IMPLEMENTED` / `RESEARCHED` | Completed in current loop |
| `WON'T DO` / `SKIP` | Skipped intentionally (with reason) |
| `PENDING - MANUAL REVIEW` | Requires human decision |

## Using These Playbooks

### Setup in Maestro

1. Open Maestro and select Auto Run mode
2. Choose a playbook folder (e.g., `Development/Performance/`)
3. **For Research playbooks**: Configure `Agent-Prompt.md` with your target topic
4. Configure settings:
   - **Loop Mode**: ON (for continuous iteration)
   - **Max Loops**: Set a reasonable limit (5-10 for Development, 20-30 for Research)
   - Documents 1-4: `Reset: OFF`
   - Document 5: `Reset: ON`

### Review-First Approach (Recommended)

1. Run once with Loop Mode OFF
2. Review the generated `LOOP_1_PLAN.md`
3. Manually adjust statuses if needed:
   - Change `PENDING` to `WON'T DO` / `SKIP` to skip items
   - Change to `PENDING - MANUAL REVIEW` for risky items
4. Run again with Loop Mode ON

### Template Variables

These variables are substituted by Maestro at runtime:

| Variable | Description |
|----------|-------------|
| `{{AGENT_NAME}}` | Name of the Maestro agent |
| `{{AGENT_PATH}}` | Root path of the target project |
| `{{AUTORUN_FOLDER}}` | Path to the Auto Run folder |
| `{{LOOP_NUMBER}}` | Current loop iteration (1, 2, 3...) |
| `{{DATE}}` | Today's date (YYYY-MM-DD) |
| `{{CWD}}` | Current working directory |

## Customization

### Adjusting Aggressiveness

Edit `4_IMPLEMENT.md` in any playbook to change which items get auto-processed:

- Default: LOW complexity/risk + HIGH gain/benefit only
- More aggressive: Include MEDIUM complexity
- Conservative: Require VERY HIGH gain

### Adding Custom Tactics

Edit `1_ANALYZE.md` to add domain-specific investigation patterns.

### Creating New Playbooks

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide to creating and submitting playbooks to the exchange.

Quick overview:

1. Create a folder in `Category/Subcategory/` format
2. Add README.md and documents 1-5 (optionally 0)
3. Add your entry to `manifest.json`
4. Submit a pull request

## Tips

1. **Start without loop mode** - Review what it finds before enabling automation
2. **Set max loops** - Prevent runaway iterations
3. **Check the logs** - Each playbook maintains a cumulative log file
4. **Commit frequently** - Each loop iteration is a good commit point
5. **Run tests** - After Development playbook changes, verify nothing broke

## Contributing

This repository powers the Maestro in-app Playbook Exchange. We welcome community contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on creating and submitting new playbooks.

## License

See [LICENSE](LICENSE) for details.
