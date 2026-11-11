#!/usr/bin/env python3
"""
memory_promote.py: nightly promotion of what was captured into the fact store.

WHY
Capture is automatic (the per-message journal nudge, Maestro's turn history, the
the activity recorder and Recordings ingests) but nothing moved it into `Agent/Memory/Store/`.
A durable rule existed only if I noticed it in the moment. Decided 2026-11-10
. Runs from a Cue, not a harness
hook, so it works under any harness.

WHAT IT DOES (for one day, default yesterday)
  1. REPLAY   read Agent/Journal/<day>.md, `maestro-cli timeline` history for this
              agent, and the activity recorder's "Decisions & Commitments" for that day.
  2. EXTRACT  one model call via memstore.model_call (config `model_cmd`; default: Claude Code, here
              through lib/claude_auth's account fall-through)
              with the store's catalog, returning new memories and updates to
              existing ones, each with its source, a quote, and `said_by`.
  3. VALIDATE drop anything malformed, off-limits, or over the nightly cap.
  4. WRITE    (apply mode only) new files in harness format + a pointer in the
              matching section index; updates are appended to the body as a dated
              paragraph. Nothing is ever deleted or rewritten.
  5. LOG      Agent/Memory/Promotions/<day>.md: every proposal or change, with
              its reason and source, in both modes.

MODES
  dry-run: proposals go to the log only. The default.
  apply: writes. Every way of asking for it (config `promote.mode: apply`, `--apply`, or
  the automatic switch from dry-run) must pass the REVIEW GATE first:
    - `promote.apply_after` is set and today is on or after it, AND
    - `promote.reviewed: true`, unless `promote.require_review: false`.
  The automatic switch happens only when the gate passes. An explicit apply that fails
  the gate is refused. `--override-gate` skips the gate; schedulers must never pass it.
  `--dry-run` always wins. `readonly: true` in config forces dry-run.
  Apply also needs the core index (`<store_dir>/MEMORY.md`), the promoted shard (config
  `promote.promoted_shard`, default `<store_dir>/index_promoted.md`) AND a pointer line to it in MEMORY.md.
  Switch off: AGENT_MEMORY=0, Agent/Memory/.disabled, or config enabled/promote.enabled
  false.

CONFIG KEYS (Memory/config.json; all optional)
  promote.journal_glob   journal files for a day, relative to the agent folder, `{date}` = YYYY-MM-DD;
                         default `Journal/{date}.md`; a day may span several files
  store_dir              the fact store folder (holds MEMORY.md), relative to the Memory folder; default
                         `Store`, `.` = flat. Never guessed
  promote.maestro_cli    Maestro CLI for the timeline source (env MAESTRO_CLI wins); then `maestro-cli` on
                         PATH, then the macOS app bundle. None found, a non-zero exit, or output that is not
                         JSON: the source is logged as skipped with the reason
  promote.off_limits     regex; matching source lines are redacted before the model AND candidates dropped
  model_cmd              argv of the model CLI, prompt on stdin, `{model}` = promote.model; default Claude Code

REDACT (before the model call)
  Every line of every source that matches promote.off_limits or a credential pattern is replaced by a
  marker. The quote check below runs on the redacted text, so a quote of a redacted line fails.

VALIDATE
  Every candidate's `quote` must appear in that day's captured source text (normalized:
  lowercase, punctuation as spaces), at least 3 words or a whole source line. Anything
  else is dropped and counted as `unquoted` in the log.

EXIT CODES
  0  ran (dry-run or apply), nothing captured, switched off, day already applied, or a
     transient model failure (logged; the day is retried next run, nothing written)
  2  setup error, nothing written, day not marked done: promoted shard missing, or no
     MEMORY.md pointer to it. (argparse also exits 2 on bad command-line usage.)
  3  apply refused by the review gate, nothing written, day not marked done
  1  unexpected crash

USAGE
  memory_promote.py                    # yesterday, mode from config
  memory_promote.py --date 2026-11-09 --dry-run
  memory_promote.py --date 2026-11-09 --apply [--force]   # --force re-applies a day
  memory_promote.py --print-prompt     # show the extraction prompt, call nothing

State: ~/.config/agent-memory/promote.json (days applied).
Doc: memory_promote.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import glob
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import os  # noqa: E402
import memstore as ms  # noqa: E402
from memstore import model_call  # noqa: E402

AGENT_ID = os.environ.get("MAESTRO_AGENT_ID", "")
MAESTRO_BUNDLE = "/Applications/Maestro.app/Contents/Resources/maestro-cli.js"     # macOS app, last resort
STATE_FILE = ms.STATE / "promote.json"
LOG = ms.AGENT / "Logs" / "memory_promote.log"


def off_limits() -> re.Pattern | None:
    """Topics that must never become a memory (config `promote.off_limits`, a regex)."""
    rx = ms.config().get("promote", {}).get("off_limits")
    return re.compile(rx, re.I) if rx else None


class SourceSkipped(Exception):
    """A source that could not be read at all (no tool, no permission). Logged as skipped with its reason,
    never reported as an empty source (spec 2026-11-10.4, G12)."""


def maestro_cli_cmd() -> list[str]:
    """argv prefix for the Maestro CLI: env MAESTRO_CLI, then config promote.maestro_cli, then `maestro-cli` on
    PATH, then the macOS app bundle. A `.js` path runs under node. Raises SourceSkipped when none is found."""
    want = os.environ.get("MAESTRO_CLI") or (ms.config().get("promote") or {}).get("maestro_cli")
    if want:
        p = Path(str(want)).expanduser()
        found = str(p) if p.exists() else shutil.which(str(want))
        if not found:
            raise SourceSkipped(f"configured Maestro CLI not found: {want}")
    else:
        found = shutil.which("maestro-cli") or (MAESTRO_BUNDLE if Path(MAESTRO_BUNDLE).exists() else None)
        if not found:
            raise SourceSkipped("no Maestro CLI: set promote.maestro_cli or MAESTRO_CLI, or put maestro-cli on PATH")
    if found.endswith(".js"):
        node = shutil.which("node")
        if not node:
            raise SourceSkipped(f"{found} needs node, and node is not on PATH")
        return [node, found]
    return [found]


def log(msg: str) -> None:
    line = f"{dt.datetime.now(ms.TZ):%Y-%m-%d %H:%M:%S} | {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ---------- 1. REPLAY ----------

DEFAULT_JOURNAL_GLOB = "Journal/{date}.md"


def journal_files(day: str) -> list[Path]:
    """Config `promote.journal_glob`, relative to the agent folder (or absolute), `{date}` = YYYY-MM-DD.
    Default `Journal/{date}.md`. A day may span several files; they are read in name order (G14)."""
    pat = str((ms.config().get("promote") or {}).get("journal_glob") or DEFAULT_JOURNAL_GLOB)
    pat = pat.replace("{date}", glob.escape(day))
    full = Path(pat).expanduser()
    full = full if full.is_absolute() else ms.AGENT / full
    return [Path(f) for f in sorted(glob.glob(str(full))) if Path(f).is_file()]


def src_journal(day: str) -> str:
    files = journal_files(day)
    parts = []
    for p in files:
        text = p.read_text()
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)            # session markers
        text = re.sub(r"\[↩ [^\]]*\]\(maestro://[^)]*\)", "", text)    # deep links
        text = text.strip()
        if text:
            parts.append(f"### file: {p.name}\n{text}" if len(files) > 1 else text)
    return "\n\n".join(parts)


def src_timeline(day: str) -> str:
    cli = maestro_cli_cmd()                 # raises SourceSkipped
    start = dt.datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=ms.TZ)
    end = start + dt.timedelta(days=1)
    try:
        out = subprocess.run(
            [*cli, "timeline", "--agent", AGENT_ID, "--sources", "history",
             "--since", start.isoformat(), "--until", end.isoformat(),
             "--per-source", "500", "--tail", "500", "--json"],
            capture_output=True, text=True, timeout=60)
    except Exception as e:
        raise SourceSkipped(f"timeline did not run: {type(e).__name__}: {e}") from e
    if out.returncode != 0:
        # G17: a CLI without the `timeline` command (or any failure) is a skipped source with its own words,
        # never a JSON parse error.
        first = next((ln.strip() for ln in (out.stderr or "").splitlines() if ln.strip()), "no stderr")
        raise SourceSkipped(f"exit {out.returncode}: {first[:200]}")
    try:
        events = json.loads(out.stdout).get("events", [])
    except Exception as e:
        raise SourceSkipped(f"timeline output is not JSON: {type(e).__name__}") from e
    lines = []
    for e in events:
        t = dt.datetime.fromtimestamp(e.get("ts", 0) / 1000, ms.TZ).strftime("%H:%M")
        lines.append(f"{t} {e.get('text', '')}")
    return "\n".join(lines)


def src_activity(day: str) -> str:
    p = ms.AGENT / "Activity" / "Days" / f"{day}.md"
    if not p.exists():
        return ""
    m = re.search(r"^## Decisions & Commitments\n(.*?)(?=^## |\Z)", p.read_text(), re.S | re.M)
    return m.group(1).strip() if m else ""


SOURCES = {"journal": src_journal, "timeline": src_timeline, "activity": src_activity}


# ---------- 2. EXTRACT ----------

PROMPT = """You maintain the long-term memory of {agent}, the AI agent that runs {owner}'s notes vault.
Below is everything captured on {day}, then the catalog of memories that already exist.
Decide what from {day} deserves to be remembered for MONTHS, and return JSON only.

