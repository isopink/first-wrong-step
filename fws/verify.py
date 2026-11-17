"""Deterministic checks on a transcribed solution, independent of the LLM.

What it can say, line by line:
- a chain written as one line (a = b = c) holds or does not hold as an identity or as arithmetic
- an equation keeps or changes its solution set from the previous equation line
- a list of roots (x = 4, -2) matches or differs from the previous equation's roots
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
_NOT_CHECKED = ("<", ">", r"\le", r"\ge", r"\ne", r"\Rightarrow", r"\iff")


def _clean(latex: str) -> str:
    s = latex.strip().strip("$")
    for a, b in _REPLACE:
        s = s.replace(a, b)
    s = re.sub(r"\\(text|mathrm)\{[^}]*\}", " ", s)
    return s.strip().rstrip(".,")


def parse(latex: str):
    """LaTeX to a SymPy expression, or None. Decimals become exact fractions."""
    s = _clean(latex)
    if not s or len(s) > MAX_LATEX or "," in s:
        return None
    try:
        from sympy.parsing.latex import parse_latex

        e = parse_latex(s)
    except Exception:
        try:  # plain answers like 12, -3/4, 2*sqrt(3)
            e = sp.sympify(s.replace("^", "**"), evaluate=True)
        except Exception:
            return None
    if not isinstance(e, sp.Expr):
        return None
    if e.has(sp.Float):
        e = sp.nsimplify(e, rational=True)
    return e


def _is_name(e) -> bool:
    """A bare symbol or a function value like f(3) or P(A): a name being assigned."""
    return isinstance(e, (sp.Symbol, sp.core.function.AppliedUndef))


def _compound(e) -> bool:
    return not (_is_name(e) or e.is_Number)


def _same_value(a, b, trials: int = 4) -> bool | None:
    """True if a and b agree as functions (checked at random points), None if unknown."""
    try:
        diff = a - b
        syms = sorted(diff.free_symbols, key=str)
        if not syms:
            return abs(complex(sp.N(diff))) < 1e-9
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


def _value_list(text: str):
    """'4, -2' or '4 or -2' or '4 또는 -2' to a FiniteSet of numbers, else None."""
    parts = [p for p in re.split(r",|\bor\b|또는", _clean(text)) if p.strip()]
    if len(parts) < 2:
        return None
    vals = [parse(p) for p in parts]
    if any(v is None or v.free_symbols for v in vals):
        return None
    return sp.FiniteSet(*vals)


def _check_line(st: Step, prev_solutions):
    """(status, detail, solutions to carry to the next line)."""
    if st.crossed_out:
        return "skipped", "crossed out", prev_solutions
    if not st.latex.strip() or st.legibility == "illegible":
        return "skipped", "no math or illegible", prev_solutions
    if any(op in st.latex for op in _NOT_CHECKED):
        return "unparsed", "inequality or implication not checked", None
    pieces = [p.strip() for p in _REL_SPLIT.split(_clean(st.latex)) if p.strip()]

    # "x = 4, -2": roots listed, compared with the previous equation's roots.
    if len(pieces) == 2:
        head = parse(pieces[0])
        vals = _value_list(pieces[1])
        if head is not None and _is_name(head) and vals is not None:
            if prev_solutions is not None and vals != prev_solutions:
                return "broken", f"roots listed {sp.sstr(vals)} differ from the previous equation's {sp.sstr(prev_solutions)}", vals
            return "ok", f"roots {sp.sstr(vals)}", vals

    exprs = [parse(p) for p in pieces]
    # A leading name (f(3) = ..., P(A|B) = ..., a_1 = ...) is being assigned; check the rest of the chain.
    lead = len(exprs) >= 3 and (exprs[0] is None or _is_name(exprs[0]))
    if lead:
        pieces, exprs = pieces[1:], exprs[1:]
    if len(exprs) < 2 or any(e is None for e in exprs):
        return "unparsed", "could not parse", prev_solutions

    links = [_same_value(exprs[i], exprs[i + 1]) for i in range(len(exprs) - 1)]
    if all(l is True for l in links):
        return "ok", "each '=' holds" + (" after the assigned name" if lead else ""), prev_solutions
    if False in links:
        bad = links.index(False)
        a, b = exprs[bad], exprs[bad + 1]
        if not (a - b).free_symbols:
            return "broken", f"arithmetic: {pieces[bad]} is not equal to {pieces[bad + 1]}", prev_solutions
        if len(exprs) > 2 or lead:
            return "broken", f"{pieces[bad]} = {pieces[bad + 1]} does not hold for all values", prev_solutions

    if len(exprs) == 2:  # an equation with symbols: compare its roots with the previous one
        sols = _solutions(exprs[0], exprs[1])
        if sols is not None:
            if prev_solutions is not None and sols != prev_solutions:
                return "broken", f"solution set changed from {sp.sstr(prev_solutions)} to {sp.sstr(sols)}", sols
            return "ok", f"equation, solutions {sp.sstr(sols)}", sols
        if _compound(exprs[0]) and _compound(exprs[1]):
            return "suspect", f"{pieces[0]} = {pieces[1]} is not an identity; fine only if it is an equation or a given condition", None
        return "unparsed", "equation in several unknowns, not checked", None
    return "unparsed", "chain not checked", prev_solutions


def check_steps(steps: list[Step]) -> list[StepCheck]:
    out: list[StepCheck] = []
    prev = None
    for st in steps:
        status, detail, prev = _check_line(st, prev)
        out.append(StepCheck(n=st.n, status=status, detail=detail))
    return out


def answers_match(student: str | None, key: str | None) -> bool | None:
    if not student or not key:
        return None
    circled = "①②③④⑤"

    def norm(t: str) -> str:
        t = _clean(t)
        return str(circled.index(t) + 1) if t in circled else t

    a, b = norm(student), norm(key)
    if a.replace(" ", "") == b.replace(" ", ""):
        return True
    la, lb = _value_list(a), _value_list(b)
    if la is not None or lb is not None:  # several answers must match as a set
        ea, eb = parse(a), parse(b)
        sa = la if la is not None else (sp.FiniteSet(ea) if ea is not None else None)
        sb = lb if lb is not None else (sp.FiniteSet(eb) if eb is not None else None)
        return None if sa is None or sb is None else sa == sb
    ea, eb = parse(a), parse(b)
    if ea is None or eb is None:
        return None
    return _same_value(ea, eb)
