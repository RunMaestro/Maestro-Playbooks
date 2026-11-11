#!/usr/bin/env python3
"""memory: an agent's long-term memory, built from its session transcripts and consolidated by a nightly dream.

Reference implementation of the dream layer (L5) in ARCHITECTURE.md. One file, stdlib only, plus a headless model
CLI for the two model phases (EXTRACT and REFLECT): config `model_cmd`, default Claude Code. Everything else is
deterministic.

  Store    one memory per file, $MEMORY_DIR/Store/<slug>.md, front matter + the fact (memory-record.schema.json).
  Decay    R = exp(-days / S), S = S0[type] x 1.8^reinforcements (capped at 10 x S0). Rules never decay.
  Tiers    active = what fits the hot budget, ranked rule/pinned > salience > R;
           dormant = the rest, still recallable; archived = R < 0.05 AND 180 days untouched AND no inbound
           links: the file moves to Archive/. Superseded memories stay too. Nothing is ever deleted
           (only `purge` deletes, and only by hand).
  Dream    REPLAY new session transcripts (only what the owner said or typed, and task results) -> EXTRACT
           (small model, budget-capped) -> CONSOLIDATE (reinforce, supersede, promote) -> LINK (k nearest, both
           ways) -> CONTRADICT (newer wins only from an equal or higher source) -> DECAY -> REFLECT (weekly, an
           insight needs 3+ children from 3+ days) -> COMPILE (HOT.md, history.jsonl, Dreams/<date>.md).
           Files first, then indexes, then the report. Every change is a line in the dream log.
  Recall   lexical similarity + subject adjacency, R breaks ties (a static R/salience weighting lost to plain
           lexical in a backtest). A recall is rehearsal: touched memories get reinforced at the next dream.
  Switches config.json (enabled, readonly, per-phase); AGENT_MEMORY=0 or a .disabled file beats everything.
           Fail-open: any error means "no memory", never a broken session.

Environment:
  MEMORY_DIR         store root (default ~/.agent-memory)
  MEMORY_SESSIONS    folder of <YYYY-MM-DD-HHMMSS>/transcript.md session folders (default $MEMORY_DIR/../sessions)
  MEMORY_MODEL       model for EXTRACT/REFLECT (default: config `model`, else haiku)
  config model_cmd   argv of the model CLI, prompt on stdin; `{model}` placeholder (default: Claude Code)
  AGENT_MEMORY=0     hard kill, beats config
  AGENT_MEMORY_LLM=0 no model calls (dream runs the deterministic phases only)

  memory.py status                 counts, last dream, switches
  memory.py dream [--dry-run]      one dream over the sessions not yet replayed
  memory.py backfill               one dream per past day, oldest first (fills the history graphs)
  memory.py recall "question"      what the agent would get back
  memory.py add "fact" [--rule]    file one memory now (an explicit "remember ...")
  memory.py show                   the hot digest that goes into the prompt
  memory.py dreams [N]             the last N dream logs
  memory.py forget "text|slug"     move the best match to Archive as forgotten (never recalled again)
  memory.py purge <slug>           delete a file for real (by hand only)
  memory.py on|off|freeze|thaw     switches
"""
from __future__ import annotations

import difflib
import json
import math
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(os.environ.get("MEMORY_DIR", Path.home() / ".agent-memory")).expanduser()
SESSIONS = Path(os.environ.get("MEMORY_SESSIONS", ROOT.parent / "sessions")).expanduser()

TYPES = ("rule", "preference", "fact", "project", "procedure", "insight", "episode", "reference")
S0 = {"episode": 14, "project": 45, "fact": 180, "preference": 365, "reference": 365, "insight": 270,
      "procedure": 365, "rule": math.inf}
GROWTH, CAP_X = 1.8, 10
HOT_CAP = 2400                     # chars of hot digest injected into the prompt
RULE_SHARE = 0.5                   # rules go first but take at most half of it; the rest stay dormant, never decay
ARCHIVE_R, ARCHIVE_DAYS = 0.05, 180
TIER = {"owner": 3, "task": 2, "inferred": 1}      # source tiers for CONTRADICT: what the owner said wins
DUP_SIM = 0.78                     # this close to an existing memory = the same memory seen again
LINK_K, LINK_MIN = 3, 0.18
CHUNK = 22_000                     # chars of transcript per extract call
DEFAULT_CFG = {
    "enabled": True, "readonly": False, "budget_calls": 14,
    "owner": "Owner",                                   # the person the agent works for
    "people": [],                                       # other names a "remember ..." may be about
    "assistant": "Assistant",                           # the agent's own name in transcripts and prompts
    "sensitive": r"\b(health|diagnos\w*|money|salary|password|secret|address|divorce)\b",
    "roles": {"User": "OWNER", "Typed": "OWNER (typed)", "Texted": "OWNER (text)", "Phone": "OWNER (call)",
              "Task": "TASK RESULT", "Assistant": "ASSISTANT"},
    "phases": {"replay": True, "extract": True, "consolidate": True, "link": True, "contradict": True,
               "decay": True, "reflect": True, "compile": True}}
STOP = set("a an the and or but of to in on at for with from by is are was were be been being it its this that "
           "these those i you he she we they me him her us them my your his our their do does did have has had "
           "will would can could should just so if then than as about into over not no yes too very also "
           "what which who whom when where why how all any some more most much many like get got go going".split())


# -- switches ---------------------------------------------------------------------------------------------------

def cfg() -> dict:
    try:
        c = json.loads((ROOT / "config.json").read_text())
    except (OSError, ValueError):
        c = {}
    out = {**DEFAULT_CFG, **{k: v for k, v in c.items() if k != "phases"}}
    out["phases"] = {**DEFAULT_CFG["phases"], **(c.get("phases") or {})}
    return out


def enabled() -> bool:
    if os.environ.get("AGENT_MEMORY") == "0" or (ROOT / ".disabled").exists():
        return False
    try:
        return bool(cfg().get("enabled", True))
    except Exception:
        return False


