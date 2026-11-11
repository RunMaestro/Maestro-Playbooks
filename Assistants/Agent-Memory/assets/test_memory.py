"""Tests for memory.py. Never touches a live store (MEMORY_DIR and MEMORY_SESSIONS point at a temp dir) and never
calls a model (memory.LLM is stubbed).

Run: python3 test_memory.py   (or pytest test_memory.py)
"""
import importlib
import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def fresh(tmp: Path):
    os.environ["MEMORY_DIR"] = str(tmp / "memory")
    os.environ["MEMORY_SESSIONS"] = str(tmp / "sessions")
    os.environ.pop("AGENT_MEMORY", None)
    import memory
    m = importlib.reload(memory)
    m.set_cfg(owner="Alex", people=["Sam", "Jo"], assistant="Helper")
    return m


def session(tmp: Path, name: str, lines: list[str]) -> Path:
    d = tmp / "sessions" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "transcript.md").write_text(f"# transcript {name}\n\n" + "\n".join(lines) + "\n")
    return d


def test_replay_keeps_only_owner_and_tasks():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        m = fresh(t)
        s = session(t, "2026-11-01-100000", [
            "- `10:00:01` **User:** I like my coffee black",
            "- `10:00:02` **Heard:** the neighbors are getting divorced",
            "- `10:00:03` **Assistant:** Got it,",
            "- `10:00:03` **Assistant:** black coffee.",
            "- `10:00:04` **Typed:** never wake me before 7",
            "- `10:00:05` **Task:** ordered the oat milk, arriving Tuesday"])
        txt = m.replay([s])
        assert "coffee black" in txt and "never wake me before 7" in txt and "oat milk" in txt
        assert "divorced" not in txt                       # unattributed room talk never reaches the model
        assert "ASSISTANT: Got it, black coffee." in txt   # streamed phrases joined


def test_dream_new_reinforce_supersede_and_sensitive():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        m = fresh(t)
        session(t, "2026-11-01-100000", ["- `10:00:01` **User:** Sam is nine and loves chess"])
        m.LLM = lambda p: {"memories": [
            {"type": "fact", "subject": "Sam", "fact": "Sam is nine years old", "said_by": "owner", "salience": 4,
             "evidence": "Sam is nine"},
            {"type": "preference", "subject": "Sam", "fact": "Sam loves playing chess", "said_by": "owner",
             "evidence": "and loves chess"},
            {"type": "fact", "subject": "Alex", "fact": "Alex has a health checkup on Friday", "said_by": "owner"}]}
        r = m.dream("2026-11-01")
        assert r["new"] == 2 and r["nodes"] == 2            # the health line is sensitive: dropped unread
        assert (t / "memory" / "HOT.md").read_text().count("\n") == 2
        assert (t / "memory" / "Dreams" / "2026-11-01.md").exists()
        mems = m.load_all()
        age = next(k for k, v in mems.items() if "nine" in v["description"])
        chess = next(k for k, v in mems.items() if "chess" in v["description"])
        assert chess in mems[age]["links"] and age in mems[chess]["links"]   # LINK both ways (same subject)
        assert m.dream("2026-11-01")["sessions"] == 0        # the same transcript is not replayed twice
        session(t, "2026-11-02-100000", ["- `10:00:01` **User:** Sam turned ten today and still loves chess"])
        m.LLM = lambda p: {"memories": [
            {"type": "fact", "subject": "Sam", "fact": "Sam is ten years old", "said_by": "owner",
             "relation": f"updates:{age}", "evidence": "Sam turned ten today"},
            {"type": "preference", "subject": "Sam", "fact": "Sam loves playing chess", "said_by": "owner",
             "evidence": "still loves chess"}]}
        r = m.dream("2026-11-02")
        mems = m.load_all()
        assert mems[age]["status"] == "superseded" and mems[age]["superseded_by"]
        assert mems[chess]["reinforcements"] == 1
        assert r["superseded_today"] == 1 and r["retired"] == 1 and r["reinforced"] == 1
        h = m.history()
        assert [x["date"] for x in h] == ["2026-11-01", "2026-11-02"] and h[-1]["nodes"] == 2


def test_contradiction_from_lower_tier_keeps_both():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        m = fresh(t)
        assert m.add("Alex's favorite color is purple", subject="Alex", type_="preference") == "saved"
        slug = next(iter(m.load_all()))
        session(t, "2026-11-03-100000", ["- `10:00:01` **Task:** set the lights to green, their favorite"])
        m.LLM = lambda p: {"memories": [{"type": "preference", "subject": "Alex", "fact": "Alex's favorite "
                                         "color is green", "said_by": "task", "relation": f"contradicts:{slug}",
                                         "evidence": "set the lights to green"}]}
        r = m.dream("2026-11-03")
        assert r["flagged"] == 1 and m.load_all()[slug]["status"] == "active"


