"""Tests for the L2 jobs: memory_promote.py and memory_smoke.py (spec 2026-11-10.3: G4, G7, G8, G9, G10, G11).

Every test builds a throwaway vault in a temp dir, points AGENT_VAULT / AGENT_MEMORY_STATE at it, and stubs the
model call. Nothing touches a real store and nothing calls a model.

Run: python3 test_memory_jobs.py   (or pytest test_memory_jobs.py). Needs PyYAML, like memstore.py.
Spec 2026-11-10.4 adds G12 (Maestro CLI resolution), G13 (redaction before the model), G14 (journal glob) and
G15 (model_cmd with a stub command). 2026-11-10.5 adds G16 (one test per credential pattern, synthetic values
built at run time so this file holds nothing token-shaped), G17 (CLI that exits non-zero) and G18 (store_dir).
2026-11-10.6 adds G19 (authorization header or assignment, each form tested).
2026-11-10.7 adds G21 (`"model": null` means the default model) and G22 (no vault-only tag in the Promotions log).
2026-11-10.8 adds G23 (the smoke judge sees a memory past its first 1200 characters).
2026-11-10.9 adds G24 (smoke null model), G25 (lint without MEMORY.md), G26 and G27 (link_store), G28 (external shard in the index check).
"""
import importlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

DAY = "2026-11-09"
JOURNAL = """Summary:: test day

## Morning
- Owner said: always run the linter before every commit, no exceptions.
- Moved the staging box to the new rack.
"""
TODAY = date.today()
PAST = (TODAY - timedelta(days=3)).isoformat()
FUTURE = (TODAY + timedelta(days=3)).isoformat()


def vault(tmp: Path, promote: dict | None = None, shard: str | None = "default",
          pointer: bool = True, smoke: dict | None = None, extra: dict | None = None,
          store_dir: str | None = None, build_store: str | None = None):
    """Build a vault; return (memstore, memory_promote, memory_smoke, calls) with fresh module state.
    `store_dir` goes into the config (None: key absent, default Store). `build_store` is where the files are
    really created (default: wherever store_dir points), so a test can build a layout the config does not name."""
    mem = tmp / "vault" / "Agent" / "Memory"
    store = mem / (build_store if build_store is not None else (store_dir or "Store"))
    store.mkdir(parents=True, exist_ok=True)
    default_rel = os.path.relpath(store / "index_promoted.md", mem)
    if shard == "default":
        shard = default_rel
    (tmp / "vault" / "Agent" / "Journal").mkdir(parents=True)
    (tmp / "vault" / "Agent" / "Journal" / f"{DAY}.md").write_text(JOURNAL)
    rel = ""
    if shard:
        sp = mem / shard
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text("# Promoted\n")
        rel = os.path.relpath(sp, store)
    core = "# Memory\n\n## Section Indexes\n"
    if shard and pointer:
        core += f"- [Promoted]({rel}) (0): new memories awaiting a home.\n"
    (store / "MEMORY.md").write_text(core)
    pc = {"enabled": True, "mode": "dry-run", "apply_after": PAST, "reviewed": True, "sources": ["journal"],
          "max_new_per_night": 8}
    pc.update(promote or {})
    if shard and shard != default_rel:
        pc["promoted_shard"] = shard
    if store_dir is not None:
        (extra := dict(extra or {}))["store_dir"] = store_dir
    cfg = {"spec_version": "2026-11-10.5", "owner": "Alex", "agent": "Ada", "enabled": True, "readonly": False,
           "promote": pc, "smoke": {"enabled": True, "min_abstain": 3, **(smoke or {})}, **(extra or {})}
    (mem / "config.json").write_text(json.dumps(cfg))
    os.environ.update(AGENT_VAULT=str(tmp / "vault"), AGENT_DIR="Agent", AGENT_MEMORY_STATE=str(tmp / "state"),
                      AGENT_TZ="UTC")
    os.environ.pop("AGENT_MEMORY", None)
    import memstore
    ms = importlib.reload(memstore)
    import memory_promote
    mp = importlib.reload(memory_promote)
    import memory_smoke
    sm = importlib.reload(memory_smoke)
    calls = []

    def fake_model(prompt, model, **kw):
        calls.append(prompt)
        return subprocess.CompletedProcess(["fake"], 0, stdout=json.dumps(CANDS), stderr="")
    mp.model_call = fake_model
    return ms, mp, sm, calls