A memory is worth writing when a future session, weeks from now, would act differently for knowing it:
- a rule or correction {owner} gave about how to work (type "feedback"; these matter most),
- a durable fact or preference about {owner}, their family or their life (type "user"),
- a project's lasting state, decision or constraint (type "project"),
- where something lives: a tool, path, URL, account, service (type "reference"),
- a decision that settles a question, ideally with what would reopen it.

Do NOT propose:
- one-off task details, status of work in progress, anything the code, git history or a tool doc already records,
- anything already covered by a catalog entry (propose an "update" to that slug only if {day} adds something new),
- statements by other people in meetings unless {owner} adopted them as their own,
{off_limits_line}- guesses. If the source does not say it, leave it out. Proposing nothing is a fine answer.

Return a JSON array (no prose, no code fence). Each element:
{{"action": "new" | "update",
  "slug": "for update: an existing slug from the catalog; for new: lower_snake_case starting with its type, e.g. feedback_x",
  "type": "user|feedback|project|reference",
  "name": "short title",
  "description": "one line that says when this memory is relevant",
  "body": "the fact itself, 1-4 sentences, plain language",
  "why": "for feedback/project: the reason, ideally {owner}'s words",
  "how_to_apply": "for feedback/project: when and how to use it",
  "said_by": "owner" if {owner} said or approved it, else "inferred",
  "source": "journal|timeline|activity",
  "quote": "the exact words from the source that support it (max 200 chars)",
  "shard": "one of: {shards}",
  "decision": {{"is_decision": true|false, "reopen_if": "after:YYYY-MM-DD | exists:<vault path> | grep:<vault path>::<regex> | manual:<plain words> | empty"}}
}}

