#!/usr/bin/env python3
"""run_guarded.py: run one background memory job inside the protected-files guard (README step 8).

Every scheduled memory job runs through this wrapper:

    AGENT_VAULT=<vault> AGENT_DIR=<agent folder> python3 run_guarded.py -- python3 memory_promote.py

Before the job: snapshot the agent's identity and instruction files.
After the job, whatever its outcome: restore any changed or deleted file, move aside any new one, keep the job's
version as <name>.rejected, and print one line per undo. The job's exit code is passed through.

Protected files are vault-relative globs. They come from, in order:
  1. env AGENT_PROTECTED (colon-separated)
  2. "protected" (a list) in <AGENT_VAULT>/<AGENT_DIR>/Memory/config.json
  3. the defaults below
`--allow-protected` runs the job with no guard, for a job whose purpose is to edit those files.

Standard library only, plus protected_files.py and memstore.py next to this file.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import memstore  # noqa: E402  (reads AGENT_VAULT / AGENT_DIR)
import protected_files  # noqa: E402

DEFAULTS = [
    "CLAUDE.md",
    "AGENTS.md",
    ".claude/rules/*.md",
    "{agent}/CLAUDE.md",
    "{agent}/AGENTS.md",
    "{agent}/Owner Persona.md",
    "{agent}/Rules/*.md",
]


def protected_list() -> list[str]:
    env = os.environ.get("AGENT_PROTECTED", "").strip()
    if env:
        return [p for p in env.split(":") if p]
    try:
        cfg = json.loads(memstore.CONFIG.read_text())
        listed = cfg.get("protected")
        if isinstance(listed, list) and listed:
            return [str(p) for p in listed]
    except Exception:
        pass
    return [p.format(agent=memstore.AGENT_DIR) for p in DEFAULTS]


def main(argv: list[str]) -> int:
    allow = "--allow-protected" in argv
    argv = [a for a in argv if a != "--allow-protected"]
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    if not argv:
        print("usage: run_guarded.py [--allow-protected] -- <command> [args...]", file=sys.stderr)
        return 2
    if allow:
        return subprocess.call(argv)

    protected_files.PROTECTED = protected_list()
    snap = protected_files.snapshot()
    code = 1
    try:
        code = subprocess.call(argv)
    finally:
        undone = protected_files.restore(snap)
        for rel, what in undone:
            print(f"guard: {rel}: {what}")
        if undone:
            print(f"guard: {len(undone)} protected file(s) put back after: {' '.join(argv)}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
