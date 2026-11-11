#!/usr/bin/env python3
"""Audit a CLAUDE.md and its progressive-disclosure rules files (memory layer L0).

Always-on context (CLAUDE.md plus any rules/*.md with no `paths:`) is paid for on every turn, so it has a byte
budget. Detail belongs in a path-scoped rules file that Claude Code loads only when a matching file is read.

Checks:
  budget     always-on bytes over --budget
  bullet     a single always-on block over --max-block chars (detail leaking back in)
  import     an `@path` import that does not resolve (spaces break imports silently)
  path       a backticked repo path that does not exist
  scope      a rules file whose `paths:` globs match no file (dead scope)
  unscoped   a rules file with no `paths:` (it is always-on, counted in budget)
  orphan     a rules file CLAUDE.md does not mention, or a mention with no file

Usage:
  claude_md_audit.py --root ~/Vault                          # human report, exit 1 on any finding
  claude_md_audit.py --root ~/Vault --json                   # machine report
  claude_md_audit.py --root ~/Vault --claude-md CLAUDE.md --rules .claude/rules --allow-dead "old/dir/"
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path


def front_paths(text: str) -> list[str] | None:
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m or "paths:" not in m.group(1):
        return None
    return re.findall(r'^\s*-\s*"?([^"\n]+?)"?\s*$', m.group(1).split("paths:", 1)[1], re.M)


def strip_code(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.sub(r"`[^`\n]*`", "", text)


def blocks(text: str) -> list[str]:
    """Top-level bullets and paragraphs, with their indented children."""
    out, cur = [], []
    for line in text.split("\n"):
        top = line.startswith(("- ", "#", "|")) or (line and not line.startswith((" ", "\t")))
        if top and cur:
            out.append("\n".join(cur)); cur = []
        if line.strip():
            cur.append(line)
        elif cur:
            out.append("\n".join(cur)); cur = []
    if cur:
        out.append("\n".join(cur))
    return out


def audit(root: Path, claude_md: Path, rules_dir: Path, budget: int, max_block: int, allow_dead: set[str]) -> dict:
    f: list[dict] = []
    core = claude_md.read_text()
    always = len(core.encode())
    rules = sorted(rules_dir.glob("*.md")) if rules_dir.is_dir() else []
    rel_rules = rules_dir.relative_to(root).as_posix() if rules_dir.is_relative_to(root) else rules_dir.name
    for r in rules:
        t = r.read_text()
        globs = front_paths(t)
        if globs is None:
            always += len(t.encode())
            f.append({"kind": "unscoped", "file": r.name, "detail": "no paths: frontmatter, loads every turn"})
            continue
        hits = sum(1 for g in globs if glob.glob(str(root / g), recursive=True))
        if hits == 0:
            f.append({"kind": "scope", "file": r.name, "detail": f"no glob matches any file: {globs}"})
        if f"{rel_rules}/{r.name}" not in core and r.name not in core:
            f.append({"kind": "orphan", "file": r.name, "detail": "not referenced from CLAUDE.md"})
    for ref in set(re.findall(rf"{re.escape(rel_rules)}/([\w.-]+\.md)", core)):
        if not (rules_dir / ref).exists():
            f.append({"kind": "orphan", "file": ref, "detail": "referenced from CLAUDE.md but missing"})

    if always > budget:
        f.append({"kind": "budget", "file": claude_md.name, "detail": f"always-on {always} B > budget {budget} B"})
    for b in blocks(core):
        if len(b) > max_block and not b.startswith("|"):
            f.append({"kind": "bullet", "file": claude_md.name, "detail": f"{len(b)} chars: {b.splitlines()[0][:90]}"})

    for m in re.finditer(r"(?<![\w`])@([~\w./-][^\s`)]*)", strip_code(core)):
        tok = m.group(1).rstrip(".,:;")
        if "/" not in tok and "." not in tok:
            continue  # @mentions, not imports
        base = claude_md.resolve().parent
        if not (base / tok).exists() and not (root / tok).exists() and not Path(tok).expanduser().exists():
            f.append({"kind": "import", "file": claude_md.name, "detail": f"@{tok} does not resolve"})

    for scope_file in [claude_md, *rules]:
        text = scope_file.read_text()
        for tok in set(re.findall(r"`([^`\n]+)`", text)):
            if not re.match(r"^(~/|[A-Za-z][\w .-]*/)[^<>*$|]*$", tok) or " -" in tok:
                continue
            if re.search(r"YYYY|<|\*|\s--", tok):
                continue
            if not tok.startswith("~") and not (root / tok.split("/")[0]).is_dir():
                continue  # repo slugs (Org/Repo) and relative subfolder names, not repo paths
            p = Path(tok).expanduser() if tok.startswith("~") else root / tok
            if not p.exists() and not Path(str(p).rstrip("/")).exists():
                f.append({"kind": "path", "file": scope_file.name, "detail": tok})

    # Deleted-on-purpose paths are often named in rules as warnings ("never recreate X/"); do not flag them.
    f = [x for x in f if not (x["kind"] == "path" and x["detail"] in allow_dead)]
    return {"always_on_bytes": always, "budget": budget, "rules_files": len(rules), "findings": f}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="repo or vault root (default: cwd)")
    ap.add_argument("--claude-md", type=Path, default=Path("CLAUDE.md"), help="relative to --root")
    ap.add_argument("--rules", type=Path, default=Path(".claude/rules"), help="relative to --root")
    ap.add_argument("--budget", type=int, default=18000, help="always-on byte budget (default 18000)")
    ap.add_argument("--max-block", type=int, default=900, help="max chars for one always-on block")
    ap.add_argument("--allow-dead", action="append", default=[], help="a path that is meant not to exist")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    root = a.root.expanduser().resolve()
    rep = audit(root, root / a.claude_md, (root / a.rules).resolve(), a.budget, a.max_block, set(a.allow_dead))
    if a.json:
        print(json.dumps(rep, indent=2))
    else:
        print(f"always-on: {rep['always_on_bytes']} B / budget {rep['budget']} B, rules files: {rep['rules_files']}")
        for x in rep["findings"]:
            print(f"  [{x['kind']:<8}] {x['file']}: {x['detail']}")
        if not rep["findings"]:
            print("  no findings")
    return 1 if rep["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