def writable() -> bool:
    return enabled() and not cfg().get("readonly")


def set_cfg(**kw) -> dict:
    c = cfg()
    for k, v in kw.items():
        if k in c["phases"] and isinstance(v, bool) and k not in ("enabled", "readonly"):
            c["phases"][k] = v
        else:
            c[k] = v
    ROOT.mkdir(parents=True, exist_ok=True)
    _atomic(ROOT / "config.json", json.dumps(c, indent=1))
    return c


def sensitive(text: str) -> bool:
    try:
        return bool(re.search(cfg()["sensitive"], str(text), re.I))
    except re.error:
        return bool(re.search(DEFAULT_CFG["sensitive"], str(text), re.I))


def owner() -> str:
    return str(cfg().get("owner") or "Owner")


# -- records ----------------------------------------------------------------------------------------------------

def _atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


FIELDS = ("name", "description", "type", "subject", "said_by", "salience", "learned", "last_reinforced",
          "reinforcements", "status", "supersedes", "superseded_by", "valid_to", "sources", "links", "days",
          "pinned", "forgotten", "evidence")


def parse(text: str) -> dict | None:
    if not text.startswith("---\n"):
        return None
    head, _, body = text[4:].partition("\n---\n")
    m: dict = {}
    for ln in head.splitlines():
        k, sep, v = ln.partition(":")
        if not sep:
            continue
        v = v.strip()
        try:
            m[k.strip()] = json.loads(v)
        except ValueError:
            m[k.strip()] = v
    m["body"] = body.strip()
    return m if m.get("name") else None


def dump(m: dict) -> str:
    lines = ["---"]
    for k in FIELDS:
        if k in m and m[k] not in (None, "", [], False):
            v = m[k]
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False) if not isinstance(v, str) or chr(10) in v else v}")
    lines.append("---")
    body = m.get("description", "")
    if m.get("links"):
        body += "\n\n" + " ".join(f"[[{s}]]" for s in m["links"])
    return "\n".join(lines) + "\n" + body + "\n"


def load_all() -> dict[str, dict]:
    """Every memory, Store and Archive, by slug. The folder a file sits in wins over a stale status."""
    out: dict[str, dict] = {}
    for folder in ("Store", "Archive"):
        d = ROOT / folder
        for p in sorted(d.glob("*.md")) if d.is_dir() else []:
            try:
                m = parse(p.read_text(encoding="utf-8"))
            except OSError:
                continue
            if not m:
                continue
            m["_dir"] = folder
            if folder == "Archive" and m.get("status") not in ("archived", "superseded"):
                m["status"] = "archived"
            out[m["name"]] = m
    return out


def save(m: dict) -> None:
    folder = "Archive" if m.get("status") == "archived" or m.get("forgotten") else "Store"
    target = ROOT / folder / f"{m['name']}.md"
    _atomic(target, dump(m))
    other = ROOT / ("Store" if folder == "Archive" else "Archive") / f"{m['name']}.md"
    if other.exists():
        other.unlink()                   # a move, not a delete: the record lives on in `target`
    m["_dir"] = folder


def slugify(text: str, taken) -> str:
    ws = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP]
    ws = [w for i, w in enumerate(ws) if i == 0 or w != ws[i - 1]]      # "bob bob never ..." -> one
    base = ""
    for w in ws:
        if len(base) + len(w) + 1 > 48:
            break
        base = f"{base}-{w}" if base else w
    base = base or "memory"
    s, i = base, 2
    while s in taken:
        s, i = f"{base}-{i}", i + 1
    return s


# -- scoring ----------------------------------------------------------------------------------------------------

def words(text: str) -> set[str]:
    return {w[:-1] if len(w) > 4 and w.endswith("s") else w
            for w in re.findall(r"[a-z0-9']+", str(text).lower()) if w not in STOP and len(w) > 1}


def sim(a: str, b: str) -> float:
    wa, wb = words(a), words(b)
    jac = len(wa & wb) / len(wa | wb) if wa and wb else 0.0
    return max(jac, difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() * 0.9 if jac > 0.2 else jac)


def match(query: str, text: str) -> float:
    """How well a short question or "forget X" fits a memory: similarity, or the share of the query's words the
    memory holds (a one-word "forget the stegosaurus" must still find it)."""
    q = words(query)
    return max(sim(query, text), 0.8 * len(q & words(text)) / len(q) if q else 0.0)


def _d(s) -> date:
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return date.today()


def stability(m: dict) -> float:
    s0 = S0.get(m.get("type"), 180)
    return s0 * min(GROWTH ** int(m.get("reinforcements") or 0), CAP_X)


def retrievability(m: dict, today: date | None = None) -> float:
    if m.get("type") == "rule" or m.get("pinned"):
        return 1.0
    days = max(0, ((today or date.today()) - _d(m.get("last_reinforced") or m.get("learned"))).days)
    return math.exp(-days / stability(m))


def live(m: dict) -> bool:
    return m.get("status") in ("active", "dormant") and not m.get("forgotten")


def line(m: dict) -> str:
    subj = m.get("subject") or ""
    return f"- ({m.get('type')}) {subj + ': ' if subj and subj.lower() not in m['description'].lower() else ''}" \
           f"{m['description']}"


def rank_key(m: dict, today: date):
    return (m.get("type") == "rule" or bool(m.get("pinned")), int(m.get("salience") or 2),
            retrievability(m, today), int(m.get("reinforcements") or 0))


