#!/usr/bin/env python3
"""
memory_lint.py: deterministic nightly health pass over the fact store. No model calls.

Checks :
  N2 references  every vault / home path a memory names in backticks must exist.
                 A memory whose paths all resolve gets `verified: <today>` (re-stamped
                 at most every `lint.verify_stamp_days`, so sync churn stays low).
  N1 decisions   memories with `decision: true`, `status: active` and a `reopen_if`:
                   after:YYYY-MM-DD | exists:<path> | grep:<path>::<regex> | manual:<words>
                 A condition that fires is stamped `reopen_fired: <date>` (once, ever)
                 and raised as one Maestro toast. `manual:` never fires by itself.
  index          unindexed memories, pointers to missing files, core index size.
  coverage       counts by type, `said_by`, `sources`, decision records.

Writes `Agent/Memory/🎛️ Memory Health.md` (overwritten each run) and prints a
one-line summary. Exit 0 always unless --strict (exit 1 on any dead reference,
dead pointer or unindexed memory).

USAGE
  memory_lint.py              # check, stamp, write the health page
  memory_lint.py --no-write   # report only, change nothing
  memory_lint.py --strict
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import memstore as ms  # noqa: E402

import os  # noqa: E402
HEALTH = ms.MEMDIR / "🎛️ Memory Health.md"
AGENT_ID = os.environ.get("MAESTRO_AGENT_ID", "")
MAESTRO_CLI = os.environ.get("MAESTRO_CLI", "/Applications/Maestro.app/Contents/Resources/maestro-cli.js")
CORE_BUDGET = 18000
TOP_DIRS = {p.name for p in ms.VAULT.iterdir() if p.is_dir()} | {".claude", ".maestro", ".obsidian"}
TICK = re.compile(r"`([^`\n]{2,200})`")
PLACEHOLDER = re.compile(r"YYYY|MM-DD|\bTitle\b|\bx\.png\b|<[^>]+>|\.\.\.")
GONE = re.compile(r"retired|removed|deleted|moved|renamed|gone|never recreate|archived|no longer|was at|dead|replaced|other host|second host", re.I)


def candidate_paths(token: str) -> list[str]:
    """Path-like pieces of a backticked token that we can check on this host."""
    token = token.strip().rstrip(".,;:")
    if re.search(r"[<>*{}$|]|://|^-", token):
        return []
    pieces = [token] + token.split()
    out = []
    for p in pieces:
        p = p.strip("'\"()").rstrip(".,;:/")
        if not p or ("/" not in p and not p.startswith("~")):
            continue
        if re.match(r"^[\w.-]+:", p):          # host:path, remote-ssh:~/x
            continue
        if p.startswith("~/") or p.startswith("/Users/") or p.startswith("/Applications/"):
            out.append(p)
        elif p.split("/")[0] in TOP_DIRS:
            out.append(p)
    return out


def resolve(p: str) -> bool:
    path = Path(p).expanduser()
    if not path.is_absolute():
        path = ms.VAULT / p
    return path.exists()


def check_refs(mem: ms.Memory) -> tuple[int, list[str]]:
    """(paths checked, dead paths). A token counts as live if ANY of its pieces resolve."""
    checked, dead = 0, []
    text = mem.body + "\n" + mem.description
    for mt in TICK.finditer(text):
        tok = mt.group(1)
        if PLACEHOLDER.search(tok):
            continue
        cands = candidate_paths(tok)
        if not cands:
            continue
        checked += 1
        if any(resolve(c) for c in cands):
            continue
        # A memory that SAYS the path is gone is right, not stale.
        near = text[max(0, mt.start() - 160): mt.end() + 160]
        if GONE.search(near):
            continue
        dead.append(cands[0])
    return checked, sorted(set(dead))


def reopen_fires(cond: str) -> bool | None:
    """True fired, False not yet, None cannot be checked by a machine."""
    try:
        kind, _, arg = cond.partition(":")
        if kind == "after":
            return ms.today() >= arg.strip()
        if kind == "exists":
            return resolve(arg.strip())
        if kind == "grep":
            path, _, rx = arg.partition("::")
            fp = Path(path.strip()).expanduser()
            fp = fp if fp.is_absolute() else ms.VAULT / fp
            return fp.exists() and re.search(rx, fp.read_text(errors="ignore"), re.M) is not None
    except Exception:
        return False
    return None


def toast(title: str, msg: str) -> None:
    if not Path(MAESTRO_CLI).exists():
        print(f"[toast] {title}: {msg}")
        return
    try:
        subprocess.run(["node", MAESTRO_CLI, "notify", "toast", title, msg, "--agent", AGENT_ID],
                       capture_output=True, timeout=30)
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    on, why = ms.layer_on("lint")
    if not on:
        print(f"memory_lint: skipped ({why})")
        return 0
    write = not args.no_write and not ms.readonly()
    cfg = ms.config()
    stamp_days = int(cfg.get("lint", {}).get("verify_stamp_days", 30))
    today = ms.today()
    cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=stamp_days)).isoformat()

    mems = ms.load_all()
    indexed = ms.indexed_filenames()
    files = {m.filename for m in mems}
    unindexed = sorted(files - indexed)
    dead_pointers = sorted(f for f in indexed if f not in files
                           and not (ms.STORE / f).exists())
    core_bytes = ms.CORE_INDEX.stat().st_size

    dead_refs, stamped, no_refs = {}, 0, 0
    for m in mems:
        checked, dead = check_refs(m)
        if not checked:
            no_refs += 1
            continue
        if dead:
            dead_refs[m.filename] = dead
            continue
        v = str(m.meta.get("verified") or "")
        if write and (not v or v < cutoff):
            if ms.set_meta(m.path, {"verified": today}):
                stamped += 1

    decisions = [m for m in mems if m.meta.get("decision")]
    fired_now, waiting, manual = [], [], []
    if ms.layer_on("decisions")[0]:
        for m in decisions:
            if str(m.meta.get("status", "active")) != "active":
                continue
            cond = str(m.meta.get("reopen_if") or "")
            if not cond:
                continue
            res = reopen_fires(cond)
            if res is None:
                manual.append((m, cond))
            elif res and not m.meta.get("reopen_fired"):
                fired_now.append((m, cond))
                if write:
                    ms.set_meta(m.path, {"reopen_fired": today})
            elif not res:
                waiting.append((m, cond))
        if fired_now and write:
            names = "; ".join(m.name for m, _ in fired_now)[:300]
            toast("Parked decision can reopen", f"Condition met: {names}")

    by_type: dict[str, int] = {}
    for m in mems:
        by_type[m.type or "?"] = by_type.get(m.type or "?", 0) + 1
    said = {k: sum(1 for m in mems if m.meta.get("said_by") == k) for k in (ms.OWNER_KEY, "inferred", "task")}
    with_sources = sum(1 for m in mems if m.meta.get("sources"))
    verified = sum(1 for m in mems if m.meta.get("verified")) + stamped

    promo = sorted(ms.PROMOTIONS.glob("*.md"))
    last_promo = promo[-1].stem if promo else "never"
    smoke = ms.STATE / "smoke.json"
    try:
        sm = json.loads(smoke.read_text())
        smoke_line = (f"{sm['date']}: {sm['passed']}/{sm['total']} passed, "
                      f"{sm['abstained_ok']}/{sm['abstain_total']} correct abstentions, "
                      f"{'PASS' if sm['ok'] else 'FAIL'}")
    except Exception:
        smoke_line = "not run yet"

    summary = (f"{len(mems)} memories, {len(unindexed)} unindexed, {len(dead_pointers)} dead pointers, "
               f"{len(dead_refs)} with dead paths, {stamped} verified today, "
               f"{len(fired_now)} decisions reopened")
    print(f"memory_lint: {summary}")

    if write:
        L = [f"Summary:: {summary}", "",
             "# 🎛️ Memory Health", "",
             f"Generated {dt.datetime.now(ms.TZ):%Y-%m-%d %H:%M %Z} by `memory_lint.py`. "
             f"Overwritten every run; do not edit. Hub: [[{ms.AGENT_DIR}/Memory/🗺️ Memory]].", "",
             "| Measure | Value |", "|---|---|",
             f"| Memories | {len(mems)} ({', '.join(f'{k} {v}' for k, v in sorted(by_type.items()))}) |",
             f"| Core index `MEMORY.md` | {core_bytes:,} B of {CORE_BUDGET:,} B budget |",
             f"| `said_by` set | {ms.OWNER_KEY} {said[ms.OWNER_KEY]}, inferred {said['inferred']}, task {said['task']}, "
             f"unset {len(mems) - sum(said.values())} |",
             f"| With `sources:` | {with_sources} |",
             f"| `verified:` stamped | {verified} (paths in {len(mems) - no_refs} memories checked) |",
             f"| Decision records | {len(decisions)} ({len(waiting)} waiting, {len(manual)} manual) |",
             f"| Last promotion log | {last_promo} |",
             f"| Smoke test | {smoke_line} |", ""]
        if fired_now:
            L += ["## Reopened Decisions", ""] + [f"- [[{m.slug}]] `{c}` fired {today}" for m, c in fired_now] + [""]
        if dead_refs:
            L += ["## Dead References", ""]
            L += [f"- `{f}`: " + ", ".join(f"`{d}`" for d in ds) for f, ds in sorted(dead_refs.items())] + [""]
        if unindexed:
            L += ["## Unindexed Memories", ""] + [f"- `{f}`" for f in unindexed] + [""]
        if dead_pointers:
            L += ["## Dead Index Pointers", ""] + [f"- `{f}`" for f in dead_pointers] + [""]
        if waiting or manual:
            L += ["## Decisions Waiting", ""]
            L += [f"- [[{m.slug}]] `{c}`" for m, c in waiting + manual] + [""]
        L.append("#claude")
        HEALTH.write_text("\n".join(L) + "\n")

    bad = bool(dead_refs or dead_pointers or unindexed)
    return 1 if (args.strict and bad) else 0


if __name__ == "__main__":
    sys.exit(main())
