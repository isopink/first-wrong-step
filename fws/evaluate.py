"""Two ways to measure the pipeline.

run_labels: photos a teacher has marked by hand (eval/labels.jsonl), scored line by line.
from_reviews: what teachers changed in the review queue during real use.

The number that matters most is `wrong_sent_unreviewed`: problems the system sent to a
student without review where the first wrong line or the verdict was wrong. A tutor can
live with a long review queue; not with wrong feedback going out on its own.
"""

from __future__ import annotations

import json
from pathlib import Path

from .bank import Bank
from .llm import LLM
from .pipeline import process_sheet


def _rate(n: int, d: int) -> float | None:
    return round(n / d, 3) if d else None


def run_labels(labels: Path, bank: Bank, model: str) -> dict:
    """labels.jsonl rows: {"image": path, "map": {"21": item_id}, "problems": {"21": {"first_wrong_step": 3|null, "error_type": "algebra"|null}}}"""
    llm = LLM(model=model)
    n = step_exact = step_near = verdict_ok = type_ok = type_n = false_correct = auto = auto_wrong = 0
    cost = secs = 0.0
    sheets = 0
    rows = [json.loads(l) for l in labels.read_text(encoding="utf-8").splitlines() if l.strip()]
    for row in rows:
        r = process_sheet(labels.parent / row["image"], "eval", bank, llm, row.get("map", {}), set(), log=lambda *_: None)
        sheets += 1
        cost += r.usage["cost_usd"]
        secs += r.seconds
        for p in r.problems:
            truth = row["problems"].get(p.label.rstrip("번").strip())
            if truth is None:
                continue
            n += 1
            d = p.diagnosis
            t_step = truth["first_wrong_step"]
            same_step = d.first_wrong_step == t_step
            step_exact += same_step
            step_near += t_step is not None and d.first_wrong_step is not None and abs(d.first_wrong_step - t_step) <= 1 or same_step
            verdict_ok += d.is_correct == (t_step is None)
            false_correct += d.is_correct and t_step is not None
            if truth.get("error_type"):
                type_n += 1
                type_ok += d.error_type == truth["error_type"]
            if p.route == "auto":
                auto += 1
                auto_wrong += not same_step
    return {
        "sheets": sheets, "problems": n,
        "first_wrong_line_exact": _rate(step_exact, n), "first_wrong_line_within_1": _rate(step_near, n),
        "verdict_accuracy": _rate(verdict_ok, n), "error_type_accuracy": _rate(type_ok, type_n),
        "marked_correct_but_wrong": false_correct,
        "auto_share": _rate(auto, n), "wrong_sent_unreviewed": auto_wrong,
        "cost_usd_per_sheet": round(cost / sheets, 4) if sheets else None,
        "seconds_per_sheet": round(secs / sheets, 1) if sheets else None, "model": model,
    }


def from_reviews(store) -> dict:
    edits = store.review_edits()
    n = len(edits)
    changed = {k: sum(o[k] != f[k] for o, f in edits) for k in ("is_correct", "first_wrong_step", "error_type", "feedback")}
    return {"reviewed": n, **{f"teacher_changed_{k}": _rate(v, n) for k, v in changed.items()}}