def test_decay_rules_never_decay_and_archive_floor():
    with tempfile.TemporaryDirectory() as t:
        m = fresh(Path(t))
        old = (date.today() - timedelta(days=400)).isoformat()
        rule = {"name": "r", "description": "x", "type": "rule", "last_reinforced": old, "status": "active"}
        ep = {"name": "e", "description": "y", "type": "episode", "last_reinforced": old, "status": "active"}
        assert m.retrievability(rule) == 1.0 and m.retrievability(ep) < 0.05
        strong = {**ep, "reinforcements": 3}
        assert m.retrievability(strong) > m.retrievability(ep)           # rehearsal extends life
        mems = {"r": rule, "e": ep, "f": {"name": "f", "description": "z", "type": "fact", "status": "active",
                                          "last_reinforced": date.today().isoformat(), "links": []}}
        active, dormant, arch = m.tiers(mems, date.today())
        assert "r" in active and "e" in arch
        mems["f"]["links"] = ["e"]                         # an inbound link keeps it out of the archive
        assert "e" not in m.tiers(mems, date.today())[2]


def test_recall_touch_reinforces_at_next_dream_and_forget():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        m = fresh(t)
        m.add("Jo's favorite dinosaur is the stegosaurus", subject="Jo", type_="preference")
        hits = m.recall("what dinosaur does Jo like?")
        assert hits and "stegosaurus" in hits[0]["description"]
        assert "do not remember" in m.recall_line("what is the wifi network called")   # abstains, never guesses
        m.LLM = lambda p: {"memories": []}
        tf = t / "memory" / "touches.jsonl"
        tomorrow = (date.today() + timedelta(days=1)).isoformat()   # one reinforcement per memory per day
        tf.write_text(tf.read_text().replace(date.today().isoformat(), tomorrow))
        r = m.dream(tomorrow)
        assert r["reinforced"] == 1
        assert m.dream(tomorrow)["reinforced"] == 0                  # a touch counts once
        assert m.forget("stegosaurus")
        assert not m.recall("dinosaur Jo") and m.snapshot(m.load_all(), date.today())["nodes"] == 0
        assert list((t / "memory" / "Archive").glob("*.md"))      # moved, not deleted


def test_switches_fail_open():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        m = fresh(t)
        m.set_cfg(readonly=True)
        assert m.add("Alex likes tacos") == "off" and m.dream("2026-11-01")["skipped"]
        m.set_cfg(readonly=False, enabled=False)
        assert m.digest() == "memory is switched off" and m.recall("tacos") == []
        m.set_cfg(enabled=True)
        os.environ["AGENT_MEMORY"] = "0"
        assert not m.enabled()
        os.environ.pop("AGENT_MEMORY")
        (t / "memory" / "config.json").write_text("{broken")
        assert m.enabled() and m.digest().startswith("nothing")   # a broken config is "no memory", not a crash


def test_explore_props_fit_the_cap():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        m = fresh(t)
        import random
        rnd = random.Random(4)
        vocab = [f"w{j}x" for j in range(3000)]
        for i in range(400):
            m.add(" ".join(rnd.sample(vocab, 9)), subject=["Alex", "Sam", "Jo"][i % 3])
        p = m.explore("Sam")
        assert len(json.dumps(p, ensure_ascii=False).encode()) <= 11_000
        assert p["shown"] < p["of"] == 400 and any(n.get("f") for n in p["nodes"])
        d = m.dash()
        assert d["now"]["nodes"] == 400 and len(d["top"]) == 8


def test_reflect_needs_three_children_from_three_days():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        m = fresh(t)
        today = date.today()
        for i, fact in enumerate(["Alex builds widgets at night", "Alex asked for a new chart late",
                                  "Alex ships changes after midnight"]):
            d = (today - timedelta(days=3 - i)).isoformat()
            session(t, f"{d}-100000", [f"- `10:00:01` **User:** {fact}"])
            m.LLM = lambda p, f=fact: {"memories": [{"type": "episode", "subject": "Alex", "fact": f,
                                                     "said_by": "owner", "evidence": f}]}
            m.dream(d, reflect=False)
        kids = list(m.load_all())
        m.LLM = lambda p: {"insights": [{"subject": "Alex", "fact": "Alex does their building late at night",
                                         "children": kids}, {"subject": "Alex", "fact": "thin", "children": kids[:1]}]}
        m.dream(today.isoformat(), sessions=[], reflect=True)
        ins = [v for v in m.load_all().values() if v["type"] == "insight"]
        assert len(ins) == 1 and set(kids) <= set(ins[0]["links"])


def test_replay_keeps_texts_and_calls():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        m = fresh(t)
        s = session(t, "2026-11-09-160000", [
            "- `16:00:01` **Texted:** remember my flight is Tuesday",
            "- `16:00:05` **Assistant:** Got it.",
            "- `16:01:00` **Phone:** I'm at the airport"])
        out = m.replay([s])
        assert "OWNER (text): remember my flight is Tuesday" in out and "OWNER (call): I'm at the airport" in out
        assert "ASSISTANT: Got it." in out