At most {cap} elements. Prefer fewer, stronger memories.

=== CAPTURED ON {day} ===
{sources}

=== EXISTING MEMORY CATALOG (slug | type | description) ===
{catalog}
"""


LAST_SOURCES: dict = {"text": "", "skipped": {}, "redacted": {"off_limits": 0, "secret": 0}}


def build_prompt(day: str, cfg: dict) -> tuple[str, dict]:
    pc = cfg.get("promote", {})
    budget = int(pc.get("max_source_chars", 60000))
    parts, sizes, skipped, redacted = [], {}, {}, {"off_limits": 0, "secret": 0}
    rx = off_limits()
    for name in pc.get("sources", list(SOURCES)):
        fn = SOURCES.get(name)
        if not fn:
            skipped[name] = "unknown source name"
            continue
        try:
            txt = fn(day)
        except SourceSkipped as e:
            skipped[name] = str(e)
            log(f"{day}: source {name} skipped: {e}")
            continue
        # G13: secrets and off-limits lines never reach the model. Same rules as the candidate filter.
        txt, n = ms.redact(txt, rx)
        for k in redacted:
            redacted[k] += n[k]
        sizes[name] = len(txt)
        if txt:
            parts.append(f"--- source: {name} ---\n{txt}")
    LAST_SOURCES["skipped"], LAST_SOURCES["redacted"] = skipped, redacted
    blob = "\n\n".join(parts)
    if len(blob) > budget:
        blob = blob[:budget] + "\n[truncated]"
    LAST_SOURCES["text"] = blob             # what the model saw: quotes are checked against this (G10)
    catalog = "\n".join(f"{m.slug} | {m.type} | {m.description[:160]}" for m in ms.load_all())
    owner, agent = ms.names()
    ol = pc.get("off_limits_words")
    prompt = PROMPT.format(day=day, sources=blob or "(nothing captured)", catalog=catalog,
                           owner=owner, agent=agent,
                           off_limits_line=f"- anything about {ol},\n" if ol else "",
                           shards=", ".join(sorted(ms.shards())),
                           cap=int(pc.get("max_new_per_night", 8)))
    return prompt, sizes


def parse_json_array(text: str) -> list | None:
    text = text.strip()
    a, b = text.find("["), text.rfind("]")
    if a < 0 or b <= a:
        return None
    try:
        out = json.loads(text[a:b + 1])
        return out if isinstance(out, list) else None
    except Exception:
        return None


# ---------- 3. VALIDATE ----------

REOPEN_RE = re.compile(r"^(after:\d{4}-\d{2}-\d{2}|exists:.+|grep:.+::.+|manual:.+)$")


UNQUOTED = "quote not found in the day's sources (unquoted)"


def validate(cands: list, cap: int, source_text: str | None = None) -> tuple[list, list]:
    """`source_text`: the day's captured text the model saw. None skips the quote check (tests of other rules)."""
    by_slug = {m.slug: m for m in ms.load_all()}
    keep, dropped = [], []
    for c in cands:
        if not isinstance(c, dict):
            dropped.append(("not an object", str(c)[:80]))
            continue
        blob = json.dumps(c, ensure_ascii=False)
        rx = off_limits()
        if rx and rx.search(blob):
            dropped.append(("off-limits topic", c.get("slug", "?")))
            continue
        if ms.SECRET_RE.search(blob):
            dropped.append(("contains a secret", c.get("slug", "?")))
            continue
        if c.get("action") not in ("new", "update") or c.get("type") not in ms.TYPES:
            dropped.append(("bad action/type", c.get("slug", "?")))
            continue
        if not c.get("body") or not c.get("quote"):
            dropped.append(("no body or no supporting quote", c.get("slug", "?")))
            continue
        if source_text is not None and not ms.quote_in(c["quote"], source_text):
            dropped.append((UNQUOTED, c.get("slug", "?")))
            continue
        if c["action"] == "update" and c.get("slug") not in by_slug:
            dropped.append(("update to unknown slug", c.get("slug", "?")))
            continue
        if c["action"] == "new":
            c["slug"] = ms.slugify(c.get("slug") or c.get("name", ""))
            if not c["slug"].startswith(c["type"]):
                c["slug"] = f"{c['type']}_{c['slug']}"
            if c["slug"] in by_slug:
                c["action"] = "update"
        d = c.get("decision") or {}
        r = (d.get("reopen_if") or "").strip()
        d["reopen_if"] = r if REOPEN_RE.match(r) else ""
        c["decision"] = d
        sb = c.get("said_by")
        c["said_by"] = ms.OWNER_KEY if sb in ("owner", ms.OWNER_KEY) else "inferred"
        keep.append(c)
    if len(keep) > cap:
        dropped += [("over nightly cap", c["slug"]) for c in keep[cap:]]
        keep = keep[:cap]
    return keep, dropped


