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
  spec drift     (spec 2026-11-11.1) reads the live `Spec version:` line from the README of
                 the gist named in `lint.spec_gist` and prints one
                 `WARN spec drift: local X, live Y` line when the config's `spec_version` is
                 older. Never changes the exit code; an unreachable network, a missing `gh`
                 or an unset `lint.spec_gist` logs `drift check skipped (...)`.
                 `lint.drift_check: false` turns it off (default on).

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
import shutil
import subprocess
import sys
import urllib.request
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


# ---------- spec drift (2026-11-11.1) ----------

SPEC_LINE = re.compile(r"^Spec version: (\S+?)\.?\s*$", re.M)


def version_key(v) -> tuple | None:
    """`YYYY-MM-DD` or `YYYY-MM-DD.N` -> (date, N); no suffix counts as 0, so every suffix sorts after it."""
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?:\.(\d+))?", str(v or "").strip())
    return (m.group(1), int(m.group(2) or 0)) if m else None


def fetch_readme(gist_id: str, timeout: int = 20) -> str:
    """The README of the gist's latest revision: `gh api` when gh is installed, else the public API."""
    gh = shutil.which("gh")
    if gh:
        r = subprocess.run([gh, "api", f"gists/{gist_id}", "--jq", '.files["README.md"].content'],
                           capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0 or not r.stdout.strip():
            first = next((ln.strip() for ln in (r.stderr or "").splitlines() if ln.strip()), "no output")
            raise RuntimeError(f"gh exit {r.returncode}: {first[:120]}")
        return r.stdout
    with urllib.request.urlopen(f"https://api.github.com/gists/{gist_id}", timeout=timeout) as resp:
        return json.loads(resp.read().decode())["files"]["README.md"]["content"]


FETCH = fetch_readme                        # tests replace this


def drift_check(cfg: dict) -> str:
    """One line for the log. Never raises: any failure is `drift check skipped (...)`."""
    lc = cfg.get("lint") or {}
    if lc.get("drift_check", True) is False:
        return "drift check off (lint.drift_check: false)"
    gid = str(lc.get("spec_gist") or "").strip()
    if not gid:
        return "drift check skipped (no lint.spec_gist set)"
    try:
        m = SPEC_LINE.search(FETCH(gid))
    except Exception as e:
        return f"drift check skipped ({type(e).__name__}: {str(e)[:120]})"
    live = m.group(1) if m else ""
    local = str(cfg.get("spec_version") or "")
    lk, vk = version_key(local), version_key(live)
    if vk is None:
        return f"drift check skipped (no readable Spec version line in the live README: {live!r})"
    if lk is None or lk < vk:
        return f"WARN spec drift: local {local or 'unset'}, live {live}"
    return f"spec {local} is current (live {live})"


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
    # G25: a missing core index is a finding, not a crash (wrong store_dir, deleted file).
    core_bytes = ms.CORE_INDEX.stat().st_size if ms.CORE_INDEX.exists() else -1

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
    if core_bytes < 0:
        summary = f"MISSING core index {ms.CORE_INDEX}; " + summary
    print(f"memory_lint: {summary}")
    drift = drift_check(cfg)
    print(drift if drift.startswith("WARN") else f"memory_lint: {drift}")

    if write:
        L = [f"Summary:: {summary}", "",
             "# 🎛️ Memory Health", "",
             f"Generated {dt.datetime.now(ms.TZ):%Y-%m-%d %H:%M %Z} by `memory_lint.py`. "
             f"Overwritten every run; do not edit. Hub: [[{ms.AGENT_DIR}/Memory/🗺️ Memory]].", "",
             "| Measure | Value |", "|---|---|",
             f"| Memories | {len(mems)} ({', '.join(f'{k} {v}' for k, v in sorted(by_type.items()))}) |",
             f"| Core index `MEMORY.md` | " + (f"{core_bytes:,} B of {CORE_BUDGET:,} B budget" if core_bytes >= 0 else "**MISSING**") + " |",
             f"| `said_by` set | {ms.OWNER_KEY} {said[ms.OWNER_KEY]}, inferred {said['inferred']}, task {said['task']}, "
             f"unset {len(mems) - sum(said.values())} |",
             f"| With `sources:` | {with_sources} |",
             f"| `verified:` stamped | {verified} (paths in {len(mems) - no_refs} memories checked) |",
             f"| Decision records | {len(decisions)} ({len(waiting)} waiting, {len(manual)} manual) |",
             f"| Last promotion log | {last_promo} |",
             f"| Smoke test | {smoke_line} |",
             f"| Spec version | {cfg.get('spec_version') or 'unset'}: {drift} |", ""]
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

    bad = bool(dead_refs or dead_pointers or unindexed or core_bytes < 0)
    return 1 if (args.strict and bad) else 0


if __name__ == "__main__":
    sys.exit(main())