def tiers(mems: dict[str, dict], today: date) -> tuple[list[str], list[str], list[str]]:
    """(active, dormant, to_archive) slugs: byte-budget rank cut for the hot index, absolute floor for archival."""
    pool = sorted((m for m in mems.values() if live(m)), key=lambda m: rank_key(m, today), reverse=True)
    inbound = Counter(s for m in mems.values() if live(m) for s in m.get("links") or [])
    active, dormant, arch, used, ruled = [], [], [], 0, 0
    for m in pool:
        n = len(line(m)) + 1
        last = _d(m.get("last_reinforced") or m.get("learned"))
        if m.get("type") == "rule" or m.get("pinned"):
            # exempt from decay and from the archive, NOT from the budget: an index that overflows its cap is
            # the silent-truncation failure the design exists to kill
            if ruled + n <= HOT_CAP * RULE_SHARE:
                active.append(m["name"])
                used, ruled = used + n, ruled + n
            else:
                dormant.append(m["name"])
        elif retrievability(m, today) < ARCHIVE_R and (today - last).days >= ARCHIVE_DAYS and not inbound[m["name"]]:
            arch.append(m["name"])           # genuine death only: the floor is checked before the budget
        elif used + n <= HOT_CAP:
            active.append(m["name"])
            used += n
        else:
            dormant.append(m["name"])
    return active, dormant, arch


# -- in-session API (fail-open) ---------------------------------------------------------------------------------

def digest(cap: int = HOT_CAP) -> str:
    """The hot memory for the prompt: the compiled HOT.md if the dream wrote one."""
    if not enabled():
        return "memory is switched off"
    try:
        hot = (ROOT / "HOT.md").read_text(encoding="utf-8").strip()
        if len(hot) > cap:
            hot = hot[:cap].rsplit("\n", 1)[0]          # whole lines only
        return hot or "nothing yet: the first dream has not run"
    except OSError:
        return "nothing yet: the first dream has not run"
    except Exception:
        return "nothing loaded"


def recall(query: str, k: int = 6, include_dormant: bool = True, touch: bool = True) -> list[dict]:
    """Best matches for a question. Lexical (idf-weighted) + subject adjacency; R only breaks ties."""
    if not enabled() or not str(query).strip():
        return []
    try:
        mems = load_all()
    except Exception:
        return []
    today = date.today()
    q = str(query)
    ql = q.lower()
    subjects = {(m.get("subject") or "").lower() for m in mems.values()} - {""}
    named = {s for s in subjects if re.search(rf"\b{re.escape(s)}\b", ql)}
    if re.search(r"\b(me|my|i)\b", ql):
        named.add(owner().lower())
    pool = [m for m in mems.values() if live(m) and (m["status"] == "active" or include_dormant)]
    bags = {m["name"]: words(m["description"] + " " + (m.get("subject") or "")) for m in pool}
    df = Counter(w for b in bags.values() for w in b)
    idf = lambda w: math.log((len(pool) + 1) / (df[w] + 0.5))        # noqa: E731 - a word no memory has weighs most
    qw = words(q) - named - words(cfg().get("assistant", "")) - {"remember", "know", "tell", "say", "said",
                                                                  "want", "wants"}
    only_names = not qw and bool(named)        # "what do you know about Sam": the person alone qualifies
    hits = []
    for m in pool:
        b = bags[m["name"]]
        s = sum(idf(w) for w in qw & b) / sum(idf(w) for w in qw) if qw else 0.0
        adj = 1.0 if (m.get("subject") or "").lower() in named else 0.0
        score = 0.72 * s + 0.22 * adj + 0.06 * retrievability(m, today)
        if s >= 0.34 or (only_names and adj):
            hits.append((score, m))
    hits.sort(key=lambda h: h[0], reverse=True)
    # one hop: a strong hit pulls in its linked neighbours (HippoRAG-lite), ranked below it
    out, seen = [], set()
    for score, m in hits[:k]:
        if m["name"] not in seen:
            out.append({**_pub(m, today), "score": round(score, 3)})
            seen.add(m["name"])
    for score, m in hits[:2]:
        for s in m.get("links") or []:
            n = mems.get(s)
            if n and live(n) and s not in seen and len(out) < k + 2:
                out.append({**_pub(n, today), "score": round(score * 0.5, 3), "via": m["name"]})
                seen.add(s)
    if touch and out and writable():
        try:
            with (ROOT / "touches.jsonl").open("a") as f:
                for h in out[:3]:
                    f.write(json.dumps({"t": datetime.now().isoformat(timespec="seconds"), "slug": h["name"],
                                        "q": q[:120]}) + "\n")
        except OSError:
            pass
    return out


def recall_line(query: str) -> str:
    """One prompt-ready line. The abstain instruction is part of the contract: no hit means "I do not know"."""
    hits = recall(query)
    if not hits:
        return "Nothing in memory about that. Say you do not remember; never guess."
    return "From memory (answer only from these; if they do not answer it, say you do not remember): " + \
        " | ".join(f"{h['subject'] + ': ' if h.get('subject') else ''}{h['description']} ({h['type']}, "
                   f"learned {h['learned']})" for h in hits)


def guess_subject(fact: str) -> str:
    """Who a "remember ..." is about: the first configured name in it, else the owner."""
    names = [owner(), *cfg().get("people", []), str(cfg().get("assistant", ""))]
    hits = [(m.start(), n) for n in names if n for m in [re.search(rf"\b{re.escape(n)}\b", fact)] if m]
    return min(hits)[1] if hits else owner()


def add(fact: str, subject: str = "", type_: str = "fact", said_by: str = "owner", salience: int = 4,
        source: str = "live") -> str:
    """File one memory now (the owner said "remember ..."). Returns saved, reinforced, sensitive, off or empty."""
    fact = " ".join(str(fact).split())
    if not fact:
        return "empty"
    if not writable():
        return "off"
    if sensitive(fact):
        return "sensitive"
    try:
        mems = load_all()
        r = _upsert(mems, {"fact": fact, "subject": subject or guess_subject(fact),
                           "type": type_ if type_ in TYPES else "fact",
                           "said_by": said_by, "salience": salience, "relation": "new"},
                    date.today().isoformat(), source, [])
        return r[0]
    except Exception:
        return "off"


