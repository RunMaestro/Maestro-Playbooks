"""
memstore.py: shared access to the agent's fact store (L2) and its index (L1).

The store is `Agent/Memory/Store/` (every Claude account's harness memory path is
a symlink to it). One memory per file, harness format:

    ---
    name: feedback-no-emdash
    description: one line, used to decide relevance
    metadata:
      node_type: memory
      type: feedback            # user | feedback | project | reference
      said_by: <OWNER_KEY>      # OWNER_KEY | inferred | task   (added 2026-11-10)
      sources: ["journal:2026-11-09"]
      verified: 2026-11-10      # last time every path it names resolved
      decision: true            # decision records only
      status: active            # active | superseded
      supersedes: other-slug
      reopen_if: "after:2027-01-01"
    ---
    body

`MEMORY.md` is the always-loaded core index; `index_*.md` are section indexes.

Switches (fail-open: anything wrong means OFF, never a broken caller):
  `AGENT_MEMORY=0` or a `Agent/Memory/.disabled` file beats everything;
  `Agent/Memory/config.json` holds `enabled`, `readonly` and one block per layer.

Used by memory_promote.py, memory_lint.py, memory_smoke.py.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

VAULT = Path(os.environ.get("AGENT_VAULT", "~/Vault")).expanduser()
AGENT_DIR = os.environ.get("AGENT_DIR", "Agent")       # the agent's own folder in the vault
STATE = Path(os.environ.get("AGENT_MEMORY_STATE", "~/.config/agent-memory")).expanduser()
AGENT = VAULT / AGENT_DIR
MEMDIR = AGENT / "Memory"
CONFIG = MEMDIR / "config.json"
PROMOTIONS = MEMDIR / "Promotions"
DEFAULT_STORE_DIR = "Store"


def _store_dir() -> Path:
    """The fact store: config `store_dir`, relative to the Memory folder (or absolute); default `Store`, and
    `"."` means a flat Memory folder. Read once at import. Explicit only: no layout is guessed (spec 2026-11-10.5,
    G18). MEMORY.md lives in this folder; a missing folder makes every job report it, not fall back."""
    try:
        raw = json.loads(CONFIG.read_text()).get("store_dir")
    except Exception:
        raw = None
    p = Path(str(raw or DEFAULT_STORE_DIR)).expanduser()
    return p if p.is_absolute() else (MEMDIR / p)


STORE = _store_dir()
TZ = ZoneInfo(os.environ.get("AGENT_TZ", "UTC"))     # set AGENT_TZ to your zone

CORE_INDEX = STORE / "MEMORY.md"
# The `said_by` value for "the owner said it". The vault predates the generic name.
OWNER_KEY = "owner"
TYPES = ("user", "feedback", "project", "reference")
FM_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.S)


def today() -> str:
    return dt.datetime.now(TZ).strftime("%Y-%m-%d")


# ---------- switches ----------

def config() -> dict:
    try:
        return json.loads(CONFIG.read_text())
    except Exception:
        return {"enabled": False, "_error": "config unreadable"}


def layer_on(layer: str | None = None) -> tuple[bool, str]:
    """(on, why). Fail-open: any doubt means off."""
    if os.environ.get("AGENT_MEMORY") == "0":
        return False, "AGENT_MEMORY=0"
    if (MEMDIR / ".disabled").exists():
        return False, ".disabled file present"
    cfg = config()
    if cfg.get("_error"):
        return False, cfg["_error"]
    if not cfg.get("enabled", False):
        return False, "config enabled=false"
    if layer and not cfg.get(layer, {}).get("enabled", False):
        return False, f"{layer}.enabled=false"
    return True, "on"


def readonly() -> bool:
    return bool(config().get("readonly", False))


def names() -> tuple[str, str]:
    """(owner, agent) display names used in model prompts."""
    cfg = config()
    return cfg.get("owner", "the owner"), cfg.get("agent", "the agent")


# ---------- model call ----------
# Config `model_cmd`: the argv of any headless model CLI, prompt on stdin, answer on stdout. `{model}` in an
# argument is replaced by the job's model name; with no placeholder the model name is not passed. Absent: the
# default below (Claude Code). Spec 2026-11-10.4, G15.
DEFAULT_MODEL_CMD = ["claude", "-p", "--model", "{model}"]


def model_argv(model: str) -> list[str] | None:
    """The configured model command for `model`, or None when the config sets none (use the default)."""
    cmd = config().get("model_cmd")
    if not cmd:
        return None
    if not isinstance(cmd, list) or not all(isinstance(a, str) for a in cmd):
        raise ValueError("config model_cmd must be a list of strings")
    return [a.replace("{model}", model) for a in cmd]


def model_call(prompt: str, model: str, *, timeout: int = 600, cwd: str | None = None, label: str = "",
               log_fn=None):
    """One headless model call -> CompletedProcess (stdout = the answer). Prompt goes on stdin."""
    import subprocess
    argv = model_argv(model)
    if argv is None:
        return _default_model_call(prompt, model, timeout=timeout, cwd=cwd, label=label, log_fn=log_fn)
    return subprocess.run(argv, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=cwd)


def _default_model_call(prompt, model, *, timeout, cwd, label, log_fn):
    """Headless Claude Code, prompt on stdin."""
    import subprocess
    argv = [a.replace("{model}", model) for a in DEFAULT_MODEL_CMD]
    return subprocess.run(argv, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=cwd)


# ---------- records ----------

@dataclass
class Memory:
    slug: str            # filename stem
    path: Path
    name: str
    description: str
    type: str
    meta: dict = field(default_factory=dict)
    body: str = ""

    @property
    def filename(self) -> str:
        return self.path.name


def is_index(p: Path) -> bool:
    return p.name == "MEMORY.md" or p.name.startswith("index_")


def parse(path: Path) -> Memory | None:
    try:
        text = path.read_text()
    except Exception:
        return None
    m = FM_RE.match(text)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
        if not isinstance(fm, dict):
            raise ValueError("front matter is not a mapping")
    except Exception:
        # The harness writes loose YAML (unquoted colons in descriptions). Read it
        # the way the harness does: top-level `key: value`, then indented metadata.
        fm = _lenient(m.group(1))
    meta = fm.get("metadata") or {}
    if not isinstance(meta, dict):
        meta = {}
    return Memory(
        slug=path.stem, path=path,
        name=str(fm.get("name", path.stem)),
        description=str(fm.get("description", "")),
        type=str(meta.get("type") or fm.get("type") or ""),
        meta=meta, body=text[m.end():],
    )


def load_all() -> list[Memory]:
    out = []
    for p in sorted(STORE.glob("*.md")):
        if is_index(p):
            continue
        mem = parse(p)
        if mem:
            out.append(mem)
    return out


def _lenient(fm_text: str) -> dict:
    out: dict = {}
    meta: dict = {}
    in_meta = False
    for ln in fm_text.split("\n"):
        if not ln.strip():
            continue
        if not ln.startswith(" "):
            k, _, v = ln.partition(":")
            in_meta = k.strip() == "metadata" and not v.strip()
            if not in_meta:
                out[k.strip()] = v.strip().strip('"')
        elif in_meta:
            k, _, v = ln.strip().partition(":")
            v = v.strip()
            try:
                meta[k.strip()] = yaml.safe_load(v) if v else None
            except Exception:
                meta[k.strip()] = v.strip('"')
    out["metadata"] = meta
    return out


def _scalar(v) -> str:
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    s = str(v)
    if re.fullmatch(r"[A-Za-z0-9_./@+-]+", s) and s.lower() not in ("true", "false", "null", "yes", "no"):
        return s
    return json.dumps(s, ensure_ascii=False)


def set_meta(path: Path, updates: dict) -> bool:
    """Set keys under `metadata:` by text edit, leaving every other byte alone.
    Returns True if the file changed."""
    text = path.read_text()
    m = FM_RE.match(text)
    if not m:
        return False
    lines = m.group(1).split("\n")
    try:
        mi = next(i for i, ln in enumerate(lines) if ln.rstrip() == "metadata:")
    except StopIteration:
        lines.append("metadata:")
        mi = len(lines) - 1
    end = mi + 1
    while end < len(lines) and (lines[end].startswith("  ") or not lines[end].strip()):
        end += 1
    block = lines[mi + 1:end]
    indent = next((len(b) - len(b.lstrip(" ")) for b in block if b.strip()), 2)
    pad = " " * indent
    for k, v in updates.items():
        new = f"{pad}{k}: {_scalar(v)}"
        for i, ln in enumerate(block):
            if re.match(rf"{pad}{re.escape(k)}:", ln):
                block[i] = new
                break
        else:
            block.append(new)
    lines[mi + 1:end] = block
    out = "---\n" + "\n".join(lines) + "\n---\n" + text[m.end():]
    if out == text:
        return False
    path.write_text(out)
    return True


def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return s[:70] or "memory"


def write_new(slug: str, name: str, description: str, mtype: str, body: str,
              meta: dict) -> Path:
    """Create a new memory file. Never overwrites: a taken slug gets a suffix."""
    assert mtype in TYPES, mtype
    path = STORE / f"{slug}.md"
    n = 2
    while path.exists():
        path = STORE / f"{slug}_{n}.md"
        n += 1
    md = {"node_type": "memory", "type": mtype, **meta}
    fm = ["---", f"name: {_scalar(name)}", f"description: {_scalar(description)}", "metadata:"]
    fm += [f"  {k}: {_scalar(v)}" for k, v in md.items()]
    fm.append("---")
    path.write_text("\n".join(fm) + "\n\n" + body.strip() + "\n")
    return path


# ---------- index ----------

POINTER_RE = re.compile(r"\]\(([^)\s]+\.md)\)")


def promoted_shard() -> Path:
    """Where promotion indexes new memories. Config `promote.promoted_shard`, relative to the Memory folder
    (or absolute); default `index_promoted.md` inside the store folder, so `<store_dir>/index_promoted.md`
    (spec 2026-11-10.3 G11; default follows `store_dir` since 2026-11-10.5 G18)."""
    rel = (config().get("promote") or {}).get("promoted_shard")
    if not rel:
        return STORE / "index_promoted.md"
    p = Path(str(rel)).expanduser()
    return p if p.is_absolute() else MEMDIR / p


def shard_pointer(shard: Path) -> str:
    """The link target MEMORY.md must use for a shard: its path relative to MEMORY.md's folder."""
    return os.path.relpath(shard, CORE_INDEX.parent)


