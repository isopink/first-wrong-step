"""The checker on the six SAMPLE sheets (planted mistakes, see samples/make_samples.py)."""

import json
from pathlib import Path

from fws.bank import Bank
from fws.models import TranscribedProblem
from fws.verify import answers_match, check_steps

ROOT = Path(__file__).parent.parent / "samples"


def run():
    bank = Bank(ROOT / "bank.sample.jsonl")
    out = {}
    for s in json.loads((ROOT / "demo" / "sheets.json").read_text(encoding="utf-8")):
        tp = TranscribedProblem(**s["transcription"])
        out[s["item_id"]] = ([c.status for c in check_steps(tp.steps)], answers_match(tp.final_answer, bank.get(s["item_id"]).answer))
    return out


def test_checker_on_samples():
    """What the checker alone sees on the planted mistakes. Only the arithmetic slip is caught by line;
    the answer key catches every wrong answer. Condition, concept and algebra slips are left to the model."""
    r = run()
    assert r["sample-11"] == (["ok", "unparsed", "unparsed", "ok", "ok", "ok"], False)   # condition x > 2: unseen
    assert r["sample-08"] == (["unparsed", "unparsed", "ok", "broken", "ok"], False)     # 27-54+27+1 = 2: caught at line 4
    assert r["sample-06"] == (["ok", "ok", "ok", "ok"], False)                           # P(A) used for P(A^C): unseen
    assert r["sample-09"] == (["unparsed", "ok", "ok", "ok", "unparsed"], True)          # correct solution
    assert r["sample-03"] == (["unparsed", "ok", "ok", "ok"], False)                     # dropped /2: unseen
    assert r["sample-02"] == (["ok", "ok", "ok", "ok"], False)                           # a1 + 10d: unseen