CANDS = [
    {"action": "new", "slug": "feedback_lint_before_commit", "type": "feedback", "name": "Lint before commit",
     "description": "Run the linter before every commit", "body": "Always run the linter before committing.",
     "said_by": "owner", "source": "journal", "quote": "always run the linter before every commit",
     "shard": "promoted", "decision": {"is_decision": False}},
]


def store_files(ms) -> list[str]:
    return sorted(p.name for p in ms.STORE.glob("*.md") if p.name != "MEMORY.md" and not p.name.startswith("index_"))


def untouched(ms, calls) -> bool:
    """Nothing written: no new memory, no Promotions log, no state, no model call."""
    return (not store_files(ms) and not ms.PROMOTIONS.exists() and not (ms.STATE / "promote.json").exists()
            and not calls)


# ---------- G7: review gate ----------

def test_g7_apply_before_gate_date_is_refused():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t), {"apply_after": FUTURE})
        assert mp.main(["--date", DAY, "--apply"]) == 3
        assert untouched(ms, calls)


def test_g7_apply_without_reviewed_is_refused():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t), {"require_review": True, "reviewed": False})
        assert mp.main(["--date", DAY, "--apply"]) == 3
        assert untouched(ms, calls)


def test_g7_config_mode_apply_obeys_the_gate():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t), {"mode": "apply", "apply_after": FUTURE})
        assert mp.main(["--date", DAY]) == 3
        assert untouched(ms, calls)


def test_g7_closed_gate_keeps_the_default_run_in_dry_run():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t), {"require_review": True, "reviewed": False})
        assert mp.main(["--date", DAY]) == 0
        assert not store_files(ms) and (ms.PROMOTIONS / f"{DAY}.md").read_text().startswith("Summary:: dry-run")


def test_g7_open_gate_switches_to_apply_and_require_review_false_skips_reviewed():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t), {"reviewed": False, "require_review": False})
        assert mp.main(["--date", DAY]) == 0
        assert store_files(ms) == ["feedback_lint_before_commit.md"]


def test_g7_override_gate_is_explicit_and_logged():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t), {"apply_after": FUTURE, "reviewed": False})
        assert mp.main(["--date", DAY, "--apply", "--override-gate"]) == 0
        assert store_files(ms) == ["feedback_lint_before_commit.md"]
        assert "--override-gate" in (ms.PROMOTIONS / f"{DAY}.md").read_text()


def test_g7_dry_run_flag_always_wins():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t))
        assert mp.main(["--date", DAY, "--dry-run"]) == 0
        assert not store_files(ms)


# ---------- G4 + G8: shard and pointer ----------

def test_g4_missing_shard_fails_closed():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t), shard=None)
        assert mp.main(["--date", DAY, "--apply"]) == 2
        assert untouched(ms, calls)


def test_g4_pointer_present_but_shard_file_missing_fails_closed():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t))
        (ms.STORE / "index_promoted.md").unlink()            # MEMORY.md still points at it
        assert ms.has_core_pointer(ms.promoted_shard())
        assert mp.main(["--date", DAY, "--apply"]) == 2
        assert untouched(ms, calls)


def test_g8_shard_without_memory_md_pointer_fails_closed():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t), pointer=False)
        assert mp.main(["--date", DAY, "--apply"]) == 2
        assert untouched(ms, calls)


def test_g4_g8_shard_and_pointer_present_applies_and_bumps_count():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t))
        assert mp.main(["--date", DAY, "--apply"]) == 0
        assert store_files(ms) == ["feedback_lint_before_commit.md"]
        assert "(feedback_lint_before_commit.md)" in (ms.STORE / "index_promoted.md").read_text()
        assert "(index_promoted.md) (1)" in ms.CORE_INDEX.read_text()
        assert mp.main(["--date", DAY, "--apply"]) == 0 and len(calls) == 1      # day marked done once


# ---------- G11: configurable shard path ----------

def test_g11_promoted_shard_key_moves_the_shard():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t), shard="index_promoted.md")        # flat: Memory/index_promoted.md
        assert ms.promoted_shard() == ms.MEMDIR / "index_promoted.md"
        assert mp.main(["--date", DAY, "--apply"]) == 0
        assert "(feedback_lint_before_commit.md)" in (ms.MEMDIR / "index_promoted.md").read_text()
        assert "(../index_promoted.md) (1)" in ms.CORE_INDEX.read_text()


