"""One photo of handwritten work in, one checked and routed SheetResult out.

    photo -> transcribe (LLM, vision) -> match to bank item -> verify (SymPy, answer key)
          -> diagnose + feedback (LLM, sees the verifier output) -> route -> recommend
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from . import images
from .bank import Bank
from .llm import LLM, Usage, image_block
from .models import BankItem, Diagnosis, ProblemResult, SheetResult, StepCheck, TranscribedProblem, Transcription
from .recommend import recommend
from .taxonomy import ERROR_TYPES, unit_of, vocab_prompt
from .verify import answers_match, check_steps

CONFIDENCE_FLOOR = 0.7

TRANSCRIBE_SYSTEM = """You transcribe a photo of a Korean high school student's handwritten math solutions.

Copy what is written, not what should be written. Keep every mistake exactly: a wrong sign, a dropped term, a wrong number. Never fix, finish or solve anything.

- One step is one written line, in the order the student wrote it (top to bottom; follow arrows if the student used them).
- latex: the math on that line in LaTeX. words: any words on the line.
- crossed_out: true if the line is struck through. Still transcribe it.
- legibility: clear, unclear (you are guessing some symbols), or illegible. Be honest; a teacher checks every unclear line.
- If the page holds several problems, list each separately with its number as written.
- final_answer: what the student boxed, circled or marked as the answer, else null.
- source_hint: any exam source written on the page, e.g. "2024 수능 22", else null.
"""

DIAGNOSE_SYSTEM = f"""You mark one handwritten solution for a Korean 고3 student preparing for the CSAT math section.

You receive the problem (when known), its official answer, the student's lines as transcribed, and a deterministic checker's result per line. Your job:

1. Find the first line that is wrong. A line is wrong if it does not follow from the problem and the lines before it: a wrong transformation, a dropped condition, a missing case, a misused theorem, a misread question. Later lines that only carry the error forward are not the first wrong line.
2. Name the error type and 1 to 3 skill tags from the closed lists.
3. Write the feedback.

Using the checker:
- "broken" on arithmetic or on a changed solution set is reliable as algebra. It cannot see the problem's conditions, so a changed solution set can be a correct rejection of a root (for example x > 0). Decide which it is.
- "suspect" is weak evidence. "unparsed" and "skipped" mean nothing.
- If you disagree with a "broken", say why in what_went_wrong.

Feedback, in Korean, 해요체, 4 to 6 sentences, the way a good 고3 math tutor marks a page:
- Start with the line that is right and matters (one sentence, specific, no praise words).
- Name the first wrong line by its number and say exactly what is wrong in it.
- Say the idea that fixes it, in CSAT terms (조건, 범위, 경우, 정의).
- Do not write the full solution. The student should finish it.
If the solution is fully right, say what made it right and one place where it could be shorter or safer.

confidence: how sure you are about first_wrong_step, 0 to 1. Lower it when lines are unclear or when the problem text is missing.

