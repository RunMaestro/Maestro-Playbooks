#!/usr/bin/env python3
"""Check the harness memory store and its hot index (memory layers L1 + L2). Read-only, no model calls.

The harness loads MEMORY.md into every session and silently drops whatever is past its load limit. That is
forgetting with no policy and no log, so this check fails loudly before it happens.

Checks:
  budget    MEMORY.md over --max-bytes (or --max-lines, if your harness truncates by line)
  pointer   an index line `[Title](file.md)` whose file does not exist
  unindexed a memory file no index (MEMORY.md or a shard index_*.md) points at
  shard     a shard index_*.md that MEMORY.md does not point at (unreachable)
  front     a memory file without name / description / type front matter
  link      a [[slug]] inside a memory that matches no memory's name (reported, not failed: a dangling link
            marks something worth writing later)

Usage:
  memory_index_check.py ~/.claude/projects/<project-slug>/memory          # human report, exit 1 on failure
  memory_index_check.py <store> --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PTR = re.compile(r"\]\(([^)\s]+\.md)\)")
WIKI = re.compile(r"\[\[([^\]|#]+)")


def front(text: str) -> dict:
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    out: dict = {}
    if not m:
        return out
    for ln in m.group(1).splitlines():
        k, sep, v = ln.strip().partition(":")
        if sep:
            out[k.strip()] = v.strip()
    return out


def check(store: Path, max_bytes: int, max_lines: int) -> dict:
    fails, notes = [], []
    index = store / "MEMORY.md"
    if not index.exists():
        return {"fails": [{"kind": "budget", "detail": f"no MEMORY.md in {store}"}], "notes": [], "stats": {}}
    idx_text = index.read_text()
    size, lines = len(idx_text.encode()), idx_text.count("\n") + 1
    if size > max_bytes:
        fails.append({"kind": "budget", "detail": f"MEMORY.md {size} B > {max_bytes} B: the tail will not load"})
    if max_lines and lines > max_lines:
        fails.append({"kind": "budget", "detail": f"MEMORY.md {lines} lines > {max_lines}"})

    shards = sorted(store.glob("index_*.md"))
    # G28: a shard may live outside the store (promote.promoted_shard), so MEMORY.md points at it with a
    # relative path such as ../index_promoted.md. Shard pointers resolve against the file that holds them;
    # memory pointers name a file in the store by its basename, as the harness reads them.
    in_store = {s.resolve() for s in shards}
    for t in PTR.findall(idx_text):
        p = (index.parent / t).resolve()
        if Path(t).name.startswith("index_") and p.exists() and p not in in_store:
            shards.append(p)
            in_store.add(p)
    indexed: set[str] = set()
    for f in [index, *shards]:
        for target in PTR.findall(f.read_text()):
            name = Path(target).name
            if name.startswith("index_"):
                ok = (f.parent / target).resolve().exists()
            else:
                indexed.add(name)
                ok = (store / name).exists()
            if not ok:
                fails.append({"kind": "pointer", "detail": f"{f.name} -> {target} (missing)"})
    reachable = {(index.parent / t).resolve() for t in PTR.findall(idx_text)}
    for s in shards:
        if s.resolve() not in reachable:
            fails.append({"kind": "shard", "detail": f"{s.name} is not reachable from MEMORY.md"})

    mems = [p for p in sorted(store.glob("*.md")) if p.name != "MEMORY.md" and not p.name.startswith("index_")]
    names = set()
    for p in mems:
        fm = front(p.read_text())
        names.add(fm.get("name", p.stem))
        missing = [k for k in ("name", "description") if not fm.get(k)]
        if not (fm.get("type") or "metadata" in fm):
            missing.append("type")
        if missing:
            fails.append({"kind": "front", "detail": f"{p.name}: missing {', '.join(missing)}"})
        if p.name not in indexed:
            fails.append({"kind": "unindexed", "detail": p.name})
    for p in mems:
        for slug in WIKI.findall(p.read_text()):
            if slug.strip() not in names and not (store / f"{slug.strip()}.md").exists():
                notes.append({"kind": "link", "detail": f"{p.name} -> [[{slug.strip()}]]"})
    return {"fails": fails, "notes": notes,
            "stats": {"memories": len(mems), "shards": len(shards), "index_bytes": size, "index_lines": lines,
                      "max_bytes": max_bytes, "dangling_links": len(notes)}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("store", type=Path)
    ap.add_argument("--max-bytes", type=int, default=24_400,
                    help="hot index byte budget (default 24400, the load limit measured on our harness)")
    ap.add_argument("--max-lines", type=int, default=0, help="line budget, 0 = off")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    rep = check(a.store.expanduser().resolve(), a.max_bytes, a.max_lines)
    if a.json:
        print(json.dumps(rep, indent=2))
    else:
        s = rep["stats"]
        if s:
            print(f"{s['memories']} memories, {s['shards']} shards, MEMORY.md {s['index_bytes']} B / "
                  f"{s['max_bytes']} B, {s['dangling_links']} dangling [[links]]")
        for x in rep["fails"]:
            print(f"  FAIL [{x['kind']:<9}] {x['detail']}")
        if not rep["fails"]:
            print("  no failures")
    return 1 if rep["fails"] else 0


if __name__ == "__main__":
    sys.exit(main())