def test_g11_moved_shard_still_needs_its_pointer():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t), shard="index_promoted.md", pointer=False)
        assert mp.main(["--date", DAY, "--apply"]) == 2
        assert untouched(ms, calls)


# ---------- G10: quote must be in the day's sources ----------

def test_g10_quote_must_appear_in_the_days_sources():
    global CANDS
    saved = CANDS
    CANDS = saved + [
        {**saved[0], "slug": "feedback_invented", "name": "Invented", "quote": "never deploy on a friday"},
        {**saved[0], "slug": "feedback_fragment", "name": "Fragment", "quote": "the linter"},
        {**saved[0], "slug": "feedback_punctuation", "name": "Punctuation",
         "quote": "ALWAYS run the linter, before every commit!"},       # same words, different case and marks
    ]
    try:
        with tempfile.TemporaryDirectory() as t:
            ms, mp, _, calls = vault(Path(t))
            assert mp.main(["--date", DAY, "--apply"]) == 0
            files = store_files(ms)
            assert "feedback_invented.md" not in files and "feedback_fragment.md" not in files
            assert "feedback_lint_before_commit.md" in files and "feedback_punctuation.md" in files
            log = (ms.PROMOTIONS / f"{DAY}.md").read_text()
            assert "(2 unquoted)" in log.splitlines()[0]
    finally:
        CANDS = saved


def test_g10_quote_in_unit():
    import memstore as ms
    text = "line one about nothing\nthe owner prefers tea in the morning\nok"
    assert ms.quote_in("prefers tea in", text)
    assert ms.quote_in("OK", text)                              # a whole short line
    assert not ms.quote_in("tea", text)                         # 1 word, not a whole line
    assert not ms.quote_in("nothing the owner", text)           # spans two lines
    assert not ms.quote_in("prefers te", text)                  # not on a word boundary


# ---------- G9: smoke judge parsing ----------

CODEX_YES = "codex\nYES\n--------\ntokens used: 1,204\n"
CODEX_NO = "[assistant]\n**NO**\nDone in 2.1s"
GARBLED = "codex\nThe memories seem to suggest yes, probably.\ntokens used: 98"


def test_g9_parse_verdict():
    import memory_smoke as sm
    assert sm.parse_verdict(CODEX_YES) == 0.9
    assert sm.parse_verdict(CODEX_NO) == 0.1
    assert sm.parse_verdict("NO.") == 0.1
    assert sm.parse_verdict("YES\nNO") == 0.9                   # the first verdict line wins
    assert sm.parse_verdict(GARBLED) is None
    assert sm.parse_verdict("YESTERDAY") is None
    assert sm.parse_verdict("") is None and sm.parse_verdict(None) is None


def smoke_vault(tmp: Path, judge_text):
    ms, mp, sm, _ = vault(tmp)
    ms.write_new("user_tea", "Tea", "Alex drinks tea every morning", "user",
                 "Alex drinks green tea every morning.", {"said_by": "owner"})
    (ms.MEMDIR / "smoke.json").write_text(json.dumps({"questions": [
        {"q": "What does Alex drink every morning?", "expect": "user_tea"},
        {"q": "What is Alex's blood type?", "abstain": True},
        {"q": "Which airline does Alex fly?", "abstain": True},
        {"q": "What is the name of Alex's boat?", "abstain": True}]}))
    sm.judge = lambda q, ctx: sm.parse_verdict(judge_text(q))
    return ms, sm


def test_g9_smoke_passes_with_codex_style_answers():
    with tempfile.TemporaryDirectory() as t:
        ms, sm = smoke_vault(Path(t), lambda q: CODEX_YES if "drink" in q else CODEX_NO)
        sys.argv = ["memory_smoke.py"]
        assert sm.main() == 0
        r = json.loads((ms.STATE / "smoke.json").read_text())
        assert r["answered_ok"] == 1 and r["abstained_ok"] == 3


def test_g9_no_verdict_is_a_miss_even_for_abstain_questions():
    with tempfile.TemporaryDirectory() as t:
        ms, sm = smoke_vault(Path(t), lambda q: CODEX_YES if "drink" in q else GARBLED)
        sys.argv = ["memory_smoke.py"]
        assert sm.main() == 1
        r = json.loads((ms.STATE / "smoke.json").read_text())
        assert r["abstained_ok"] == 0 and all(row["p"] is None for row in r["rows"][1:])