{vocab_prompt()}
"""


def _problem_context(item: BankItem | None) -> str:
    if not item:
        return "Problem text: unknown (no bank match). Judge from the lines alone and lower confidence."
    ch = "".join(f"\n  ({i + 1}) {c}" for i, c in enumerate(item.choices))
    return f"Problem ({item.exam} {item.number}번, {item.subject} {item.unit}):\n{item.text_latex}{ch}\nOfficial answer: {item.answer}"


def _lines(tp: TranscribedProblem, checks: list[StepCheck]) -> str:
    by_n = {c.n: c for c in checks}
    out = []
    for st in tp.steps:
        c = by_n.get(st.n)
        flags = []
        if st.crossed_out:
            flags.append("crossed out")
        if st.legibility != "clear":
            flags.append(st.legibility)
        check = f"[checker: {c.status}{': ' + c.detail if c.detail else ''}]" if c else ""
        out.append(f"{st.n}. {st.latex}  {st.text}  {'(' + ', '.join(flags) + ')' if flags else ''} {check}".rstrip())
    out.append(f"Final answer marked: {tp.final_answer}")
    return "\n".join(out)


def route(tp: TranscribedProblem, checks: list[StepCheck], diag: Diagnosis, key_match: bool | None,
          item: BankItem | None) -> list[str]:
    """Reasons to send this problem to a teacher. Empty means it can go out as is."""
    reasons: list[str] = []
    step_ns = {s.n for s in tp.steps}
    upto = diag.first_wrong_step or max(step_ns, default=0)
    if any(s.legibility != "clear" for s in tp.steps if s.n <= upto and not s.crossed_out):
        reasons.append("unclear handwriting at or before the first wrong line")
    if item is None:
        reasons.append("no bank match, so no problem text or answer key")
    if key_match is False and diag.is_correct:
        reasons.append("answer differs from the key but the model marked it correct")
    if key_match is True and not diag.is_correct and diag.first_wrong_step is None:
        reasons.append("model marked it wrong without naming a line")
    broken = sorted(c.n for c in checks if c.status == "broken")
    if broken:
        if diag.is_correct:
            reasons.append(f"checker found a broken line ({broken[0]}) but the model marked it correct")
        elif diag.first_wrong_step and broken[0] < diag.first_wrong_step:
            reasons.append(f"checker breaks at line {broken[0]}, before the model's line {diag.first_wrong_step}")
    if diag.first_wrong_step is not None and diag.first_wrong_step not in step_ns:
        reasons.append("model named a line that does not exist")
    if diag.error_type and diag.error_type not in ERROR_TYPES:
        reasons.append("unknown error type")
    if any(unit_of(t) is None for t in diag.skill_tags):
        reasons.append("skill tag outside the closed list")
    if diag.confidence < CONFIDENCE_FLOOR:
        reasons.append(f"model confidence {diag.confidence:.2f} below {CONFIDENCE_FLOOR}")
    return reasons


def process_sheet(photo: Path, student: str, bank: Bank, llm: LLM, mapping: dict[str, str] | None = None,
                  already_given: set[str] | None = None, log=print) -> SheetResult:
    t0 = time.perf_counter()
    mapping = mapping or {}
    given = set(already_given or ())
    llm.usage = Usage()  # count this sheet only
    b64, _ = images.prepare(photo)

    tr = llm.structured(TRANSCRIBE_SYSTEM, [image_block(b64), {"type": "text", "text": "Transcribe this page."}], Transcription)
    log(f"  transcribed {len(tr.problems)} problem(s)")

    results: list[ProblemResult] = []
    for tp in tr.problems:
        item = bank.get(mapping.get(tp.label.rstrip("번").strip())) or bank.find_by_hint(tp.source_hint)
        checks = check_steps(tp.steps)
        key_match = answers_match(tp.final_answer, item.answer if item else None)
        img = image_block(b64)
        img["cache_control"] = {"type": "ephemeral"}  # same photo for every problem on the page
        content = [
            img,
            {"type": "text", "text": f"{_problem_context(item)}\n\nKey check of the marked answer: {key_match}\n\n"
                                     f"Student lines for problem {tp.label}:\n{_lines(tp, checks)}"},
        ]
        diag = llm.structured(DIAGNOSE_SYSTEM, content, Diagnosis)
        reasons = route(tp, checks, diag, key_match, item)
        recs = recommend(bank, diag, item, given)
        given.update(r.item_id for r in recs)
        results.append(ProblemResult(
            label=tp.label, bank_item_id=item.item_id if item else None, transcription=tp, checks=checks,
            answer_matches_key=key_match, diagnosis=diag, route="review" if reasons else "auto",
            route_reasons=reasons, recommendations=recs,
        ))
        log(f"  problem {tp.label}: {'correct' if diag.is_correct else f'line {diag.first_wrong_step} {diag.error_type}'}"
            f", {'review' if reasons else 'auto'}")

    return SheetResult(
        sheet_id=time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6], student=student, image_path=str(photo.resolve()),
        image_sha256=images.sha256(photo), model=llm.model, problems=results, page_notes=tr.page_notes,
        usage=llm.usage.as_dict(), seconds=round(time.perf_counter() - t0, 2),
    )


def to_json(r: SheetResult) -> str:
    return json.dumps(r.model_dump(), ensure_ascii=False, indent=2)
