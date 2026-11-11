#!/usr/bin/env python3
"""Convert Claude Code session transcripts (JSONL) into the session folders memory.py replays.

Claude Code writes one JSONL per session under <CLAUDE_CONFIG_DIR>/projects/<cwd-slug>/. memory.py's REPLAY reads
<MEMORY_SESSIONS>/<YYYY-MM-DD-HHMMSS-id>/transcript.md with one line per utterance:

  - `HH:MM:SS` **User:** what the owner typed
  - `HH:MM:SS` **Assistant:** what the agent answered

The full format, as a contract for converters from other harnesses, is SESSION-FORMAT.md.

Kept: the owner's typed prompts and the assistant's visible text. Dropped: tool calls, tool results, thinking,
meta/system entries, and harness wrappers (any user text that starts with '<', such as command or reminder blocks).
That keeps the extractor on what was said, not on file dumps it should never memorize.

Idempotent: a transcript is rewritten only when its content changed. memory.py notices the size change and
replays the session again; a restated memory then counts as "same" (one reinforcement per day at most).

Usage:
  cc_sessions.py --projects ~/.claude/projects/<cwd-slug> --out ~/.agent-memory/../sessions [--days 3]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

MAX_LINE = 2000


def _text(content, role: str) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for b in content or []:
        if isinstance(b, dict) and b.get("type") == "text":
            parts.append(b.get("text") or "")
    return "\n".join(parts)


def rows(path: Path) -> list[tuple[datetime, str, str]]:
    out = []
    for ln in path.open(encoding="utf-8", errors="replace"):
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        role = d.get("type")
        if role not in ("user", "assistant") or d.get("isMeta") or d.get("isSidechain"):
            continue
        text = " ".join(_text((d.get("message") or {}).get("content"), role).split())
        if not text or (role == "user" and text.startswith("<")):
            continue
        try:
            ts = datetime.fromisoformat(str(d.get("timestamp")).replace("Z", "+00:00")).astimezone()
        except ValueError:
            continue
        out.append((ts, "User" if role == "user" else "Assistant", text[:MAX_LINE]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--projects", required=True, type=Path, help="the project's transcript folder")
    ap.add_argument("--out", required=True, type=Path, help="MEMORY_SESSIONS folder")
    ap.add_argument("--days", type=float, default=3, help="only transcripts modified in the last N days")
    a = ap.parse_args()
    cutoff = time.time() - a.days * 86400
    wrote = same = empty = 0
    for f in sorted(a.projects.expanduser().glob("*.jsonl")):
        if f.stat().st_mtime < cutoff:
            continue
        r = rows(f)
        if not any(who == "User" for _, who, _ in r):
            empty += 1
            continue
        r.sort(key=lambda x: x[0])
        name = f"{r[0][0]:%Y-%m-%d-%H%M%S}-{f.stem[:8]}"
        body = f"# session {f.stem}\n\n" + "\n".join(f"- `{ts:%H:%M:%S}` **{who}:** {t}" for ts, who, t in r) + "\n"
        dest = a.out.expanduser() / name / "transcript.md"
        if dest.exists() and dest.read_text(encoding="utf-8") == body:
            same += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(dest)
        wrote += 1
    print(json.dumps({"wrote": wrote, "unchanged": same, "no_user_lines": empty}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