# ---------- G12: Maestro CLI resolution ----------

def stub_exe(tmp: Path, name: str, body: str) -> Path:
    s = tmp / name
    s.write_text(f"#!{sys.executable}\n" + body)
    s.chmod(0o755)
    return s


TIMELINE_STUB = """import json, sys
print(json.dumps({"events": [{"ts": 1762700000000, "text": "timeline says alpha beta gamma delta"}]}))
"""


def test_g12_configured_maestro_cli_feeds_the_timeline():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        cli = stub_exe(t, "fake-maestro-cli", TIMELINE_STUB)
        ms, mp, _, calls = vault(t, {"sources": ["journal", "timeline"], "maestro_cli": str(cli)})
        os.environ.pop("MAESTRO_CLI", None)
        assert mp.maestro_cli_cmd() == [str(cli)]
        assert mp.main(["--date", DAY, "--dry-run"]) == 0
        assert "alpha beta gamma delta" in calls[0]
        assert "timeline 4" in (ms.PROMOTIONS / f"{DAY}.md").read_text()      # a real size, not skipped


def test_g12_no_cli_anywhere_is_logged_as_skipped_not_empty():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        ms, mp, _, calls = vault(t, {"sources": ["journal", "timeline"]})
        old_path = os.environ.get("PATH", "")
        os.environ.pop("MAESTRO_CLI", None)
        os.environ["PATH"] = str(t / "empty-bin")
        mp.MAESTRO_BUNDLE = str(t / "no-such-bundle.js")
        try:
            assert mp.main(["--date", DAY, "--dry-run"]) == 0
        finally:
            os.environ["PATH"] = old_path
        log = (ms.PROMOTIONS / f"{DAY}.md").read_text()
        assert "skipped: timeline (no Maestro CLI" in log and "timeline 0 chars" not in log


def test_g12_env_wins_and_a_missing_configured_path_is_skipped():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        cli = stub_exe(t, "env-cli", TIMELINE_STUB)
        ms, mp, _, calls = vault(t, {"sources": ["journal", "timeline"], "maestro_cli": str(t / "missing")})
        os.environ["MAESTRO_CLI"] = str(cli)
        try:
            assert mp.maestro_cli_cmd() == [str(cli)]
        finally:
            os.environ.pop("MAESTRO_CLI", None)
        assert mp.main(["--date", DAY, "--dry-run"]) == 0
        assert "configured Maestro CLI not found" in (ms.PROMOTIONS / f"{DAY}.md").read_text()


# ---------- G13: redaction before the model ----------

def test_g13_secrets_and_off_limits_lines_never_reach_the_model():
    global CANDS
    saved = CANDS
    CANDS = saved + [{**saved[0], "slug": "feedback_hire", "name": "Hire",
                      "quote": "the private-project hire starts monday"},           # off-limits: candidate filter
                     {**saved[0], "slug": "feedback_deploy_key", "name": "Deploy key",
                      "quote": "deploy key api_key"}]          # quotes a redacted line: unquoted
    try:
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            ms, mp, _, calls = vault(t, {"off_limits": r"\b(old-employer|private-project)\b"})
            j = ms.AGENT / "Journal" / f"{DAY}.md"
            j.write_text(JOURNAL + "- Note: the private-project hire starts monday.\n"
                         "- deploy key api_key = abcd1234efgh5678ijkl\n")
            assert mp.main(["--date", DAY, "--apply"]) == 0
            prompt = calls[0]
            assert "private-project hire" not in prompt and "abcd1234efgh5678ijkl" not in prompt
            assert "[redacted: off-limits]" in prompt and "[redacted: secret]" in prompt
            assert "always run the linter" in prompt                    # the rest still goes through
            files = store_files(ms)
            assert files == ["feedback_lint_before_commit.md"]
            log = (ms.PROMOTIONS / f"{DAY}.md").read_text()
            assert "1 off-limits, 1 secret" in log and "(1 unquoted)" in log.splitlines()[0]
            assert "`feedback_hire`: off-limits topic" in log
    finally:
        CANDS = saved


