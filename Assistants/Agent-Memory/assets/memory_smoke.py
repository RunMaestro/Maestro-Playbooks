#!/usr/bin/env python3
"""
memory_smoke.py: does the fact store answer what it knows, and refuse what it does not?

 Fixed questions live in
`Agent/Memory/smoke.json`. For each one:
  1. lexical recall (memstore.recall) takes the top 5 memories;
  2. one jev noul asks: do these memories contain the answer to the question?
An `expect` question passes when jev says yes (p >= 0.5) AND the expected slug is in
the top 5. An `abstain` question passes when jev says no. Word overlap alone cannot
abstain ("blood type" matches a memory about type size), which is why the judgment
is jev's and not a score threshold.

Gate: answers >= 80% correct AND at least `smoke.min_abstain` correct abstentions.
Result to ~/.config/agent-memory/smoke.json (+ smoke_history.jsonl), read by
memory_lint.py for the health page. Exit 0 pass, 1 fail, 0 when switched off.

USAGE
  memory_smoke.py            # run, record
  memory_smoke.py -v         # show each question's hits and p
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import memstore as ms  # noqa: E402

QUESTIONS = ms.MEMDIR / "smoke.json"


# G23: how much of each memory the judge sees. It was 1200, and 160 of 232 real memories are longer, so a
# memory whose answer sat past that point failed its own question. 6000 covers the longest real memory (5141).
JUDGE_CHARS = 6000

JUDGE_Q = ("Do the `memories` state the answer to `question` directly, "
           "so it could be answered without guessing?")

_VERDICT = re.compile(r"^[\s>*_`\"'\[(]*(YES|NO)[\s.!*_`\"'\])]*$", re.I)


def parse_verdict(text: str) -> float | None:
    """The first line that is only YES or NO (markdown, quotes and a full stop allowed), as 0.9 / 0.1.
    Channel labels, preambles and footers on other lines are ignored. No such line: None, which the caller
    counts as a miss for answer AND abstain questions, so a garbled judge can never pass (spec 2026-11-10.3,
    G9)."""
    for ln in str(text or "").splitlines():
        m = _VERDICT.match(ln)
        if m:
            return 0.9 if m.group(1).upper() == "YES" else 0.1
    return None


def judge(question: str, ctx: str) -> float | None:
    """P(the memories answer the question), or None when the judge gave no verdict. Any
    yes/no judge works; this uses a small model. parse_verdict() reads its answer."""
    prompt = (f"question: {question}\n\nmemories:\n{ctx}\n\n{JUDGE_Q} "
              "Answer with YES or NO on a line of its own.")
    model = (ms.config().get("smoke") or {}).get("model", "haiku")
    return parse_verdict(ms.model_call(prompt, model, timeout=120, label="memory_smoke").stdout)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    on, why = ms.layer_on("smoke")
    if not on:
        print(f"memory_smoke: skipped ({why})")
        return 0
    qs = json.loads(QUESTIONS.read_text())["questions"]
    mems = ms.load_all()
    rows, answered_ok, ans_total, abst_ok, abst_total = [], 0, 0, 0, 0
    for item in qs:
        hits = ms.recall(item["q"], mems, k=5)
        ctx = "\n\n".join(f"[{m.slug}] {m.description}\n{m.body[:JUDGE_CHARS]}" for _, m in hits) or "(no memories)"
        try:
            p = judge(item["q"], ctx)
        except Exception as e:
            print(f"memory_smoke: jev failed ({e}); not recorded")
            return 0
        slugs = [m.slug for _, m in hits]
        if item.get("abstain"):
            abst_total += 1
            ok = p is not None and p < 0.5           # no verdict is a miss, never an abstention
            abst_ok += ok
        else:
            ans_total += 1
            ok = p is not None and p >= 0.5 and item["expect"] in slugs
            answered_ok += ok
        rows.append({"q": item["q"], "p": None if p is None else round(p, 3), "ok": bool(ok), "top": slugs[:3]})
        if args.verbose:
            shown = "none" if p is None else f"{p:.2f}"
            print(f"{'PASS' if ok else 'FAIL'} p={shown} {item['q']}  -> {slugs[:3]}")

    min_abst = int(ms.config().get("smoke", {}).get("min_abstain", 3))
    ok = ans_total > 0 and answered_ok / ans_total >= 0.8 and abst_ok >= min_abst
    res = {"date": ms.today(), "passed": answered_ok + abst_ok, "total": len(qs),
           "answered_ok": answered_ok, "answer_total": ans_total,
           "abstained_ok": abst_ok, "abstain_total": abst_total, "ok": ok, "rows": rows}
    ms.STATE.mkdir(parents=True, exist_ok=True)
    (ms.STATE / "smoke.json").write_text(json.dumps(res, indent=1))
    with (ms.STATE / "smoke_history.jsonl").open("a") as f:
        f.write(json.dumps({k: v for k, v in res.items() if k != "rows"}) + "\n")
    print(f"memory_smoke: {'PASS' if ok else 'FAIL'} answers {answered_ok}/{ans_total}, "
          f"abstentions {abst_ok}/{abst_total}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
