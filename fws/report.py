"""Printable one-sheet report for the student. Only released diagnoses appear in it."""

from __future__ import annotations

from html import escape

from .bank import Bank
from .models import SheetResult
from .store import Store
from .taxonomy import ERROR_TYPES

KATEX = "https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.9"

CSS = """
:root{--ink:#111;--muted:#666;--line:#ddd;--paper:#fff}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--ink:#eee;--muted:#999;--line:#333;--paper:#111}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.65 "Pretendard","Apple SD Gothic Neo","Malgun Gothic",sans-serif}
main{max-width:760px;margin:0 auto;padding:32px 16px}h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 8px}
.meta{color:var(--muted);font-size:13px}section{border-top:1px solid var(--line);padding:16px 0}
.verdict{font-weight:600}.fix{padding:8px 12px;border-left:3px solid var(--ink);margin:8px 0;overflow-x:auto}
.item{border:1px solid var(--line);padding:12px;margin:8px 0;break-inside:avoid}.why{color:var(--muted);font-size:13px}
table{border-collapse:collapse;font-size:14px}td{padding:2px 12px 2px 0}.answers{font-size:13px;color:var(--muted)}
@media print{main{padding:0}a{color:inherit}}
"""


def _p(text: str) -> str:
    return "".join(f"<p>{escape(t)}</p>" for t in text.split("\n") if t.strip())


def render_sheet(r: SheetResult, store: Store, bank: Bank) -> str:
    finals = store.final_diagnoses(r.sheet_id)
    prof = store.profile(r.student)
    parts: list[str] = []
    answers: list[str] = []
    for p, d in zip(r.problems, finals):
        head = f"<h2>{escape(p.label)}번</h2>"
        if d is None:
            parts.append(f"<section>{head}<p class=meta>선생님이 확인하고 있어요. 확인이 끝나면 다시 보내 드릴게요.</p></section>")
            continue
        verdict = "맞았어요" if d.is_correct else f"{d.first_wrong_step}번째 줄부터 다시 볼게요. ({ERROR_TYPES.get(d.error_type or '', '').split(':')[0]})"
        fix = f"<div class=fix>$${escape(d.corrected_line)}$$</div>" if d.corrected_line else ""
        items = []
        for rec in p.recommendations:
            it = bank.get(rec.item_id)
            if not it:
                continue
            ch = "".join(f"<div>({i + 1}) {escape(c)}</div>" for i, c in enumerate(it.choices))
            items.append(f"<div class=item><div class=why>{escape(rec.reason)}</div>{_p(it.text_latex)}{ch}</div>")
            answers.append(f"{escape(it.exam)} {it.number}번: {escape(it.answer)}")
        more = f"<h3>이어서 풀 문제</h3>{''.join(items)}" if items else ""
        parts.append(f"<section>{head}<p class=verdict>{escape(verdict)}</p>{_p(d.feedback)}{fix}"
                     f"<p><b>다음에 확인할 것</b> {escape(d.habit)}</p>{more}</section>")

    rows = "".join(f"<tr><td>{escape(ERROR_TYPES[k].split(':')[0])}</td><td>{v}</td></tr>" for k, v in prof["errors"].items())
    profile = (f"<section><h2>지금까지</h2><p class=meta>확인된 {prof['problems']}문항 중 {prof['wrong']}문항에서 막혔어요.</p>"
               f"<table>{rows}</table></section>") if prof["problems"] else ""
    ans = f"<section class=answers><h2>정답</h2>{'<br>'.join(answers)}</section>" if answers else ""
    return f"""<!doctype html><html lang=ko><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{escape(r.student)} 풀이 첨삭</title><style>{CSS}</style>
<link rel=stylesheet href="{KATEX}/katex.min.css">
<script defer src="{KATEX}/katex.min.js"></script>
<script defer src="{KATEX}/contrib/auto-render.min.js" onload="renderMathInElement(document.body,{{delimiters:[{{left:'$$',right:'$$',display:true}},{{left:'$',right:'$',display:false}}]}})"></script>
</head><body><main><h1>{escape(r.student)} 풀이 첨삭</h1><div class=meta>{escape(r.sheet_id)}{', SAMPLE data, not a real student' if r.model.startswith('SAMPLE') else ''}</div>
{''.join(parts)}{profile}{ans}</main></body></html>"""
