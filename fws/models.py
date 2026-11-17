"""Data shapes. The LLM-facing ones double as JSON schemas for structured output."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Legibility = Literal["clear", "unclear", "illegible"]
ErrorType = Literal["concept", "condition", "case", "algebra", "arithmetic", "logic", "misread", "incomplete"]


# ---------- transcription (LLM output) ----------

class Step(BaseModel):
    n: int = Field(description="1-based line number in the order the student wrote it")
    latex: str = Field(description="The math on this line in LaTeX, exactly as written, mistakes kept. Empty if the line is words only.")
    text: str = Field(description="Any Korean or English words on the line, as written")
    legibility: Legibility
    crossed_out: bool = Field(description="True if the student struck this line through")


class TranscribedProblem(BaseModel):
    label: str = Field(description="The problem number or label as written on the page, e.g. '21' or '3번'")
    source_hint: Optional[str] = Field(description="Any exam source the student or teacher wrote, e.g. '2024 수능 22', else null")
    steps: list[Step]
    final_answer: Optional[str] = Field(description="The answer the student boxed or marked, as written, else null")


class Transcription(BaseModel):
    problems: list[TranscribedProblem]
    page_notes: str = Field(description="Anything that made reading hard: glare, cut-off edges, rotation. Empty if none.")


# ---------- diagnosis (LLM output) ----------

class Diagnosis(BaseModel):
    is_correct: bool = Field(description="True only if the reasoning and the final answer are both right")
    first_wrong_step: Optional[int] = Field(description="Step number n of the first line that is wrong, null if none")
    error_type: Optional[ErrorType] = Field(description="Key from the error type list, null if correct")
    skill_tags: list[str] = Field(description="1 to 3 skill tags from the closed list that the mistake is about (or the problem tests, if correct)")
    what_went_wrong: str = Field(description="Korean, 2 sentences or fewer, naming the step number")
    corrected_line: str = Field(description="The first wrong line rewritten correctly, in LaTeX. Empty if correct.")
    feedback: str = Field(description="Korean feedback for a 고3 student, 4 to 6 sentences, see the system prompt")
    habit: str = Field(description="One concrete check the student should do next time, Korean, 1 sentence")
    confidence: float = Field(description="0 to 1, how sure you are about first_wrong_step")


# ---------- problem bank ----------

class BankItem(BaseModel):
    item_id: str = Field(description="exam id plus number, e.g. 2025-11-csat-22")
    exam: str = Field(description="Exam name as printed, e.g. 2025학년도 대학수학능력시험")
    number: int
    subject: str
    unit: str
    skills: list[str]
    text_latex: str = Field(description="The problem text with math in LaTeX")
    choices: list[str] = Field(description="The five choices for multiple choice, empty for short answer")
    answer: str = Field(description="Official answer from the answer key")
    points: Optional[int] = None
    correct_rate: Optional[float] = Field(default=None, description="Share of test takers who got it right, 0 to 1, if a source gives it")
    page: Optional[int] = None
    source_pdf: Optional[str] = None


class ExtractedItem(BaseModel):
    """What the model pulls from one exam page. The answer comes from the answer key, not the model."""
    number: int
    skills: list[str] = Field(description="1 to 3 skill tags from the closed list")
    text_latex: str
    choices: list[str]
    points: Optional[int] = Field(description="Points printed next to the problem, e.g. 4 for [4점], else null")


class ExtractedPage(BaseModel):
    items: list[ExtractedItem]


# ---------- internal records ----------

class StepCheck(BaseModel):
    n: int
    status: Literal["ok", "broken", "suspect", "unparsed", "skipped"]
    detail: str = ""


class Recommendation(BaseModel):
    item_id: str
    reason: str
    score: float


class ProblemResult(BaseModel):
    label: str
    bank_item_id: Optional[str]
    transcription: TranscribedProblem
    checks: list[StepCheck]
    answer_matches_key: Optional[bool]
    diagnosis: Diagnosis
    route: Literal["auto", "review"]
    route_reasons: list[str]
    recommendations: list[Recommendation]


class SheetResult(BaseModel):
    sheet_id: str
    student: str
    image_path: str
    image_sha256: str
    model: str
    problems: list[ProblemResult]
    page_notes: str
    usage: dict
    seconds: float
