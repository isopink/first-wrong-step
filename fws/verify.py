"""Deterministic checks on a transcribed solution, independent of the LLM.

What it can say, line by line:
- a chain written as one line (a = b = c) holds or does not hold as an identity or as arithmetic
- an equation keeps or changes its solution set from the previous equation line
- the final answer equals or differs from the answer key

Anything it cannot parse is reported as "unparsed", never guessed. The diagnosis
prompt receives these results as evidence, and the router sends a sheet to a teacher
when the two disagree.
"""

from __future__ import annotations

import random
import re

import sympy as sp

from .models import Step, StepCheck

MAX_LATEX = 160
_REL_SPLIT = re.compile(r"(?<![<>!])=(?!=)")

_REPLACE = [
    (r"\left", ""), (r"\right", ""), (r"\dfrac", r"\frac"), (r"\tfrac", r"\frac"),
    (r"\cdot", r"\times "), (r"\,", " "), (r"\;", " "), (r"\!", ""), (r"\quad", " "),
    (r"\qquad", " "), (r"\therefore", ""), (r"\because", ""), (r"\displaystyle", ""),
]


def _clean(latex: str) -> str:
    s = latex.strip().strip("$")
    for a, b in _REPLACE:
        s = s.replace(a, b)
    s = re.sub(r"\\(text|mathrm)\{[^}]*\}", " ", s)
    return s.strip().rstrip(".,")


def parse(latex: str):
    """LaTeX to a SymPy expression, or None."""
    s = _clean(latex)
    if not s or len(s) > MAX_LATEX:
        return None
    try:
        from sympy.parsing.latex import parse_latex

        return parse_latex(s)
    except Exception:
        pass
    try:  # plain answers like 12, -3/4, 2*sqrt(3)
        return sp.sympify(s.replace("^", "**"), evaluate=True)
    except Exception:
        return None


def _same_value(a, b, trials: int = 4) -> bool | None:
    """True if a and b agree as functions (checked at random points), None if unknown."""
    try:
        diff = sp.nsimplify(a - b) if not (a - b).free_symbols else a - b
        syms = sorted(diff.free_symbols, key=str)
        if not syms:
            v = complex(sp.N(diff))
            return abs(v) < 1e-9
        rng = random.Random(7)
        seen = 0
        for _ in range(trials * 3):
            point = {s: sp.Rational(rng.randint(-29, 29), rng.randint(1, 7)) for s in syms}
            try:
                v = complex(sp.N(diff.subs(point)))
            except (TypeError, ValueError, ZeroDivisionError):
                continue
            if v != v or abs(v) == float("inf"):  # nan or pole
                continue
            if abs(v) > 1e-7 * max(1.0, abs(complex(sp.N(a.subs(point))))):
                return False
            seen += 1
            if seen >= trials:
                return True
        return None
    except Exception:
        return None


def _solutions(lhs, rhs):
    syms = (lhs - rhs).free_symbols
    if len(syms) != 1:
        return None
    x = next(iter(syms))
    try:
        sol = sp.solveset(sp.simplify(lhs - rhs), x, domain=sp.S.Reals)
        return sol if isinstance(sol, sp.FiniteSet) else None
    except Exception:
        return None


def check_steps(steps: list[Step]) -> list[StepCheck]:
    out: list[StepCheck] = []
    prev_solutions = None
    for st in steps:
        if st.crossed_out:
            out.append(StepCheck(n=st.n, status="skipped", detail="crossed out"))
            continue
        if not st.latex.strip() or st.legibility == "illegible":
            out.append(StepCheck(n=st.n, status="skipped", detail="no math or illegible"))
            continue
        pieces = [p for p in _REL_SPLIT.split(_clean(st.latex)) if p.strip()]
        if any(op in st.latex for op in ("<", ">", r"\le", r"\ge", r"\ne", r"\Rightarrow", r"\iff")):
            out.append(StepCheck(n=st.n, status="unparsed", detail="inequality or implication not checked"))
            prev_solutions = None
            continue
        exprs = [parse(p) for p in pieces]
        if len(exprs) < 2 or any(e is None for e in exprs):
            out.append(StepCheck(n=st.n, status="unparsed", detail="could not parse"))
            continue

        # 1) Is every link of the chain an identity (or exact arithmetic)?
        links = [_same_value(exprs[i], exprs[i + 1]) for i in range(len(exprs) - 1)]
        if all(l is True for l in links):
            out.append(StepCheck(n=st.n, status="ok", detail="each '=' holds as an identity"))
            continue
        no_symbols = all(not e.free_symbols for e in exprs)
        if no_symbols and any(l is False for l in links):
            bad = links.index(False)
            out.append(StepCheck(n=st.n, status="broken",
                                 detail=f"arithmetic: {pieces[bad].strip()} is not equal to {pieces[bad + 1].strip()}"))
            continue

        # 2) Otherwise treat a two-sided line as an equation and compare its roots with the previous one.
        if len(exprs) == 2:
            sols = _solutions(exprs[0], exprs[1])
            if sols is None:
                if links[0] is False:
                    detail = f"{pieces[0].strip()} = {pieces[1].strip()} is not an identity; fine only if it is an equation or a given condition"
                    out.append(StepCheck(n=st.n, status="suspect", detail=detail))
                else:
                    out.append(StepCheck(n=st.n, status="unparsed", detail="equation not solvable in one variable"))
                prev_solutions = None
                continue
            if prev_solutions is not None and sols != prev_solutions:
                out.append(StepCheck(n=st.n, status="broken",
                                     detail=f"solution set changed from {sp.sstr(prev_solutions)} to {sp.sstr(sols)}"))
            else:
                out.append(StepCheck(n=st.n, status="ok", detail=f"equation, solutions {sp.sstr(sols)}"))
            prev_solutions = sols
            continue
        if any(l is False for l in links):
            bad = links.index(False)
            out.append(StepCheck(n=st.n, status="suspect",
                                 detail=f"{pieces[bad].strip()} = {pieces[bad + 1].strip()} is not an identity; fine only if it is an equation or a given condition"))
            continue
        out.append(StepCheck(n=st.n, status="unparsed", detail="chain is neither identity nor single equation"))
    return out


def answers_match(student: str | None, key: str | None) -> bool | None:
    if not student or not key:
        return None
    a, b = _clean(student), _clean(key)
    circled = "①②③④⑤"
    a = str(circled.index(a) + 1) if a in circled else a
    b = str(circled.index(b) + 1) if b in circled else b
    if a.replace(" ", "") == b.replace(" ", ""):
        return True
    ea, eb = parse(a), parse(b)
    if ea is None or eb is None:
        return None
    same = _same_value(ea, eb)
    return same