# ---------- 4. WRITE ----------

def render_body(c: dict) -> str:
    out = c["body"].strip()
    if c["type"] in ("feedback", "project"):
        if c.get("why"):
            out += f"\n\n**Why:** {c['why'].strip()}"
        if c.get("how_to_apply"):
            out += f"\n\n**How to apply:** {c['how_to_apply'].strip()}"
    out += f"\n\nSource ({c['source']}, {c['_day']}): \"{c['quote'].strip()}\""
    return out


def apply(c: dict, day: str) -> str:
    src = f"{c['source']}:{day}"
    d = c["decision"]
    if c["action"] == "new":
        meta = {"said_by": c["said_by"], "sources": [src], "learned": day,
                "modified": ms.today(), "promoted": day}
        if d.get("is_decision"):
            meta.update({"decision": True, "status": "active"})
            if d.get("reopen_if"):
                meta["reopen_if"] = d["reopen_if"]
        path = ms.write_new(c["slug"], c["name"], c["description"], c["type"], render_body(c), meta)
        shard = c.get("shard") if c.get("shard") in ms.shards() else "promoted"
        hook = c["description"][:140]
        target = ms.add_pointer(shard, c["name"], path.name, hook)
        return f"wrote {path.name}, indexed in {target.name}"
    path = ms.STORE / f"{c['slug']}.md"
    mem = ms.parse(path)
    sources = list((mem.meta.get("sources") if mem else None) or [])
    if src not in sources:
        sources.append(src)
    with path.open("a") as f:
        f.write(f"\n**Update {day}:** {c['body'].strip()} "
                f"(source {c['source']}: \"{c['quote'].strip()[:200]}\")\n")
    upd = {"sources": sources, "modified": ms.today()}
    if c["said_by"] == ms.OWNER_KEY:
        upd["said_by"] = ms.OWNER_KEY
    if d.get("is_decision") and d.get("reopen_if"):
        upd.update({"decision": True, "status": "active", "reopen_if": d["reopen_if"]})
    ms.set_meta(path, upd)
    return f"updated {path.name}"