def forget(text: str) -> str:
    """Move the best match to Archive as forgotten. Returns what was forgotten, or ''."""
    if not writable():
        return ""
    mems = load_all()
    m = mems.get(text.strip())
    if not m:
        best = max(((match(text, x["description"] + " " + (x.get("subject") or "")), x)
                    for x in mems.values() if live(x)), key=lambda h: h[0], default=(0, None))
        m = best[1] if best[0] >= 0.3 else None
    if not m:
        return ""
    m.update(forgotten=True, status="archived")
    save(m)
    _log_line(date.today().isoformat(), f"🗑️ FORGOT on request: {m['name']}")
    return m["description"]


def _pub(m: dict, today: date) -> dict:
    return {"name": m["name"], "description": m["description"], "type": m.get("type"), "subject": m.get("subject"),
            "status": m.get("status"), "learned": m.get("learned"), "r": round(retrievability(m, today), 3),
            "reinforcements": int(m.get("reinforcements") or 0), "links": m.get("links") or []}


# -- the dream --------------------------------------------------------------------------------------------------

def _keep_re() -> re.Pattern:
    roles = "|".join(re.escape(r) for r in sorted(cfg()["roles"], key=len, reverse=True))
    return re.compile(rf"^- `(\d\d:\d\d(?::\d\d)?)` \*\*({roles}):\*\* (.*)$")


def replay(sessions: list[Path]) -> str:
    """What the extractor may read: the owner's own words, task results, and the assistant's lines for context.
    Any role not in config `roles` (for example unattributed room audio) is left out: never remember overheard
    talk."""
    roles = cfg()["roles"]
    keep = _keep_re()
    out = []
    for s in sessions:
        try:
            rows = (s / "transcript.md").read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        out.append(f"## session {s.name}")
        prev = None
        for r in rows:
            m = keep.match(r)
            if not m:
                continue
            who = roles[m.group(2)]
            text = m.group(3).strip()
            if who == "ASSISTANT" and prev == "ASSISTANT":
                out[-1] += " " + text           # streamed phrases come one per line: join them
            else:
                out.append(f"{who}: {text}")
            prev = who
    return "\n".join(out)


def _norm(s) -> str:
    return " ".join(re.sub(r"[^\w']+", " ", str(s).lower()).split())


def turn_spans(chunk: str) -> tuple[str, str]:
    """(owner turns, task-result turns) of a replay chunk: normalized, one turn per line, space-padded so a
    quote can only match whole words inside a single turn."""
    own, task = [], []
    for ln in chunk.splitlines():
        who, sep, text = ln.partition(": ")
        if not sep:
            continue
        if who.startswith("OWNER"):
            own.append(_norm(text))
        elif who == "TASK RESULT":
            task.append(_norm(text))
    pad = lambda xs: " " + " \n ".join(xs) + " "      # noqa: E731
    return pad(own), pad(task)


def quote_source(cand: dict, own: str, task: str) -> str | None:
    """Where a candidate's `evidence` quote appears: "owner", "task", or None (reject).
    The quote must be copied from ONE owner turn (or one task-result turn), at least 3 words, or the whole
    turn if the turn is shorter. Assistant lines never count: that is how assistant context got attributed
    to the owner (spec 2026-11-10.2, G1)."""
    ev = _norm(cand.get("evidence", ""))
    if not ev:
        return None
    for label, text in (("owner", own), ("task", task)):
        if f" {ev} " not in text:
            continue
        if len(ev.split()) >= 3 or f"\n {ev} \n" in "\n" + text + "\n":
            return label
    return None


EXTRACT_PROMPT = """You are the long-term memory of {assistant}, an AI assistant that works for {owner}. Below are \
transcript lines from conversations on {day}. OWNER lines are {owner} (spoken, typed, texted or on a call). TASK \
RESULT lines are outcomes of jobs the assistant ran. ASSISTANT lines are only context.

Extract what is worth remembering for future conversations: facts about {owner} and the people they mention, their \
preferences, standing rules they gave the assistant ("always", "never", "from now on"), projects in flight, how a \
kind of task went (procedure), and memorable episodes. Only from OWNER and TASK RESULT lines. Skip small talk, \
one-off questions, and anything the assistant said on its own. Skip requests to change the assistant's own code or \
settings: those become code, not memories; a rule is only a standing instruction for how to talk, behave or act. \
Skip anything about health, money, relationships, secrets, credentials or addresses. At most 12 memories; fewer is \
better. Each fact one plain sentence under 25 words, written about the subject ("{owner} prefers ...", "Sam ...").

Existing memories (slug: fact) you may match:
{existing}

Return ONLY JSON: {{"memories": [{{"type": "rule|preference|fact|project|procedure|episode|reference", \
"subject": "{owner}|<name>", "fact": "...", "said_by": "owner|task", \
"salience": 1-5, "relation": "new|same:<slug>|updates:<slug>|contradicts:<slug>", "evidence": "3 to 12 words"}}]}}
`evidence` is REQUIRED: 3 to 12 words copied word for word from ONE OWNER line (or one TASK RESULT line for a \
task outcome), never from an ASSISTANT line. A memory without such a quote is discarded.
Use same:<slug> when it restates an existing memory, updates:<slug> when it changes one over time (a new \
age, a finished project), contradicts:<slug> when it says the opposite.

Transcript:
{text}"""

REFLECT_PROMPT = """You are the long-term memory of an AI assistant, reflecting on a week. Below are memories \
(slug | day | fact). Find at most 3 themes that recur across at least 3 different memories from at least 3 \
different days, and write each as one insight sentence about {owner} that would help the assistant serve them \
better. Nothing about health, money or relationships.
Return ONLY JSON: {{"insights": [{{"subject": "...", "fact": "...", "children": ["slug", ...]}}]}}

{rows}"""


DEFAULT_MODEL_CMD = ["claude", "-p", "--model", "{model}", "--strict-mcp-config", "--setting-sources", ""]


