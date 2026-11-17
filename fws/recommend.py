"""Pick follow-up problems from the bank for one diagnosed problem.

Rules, in plain terms:
- The skill the mistake is about matters most; the same unit is a smaller plus.
- After a miss, start one step easier than the missed item (higher correct rate, or
  fewer points when rates are unknown), then the same level, then one harder.
- After a correct solution, give one harder item on the same skill.
- Never the same item, never one this student was already given.
"""

from __future__ import annotations

from .bank import Bank
from .models import BankItem, Diagnosis, Recommendation


def _level(it: BankItem) -> float | None:
    """Higher is easier. Correct rate if known, else a rough level from points."""
    if it.correct_rate is not None:
        return it.correct_rate
    if it.points is not None:
        return {2: 0.9, 3: 0.7, 4: 0.4}.get(it.points)
    return None


def _fmt_rate(it: BankItem) -> str:
    if it.correct_rate is not None:
        return f"정답률 {round(it.correct_rate * 100)}%"
    if it.points is not None:
        return f"{it.points}점"
    return "난이도 정보 없음"


def recommend(bank: Bank, diag: Diagnosis, missed: BankItem | None, already_given: set[str], k: int = 3) -> list[Recommendation]:
    tags = set(diag.skill_tags)
    base = _level(missed) if missed else None
    scored: list[tuple[float, str, BankItem, str]] = []
    for it in bank.items.values():
        if missed and it.item_id == missed.item_id or it.item_id in already_given:
            continue
        overlap = tags & set(it.skills)
        if not overlap:
            continue
        score = 3.0 * len(overlap)
        if missed and it.unit == missed.unit:
            score += 1.0
        lv = _level(it)
        band = "same"
        if base is not None and lv is not None:
            gap = lv - base
            band = "easier" if gap > 0.08 else "harder" if gap < -0.08 else "same"
            if diag.is_correct:
                score += 1.5 if band == "harder" else 0.0
            else:
                score += 1.5 if band == "easier" and gap <= 0.35 else 0.8 if band == "same" else 0.0
        scored.append((score, band, it, ", ".join(sorted(overlap))))

    scored.sort(key=lambda t: (-t[0], t[2].item_id))
    picked: list[Recommendation] = []
    wanted = ["harder"] if diag.is_correct else ["easier", "same", "harder"]
    for band in wanted:  # one per band first, so the set climbs back to the missed level
        for s, b, it, why in scored:
            if b == band and all(p.item_id != it.item_id for p in picked):
                picked.append(_rec(it, s, b, why, missed))
                break
    for s, b, it, why in scored:  # fill the rest by score
        if len(picked) >= k:
            break
        if all(p.item_id != it.item_id for p in picked):
            picked.append(_rec(it, s, b, why, missed))
    return picked[:k]


def _rec(it: BankItem, score: float, band: str, why: str, missed: BankItem | None) -> Recommendation:
    rel = {"easier": "원 문항보다 쉬움", "same": "원 문항과 비슷함", "harder": "원 문항보다 어려움"}[band]
    base = f" (원 문항 {_fmt_rate(missed)})" if missed else ""
    reason = f"{it.exam} {it.number}번. 같은 기능: {why}. {_fmt_rate(it)}, {rel}{base}."
    return Recommendation(item_id=it.item_id, reason=reason, score=round(score, 2))