def test_g13_candidate_with_a_secret_is_dropped():
    global CANDS
    saved = CANDS
    CANDS = [{**saved[0], "body": "Use token = zyxw9876vuts5432 for deploys."}]
    try:
        with tempfile.TemporaryDirectory() as t:
            ms, mp, _, calls = vault(Path(t))
            assert mp.main(["--date", DAY, "--apply"]) == 0
            assert not store_files(ms)
            assert "contains a secret" in (ms.PROMOTIONS / f"{DAY}.md").read_text()
    finally:
        CANDS = saved


# ---------- G14: journal glob ----------

def test_g14_journal_glob_reads_a_multi_file_day():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        ms, mp, _, calls = vault(t, {"journal_glob": "JOURNAL/{date}-*.md"})
        jd = ms.AGENT / "JOURNAL"
        jd.mkdir(exist_ok=True)              # case-insensitive filesystems: same folder as Journal/
        (jd / f"{DAY}-0900-standup.md").write_text("- Owner said: always run the linter before every commit.\n")
        (jd / f"{DAY}-1400-review.md").write_text("- Afternoon file says omega sigma tau.\n")
        (jd / "2026-11-08-0900-other.md").write_text("- Other day says never read this.\n")
        assert [p.name for p in mp.journal_files(DAY)] == [f"{DAY}-0900-standup.md", f"{DAY}-1400-review.md"]
        assert mp.main(["--date", DAY, "--apply"]) == 0
        assert "omega sigma tau" in calls[0] and "never read this" not in calls[0]
        assert "### file:" in calls[0]
        assert store_files(ms) == ["feedback_lint_before_commit.md"]


def test_g14_default_layout_unchanged():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t))
        assert [p.name for p in mp.journal_files(DAY)] == [f"{DAY}.md"]


# ---------- G15: model_cmd ----------

MODEL_STUB = """import json, sys
prompt = sys.stdin.read()
open(sys.argv[1], "w").write(json.dumps({"argv": sys.argv[2:], "chars": len(prompt),
                                         "captured": "CAPTURED ON" in prompt}))
print("codex")                                    # a channel label before the answer
print(%s)
print("tokens used: 42")
"""


def test_g15_model_cmd_runs_a_stub_with_the_prompt_on_stdin():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        seen = t / "seen.json"
        stub = stub_exe(t, "model-stub", MODEL_STUB % repr(json.dumps(CANDS)))
        ms, mp, _, calls = vault(t, {"model": "test-model"},
                                 extra={"model_cmd": [str(stub), str(seen), "--model", "{model}"]})
        mp.model_call = ms.model_call                     # the real one, no fake
        assert mp.main(["--date", DAY, "--apply"]) == 0
        s = json.loads(seen.read_text())
        assert s["argv"] == ["--model", "test-model"] and s["captured"] and s["chars"] > 500
        assert store_files(ms) == ["feedback_lint_before_commit.md"]


def test_g15_bad_model_cmd_is_a_transient_failure_not_a_write():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t), extra={"model_cmd": "claude -p"})      # a string, not a list
        mp.model_call = ms.model_call
        assert mp.main(["--date", DAY, "--apply"]) == 0
        assert not store_files(ms) and not (ms.STATE / "promote.json").exists()


def test_g15_smoke_judge_uses_model_cmd():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        mark = t / "judge-ran"
        judge = stub_exe(t, "judge-stub", f"import sys\nopen({str(mark)!r}, 'a').write('x')\np = sys.stdin.read()\n"
                         "print('codex')\nprint('YES' if 'drink' in p.split('memories:')[0] else 'NO')\n"
                         "print('tokens used: 7')\n")
        ms, sm = smoke_vault(t, lambda q: "")
        cfg = json.loads(ms.CONFIG.read_text())
        cfg["model_cmd"] = [str(judge)]
        ms.CONFIG.write_text(json.dumps(cfg))
        import memory_smoke
        sm = importlib.reload(memory_smoke)               # the real judge()
        sys.argv = ["memory_smoke.py"]
        assert sm.main() == 0
        r = json.loads((ms.STATE / "smoke.json").read_text())
        assert r["answered_ok"] == 1 and r["abstained_ok"] == 3
        assert mark.read_text() == "xxxx"                   # the stub judged all 4 questions, not a real model


# ---------- G16: credential patterns (synthetic values, assembled at run time) ----------