def model_argv() -> list[str]:
    """Config `model_cmd`: argv of any headless model CLI, prompt on stdin, answer on stdout. `{model}` is
    replaced by MEMORY_MODEL or config `model` (default haiku); with no placeholder no model is passed.
    Absent: Claude Code (spec 2026-11-10.4, G15)."""
    cmd = cfg().get("model_cmd") or DEFAULT_MODEL_CMD
    if not isinstance(cmd, list) or not all(isinstance(a, str) for a in cmd):
        raise ValueError("config model_cmd must be a list of strings")
    model = os.environ.get("MEMORY_MODEL") or str(cfg().get("model") or "haiku")
    return [a.replace("{model}", model) for a in cmd]


def _claude(prompt: str, timeout: int = 150) -> dict | None:
    """One headless model call through `model_argv()`, prompt on stdin. Returns parsed JSON or None."""
    if os.environ.get("AGENT_MEMORY_LLM") == "0":
        return None
    try:
        r = subprocess.run(model_argv(), input=prompt, capture_output=True, text=True, timeout=timeout,
                           cwd=str(ROOT))
    except Exception:
        return None
    if r.returncode != 0:
        return None
    txt = r.stdout
    try:
        return json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
    except ValueError:
        return None


LLM = _claude                       # tests replace this


def _existing_block(mems: dict[str, dict], text: str, cap: int = 6000) -> str:
    pool = sorted((m for m in mems.values() if live(m)),
                  key=lambda m: sim(text[:4000], m["description"]) + 0.1 * int(m.get("salience") or 2), reverse=True)
    out, n = [], 0
    for m in pool:
        ln = f"{m['name']}: {m['description']}"
        if n + len(ln) > cap:
            break
        out.append(ln)
        n += len(ln) + 1
    return "\n".join(out) or "(none yet)"


class Dream:
    def __init__(self, day: str, dry: bool = False):
        self.day, self.dry = day, dry
        self.log: list[str] = []
        self.calls = 0
        self.new = self.reinforced = self.superseded = self.archived = self.promoted = self.flagged = 0
        self.dropped = self.links = self.reactivated = self.unquoted = 0

    def say(self, s: str) -> None:
        self.log.append(s)


def _upsert(mems: dict[str, dict], c: dict, day: str, source: str, log: list[str], dream: Dream | None = None,
            dry: bool = False) -> tuple[str, str]:
    fact = " ".join(str(c.get("fact", "")).split())[:240]
    typ = c.get("type") if c.get("type") in TYPES else "fact"
    subj = " ".join(str(c.get("subject") or "").split())[:40] or owner()
    if len(subj.split()) > 3:
        subj = owner()                   # a subject is a person or a thing, not a phrase
    by = c.get("said_by") if c.get("said_by") in TIER else "inferred"
    rel = str(c.get("relation") or "new")
    kind, _, ref = rel.partition(":")
    target = mems.get(ref.strip()) if ref else None
    if not target or not live(target):
        best = max(((sim(fact, m["description"]), m) for m in mems.values() if live(m)),
                   key=lambda h: h[0], default=(0, None))
        if best[0] >= DUP_SIM:
            kind, target = "same", best[1]
        elif kind in ("same", "updates", "contradicts"):
            kind, target = "new", None
    if kind == "same" and target:
        if day not in (target.get("days") or []):
            target["reinforcements"] = int(target.get("reinforcements") or 0) + 1
            target["days"] = sorted({*(target.get("days") or []), day})
        target["last_reinforced"] = max(str(target.get("last_reinforced") or day), day)
        target["sources"] = list(dict.fromkeys([*(target.get("sources") or []), source]))[-12:]
        if TIER.get(by, 1) > TIER.get(target.get("said_by"), 1):
            target["said_by"] = by
        if target.get("status") == "dormant":
            target["status"] = "active"
            if dream:
                dream.reactivated += 1
        if not dry:
            save(target)
        log.append(f"🔁 reinforced {target['name']} (x{target['reinforcements']})")
        if dream:
            dream.reinforced += 1
        return "reinforced", target["name"]
    m = {"name": slugify(f"{subj} {fact}", mems), "description": fact, "type": typ, "subject": subj, "said_by": by,
         "salience": max(1, min(5, int(c.get("salience") or 3))), "learned": day, "last_reinforced": day,
         "reinforcements": 0, "status": "active", "sources": [source], "days": [day], "links": [],
         "evidence": str(c.get("evidence") or "")[:120]}
    if kind in ("updates", "contradicts") and target:
        newer_ok = day >= str(target.get("learned") or "")
        tier_ok = TIER.get(by, 1) >= TIER.get(target.get("said_by"), 1)
        if kind == "updates" or (newer_ok and tier_ok):
            target.update(status="superseded", superseded_by=m["name"], valid_to=day)
            m["supersedes"] = target["name"]
            m["reinforcements"] = min(int(target.get("reinforcements") or 0), 3)   # the topic keeps its history
            if not dry:
                save(target)
            log.append(f"♻️ {kind}: {target['name']} superseded by {m['name']}")
            if dream:
                dream.superseded += 1
        else:
            log.append(f"⚠️ contradiction kept both: {m['name']} vs {target['name']} (lower source tier)")
            if dream:
                dream.flagged += 1
    mems[m["name"]] = m
    if not dry:
        save(m)
    log.append(f"✨ new {typ}: {m['name']}: {fact}")
    if dream:
        dream.new += 1
    return "saved", m["name"]


def _state() -> dict:
    try:
        return json.loads((ROOT / "state.json").read_text())
    except (OSError, ValueError):
        return {}


def _sessions_by_day(state: dict, until: str | None = None) -> dict[str, list[Path]]:
    done = state.get("replayed") or {}
    out: dict[str, list[Path]] = defaultdict(list)
    for s in sorted(SESSIONS.glob("*/transcript.md")) if SESSIONS.is_dir() else []:
        d = s.parent.name[:10]
        if until and d > until:
            continue
        if done.get(s.parent.name) == s.stat().st_size:
            continue                      # replayed already, and unchanged since
        out[d].append(s.parent)
    return dict(sorted(out.items()))