# ---------- 5. LOG ----------

def write_log(day: str, mode: str, sizes: dict, keep: list, dropped: list, results: list,
              note: str = "") -> Path:
    ms.PROMOTIONS.mkdir(parents=True, exist_ok=True)
    p = ms.PROMOTIONS / f"{day}.md"
    src = ", ".join(f"{k} {v:,} chars" for k, v in sizes.items()) or "none"
    sk = LAST_SOURCES.get("skipped") or {}
    if sk:
        src += "; skipped: " + "; ".join(f"{k} ({v})" for k, v in sk.items())
    rd = LAST_SOURCES.get("redacted") or {}
    if any(rd.values()):
        src += f"; redacted before the model: {rd.get('off_limits', 0)} off-limits, {rd.get('secret', 0)} secret line(s)"
    unq = sum(1 for why, _ in dropped if why == UNQUOTED)
    lines = [f"Summary:: {mode}: {len(keep)} proposed, {len(results)} written, {len(dropped)} dropped "
             f"({unq} unquoted)",
             "", f"# Memory Promotion {day}", "",
             f"- Mode: **{mode}**  ", f"- Sources: {src}  ",
             f"- Run: {dt.datetime.now(ms.TZ):%Y-%m-%d %H:%M %Z}"]
    if note:
        lines += ["", f"> [!NOTE]\n> {note}"]
    lines += ["", "## Proposals", ""]
    if not keep:
        lines.append("Nothing worth remembering long-term.")
    for i, c in enumerate(keep, 1):
        res = results[i - 1] if i <= len(results) else "not written (dry-run)"
        reopen = c["decision"].get("reopen_if") or ""
        lines += [f"### {i}. {c['action'].upper()} `{c['slug']}` ({c['type']}, said_by {c['said_by']})",
                  "", f"**{c.get('name', '')}**: {c.get('description', '')}", "", c["body"].strip(), ""]
        if c.get("why"):
            lines.append(f"- Why: {c['why']}")
        if c.get("how_to_apply"):
            lines.append(f"- How to apply: {c['how_to_apply']}")
        lines += [f"- Source: {c['source']}: \"{c['quote'][:200]}\""]
        if c["decision"].get("is_decision"):
            lines.append(f"- Decision record, reopen_if: `{reopen or 'none'}`")
        lines += [f"- Result: {res}", ""]
    if dropped:
        lines += ["## Dropped", ""] + [f"- `{s}`: {why}" for why, s in dropped] + [""]
    # G22: the vault tags every file it writes; a generic install does not.
    p.write_text("\n".join(lines) + "\n")
    return p


# ---------- main ----------

def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"applied": []}


def save_state(st: dict) -> None:
    ms.STATE.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1))
    tmp.replace(STATE_FILE)


def review_gate(pc: dict) -> tuple[bool, str]:
    """(open, why closed). Open = apply_after reached AND (reviewed, or require_review is false)."""
    after = str(pc.get("apply_after") or "")
    if not after:
        return False, "promote.apply_after is not set"
    if ms.today() < after:
        return False, f"the dry-run review period runs until {after}"
    if pc.get("require_review", True) and pc.get("reviewed") is not True:
        return False, "promote.reviewed is not true (set it after reading the dry-run proposals)"
    return True, ""


