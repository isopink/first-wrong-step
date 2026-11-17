"""Few-shot examples for the diagnosis call. No fine-tuning: the model learns the marking
standard from examples in the prompt, and the examples improve as teachers correct it.

Two sources:
1. STATIC: three worked examples written for this repo. Each teaches one rule that a
   plain prompt gets wrong most often: mark the first wrong line, not a later line
   that only carries the error forward; a missed case is an error even when every line
   is algebraically true; a right answer does not make a solution right.
   They use problems that are not in the sample bank, so the eval does not leak.
2. TEACHER: approved reviews where a teacher changed the model's verdict, line or error
   type, picked by overlap with the skills of the problem being marked. This is how a
   tutor's own standard reaches the model without retraining.

`fws eval --fewshot off|static|teacher` runs the same labels under each setting.
"""

from __future__ import annotations

import json
from typing import Literal

FewShot = Literal["off", "static", "teacher"]

STATIC = [
    {
        "problem": r"$0 \le x < 2\pi$일 때, 방정식 $\sin x = \frac{1}{2}$의 모든 해의 합을 구하시오.",
        "answer": r"\pi",
        "lines": [r"\sin x = \frac{1}{2}", r"x = \frac{\pi}{6}", r"\text{합} = \frac{\pi}{6}"],
        "out": {"is_correct": False, "first_wrong_step": 2, "error_type": "case", "skill_tags": ["삼각함수의 그래프"],
                "what_went_wrong": "2번째 줄에서 제2사분면의 해 x=5π/6을 빠뜨렸어요.",
                "corrected_line": r"x=\frac{\pi}{6},\ \frac{5\pi}{6}",
                "feedback": "sin x = 1/2에서 기준각 π/6을 찾은 것은 맞아요. 2번째 줄에서 주어진 범위 0 ≤ x < 2π 안의 해를 하나만 적었어요. "
                            "사인값이 양수인 곳은 제1, 2사분면 두 곳이에요. 범위 안의 해를 모두 적은 뒤 합을 다시 구해 보세요.",
                "habit": "삼각방정식은 단위원이나 그래프를 그려 범위 안의 교점 개수부터 센다.", "confidence": 0.95},
    },
    {
        "problem": r"수열 $\{a_n\}$의 첫째항부터 제$n$항까지의 합 $S_n$이 $S_n=n^2+1$일 때, $a_1+a_5$의 값을 구하시오.",
        "answer": "11",
        "lines": [r"a_n = S_n - S_{n-1}", r"a_n = n^2+1-((n-1)^2+1) = 2n-1", r"a_1 = 1,\ a_5 = 9", r"a_1+a_5 = 10"],
        "out": {"is_correct": False, "first_wrong_step": 3, "error_type": "condition", "skill_tags": ["수열의 합과 시그마"],
                "what_went_wrong": "3번째 줄에서 n ≥ 2에서만 성립하는 a_n = 2n-1에 n=1을 넣었어요. a_1은 S_1 = 2예요.",
                "corrected_line": r"a_1 = S_1 = 2,\ a_5 = 9",
                "feedback": "2번째 줄의 계산은 정확해요. 그런데 a_n = S_n - S_{n-1}은 n ≥ 2일 때만 쓸 수 있어요. "
                            "3번째 줄에서 이 식에 n=1을 넣은 게 문제예요. 2번째 줄까지는 식이 모두 참이지만, 쓸 수 있는 범위를 넘어선 거예요. "
                            "a_1은 따로 S_1로 구해서 다시 더해 보세요.",
                "habit": "S_n으로 a_n을 구하면 a_1 = S_1을 따로 확인한다.", "confidence": 0.93},
    },
    {
        "problem": r"곡선 $y=x^3-2x$ 위의 점 $(1,-1)$에서의 접선의 기울기를 구하시오.",
        "answer": "1",
        "lines": [r"y' = 3x^2 - 2x", r"y'(1) = 3 - 2 = 1", r"\text{기울기} = 1"],
        "out": {"is_correct": False, "first_wrong_step": 1, "error_type": "concept", "skill_tags": ["미분계수와 도함수"],
                "what_went_wrong": "1번째 줄에서 -2x를 미분해 -2x로 남겼어요. -2x의 도함수는 -2예요. 답은 우연히 맞았어요.",
                "corrected_line": r"y' = 3x^2 - 2",
                "feedback": "접선의 기울기를 x=1에서의 미분계수로 구하려는 방향은 맞아요. 1번째 줄에서 -2x를 미분한 값이 -2가 아니라 -2x로 적혔어요. "
                            "x=1에서는 두 값이 같아서 답이 맞게 나왔지만, 다른 점이었다면 틀렸을 거예요. 일차항의 미분부터 다시 확인해 보세요.",
                "habit": "답이 맞아도 도함수를 쓴 줄은 항마다 다시 미분해 본다.", "confidence": 0.9},
    },
]


def _example_text(i: int, ex: dict) -> str:
    lines = "\n".join(f"{n}. {l}" for n, l in enumerate(ex["lines"], 1))
    return (f"<example {i}>\nProblem: {ex['problem']}\nOfficial answer: {ex['answer']}\nStudent lines:\n{lines}\n"
            f"Marking:\n{json.dumps(ex['out'], ensure_ascii=False)}\n</example {i}>")


def static_block() -> str:
    """Goes at the end of the system prompt, so it is cached with it."""
    body = "\n\n".join(_example_text(i, ex) for i, ex in enumerate(STATIC, 1))
    return ("\nWorked examples of the marking standard. Follow the standard, not the topics:\n\n" + body)


def teacher_block(corrections: list[dict]) -> str:
    """Teacher corrections as examples, placed in the user turn before the case."""
    if not corrections:
        return ""
    parts = []
    for i, c in enumerate(corrections, 1):
        lines = "\n".join(f"{s['n']}. {s['latex']} {s['text']}".rstrip() for s in c["steps"])
        before = {k: c["model"][k] for k in ("is_correct", "first_wrong_step", "error_type")}
        after = {k: c["teacher"][k] for k in ("is_correct", "first_wrong_step", "error_type", "what_went_wrong")}
        parts.append(f"<correction {i}>\nStudent lines:\n{lines}\nModel marked: {json.dumps(before, ensure_ascii=False)}\n"
                     f"Teacher corrected to: {json.dumps(after, ensure_ascii=False)}\n</correction {i}>")
    return ("This tutor corrected earlier markings on similar skills. Apply the same standard:\n\n"
            + "\n\n".join(parts) + "\n\n")
