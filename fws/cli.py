"""Command line: fws bank|run|review|report|eval"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

DATA = Path(os.environ.get("FWS_DATA", "data"))


def _bank():
    from .bank import Bank

    return Bank(DATA / "bank" / "bank.jsonl")


def _store():
    from .store import Store

    return Store(DATA / "fws.sqlite")


def cmd_bank_import(a):
    from .bank import import_pdf
    from .llm import LLM

    bank, llm = _bank(), LLM(model=a.model)
    added = import_pdf(bank, llm, Path(a.pdf), a.exam_id, a.exam_name, Path(a.answers))
    print(f"added {len(added)} items, bank now {len(bank.items)}; {llm.usage.as_dict()}")


def cmd_bank_stats(a):
    print(json.dumps(_bank().stats(), ensure_ascii=False, indent=2))


def cmd_run(a):
    from .images import list_photos
    from .llm import LLM
    from .pipeline import process_sheet

    bank, store, llm = _bank(), _store(), LLM(model=a.model)
    src = Path(a.photos)
    photos = list_photos(src) if src.is_dir() else [src]
    mapping = dict(m.split("=", 1) for m in a.map or [])
    out_dir = DATA / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    for ph in photos:
        print(f"{ph.name}")
        r = process_sheet(ph, a.student, bank, llm, mapping, store.given(a.student), fewshot=a.fewshot, store=store)
        store.add_sheet(r)
        (out_dir / f"{r.sheet_id}.json").write_text(r.model_dump_json(indent=2), encoding="utf-8")
        auto = sum(p.route == "auto" for p in r.problems)
        print(f"  sheet {r.sheet_id}: {auto}/{len(r.problems)} auto, {r.usage['calls']} calls, ${r.usage['cost_usd']}, {r.seconds}s")


def cmd_demo(a):
    """Load the SAMPLE bank and sheets into data/demo and open the review queue. No API call."""
    import time
    import uuid

    from .bank import Bank
    from .images import sha256
    from .models import Diagnosis, ProblemResult, SheetResult, TranscribedProblem
    from .pipeline import route
    from .recommend import recommend
    from .review import serve
    from .store import Store
    from .verify import answers_match, check_steps

    root = Path(__file__).parent.parent / "samples"
    demo = DATA / "demo"
    if demo.exists() and a.reset:
        import shutil

        shutil.rmtree(demo)
    bank = Bank(demo / "bank.jsonl")
    for line in (root / "bank.sample.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            from .models import BankItem

            it = BankItem.model_validate_json(line)
            bank.items[it.item_id] = it
    bank.save()
    store = Store(demo / "fws.sqlite")
    if not store.sheets():
        for k, s in enumerate(json.loads((root / "demo" / "sheets.json").read_text(encoding="utf-8")), 1):
            tp = TranscribedProblem(**s["transcription"])
            diag = Diagnosis(**s["diagnosis"])
            item = bank.get(s["item_id"])
            checks = check_steps(tp.steps)
            key = answers_match(tp.final_answer, item.answer)
            reasons = route(tp, checks, diag, key, item)
            student = f"sample-{(k + 1) // 2:02d}"
            recs = recommend(bank, diag, item, store.given(student))
            photo = root / s["image"]
            store.add_sheet(SheetResult(
                sheet_id=f"demo-{k:02d}-{uuid.uuid4().hex[:4]}", student=student, image_path=str(photo.resolve()),
                image_sha256=sha256(photo), model="SAMPLE (hand-written diagnosis, no model call)",
                problems=[ProblemResult(label=tp.label, bank_item_id=item.item_id, transcription=tp, checks=checks,
                                        answer_matches_key=key, diagnosis=diag, route="review" if reasons else "auto",
                                        route_reasons=reasons, recommendations=recs)],
                page_notes="", usage={"calls": 0, "cost_usd": 0.0}, seconds=0.0))
            time.sleep(0.01)
    print(f"demo data in {demo}")
    if not a.no_serve:
        serve(store, bank, a.port)


def cmd_review(a):
    from .review import serve

    serve(_store(), _bank(), a.port)


def cmd_report(a):
    from .report import render_sheet

    store, bank = _store(), _bank()
    r = store.sheet(a.sheet)
    if not r:
        sys.exit(f"no sheet {a.sheet}")
    out = DATA / "reports" / f"{r.sheet_id}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_sheet(r, store, bank), encoding="utf-8")
    print(out)


def cmd_eval(a):
    from .evaluate import from_reviews, run_labels

    if a.from_reviews:
        res = from_reviews(_store())
    else:
        modes = ["off", "static", "teacher"] if a.fewshot == "all" else [a.fewshot]
        res = {m: run_labels(Path(a.labels), _bank(), a.model, m, _store()) for m in modes}
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if a.out:
        Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv=None):
    from .llm import DEFAULT_MODEL

    ap = argparse.ArgumentParser(prog="fws", description="Diagnose photos of handwritten math solutions.")
    sub = ap.add_subparsers(required=True)

    b = sub.add_parser("bank").add_subparsers(required=True)
    bi = b.add_parser("import", help="add one exam PDF with its answer key CSV")
    bi.add_argument("--pdf", required=True)
    bi.add_argument("--exam-id", required=True, help="e.g. 2025-11-csat-common or 2025-11-csat-calculus")
    bi.add_argument("--exam-name", required=True, help="as printed, e.g. '2025학년도 대학수학능력시험 수학 공통'")
    bi.add_argument("--answers", required=True, help="CSV: number,answer[,correct_rate]")
    bi.add_argument("--model", default=DEFAULT_MODEL)
    bi.set_defaults(fn=cmd_bank_import)
    b.add_parser("stats").set_defaults(fn=cmd_bank_stats)

    r = sub.add_parser("run", help="diagnose one photo or a folder of photos")
    r.add_argument("--student", required=True, help="an alias, not a real name")
    r.add_argument("--photos", required=True)
    r.add_argument("--map", nargs="*", help="problem label to bank item, e.g. 21=2025-11-csat-common-21")
    r.add_argument("--model", default=DEFAULT_MODEL)
    r.add_argument("--fewshot", choices=["off", "static", "teacher"], default="teacher")
    r.set_defaults(fn=cmd_run)

    v = sub.add_parser("review", help="open the teacher review queue")
    v.add_argument("--port", type=int, default=8765)
    v.set_defaults(fn=cmd_review)

    d = sub.add_parser("demo", help="open the review queue on the SAMPLE data, no API key needed")
    d.add_argument("--port", type=int, default=8765)
    d.add_argument("--reset", action="store_true")
    d.add_argument("--no-serve", action="store_true")
    d.set_defaults(fn=cmd_demo)

    p = sub.add_parser("report", help="write the student report for one sheet")
    p.add_argument("--sheet", required=True)
    p.set_defaults(fn=cmd_report)

    e = sub.add_parser("eval", help="score against labels, or against teacher edits")
    e.add_argument("--labels", default="eval/labels.jsonl")
    e.add_argument("--from-reviews", action="store_true")
    e.add_argument("--model", default=DEFAULT_MODEL)
    e.add_argument("--fewshot", choices=["off", "static", "teacher", "all"], default="all",
                   help="all runs off, static and teacher on the same labels for comparison")
    e.add_argument("--out")
    e.set_defaults(fn=cmd_eval)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