def shard_problem() -> str | None:
    if not ms.CORE_INDEX.exists():
        return f"no core index at {ms.CORE_INDEX} (check config store_dir)"
    sh = ms.promoted_shard()
    if not sh.exists():
        return f"the promoted shard {sh} does not exist"
    if not ms.has_core_pointer(sh):
        return f"{ms.CORE_INDEX} has no pointer line to the promoted shard ({ms.shard_pointer(sh)})"
    return None


def refuse(day: str, code: int, why: str) -> int:
    msg = f"{day}: ABORT, {why}. Nothing written; the day is not marked done."
    log(msg)
    print(msg, file=sys.stderr)
    return code


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="day to promote (default: yesterday)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-apply a day already applied")
    ap.add_argument("--print-prompt", action="store_true")
    ap.add_argument("--override-gate", action="store_true",
                    help="apply even though the review gate is closed (by hand only; never in a scheduler)")
    args = ap.parse_args(argv)

    day = args.date or (dt.datetime.now(ms.TZ) - dt.timedelta(days=1)).strftime("%Y-%m-%d")
    on, why = ms.layer_on("promote")
    if not on:
        log(f"{day}: skipped, memory promotion off ({why})")
        return 0
    cfg = ms.config()
    pc = cfg.get("promote", {})

    # G7: every path to apply passes the review gate. The automatic switch only happens when it is open; an
    # explicit apply (flag or config) that fails it is refused, unless --override-gate.
    gate_open, gate_why = review_gate(pc)
    if args.dry_run:
        mode = "dry-run"
    elif args.apply or pc.get("mode", "dry-run") == "apply":
        if not gate_open and not args.override_gate:
            return refuse(day, 3, f"apply refused by the review gate: {gate_why}")
        mode = "apply"
    else:
        mode = "apply" if gate_open else "dry-run"
    note = "Applied with --override-gate (review gate closed: " + gate_why + ")." \
        if mode == "apply" and not gate_open else ""
    if mode == "apply" and ms.readonly():
        mode, note = "dry-run", "Config is readonly, so this run only proposed."
    # G4 + G8: every new memory falls back to the promoted shard, so apply needs that shard AND a MEMORY.md
    # pointer to it. Checked before the model call: write nothing, leave the day unmarked, exit 2.
    if mode == "apply":
        problem = shard_problem()
        if problem:
            return refuse(day, 2, problem)

    st = load_state()
    if mode == "apply" and day in st.get("applied", []) and not args.force:
        log(f"{day}: already applied; use --force to re-run")
        return 0

    prompt, sizes = build_prompt(day, cfg)
    if args.print_prompt:
        print(prompt)
        return 0
    if not any(sizes.values()):
        p = write_log(day, mode, sizes, [], [], [], "Nothing was captured for this day.")
        log(f"{day}: nothing captured; log {p.name}")
        return 0

    try:
        # G21: `"model": null` in config must mean the default, not None.
        res = model_call(prompt, pc.get("model") or "sonnet", timeout=600,
                         cwd=str(ms.STATE if ms.STATE.exists() else Path.home()),
                         label="memory_promote", log_fn=log)
    except Exception as e:
        log(f"{day}: EXTRACT failed ({type(e).__name__}: {e}); will retry next run")
        return 0
    cands = parse_json_array(res.stdout or "") if res.returncode == 0 else None
    if cands is None:
        log(f"{day}: EXTRACT returned no JSON (exit {res.returncode}); tail={res.stdout[-200:]!r}")
        return 0
    for c in cands:
        if isinstance(c, dict):
            c["_day"] = day

    keep, dropped = validate(cands, int(pc.get("max_new_per_night", 8)), LAST_SOURCES["text"])
    results = []
    if mode == "apply":
        for c in keep:
            try:
                results.append(apply(c, day))
            except Exception as e:
                results.append(f"FAILED: {e}")
        st.setdefault("applied", []).append(day)
        st["applied"] = sorted(set(st["applied"]))[-120:]
        save_state(st)
    p = write_log(day, mode, sizes, keep, dropped, results, note)
    log(f"{day}: {mode}, {len(keep)} proposed, {len(results)} written, {len(dropped)} dropped; log {p.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
