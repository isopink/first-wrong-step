"""Recommendation and routing rules. Bank items here are synthetic test fixtures, not exam items."""

from pathlib import Path

from fws.bank import Bank
from fws.models import BankItem, Diagnosis, Step, StepCheck, TranscribedProblem
from fws.pipeline import route
from fws.recommend import recommend


def item(i, skills, rate, unit="확률"):
    return BankItem(item_id=f"t-{i}", exam="TEST", number=i, subject="확률과 통계", unit=unit, skills=skills,
                    text_latex="fixture", choices=[], answer="1", correct_rate=rate)


def diag(**kw):
    base = dict(is_correct=False, first_wrong_step=2, error_type="condition", skill_tags=["조건부확률"],
                what_went_wrong="", corrected_line="", feedback="", habit="", confidence=0.9)
    base.update(kw)
    return Diagnosis(**base)


def bank(tmp_path: Path, items):
    b = Bank(tmp_path / "b.jsonl")
    b.items = {it.item_id: it for it in items}
    return b


def test_miss_gets_easier_then_same_then_harder(tmp_path):
    missed = item(1, ["조건부확률"], 0.40)
    b = bank(tmp_path, [missed, item(2, ["조건부확률"], 0.65), item(3, ["조건부확률"], 0.42),
                        item(4, ["조건부확률"], 0.20), item(5, ["정규분포"], 0.60, unit="통계")])
    recs = recommend(b, diag(), missed, set())
    assert [r.item_id for r in recs] == ["t-2", "t-3", "t-4"]
    assert "t-1" not in [r.item_id for r in recs]


def test_correct_gets_harder_and_given_items_are_skipped(tmp_path):
    missed = item(1, ["조건부확률"], 0.40)
    b = bank(tmp_path, [missed, item(2, ["조건부확률"], 0.65), item(4, ["조건부확률"], 0.20), item(6, ["조건부확률"], 0.15)])
    recs = recommend(b, diag(is_correct=True, first_wrong_step=None, error_type=None), missed, {"t-4"})
    assert recs[0].item_id == "t-6"


def tp(legibility="clear"):
    return TranscribedProblem(label="1", source_hint=None, final_answer="3", steps=[
        Step(n=i, latex="x", text="", legibility=legibility if i == 1 else "clear", crossed_out=False) for i in (1, 2, 3)])


def test_route_clean_case_is_auto():
    it = item(1, ["조건부확률"], 0.4)
    assert route(tp(), [], diag(), False, it) == []


def test_route_flags():
    it = item(1, ["조건부확률"], 0.4)
    assert route(tp("unclear"), [], diag(), False, it)
    assert route(tp(), [], diag(), None, None)  # no bank match
    assert route(tp(), [], diag(is_correct=True, first_wrong_step=None), False, it)  # key says wrong
    assert route(tp(), [StepCheck(n=1, status="broken")], diag(first_wrong_step=3), False, it)
    assert route(tp(), [], diag(first_wrong_step=9), False, it)
    assert route(tp(), [], diag(confidence=0.5), False, it)
    assert route(tp(), [], diag(skill_tags=["made up"]), False, it)


def test_bank_hint_matching(tmp_path):
    b = bank(tmp_path, [BankItem(item_id="x-22", exam="2024학년도 대학수학능력시험", number=22, subject="수학II", unit="미분",
                                 skills=["극대와 극소"], text_latex="", choices=[], answer="1")])
    assert b.find_by_hint("2024 수능 22").item_id == "x-22"
    assert b.find_by_hint("24 수능 22번").item_id == "x-22"
    assert b.find_by_hint("2024 9월 22") is None