def synthetic_secrets() -> dict:
    x = lambda n: "X" * n                     # noqa: E731 - filler that no real credential uses
    return {
        "sk-key": "sk-" + "ant-" + x(24),
        "github-classic": ["gh" + c + "_" + x(36) for c in "pous"],          # ghp_ gho_ ghu_ ghs_
        "github-fine-grained": "github" + "_pat_" + x(22) + "_" + x(20),
        "cloud-key-id": ["AK" + "IA" + x(16), "AS" + "IA" + x(16)],
        "chat-token": "xo" + "xb-" + "1" * 10 + "-" + x(12),
        "chat-webhook": "https://hooks." + "slack.com/services/" + "T" + "0" * 8 + "/B" + "0" * 8 + "/" + x(24),
        "pem-private-key": "-----BEGIN " + "OPENSSH PRIVATE " + "KEY-----",
        "bearer": "Authorization: " + "Bearer " + x(32),
        "assignment": "password" + " = " + x(10),
        "secret-gist-url": ["https://gist." + "github.com/someone/" + "ab" * 16,
                            "https://gist." + "githubusercontent.com/someone/" + "0" * 32 + "/raw/a.md"],
        "google-api-key": "AI" + "za" + x(35),
        "payments-key": "sk" + "_live_" + x(24),
        "gitlab-token": "gl" + "pat-" + x(20),
        "npm-token": "np" + "m_" + x(36),
        "jwt": "ey" + "J" + x(10) + ".ey" + "J" + x(10) + "." + x(10),
        "url-credentials": "postgres://app:" + x(8) + "@db.example.invalid/app",
        "authorization": authorization_forms()["basic"],
    }


def authorization_forms() -> dict:
    """G19: the four required forms plus a quoted JSON header. Filler only, assembled at run time."""
    x = lambda n: "X" * n                     # noqa: E731
    return {
        "basic": "Authorization: " + "Ba" + "sic " + x(24),
        "token": "Authorization: " + "To" + "ken " + x(24),
        "bare-colon": "authorization: " + x(16),
        "bare-equals": "authorization=" + x(16),
        "json-quoted": '"Authorization": "' + x(16) + '"',
    }


def test_g19_every_authorization_form_is_redacted():
    import memstore as ms
    for form, v in authorization_forms().items():
        line = f"- request header was {v} (from the logs)"
        assert ms.SECRET_RE.search(line), (form, "missed")
        red, n = ms.redact("keep me\n" + line)
        assert red == "keep me\n[redacted: secret]" and n["secret"] == 1, form
    for s in ["the authorization flow is documented", "authorization pending from legal",
              "see the Authorization section of the doc"]:
        assert not ms.SECRET_RE.search(s), s


def test_g16_every_credential_pattern_is_caught():
    import memstore as ms
    samples = synthetic_secrets()
    assert set(samples) == {name for name, _ in ms.SECRET_PATTERNS}      # one sample per pattern, no gaps
    for name, vals in samples.items():
        for v in (vals if isinstance(vals, list) else [vals]):
            line = f"- note from the day: {v} (do not keep)"
            assert ms.SECRET_RE.search(line), (name, "missed")
            red, n = ms.redact("keep me\n" + line)
            assert red == "keep me\n[redacted: secret]" and n["secret"] == 1, name


def test_g16_ordinary_text_is_not_a_secret():
    import memstore as ms
    for s in ["the gist of the meeting was simple", "https://gist." + "github.com/someone",
              "the bearer of good news", "skeleton key in the drawer", "token budget is 8 KB",
              "see https://example.invalid/docs", "eyes on the prize", "ask the npm maintainers"]:
        assert not ms.SECRET_RE.search(s), s


def test_g16_fine_grained_token_and_gist_url_never_reach_the_model():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t))
        s = synthetic_secrets()
        j = ms.AGENT / "Journal" / f"{DAY}.md"
        j.write_text(JOURNAL + f"- token for the bot: {s['github-fine-grained']}\n- shared {s['secret-gist-url'][0]}\n")
        assert mp.main(["--date", DAY, "--dry-run"]) == 0
        assert s["github-fine-grained"] not in calls[0] and "ab" * 16 not in calls[0]
        assert "0 off-limits, 2 secret" in (ms.PROMOTIONS / f"{DAY}.md").read_text()


# ---------- G17: a CLI that exits non-zero ----------

