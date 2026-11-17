from fws.models import Step
from fws.verify import answers_match, check_steps, parse


def S(n, latex, crossed=False):
    return Step(n=n, latex=latex, text="", legibility="clear", crossed_out=crossed)


def status(lines):
    return [c.status for c in check_steps([S(i + 1, l) for i, l in enumerate(lines)])]


def test_parse_basics():
    assert parse(r"\frac{1}{2}+\frac{1}{3}") is not None
    assert parse(r"2+3\times 4") is not None


def test_equation_root_change_is_caught():
    assert status(["x^2-5x+6=0", "(x-2)(x-3)=0", "(x-1)(x-6)=0"]) == ["ok", "ok", "broken"]


def test_identity_chain():
    assert status([r"(a+b)^2=a^2+2ab+b^2"]) == ["ok"]


def test_false_expansion_is_caught():
    assert status([r"(a+b)^2=a^2+b^2"]) == ["suspect"]


def test_arithmetic():
    assert status([r"\frac{1}{2}+\frac{1}{3}=\frac{5}{6}", r"2+3\times 4=20"]) == ["ok", "broken"]


def test_crossed_out_and_inequality_are_not_judged():
    checks = check_steps([S(1, "x=3", crossed=True), S(2, "x>2")])
    assert [c.status for c in checks] == ["skipped", "unparsed"]


def test_answers():
    assert answers_match(r"\frac{5}{6}", "5/6") is True
    assert answers_match("③", "3") is True
    assert answers_match("12", "13") is False
    assert answers_match(None, "13") is None