def dream(day: str | None = None, sessions: list[Path] | None = None, dry: bool = False,
          reflect: bool | None = None) -> dict:
    """One dream. Without `sessions`, it replays every session not yet replayed (a missed night is folded in)."""
    # an early-morning run dreams about the day before (its history row and learned dates belong to that day)
    day = day or (date.today() - timedelta(days=1 if datetime.now().hour < 12 else 0)).isoformat()
    if not enabled():
        return {"skipped": "memory is switched off"}
    if cfg().get("readonly") and not dry:
        return {"skipped": "memory is frozen (readonly)"}
    c = cfg()
    ph = c["phases"]
    D = Dream(day, dry)
    lock = ROOT / ".dreaming"
    ROOT.mkdir(parents=True, exist_ok=True)
    if lock.exists() and time.time() - lock.stat().st_mtime < 3600 and not dry:
        return {"skipped": "another dream is running"}
    if not dry:
        lock.write_text(str(os.getpid()))
    t0 = time.time()
    try:
        state = _state()
        mems = load_all()
        before = {k: v.get("status") for k, v in mems.items()}
        today = _d(day)
        if sessions is None:
            sessions = [s for ss in _sessions_by_day(state, day).values() for s in ss]
        # 1 REPLAY
        text = replay(sessions) if ph["replay"] else ""
        D.say(f"## 1 Replay\n{len(sessions)} session(s), {len(text):,} chars of owner words and task results")
        # 2 EXTRACT + 3 CONSOLIDATE (+ 5 CONTRADICT inside the upsert)
        D.say("## 2-3 Extract and consolidate")
        if ph["extract"] and text.strip():
            chunks = [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)]
            for ch in chunks:
                if D.calls >= int(c.get("budget_calls") or 14):
                    D.say(f"budget reached ({D.calls} calls); the rest waits for the next dream")
                    break
                D.calls += 1
                out = LLM(EXTRACT_PROMPT.format(day=day, owner=owner(), assistant=c.get("assistant", "Assistant"),
                                                existing=_existing_block(mems, ch), text=ch))
                own, task = turn_spans(ch)
                for cand in (out or {}).get("memories") or []:
                    if not isinstance(cand, dict) or not str(cand.get("fact", "")).strip():
                        continue
                    if sensitive(cand.get("fact")):
                        D.dropped += 1
                        continue
                    src = quote_source(cand, own, task)
                    if src is None:
                        D.unquoted += 1
                        D.say(f"🚫 no owner or task quote, dropped: {str(cand.get('fact'))[:90]}")
                        continue
                    cand["said_by"] = src          # the quote decides attribution, not the model's claim
                    if not ph["contradict"] and str(cand.get("relation", "")).startswith("contradicts"):
                        cand["relation"] = "new"
                    if ph["consolidate"]:
                        _upsert(mems, cand, day, f"dream:{day}", D.log, D, dry)
                if out is None:
                    D.say("⚠️ extract call failed; those sessions will be replayed again next dream")
                    sessions = []        # do not mark them replayed
                    break
        if D.dropped:
            D.say(f"🔒 dropped {D.dropped} sensitive candidate(s) unread")
        # touches since the last dream are rehearsal (MemoryBank): one reinforcement per memory per day
        tf = ROOT / "touches.jsonl"
        touched = set()
        if tf.exists():
            for ln in tf.read_text().splitlines():
                try:
                    t = json.loads(ln)
                except ValueError:
                    continue
                if t.get("t", "")[:10] <= day and t.get("t", "") > state.get("touched_until", ""):
                    touched.add((t["slug"], t["t"][:10]))
            for slug, d in sorted(touched):
                m = mems.get(slug)
                if m and live(m) and d not in (m.get("days") or []):
                    m["reinforcements"] = int(m.get("reinforcements") or 0) + 1
                    m["days"] = sorted({*(m.get("days") or []), d})
                    m["last_reinforced"] = max(str(m.get("last_reinforced") or d), d)
                    if not dry:
                        save(m)
                    D.say(f"🔁 recalled in conversation, reinforced {slug}")
                    D.reinforced += 1
        # promotion: an episode seen on 3+ days, the oldest a day back, becomes a fact (episodic -> semantic)
        if ph["consolidate"]:
            for m in mems.values():
                if live(m) and m.get("type") == "episode" and len(m.get("days") or []) >= 3 \
                        and (today - _d(m.get("learned"))).days >= 1:
                    m["type"] = "fact"
                    D.promoted += 1
                    D.say(f"⬆️ promoted episode to fact: {m['name']}")
                    if not dry:
                        save(m)
        # 4 LINK (A-MEM): memories touched this dream wire to their nearest neighbours, both ways
        if ph["link"]:
            D.say("## 4 Link")
            changed = [m for m in mems.values() if live(m) and day in (m.get("days") or [])]
            for m in changed:
                near = sorted(((sim(m["description"], o["description"]) +
                                (0.12 if o.get("subject") == m.get("subject") else 0), o)
                               for o in mems.values() if live(o) and o["name"] != m["name"]),
                              key=lambda h: h[0], reverse=True)[:LINK_K]
                for score, o in near:
                    if score < LINK_MIN:
                        continue
                    for a, b in ((m, o), (o, m)):
                        if b["name"] not in (a.get("links") or []):
                            a["links"] = [*(a.get("links") or []), b["name"]][-8:]
                            D.links += 1
                            if not dry:
                                save(a)
            D.say(f"{D.links} new link end(s)")
        # 7 REFLECT, weekly (Sunday, or 7 days since the last one)
        last_ref = state.get("reflected") or "2000-01-01"
        do_ref = ph["reflect"] and (reflect if reflect is not None else
                                    (today.weekday() == 6 or (today - _d(last_ref)).days >= 7))
        if do_ref and D.calls < int(c.get("budget_calls") or 14) + 1:
            wk = sorted((m for m in mems.values() if live(m) and m.get("type") != "insight"
                         and (today - _d(m.get("last_reinforced") or m.get("learned"))).days <= 7),
                        key=lambda m: m.get("learned") or "")
            if len(wk) >= 3 and len({d for m in wk for d in (m.get("days") or [])}) >= 3:
                D.calls += 1
                rows = "\n".join(f"{m['name']} | {(m.get('days') or [m.get('learned')])[-1]} | {m['description']}"
                                 for m in wk[-120:])
                out = LLM(REFLECT_PROMPT.format(owner=owner(), rows=rows)) or {}
                D.say("## 7 Reflect")
                for ins in (out.get("insights") or [])[:3]:
                    kids = [s for s in ins.get("children") or [] if s in mems]
                    kdays = {d for s in kids for d in (mems[s].get("days") or [])}
                    if len(kids) < 3 or len(kdays) < 3 or sensitive(ins.get("fact", "")):
                        D.say(f"insight dropped (needs 3 children from 3 days): {str(ins.get('fact'))[:80]}")
                        continue
                    r, slug = _upsert(mems, {**ins, "type": "insight", "said_by": "inferred", "salience": 3,
                                             "relation": "new"}, day, f"reflect:{day}", D.log, D, dry)
                    new = mems[slug]
                    new["links"] = list(dict.fromkeys([*(new.get("links") or []), *kids]))[:8]
                    for k in kids:               # provenance edges both ways: the children point at their insight
                        mems[k]["links"] = list(dict.fromkeys([*(mems[k].get("links") or []), slug]))[-8:]
                        if not dry:
                            save(mems[k])
                    if not dry:
                        save(new)
                state["reflected"] = day
        # 6 DECAY + tiering
        if ph["decay"]:
            D.say("## 6 Decay")
            active, dormant, arch = tiers(mems, today)
            for s in active:
                mems[s]["status"] = "active"
            for s in dormant:
                mems[s]["status"] = "dormant"
            for s in arch:
                mems[s]["status"] = "archived"
                D.archived += 1
                D.say(f"🪦 archived {s} (R {retrievability(mems[s], today):.3f}, untouched 180d+, no inbound links)")
            moved = 0
            for s, m in mems.items():
                if before.get(s) != m.get("status") and m.get("status") in ("active", "dormant", "archived"):
                    if before.get(s) in ("active", "dormant") and m["status"] in ("active", "dormant"):
                        D.say(f"{'⬆️' if m['status'] == 'active' else '⬇️'} {s}: {before[s]} -> {m['status']}")
                    moved += 1
                    if not dry:
                        save(m)
            D.say(f"{moved} tier change(s)")
        # 8 COMPILE
        snap = snapshot(mems, today)
        snap.update(date=day, new=D.new, reinforced=D.reinforced, superseded_today=D.superseded,
                    archived_today=D.archived, retired_today=D.superseded + D.archived, promoted=D.promoted,
                    flagged=D.flagged, links_added=D.links, calls=D.calls, sessions=len(sessions),
                    unquoted=D.unquoted,
                    secs=round(time.time() - t0, 1))
        if not dry and ph["compile"]:
            hot = [line(mems[s]) for s in sorted((s for s in mems if mems[s].get("status") == "active"),
                                                 key=lambda s: rank_key(mems[s], today), reverse=True)]
            _atomic(ROOT / "HOT.md", "\n".join(hot) + ("\n" if hot else ""))
            hist = [h for h in history() if h.get("date") != day]
            _atomic(ROOT / "history.jsonl", "".join(json.dumps(h) + "\n" for h in [*hist, snap]))
            for s in sessions:
                (state.setdefault("replayed", {}))[s.name] = (s / "transcript.md").stat().st_size
            if touched:
                state["touched_until"] = max(t for _, t in touched) + "T23:59:59"
            state["last_dream"] = datetime.now().isoformat(timespec="seconds")
            _atomic(ROOT / "state.json", json.dumps(state, indent=1))
            head = (f"# Dream {day}\n\n{snap['nodes']} live memories ({snap['active']} active, {snap['dormant']} "
                    f"dormant), {snap['retired']} retired in all. Tonight: {D.new} new, {D.reinforced} reinforced, "
                    f"{D.superseded} superseded, {D.archived} archived, {D.promoted} promoted, {D.links} link ends, "
                    f"{D.unquoted} dropped without a quote, "
                    f"{D.calls} model call(s), {snap['secs']} s.\n\n")
            _atomic(ROOT / "Dreams" / f"{day}.md", head + "\n".join(D.log) + "\n")
        return {**snap, "log": D.log}
    finally:
        if not dry and lock.exists():
            lock.unlink()