def test_g17_nonzero_exit_is_a_skipped_source_with_its_stderr():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        cli = stub_exe(t, "old-maestro-cli", "import sys\n"
                       "sys.stderr.write(\"\\nerror: unknown command 'timeline'\\nsee --help\\n\")\nsys.exit(1)\n")
        ms, mp, _, calls = vault(t, {"sources": ["journal", "timeline"], "maestro_cli": str(cli)})
        os.environ.pop("MAESTRO_CLI", None)
        assert mp.main(["--date", DAY, "--dry-run"]) == 0                 # the other sources still run
        log = (ms.PROMOTIONS / f"{DAY}.md").read_text()
        assert "skipped: timeline (exit 1: error: unknown command 'timeline')" in log
        assert "not JSON" not in log and "JSONDecodeError" not in log


def test_g17_zero_exit_with_non_json_is_skipped_too():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        cli = stub_exe(t, "chatty-cli", "print('hello, this is not json')\n")
        ms, mp, _, calls = vault(t, {"sources": ["journal", "timeline"], "maestro_cli": str(cli)})
        os.environ.pop("MAESTRO_CLI", None)
        assert mp.main(["--date", DAY, "--dry-run"]) == 0
        assert "skipped: timeline (timeline output is not JSON" in (ms.PROMOTIONS / f"{DAY}.md").read_text()


# ---------- G18: explicit store_dir ----------

def test_g18_flat_layout_with_store_dir_dot():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t), store_dir=".")
        assert ms.STORE == ms.MEMDIR and ms.CORE_INDEX == ms.MEMDIR / "MEMORY.md"
        assert ms.promoted_shard() == ms.MEMDIR / "index_promoted.md"        # default follows store_dir
        assert mp.main(["--date", DAY, "--apply"]) == 0
        assert (ms.MEMDIR / "feedback_lint_before_commit.md").exists()
        assert "(feedback_lint_before_commit.md)" in (ms.MEMDIR / "index_promoted.md").read_text()
        assert "(index_promoted.md) (1)" in ms.CORE_INDEX.read_text()
        assert not (ms.MEMDIR / "Store").exists()


def test_g18_no_silent_fallback_to_a_flat_folder():
    with tempfile.TemporaryDirectory() as t:
        # files laid out flat, but the config does not say so: the default Store/ is used and is missing
        ms, mp, _, calls = vault(Path(t), build_store=".")
        assert ms.STORE == ms.MEMDIR / "Store"
        assert mp.main(["--date", DAY, "--apply"]) == 2
        assert untouched(ms, calls)


def test_g18_store_dir_pointing_at_a_missing_folder_fails_closed():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t), store_dir="Facts", build_store="Store")
        assert ms.STORE == ms.MEMDIR / "Facts" and not ms.STORE.exists()
        assert mp.main(["--date", DAY, "--apply"]) == 2
        assert untouched(ms, calls)



# ---------- G21, G22 (spec 2026-11-10.7) ----------

def test_g21_null_model_falls_back_to_the_default():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t), promote={"model": None})
        seen = []

        def fake(prompt, model, **kw):
            seen.append(model)
            return subprocess.CompletedProcess(["fake"], 0, stdout=json.dumps(CANDS), stderr="")
        mp.model_call = fake
        assert mp.main(["--date", DAY, "--dry-run"]) == 0
        assert seen and all(isinstance(m, str) and m for m in seen), seen


def test_g22_promotions_log_carries_no_vault_tag():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t))
        assert mp.main(["--date", DAY, "--dry-run"]) == 0
        log = (ms.PROMOTIONS / f"{DAY}.md").read_text()
        assert "#claude" not in log, log[-200:]


# ---------- G23 (spec 2026-11-10.8) ----------

def test_g23_smoke_judge_sees_text_past_1200_chars():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, sm, _ = vault(Path(t))
        ms.write_new("reference_jobs", "Jobs", "When the nightly memory jobs run", "reference",
                     ("Background detail. " * 90) + "The nightly jobs run at 02:30.", {"said_by": "owner"})
        (ms.MEMDIR / "smoke.json").write_text(json.dumps({"questions": [
            {"q": "When do the nightly memory jobs run?", "expect": "reference_jobs"},
            {"q": "What is Alex's blood type?", "abstain": True},
            {"q": "Which airline does Alex fly?", "abstain": True},
            {"q": "What is the name of Alex's boat?", "abstain": True}]}))
        sm.judge = lambda q, ctx: (0.9 if "02:30" in ctx else 0.1) if "nightly" in q else 0.1
        sys.argv = ["memory_smoke.py"]
        assert sm.main() == 0, json.loads((ms.STATE / "smoke.json").read_text())["rows"]


