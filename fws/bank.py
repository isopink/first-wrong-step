"""Past-exam problem bank: built from the official PDF plus its answer key, stored as JSONL.

The model reads the problem text and tags skills. The answer never comes from the
model: an item without a row in the answer key CSV is dropped.
"""

from __future__ import annotations

import base64
import csv
import json
import re
from pathlib import Path

from .llm import LLM, image_block
from .models import BankItem, ExtractedPage
from .taxonomy import unit_of, vocab_prompt

EXTRACT_SYSTEM = f"""You read one page of a Korean high school math exam (CSAT or a mock exam) and list every problem on it.

For each problem:
- number: the printed problem number.
- text_latex: the full problem text. Korean words stay Korean. All math in LaTeX inside $...$. Describe a figure in one bracketed Korean sentence, e.g. [그림: 원 위의 세 점 A, B, C].
- choices: the five choices ①..⑤ as LaTeX strings without the circled number, or [] for short answer.
- points: the printed point value, e.g. 3 for [3점], or null.
- skills: 1 to 3 tags from the closed list below that the problem mainly tests.

Skip problems that continue from the previous page if their number is not on this page. Do not solve anything.

{vocab_prompt()}
"""


class Bank:
    def __init__(self, path: Path):
        self.path = path
        self.items: dict[str, BankItem] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    it = BankItem.model_validate_json(line)
                    self.items[it.item_id] = it

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = [it.model_dump_json() for it in sorted(self.items.values(), key=lambda i: i.item_id)]
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def get(self, item_id: str | None) -> BankItem | None:
        return self.items.get(item_id) if item_id else None

    def find_by_hint(self, hint: str | None) -> BankItem | None:
        """Match a written source like '2024 수능 22' or '24년 9월 모평 21번'."""
        if not hint:
            return None
        nums = re.findall(r"\d+", hint)
        if len(nums) < 2:
            return None
        year, number = nums[0], int(nums[-1])
        year = year if len(year) == 4 else "20" + year
        month = None
        if "수능" in hint:
            month = "대학수학능력시험"
        elif m := re.search(r"(6|9)\s*월", hint):
            month = m.group(1) + "월"
        hits = [
            it for it in self.items.values()
            if it.number == number and year in it.exam and (month is None or month in it.exam)
        ]
        return hits[0] if len(hits) == 1 else None

    def stats(self) -> dict:
        by_unit: dict[str, int] = {}
        for it in self.items.values():
            by_unit[f"{it.subject} / {it.unit}"] = by_unit.get(f"{it.subject} / {it.unit}", 0) + 1
        return {"items": len(self.items), "exams": len({it.exam for it in self.items.values()}), "by_unit": by_unit}


def read_answer_key(path: Path) -> dict[int, dict]:
    """CSV with columns number,answer and optionally correct_rate (0 to 1 or a percent)."""
    rows: dict[int, dict] = {}
    with path.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rate = (r.get("correct_rate") or "").strip().rstrip("%")
            rate_v = float(rate) / (100 if rate and float(rate) > 1 else 1) if rate else None
            rows[int(r["number"])] = {"answer": r["answer"].strip(), "correct_rate": rate_v}
    return rows


def import_pdf(bank: Bank, llm: LLM, pdf: Path, exam_id: str, exam_name: str, answer_key: Path,
               log=print) -> list[str]:
    import fitz  # PyMuPDF

    key = read_answer_key(answer_key)
    added: list[str] = []
    doc = fitz.open(pdf)
    for pno in range(doc.page_count):
        pix = doc[pno].get_pixmap(dpi=160)
        b64 = base64.standard_b64encode(pix.tobytes("png")).decode()
        page = llm.structured(EXTRACT_SYSTEM, [image_block(b64, "image/png"), {"type": "text", "text": f"Page {pno + 1}."}],
                              ExtractedPage, max_tokens=16000)
        for ex in page.items:
            row = key.get(ex.number)
            skills = [s for s in ex.skills if unit_of(s)]
            if not row:
                log(f"  page {pno + 1}: problem {ex.number} has no answer key row, skipped")
                continue
            if not skills:
                log(f"  page {pno + 1}: problem {ex.number} has no valid skill tag, skipped")
                continue
            subject, unit = unit_of(skills[0])
            item = BankItem(
                item_id=f"{exam_id}-{ex.number:02d}", exam=exam_name, number=ex.number, subject=subject, unit=unit,
                skills=skills, text_latex=ex.text_latex, choices=ex.choices, answer=row["answer"],
                points=ex.points, correct_rate=row["correct_rate"], page=pno + 1, source_pdf=pdf.name,
            )
            bank.items[item.item_id] = item
            added.append(item.item_id)
        log(f"  page {pno + 1}: {len(page.items)} problems read")
    bank.save()
    return added


def dump_item(it: BankItem) -> str:
    return json.dumps(it.model_dump(), ensure_ascii=False, indent=2)
