"""
protected_files.py: background jobs may not change who the agent is.

A headless job (a Cue run through agent_cue_runner.py) snapshots the identity and
instruction files before it runs. Afterwards any file that changed, appeared or
disappeared is put back exactly as it was, and the change is reported, so a job
can SUGGEST an identity change in its report but never MAKE one.

Decided 2026-11-10 . It lives in the
job runner, not in a harness hook, because not every harness has hooks.

Jobs whose purpose is to edit these files (the monthly CLAUDE.md audit) opt out
with `--allow-protected` on the runner.

Usage:
    snap = snapshot()
    ... run the job ...
    changed = restore(snap)   # list of (relative path, what happened)
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from memstore import AGENT_DIR, VAULT

# Files and globs relative to the vault. Kept short on purpose: this is the
# agent's identity and standing instructions, not everything important.
PROTECTED = [
    f"{AGENT_DIR}/CLAUDE.md",
    f"{AGENT_DIR}/Owner Persona.md",
    f"{AGENT_DIR}/Rules/*.md",
]


def _paths() -> list[Path]:
    out: list[Path] = []
    for spec in PROTECTED:
        if any(c in spec for c in "*?["):
            out.extend(sorted(VAULT.glob(spec)))
        else:
            out.append(VAULT / spec)
    # Resolve symlinks so `.claude/CLAUDE.md -> Agent/CLAUDE.md` is one file.
    seen, uniq = set(), []
    for p in out:
        key = p.resolve() if p.exists() else p
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


def snapshot() -> dict[str, bytes | None]:
    """Bytes of every protected file now (None = did not exist)."""
    snap: dict[str, bytes | None] = {}
    for p in _paths():
        rel = str(p.relative_to(VAULT))
        try:
            snap[rel] = p.read_bytes()
        except FileNotFoundError:
            snap[rel] = None
    # Also record the glob directories' current members, so a NEW rules file a
    # job creates is caught below.
    return snap


def _digest(b: bytes | None) -> str:
    return "absent" if b is None else hashlib.sha256(b).hexdigest()[:12]


def restore(snap: dict[str, bytes | None]) -> list[tuple[str, str]]:
    """Put every protected file back to its snapshot. Returns what was undone."""
    undone: list[tuple[str, str]] = []
    current = {str(p.relative_to(VAULT)) for p in _paths()}
    for rel in sorted(set(snap) | current):
        p = VAULT / rel
        before = snap.get(rel)
        try:
            now = p.read_bytes()
        except FileNotFoundError:
            now = None
        if now == before:
            continue
        try:
            if before is None:
                # The job created a new protected file: move it aside, never delete.
                aside = p.with_name(p.name + ".rejected")
                p.rename(aside)
                undone.append((rel, f"created by job; moved to {aside.name}"))
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                if now is not None:
                    p.with_name(p.name + ".rejected").write_bytes(now)
                p.write_bytes(before)
                what = "deleted by job; restored" if now is None else "edited by job; reverted"
                undone.append((rel, f"{what} ({_digest(now)} -> {_digest(before)}), "
                                    f"job's version kept as {p.name}.rejected"))
        except Exception as e:  # never break the runner over the guard
            undone.append((rel, f"changed by job, restore FAILED: {e}"))
    return undone