# ---------- G24 to G28 (spec 2026-11-10.9) ----------

def test_g24_smoke_null_model_uses_the_default():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        seen = t / "seen.json"
        stub = stub_exe(t, "judge-stub", MODEL_STUB % repr("YES"))
        ms, mp, sm, _ = vault(t, smoke={"model": None},
                              extra={"model_cmd": [str(stub), str(seen), "--model", "{model}"]})
        sm = importlib.reload(sm)
        assert sm.judge("q?", "ctx") == 0.9
        assert json.loads(seen.read_text())["argv"] == ["--model", "haiku"]


def test_g25_lint_reports_a_missing_core_index():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, _ = vault(Path(t), extra={"lint": {"enabled": True}})
        (ms.STORE / "MEMORY.md").unlink()
        import memory_lint
        ml = importlib.reload(memory_lint)
        sys.argv = ["memory_lint.py", "--no-write", "--strict"]
        assert ml.main() == 1


def test_g26_link_store_slug_matches_the_harness():
    import link_store
    ls = importlib.reload(link_store)
    assert ls.cwd_slug(Path("/tmp/My Vault_v2.d")).endswith("-My-Vault-v2-d")


def test_g27_link_store_refuses_when_the_memory_folder_is_the_store():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        cwd = t / "proj"
        cwd.mkdir()
        import link_store
        ls = importlib.reload(link_store)
        mem = t / "cfg" / "projects" / ls.cwd_slug(cwd) / "memory"
        mem.mkdir(parents=True)
        (mem / "keep_me.md").write_text("x")
        sys.argv = ["link_store.py", "--store", str(mem), "--cwd", str(cwd), "--apply",
                    "--backup", str(t / "bak"), str(t / "cfg")]
        ls.main()
        assert (mem / "keep_me.md").exists() and not mem.is_symlink()


def test_g28_index_check_follows_an_external_promoted_shard():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, _ = vault(Path(t), shard="index_promoted.md")    # shard in MEMDIR, outside the store
        ms.write_new("feedback_x", "X", "an x rule", "feedback", "Body.", {"said_by": "owner"})
        ext = ms.MEMDIR / "index_promoted.md"
        ext.write_text("# Promoted\n- [X](feedback_x.md): an x rule\n")
        import memory_index_check
        mic = importlib.reload(memory_index_check)
        rep = mic.check(ms.STORE.resolve(), 24_400, 0)
        kinds = [(f["kind"], f["detail"]) for f in rep["fails"]]
        assert not kinds, kinds

# ---------- spec 2026-11-11: review is off unless require_review is true ----------

def test_2026_11_11_missing_require_review_leaves_gate_open_after_apply_after():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t))
        cfg = json.loads(ms.CONFIG.read_text())
        for k in ("require_review", "reviewed"):
            cfg["promote"].pop(k, None)                       # an adopter who never set either key
        ms.CONFIG.write_text(json.dumps(cfg))
        assert mp.review_gate(cfg["promote"]) == (True, "")
        assert mp.review_gate({**cfg["promote"], "apply_after": FUTURE})[0] is False   # dry-run window still holds
        assert mp.main(["--date", DAY]) == 0                  # nightly run, no flags: gate open, so it applies
        assert store_files(ms) == ["feedback_lint_before_commit.md"]


def test_2026_11_11_require_review_true_still_closes_the_gate():
    with tempfile.TemporaryDirectory() as t:
        ms, mp, _, calls = vault(Path(t), {"require_review": True})
        cfg = json.loads(ms.CONFIG.read_text())
        cfg["promote"].pop("reviewed", None)
        ms.CONFIG.write_text(json.dumps(cfg))
        is_open, why = mp.review_gate(cfg["promote"])
        assert not is_open and "reviewed" in why
        assert mp.review_gate({**cfg["promote"], "reviewed": True}) == (True, "")
        assert mp.main(["--date", DAY, "--apply"]) == 3
        assert untouched(ms, calls)


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, e)
    print(f"{fails} failed" if fails else "all passed")
    sys.exit(1 if fails else 0)
