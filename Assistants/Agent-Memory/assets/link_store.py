#!/usr/bin/env python3
"""Make one memory store the system of record for every Claude config dir (memory layer L2 residency).

The harness keys auto-memory on (config dir) x (project cwd):  <CLAUDE_CONFIG_DIR>/projects/<cwd-slug>/memory/
If an agent rotates between accounts (several CLAUDE_CONFIG_DIRs), its memory forks every time the account flips.
This script points each of those paths at one store (for example a folder inside your notes vault), so every
account reads and writes the same files and the store can be synced, versioned and linked like any other note.

Dry run by default. With --apply, for each config dir:
  1. backs up the existing memory dir to <backup>/<config-name>/ (copy, never move)
  2. merges its files into the store (an existing store file with the same name is kept; the other copy is
     reported, never overwritten)
  3. replaces the memory dir with a symlink to the store

Rollback: delete the symlink and copy the backup back. The harness never knows either way.

Usage:
  link_store.py --store ~/Vault/Agent/Memory/Store --cwd ~/Vault ~/.claude ~/.claude-work
  link_store.py --store ... --cwd ... --apply --backup ~/memory-backups ~/.claude ~/.claude-work
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path


def cwd_slug(cwd: Path) -> str:
    """The harness's project key: the absolute cwd with every '/' (and '.') turned into '-'."""
    return str(cwd.resolve()).replace("/", "-").replace(".", "-")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config_dirs", nargs="+", type=Path)
    ap.add_argument("--store", required=True, type=Path)
    ap.add_argument("--cwd", required=True, type=Path, help="the agent's working directory")
    ap.add_argument("--backup", type=Path, default=Path.home() / "memory-backups")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    store = a.store.expanduser().resolve()
    slug = cwd_slug(a.cwd.expanduser())
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if a.apply:
        store.mkdir(parents=True, exist_ok=True)
    rc = 0
    for cfg in a.config_dirs:
        mem = cfg.expanduser() / "projects" / slug / "memory"
        if mem.is_symlink():
            ok = mem.resolve() == store
            print(f"{'ok  ' if ok else 'WARN'} {mem} -> {mem.resolve()}{'' if ok else ' (points elsewhere)'}")
            rc |= 0 if ok else 1
            continue
        files = sorted(p for p in mem.glob("*") if p.is_file()) if mem.is_dir() else []
        clash = [p.name for p in files if (store / p.name).exists()]
        print(f"plan {mem}: {len(files)} file(s) to merge, {len(clash)} name clash(es) kept as-is, then symlink")
        for c in clash:
            print(f"     clash: {c} (store copy wins; other copy stays in the backup)")
        if not a.apply:
            continue
        if mem.is_dir():
            dest = a.backup.expanduser() / stamp / cfg.expanduser().name
            shutil.copytree(mem, dest)
            for p in files:
                if p.name not in clash:
                    shutil.copy2(p, store / p.name)
            shutil.rmtree(mem)
            print(f"     backed up to {dest}")
        mem.parent.mkdir(parents=True, exist_ok=True)
        mem.symlink_to(store, target_is_directory=True)
        print(f"     linked {mem} -> {store}")
    if not a.apply:
        print("dry run: nothing changed. Re-run with --apply.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