def test_extract_requires_a_quote_from_an_owner_turn():
    """G1 (spec 2026-11-10.2): a candidate must quote an owner (or task-result) turn; assistant text never counts,
    and the quote, not the model's claim, decides `said_by`."""
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        m = fresh(t)
        session(t, "2026-11-04-100000", [
            "- `10:00:01` **User:** I like my coffee black",
            "- `10:00:02` **Assistant:** You seem to love jazz music a lot",
            "- `10:00:03` **Task:** booked the dentist cleaning for Tuesday",
            "- `10:00:04` **User:** ok"])
        m.LLM = lambda p: {"memories": [
            {"type": "preference", "subject": "Alex", "fact": "Alex takes coffee black", "said_by": "owner",
             "evidence": "I like my coffee black"},                                 # owner quote: kept
            {"type": "preference", "subject": "Alex", "fact": "Alex loves jazz", "said_by": "owner",
             "evidence": "you seem to love jazz"},                                  # assistant text: dropped
            {"type": "fact", "subject": "Alex", "fact": "Alex owns a red bicycle", "said_by": "owner"},  # no quote
            {"type": "fact", "subject": "Alex", "fact": "Alex prefers window seats", "said_by": "owner",
             "evidence": "I prefer window seats"},                                  # invented quote: dropped
            {"type": "procedure", "subject": "Alex", "fact": "Cleanings get booked for Tuesdays", "said_by": "owner",
             "evidence": "booked the dentist cleaning"},                            # task quote: said_by task
            {"type": "fact", "subject": "Alex", "fact": "Alex agreed", "said_by": "owner", "evidence": "ok"},
            {"type": "fact", "subject": "Alex", "fact": "Alex likes coffee", "said_by": "owner",
             "evidence": "coffee"}]}                                                # 1 word, not a whole turn
        r = m.dream("2026-11-04")
        facts = {v["description"]: v for v in m.load_all().values()}
        assert set(facts) == {"Alex takes coffee black", "Cleanings get booked for Tuesdays", "Alex agreed"}
        assert facts["Alex takes coffee black"]["said_by"] == "owner"
        assert facts["Cleanings get booked for Tuesdays"]["said_by"] == "task"
        assert r["unquoted"] == 4 and r["new"] == 3


def test_model_cmd_runs_a_stub_with_the_prompt_on_stdin():
    """G15 (spec 2026-11-10.4): config model_cmd replaces the hard-coded `claude -p`; prompt on stdin, `{model}`
    filled from config `model`."""
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        m = fresh(t)
        session(t, "2026-11-05-100000", ["- `10:00:01` **User:** I like my coffee black"])
        seen = t / "seen.json"
        stub = t / "model-stub"
        out = json.dumps({"memories": [{"type": "preference", "subject": "Alex", "fact": "Alex takes coffee black",
                                        "said_by": "owner", "evidence": "I like my coffee black"}]})
        stub.write_text(f"#!{sys.executable}\nimport json, sys\np = sys.stdin.read()\n"
                        f"open({str(seen)!r}, 'w').write(json.dumps({{'argv': sys.argv[1:], "
                        f"'has_transcript': 'Transcript:' in p}}))\nprint('codex')\nprint({out!r})\n")
        stub.chmod(0o755)
        m.set_cfg(model_cmd=[str(stub), "-m", "{model}"], model="tiny-model")
        llm = os.environ.pop("AGENT_MEMORY_LLM", None)
        try:
            r = m.dream("2026-11-05")
        finally:
            if llm is not None:
                os.environ["AGENT_MEMORY_LLM"] = llm
        s = json.loads(seen.read_text())
        assert s == {"argv": ["-m", "tiny-model"], "has_transcript": True}
        assert r["new"] == 1 and m.model_argv() == [str(stub), "-m", "tiny-model"]
        m.set_cfg(model_cmd="claude -p")                      # not a list: refused, no call, no memory
        try:
            m.model_argv()
            assert False, "a string model_cmd must be refused"
        except ValueError:
            pass



def test_g29_budget_stop_leaves_the_day_unreplayed():
    """Spec 2026-11-10.9: when the call budget stops extraction, no session of that day is marked replayed."""
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        m = fresh(t)
        m.set_cfg(budget_calls=1)
        line = "- `10:00:01` **User:** " + ("the deploy runs on tuesdays and the cache warms first. " * 40)
        session(t, "2026-11-01-100000", [line] * 20)          # more than one CHUNK, so two extract calls
        calls = []
        m.LLM = lambda p: calls.append(1) or {"memories": []}
        m.dream("2026-11-01")
        assert len(calls) == 1
        assert not m._state().get("replayed"), m._state().get("replayed")

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