def has_core_pointer(shard: Path) -> bool:
    """True when MEMORY.md has a pointer line `[...](<shard>)` to this shard (spec 2026-11-10.3, G8)."""
    try:
        return shard_pointer(shard) in POINTER_RE.findall(CORE_INDEX.read_text())
    except OSError:
        return False


def index_files() -> list[Path]:
    out = [CORE_INDEX] + sorted(STORE.glob("index_*.md"))
    ps = promoted_shard()
    if ps.exists() and ps not in out:
        out.append(ps)
    return out


def shards() -> dict[str, Path]:
    """{'tooling': Path(index_tooling.md), ..., 'promoted': the configured promoted shard if it exists}"""
    out = {p.stem[len("index_"):]: p for p in STORE.glob("index_*.md")}
    out.pop("promoted", None)
    ps = promoted_shard()
    if ps.exists():
        out["promoted"] = ps
    return out


def norm_quote(s) -> str:
    """Quote normalizer shared with memory.py (G1): lowercase, every non-word run becomes one space."""
    return " ".join(re.sub(r"[^\w']+", " ", str(s).lower()).split())


# Credentials that must never reach a model or a memory file (spec 2026-11-10.4, G13). Line-level: a line with a
# match is dropped whole, so a quote of it can never pass the G10 check.
# Each entry: (name, pattern). The names are what tests and logs use; spec 2026-11-10.5 (G16) added the last group.
SECRET_PATTERNS = [
    ("sk-key", r"\bsk-[A-Za-z0-9_-]{16,}"),                     # sk- family, includes sk-ant- and sk-proj-
    ("github-classic", r"\bgh[pousr]_[A-Za-z0-9]{20,}"),         # ghp_ gho_ ghs_ ghu_ ghr_
    ("github-fine-grained", r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    ("cloud-key-id", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ("chat-token", r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    ("chat-webhook", r"hooks\.slack\.com/services/[A-Za-z0-9/_-]{10,}"),
    ("pem-private-key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("bearer", r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}"),
    # G19 (2026-11-10.6): an authorization header or assignment, any scheme or none, `:` or `=`, quotes allowed
    ("authorization", r"\bauthorization\b[\"']?\s*[:=]\s*[\"']?(?:[A-Za-z][A-Za-z0-9_-]*\s+)?[^\s\"']{6,}"),
    ("assignment", r"\b(?:api[_-]?key|secret|token|passw(?:or)?d)\b\s*[:=]\s*\S{6,}"),
    ("secret-gist-url", r"gist\.github(?:usercontent)?\.com/(?:[A-Za-z0-9-]+/)?[0-9a-f]{20,40}\b"),
    ("google-api-key", r"\bAIza[0-9A-Za-z_-]{30,}"),
    ("payments-key", r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}"),
    ("gitlab-token", r"\bglpat-[A-Za-z0-9_-]{20,}"),
    ("npm-token", r"\bnpm_[A-Za-z0-9]{30,}"),
    ("jwt", r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    ("url-credentials", r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]{3,}@"),
]
SECRET_RE = re.compile("(" + "|".join(p for _, p in SECRET_PATTERNS) + ")", re.I)


def redact(text: str, off_limits: re.Pattern | None = None) -> tuple[str, dict]:
    """(text with every off-limits or secret line replaced by a marker, counts). Run on every source before it
    reaches the model; the candidate filter applies the same two rules afterwards."""
    out, n = [], {"off_limits": 0, "secret": 0}
    for ln in str(text).splitlines():
        if off_limits is not None and off_limits.search(ln):
            out.append("[redacted: off-limits]")
            n["off_limits"] += 1
        elif SECRET_RE.search(ln):
            out.append("[redacted: secret]")
            n["secret"] += 1
        else:
            out.append(ln)
    return "\n".join(out), n


def quote_in(quote: str, text: str) -> bool:
    """True when `quote` appears in `text` after normalizing both, on whole-word boundaries and inside one line.
    At least 3 words, or a whole line if that line is shorter (spec 2026-11-10.3, G10; same rule as G1)."""
    q = norm_quote(quote)
    if not q:
        return False
    lines = [norm_quote(ln) for ln in str(text).splitlines()]
    for ln in lines:
        if f" {q} " in f" {ln} " and (len(q.split()) >= 3 or q == ln):
            return True
    return False


def indexed_filenames() -> set[str]:
    out = set()
    for p in index_files():
        try:
            out.update(POINTER_RE.findall(p.read_text()))
        except Exception:
            pass
    return out


def add_pointer(shard: str, title: str, filename: str, hook: str) -> Path:
    """Append one pointer line to a section index and bump its count in MEMORY.md."""
    sh = shards()
    target = sh.get(shard) or sh.get("promoted")
    if target is None:
        raise ValueError(f"no shard {shard!r}")
    line = f"- [{title}]({filename}): {hook}"
    text = target.read_text().rstrip("\n") + "\n" + line + "\n"
    target.write_text(text)
    core = CORE_INDEX.read_text()
    pat = re.compile(rf"(\]\({re.escape(shard_pointer(target))}\) \()(\d+)(\))")
    core2 = pat.sub(lambda m: f"{m.group(1)}{int(m.group(2)) + 1}{m.group(3)}", core, count=1)
    if core2 != core:
        CORE_INDEX.write_text(core2)
    return target


# ---------- recall (lexical, idf-weighted) ----------

STOP = set("a an and are as at be by for from has have how i in is it of on or that the this to was were what when where which who why with you your my me do does did not no".split())


def tokens(s: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9][a-z0-9'_-]{1,}", s.lower()) if t not in STOP]


def recall(query: str, mems: list[Memory] | None = None, k: int = 5) -> list[tuple[float, Memory]]:
    """Score = sum of idf over query terms found, weighted 3x in name/description,
    normalised by the query's total idf. 0..~1. Pure function, no side effects."""
    mems = mems if mems is not None else load_all()
    docs = []
    for m in mems:
        head = set(tokens(m.name.replace("-", " ") + " " + m.description))
        body = set(tokens(m.body))
        docs.append((m, head, body))
    n = len(docs) or 1
    df: dict[str, int] = {}
    for _, h, b in docs:
        for t in h | b:
            df[t] = df.get(t, 0) + 1
    q = list(dict.fromkeys(tokens(query)))
    if not q:
        return []
    idf = {t: math.log((n + 1) / (df.get(t, 0) + 0.5)) for t in q}
    total = sum(idf.values()) * 3 or 1.0
    scored = []
    for m, h, b in docs:
        s = sum(idf[t] * (3 if t in h else 1) for t in q if t in h or t in b)
        if s > 0:
            scored.append((s / total, m))
    scored.sort(key=lambda x: -x[0])
    return scored[:k]
