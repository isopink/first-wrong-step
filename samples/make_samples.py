"""Build the SAMPLE data in this folder. Everything here is synthetic and labelled so.

    python samples/make_samples.py

Writes
    samples/bank.sample.jsonl     12 problems written for this repo (not exam items), 4 skills x 3 levels
    samples/eval/sheet-*.png      6 rendered solution sheets with planted mistakes (not student photos)
    samples/eval/labels.jsonl     the planted first wrong line and error type for each sheet
    samples/demo/sheets.json      hand-written sample transcriptions and diagnoses for `fws demo`

The demo diagnoses are written by hand to show the screens without an API key. They are
not model output, and the review page says so.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
EXAM = "SAMPLE (written for this repo, not an exam item)"


def item(i, subject, unit, skills, text, answer, points, choices=()):
    return dict(item_id=f"sample-{i:02d}", exam=EXAM, number=i, subject=subject, unit=unit, skills=skills,
                text_latex=text, choices=list(choices), answer=answer, points=points, correct_rate=None,
                page=None, source_pdf=None)


BANK = [
    item(1, "수학I", "수열", ["등차수열"], r"첫째항이 $3$이고 공차가 $4$인 등차수열 $\{a_n\}$에 대하여 $a_{10}$의 값을 구하시오.", "39", 2),
    item(2, "수학I", "수열", ["등차수열"], r"등차수열 $\{a_n\}$에 대하여 $a_3=7$, $a_7=19$일 때, $a_{10}$의 값을 구하시오.", "28", 3),
    item(3, "수학I", "수열", ["등차수열", "수열의 합과 시그마"], r"$a_1=1$인 등차수열 $\{a_n\}$의 첫째항부터 제$10$항까지의 합이 $145$일 때, $a_{10}$의 값을 구하시오.", "28", 4),
    item(4, "확률과 통계", "확률", ["조건부확률"], r"두 사건 $A$, $B$에 대하여 $P(A)=\frac{1}{2}$, $P(A\cap B)=\frac{1}{5}$일 때, $P(B\mid A)$의 값은?", "③", 2,
         [r"$\frac{1}{5}$", r"$\frac{3}{10}$", r"$\frac{2}{5}$", r"$\frac{1}{2}$", r"$\frac{3}{5}$"]),
    item(5, "확률과 통계", "확률", ["조건부확률"], r"흰 공 $3$개와 검은 공 $2$개가 들어 있는 주머니에서 공을 한 개씩 두 번 꺼낸다. 꺼낸 공은 다시 넣지 않는다. 첫 번째 공이 흰 공일 때, 두 번째 공도 흰 공일 확률은?", "③", 3,
         [r"$\frac{1}{4}$", r"$\frac{2}{5}$", r"$\frac{1}{2}$", r"$\frac{3}{5}$", r"$\frac{3}{4}$"]),
    item(6, "확률과 통계", "확률", ["조건부확률", "확률의 뜻과 덧셈정리"], r"두 사건 $A$, $B$에 대하여 $P(A)=0.4$, $P(B\mid A)=0.5$, $P(B\mid A^C)=0.25$일 때, $P(A\mid B)$의 값은?", "③", 4,
         [r"$\frac{3}{7}$", r"$\frac{1}{2}$", r"$\frac{4}{7}$", r"$\frac{2}{3}$", r"$\frac{5}{7}$"]),
    item(7, "수학II", "미분", ["극대와 극소"], r"함수 $f(x)=x^3-3x$의 극댓값을 구하시오.", "2", 2),
    item(8, "수학II", "미분", ["극대와 극소"], r"함수 $f(x)=x^3-6x^2+9x+1$의 극댓값과 극솟값의 합을 구하시오.", "6", 3),
    item(9, "수학II", "미분", ["극대와 극소", "미분계수와 도함수"], r"함수 $f(x)=x^3+ax^2+bx$가 $x=1$과 $x=3$에서 극값을 가질 때, $a+b$의 값을 구하시오. (단, $a$, $b$는 상수이다.)", "3", 4),
    item(10, "수학I", "지수함수와 로그함수", ["로그방정식과 부등식"], r"방정식 $\log_2(x+1)=3$의 해를 구하시오.", "7", 2),
    item(11, "수학I", "지수함수와 로그함수", ["로그방정식과 부등식"], r"방정식 $\log_2 x+\log_2(x-2)=3$의 해를 구하시오.", "4", 3),
    item(12, "수학I", "지수함수와 로그함수", ["로그방정식과 부등식", "지수와 로그의 성질"], r"방정식 $\log_3(x-1)+\log_3(x+1)=1$을 만족시키는 모든 실수 $x$의 값의 합을 구하시오.", "2", 4),
]

# Each sheet: (bank item, [(shown on the page, latex)], final answer, planted first wrong line, error type, sample diagnosis)
SHEETS = [
    ("sample-11",
     [("log2 x + log2 (x-2) = 3", r"\log_2 x+\log_2(x-2)=3"),
      ("log2 x(x-2) = 3", r"\log_2 x(x-2)=3"),
      ("x(x-2) = 8", r"x(x-2)=8"),
      ("x^2 - 2x - 8 = 0", r"x^2-2x-8=0"),
      ("(x-4)(x+2) = 0", r"(x-4)(x+2)=0"),
      ("x = 4, -2", r"x=4, -2")],
     "4, -2", 6, "condition",
     dict(what_went_wrong="6번째 줄에서 진수 조건 x>2를 확인하지 않아 x=-2를 해로 남겼어요.",
          corrected_line=r"x>2 \text{ 이므로 } x=4",
          feedback="3번째 줄까지 로그의 합을 곱의 로그로 묶고 지수로 바꾼 과정은 정확해요. 6번째 줄에서 x=-2를 해로 남긴 게 문제예요. "
                   "로그방정식은 식을 풀기 전에 진수 조건부터 적어야 해요. 이 문제는 x>0과 x-2>0을 함께 만족해야 하니 범위가 x>2예요. "
                   "이 범위로 5번째 줄의 두 근을 다시 걸러 보세요.",
          habit="로그가 보이면 첫 줄에 진수 조건을 먼저 적고, 마지막 줄에서 그 조건으로 근을 거른다.",
          skill_tags=["로그방정식과 부등식"], confidence=0.93)),
    ("sample-08",
     [("f'(x) = 3x^2 - 12x + 9", r"f'(x)=3x^2-12x+9"),
      ("= 3(x-1)(x-3)", r"f'(x)=3(x-1)(x-3)"),
      ("max: f(1) = 1 - 6 + 9 + 1 = 5", r"f(1)=1-6+9+1=5"),
      ("min: f(3) = 27 - 54 + 27 + 1 = 2", r"f(3)=27-54+27+1=2"),
      ("5 + 2 = 7", r"5+2=7")],
     "7", 4, "arithmetic",
     dict(what_went_wrong="4번째 줄의 계산 27-54+27+1은 1인데 2로 적었어요.",
          corrected_line=r"f(3)=27-54+27+1=1",
          feedback="도함수를 인수분해해서 x=1에서 극대, x=3에서 극소인 것을 찾은 흐름은 맞아요. 4번째 줄에서 f(3)을 계산할 때 27-54+27+1을 2로 적었는데, 실제 값은 1이에요. "
                   "개념이 아니라 계산에서 점수가 빠진 경우예요. 극값을 대입할 때는 항을 두 개씩 묶어 계산하면 실수가 줄어요.",
          habit="함숫값을 대입한 줄은 항을 두 개씩 묶어 한 번 더 계산한다.",
          skill_tags=["극대와 극소"], confidence=0.97)),
    ("sample-06",
     [("P(A n B) = 0.4 x 0.5 = 0.2", r"P(A\cap B)=0.4\times 0.5=0.2"),
      ("P(A^c n B) = 0.4 x 0.25 = 0.1", r"P(A^c\cap B)=0.4\times 0.25=0.1"),
      ("P(B) = 0.2 + 0.1 = 0.3", r"P(B)=0.2+0.1=0.3"),
      ("P(A|B) = 0.2 / 0.3 = 2/3", r"P(A|B)=\frac{0.2}{0.3}=\frac{2}{3}")],
     "④", 2, "concept",
     dict(what_went_wrong="2번째 줄에서 P(A^C∩B)를 구할 때 P(A^C)=0.6 대신 P(A)=0.4를 곱했어요.",
          corrected_line=r"P(A^C\cap B)=0.6\times 0.25=0.15",
          feedback="1번째 줄에서 곱셈정리로 P(A∩B)를 구한 것은 맞아요. 2번째 줄에서 P(A^C∩B)=P(A^C)P(B|A^C)인데, P(A^C)가 아니라 P(A)를 곱했어요. "
                   "조건부확률의 곱셈정리에서는 조건이 되는 사건의 확률을 곱해야 해요. 2번째 줄을 고치면 P(B)부터 다시 정해지니 3번째 줄부터 다시 풀어 보세요.",
          habit="곱셈정리를 쓸 때 P(B|X) 옆에 곱하는 확률이 같은 X인지 확인한다.",
          skill_tags=["조건부확률"], confidence=0.9)),
    ("sample-09",
     [("f'(x) = 3x^2 + 2ax + b", r"f'(x)=3x^2+2ax+b"),
      ("f'(x) = 3(x-1)(x-3) = 3x^2 - 12x + 9", r"3(x-1)(x-3)=3x^2-12x+9"),
      ("2a = -12, b = 9", r"2a=-12"),
      ("a = -6", r"a=-6"),
      ("a + b = 3", r"a+b=3")],
     "3", None, None,
     dict(what_went_wrong="", corrected_line="",
          feedback="극값을 갖는 두 x값이 도함수의 두 근이라는 점을 바로 써서 f'(x)=3(x-1)(x-3)으로 놓은 게 이 풀이의 핵심이에요. "
                   "계수를 비교해서 a와 b를 구한 과정도 정확해요. 다만 극값을 가지려면 그 점에서 f'(x)의 부호가 바뀌어야 하는데, "
                   "서로 다른 두 근이라 부호가 바뀐다는 한 줄을 덧붙이면 서술형에서도 감점이 없어요.",
          habit="도함수의 근으로 극값을 잡을 때 부호가 바뀌는지 한 줄 적는다.",
          skill_tags=["극대와 극소"], confidence=0.95)),
    ("sample-03",
     [("S10 = 10(a1 + a10)/2", r"S_{10}=\frac{10(a_1+a_{10})}{2}"),
      ("145 = 10(1 + a10)", r"145=10(1+a_{10})"),
      ("1 + a10 = 14.5", r"1+a_{10}=14.5"),
      ("a10 = 13.5", r"a_{10}=13.5")],
     "13.5", 2, "algebra",
     dict(what_went_wrong="2번째 줄에서 분모 2를 빠뜨려 145=5(1+a10)이 아니라 145=10(1+a10)으로 적었어요.",
          corrected_line=r"145=5(1+a_{10})",
          feedback="등차수열의 합을 첫째항과 끝항으로 나타낸 1번째 줄은 맞아요. 2번째 줄로 옮길 때 분모 2가 사라졌어요. "
                   "식을 대입하면서 분수를 정리할 때 흔히 생기는 식 변형 실수예요. 답이 정수가 아니게 나온 것도 신호였어요. 2번째 줄을 고쳐서 다시 풀어 보세요.",
          habit="단답형에서 답이 정수가 아니면 바로 앞 두 줄의 식 변형을 다시 본다.",
          skill_tags=["수열의 합과 시그마", "등차수열"], confidence=0.92)),
    ("sample-02",
     [("a7 - a3 = 4d = 12", r"4d=12"),
      ("d = 3", r"d=3"),
      ("a1 = a3 - 2d = 1", r"a_1=7-2\times 3=1"),
      ("a10 = a1 + 10d = 31", r"a_{10}=1+10\times 3=31")],
     "31", 4, "concept",
     dict(what_went_wrong="4번째 줄에서 일반항을 a1+(n-1)d가 아니라 a1+nd로 써서 10d를 더했어요.",
          corrected_line=r"a_{10}=a_1+9d=1+27=28",
          feedback="두 항의 차로 공차를 구하고 a1을 거꾸로 구한 3번째 줄까지는 정확해요. 4번째 줄에서 a10을 a1+10d로 적었어요. "
                   "등차수열의 일반항은 a_n=a1+(n-1)d라서 제10항까지는 공차를 9번 더해요. 3번째 줄에서는 2d를 맞게 뺐으니, 같은 원리로 4번째 줄을 다시 써 보세요.",
          habit="일반항을 쓸 때 n=1을 넣어 a1이 나오는지 확인한다.",
          skill_tags=["등차수열"], confidence=0.88)),
]


def render(lines: list[str], path: Path) -> None:
    """A plain rendered page in a handwriting-style font. Not a photo of a student."""
    font_path = "C:/Windows/Fonts/LHANDW.TTF"
    try:
        font = ImageFont.truetype(font_path, 46)
        small = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 30)
    except OSError:
        font = small = ImageFont.load_default()
    img = Image.new("RGB", (1700, 300 + 120 * len(lines)), (250, 249, 244))
    d = ImageDraw.Draw(img)
    for y in range(160, img.height, 60):
        d.line([(80, y), (1620, y)], fill=(214, 226, 238), width=2)
    d.text((80, 50), "SAMPLE sheet, rendered for testing. Not a student photo.", font=small, fill=(150, 150, 150))
    for i, line in enumerate(lines):
        d.text((110 + (i % 2) * 14, 190 + 120 * i), line, font=font, fill=(30, 40, 90))
    img.save(path)


def main() -> None:
    (HERE / "eval").mkdir(exist_ok=True)
    (HERE / "demo").mkdir(exist_ok=True)
    (HERE / "bank.sample.jsonl").write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in BANK) + "\n", encoding="utf-8")

    labels, demo = [], []
    for k, (item_id, steps, answer, wrong, etype, diag) in enumerate(SHEETS, 1):
        name = f"sheet-{k:02d}.png"
        render([s for s, _ in steps] + [f"answer: {answer}"], HERE / "eval" / name)
        labels.append({"image": name, "map": {"1": item_id},
                       "problems": {"1": {"first_wrong_step": wrong, "error_type": etype}}})
        demo.append({
            "image": f"eval/{name}", "item_id": item_id,
            "transcription": {"label": "1", "source_hint": None, "final_answer": answer, "steps": [
                {"n": n, "latex": latex, "text": "", "legibility": "clear", "crossed_out": False}
                for n, (_, latex) in enumerate(steps, 1)]},
            "diagnosis": {"is_correct": wrong is None, "first_wrong_step": wrong, "error_type": etype, **diag},
        })
    (HERE / "eval" / "labels.jsonl").write_text("\n".join(json.dumps(l, ensure_ascii=False) for l in labels) + "\n", encoding="utf-8")
    (HERE / "demo" / "sheets.json").write_text(json.dumps(demo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(BANK)} bank items, {len(SHEETS)} sheets")


if __name__ == "__main__":
    main()