def _log_line(day: str, text: str) -> None:
    p = ROOT / "Dreams" / f"{day}.md"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(text + "\n")
    except OSError:
        pass


def snapshot(mems: dict[str, dict], today: date) -> dict:
    st = Counter(m.get("status") for m in mems.values() if not m.get("forgotten"))
    live_m = [m for m in mems.values() if live(m)]
    edges = {tuple(sorted((m["name"], s))) for m in live_m for s in m.get("links") or [] if s in mems}
    return {"nodes": len(live_m), "active": st["active"], "dormant": st["dormant"], "archived": st["archived"],
            "superseded": st["superseded"], "retired": st["archived"] + st["superseded"], "edges": len(edges),
            "total": len(mems), "subjects": len({m.get("subject") for m in live_m}),
            "by_type": dict(Counter(m.get("type") for m in live_m)),
            "mean_r": round(sum(retrievability(m, today) for m in live_m) / len(live_m), 3) if live_m else None}


def history() -> list[dict]:
    try:
        return [json.loads(x) for x in (ROOT / "history.jsonl").read_text().splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


def backfill(dry: bool = False) -> list[dict]:
    """One dream per past day with sessions, oldest first, so the history graphs start with real data."""
    out = []
    for day, ss in _sessions_by_day(_state()).items():
        if day >= date.today().isoformat():
            continue
        r = dream(day, ss, dry=dry)
        out.append({k: r.get(k) for k in ("date", "nodes", "new", "reinforced", "retired_today", "calls", "skipped")})
        print(json.dumps(out[-1]), flush=True)
    return out


# -- views: graph explorer and dashboard data --------------------------------------------------------------------

def explore(query: str = "", cap: int = 11_000) -> dict:
    """Nodes, edges and stats for a graph widget, cut to fit `cap` bytes of JSON.
    With a query, the best matches and their neighbours come first and are marked `f`."""
    mems = load_all()
    today = date.today()
    focus = {h["name"] for h in recall(query, k=10, touch=False)} if query.strip() else set()
    pool = sorted((m for m in mems.values() if not m.get("forgotten")),
                  key=lambda m: (m["name"] in focus, live(m), rank_key(m, today)), reverse=True)
    snap = snapshot(mems, today)
    last = (history() or [{}])[-1]
    n = len(pool)
    while True:
        keep = pool[:n]
        idx = {m["name"]: i for i, m in enumerate(keep)}
        nodes = [{"l": m["description"][:90], "t": m.get("type"), "s": m.get("subject") or "",
                  "r": round(retrievability(m, today), 2),
                  "st": {"dormant": "d", "superseded": "s", "archived": "x"}.get(m.get("status"), "a"),
                  "n": int(m.get("reinforcements") or 0), "d": m.get("learned") or "",
                  **({"f": 1} if m["name"] in focus else {})} for m in keep]
        edges = sorted({tuple(sorted((idx[m["name"]], idx[s]))) for m in keep for s in m.get("links") or []
                        if s in idx})
        props = {"q": query[:80], "nodes": nodes, "edges": [list(e) for e in edges],
                 "stats": {k: snap[k] for k in ("nodes", "active", "dormant", "retired", "edges")},
                 "dream": last.get("date") or "", "shown": len(keep), "of": len(pool)}
        if len(json.dumps(props, ensure_ascii=False).encode()) <= cap or n <= 5:
            return props
        n = int(n * 0.85)


def dash() -> dict:
    """Dashboard block: current snapshot, nightly series (node count, retirements), last dream log, top memories."""
    if not enabled():
        return {"off": True}
    mems = load_all()
    today = date.today()
    snap = snapshot(mems, today)
    hist = history()
    last = hist[-1] if hist else None
    log = []
    if last:
        try:
            log = [x for x in (ROOT / "Dreams" / f"{last['date']}.md").read_text().splitlines()
                   if x[:1] not in ("#", "") and not x.startswith(("1 session", "0 session"))][-14:]
        except OSError:
            pass
    top = sorted((m for m in mems.values() if live(m)), key=lambda m: rank_key(m, today), reverse=True)[:8]
    subj = Counter(m.get("subject") or "?" for m in mems.values() if live(m)).most_common(8)
    return {"now": snap, "series": hist[-120:], "last": last, "log": log, "subjects": subj,
            "top": [{"s": m.get("subject"), "t": m.get("type"), "d": m["description"], "n": m.get("reinforcements", 0)}
                    for m in top],
            "frozen": bool(cfg().get("readonly")), "state": _state().get("last_dream")}


def last_dream_line() -> str:
    """For "what did you dream about": the last dream's headline and a few of its changes."""
    h = history()
    if not h:
        return "No dream has run yet."
    last = h[-1]
    try:
        rows = [x for x in (ROOT / "Dreams" / f"{last['date']}.md").read_text().splitlines()
                if x.startswith(("✨", "♻️", "⬆️", "🪦"))][:6]
    except OSError:
        rows = []
    return (f"Last dream {last['date']}: {last.get('new', 0)} new memories, {last.get('reinforced', 0)} "
            f"reinforced, {last.get('retired_today', 0)} retired; {last.get('nodes', 0)} held in all. "
            + (" Changes: " + " | ".join(r.split(": ", 2)[-1] for r in rows) if rows else ""))


# -- CLI --------------------------------------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    arg = " ".join(a for a in argv[1:] if not a.startswith("--"))
    if cmd == "status":
        c, s = cfg(), _state()
        snap = snapshot(load_all(), date.today())
        print(json.dumps({"enabled": enabled(), "readonly": c.get("readonly"), "phases": c["phases"],
                          "last_dream": s.get("last_dream"), "root": str(ROOT), **snap}, indent=1))
    elif cmd == "dream":
        r = dream(dry="--dry-run" in argv, reflect=True if "--reflect" in argv else None)
        print("\n".join(r.pop("log", [])))
        print(json.dumps(r, indent=1))
    elif cmd == "backfill":
        backfill(dry="--dry-run" in argv)
    elif cmd == "recall":
        print(json.dumps(recall(arg, touch=False), indent=1, ensure_ascii=False))
    elif cmd == "add":
        print(add(arg, type_="rule" if "--rule" in argv else "fact"))
    elif cmd == "show":
        print(digest())
    elif cmd == "dreams":
        n = int(arg or 1)
        for p in sorted((ROOT / "Dreams").glob("*.md"))[-n:]:
            print(p.read_text())
    elif cmd == "forget":
        print(forget(arg) or "no match")
    elif cmd == "purge":
        for folder in ("Store", "Archive"):
            p = ROOT / folder / f"{arg}.md"
            if p.exists():
                p.unlink()
                print(f"deleted {p}")
    elif cmd in ("on", "off"):
        (ROOT / ".disabled").unlink(missing_ok=True) if cmd == "on" else None
        print(json.dumps(set_cfg(enabled=cmd == "on")))
    elif cmd in ("freeze", "thaw"):
        print(json.dumps(set_cfg(readonly=cmd == "freeze")))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
