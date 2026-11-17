"""Teacher review queue on localhost, standard library only.

/                      sheets, newest first, with how many problems wait for review
/sheet/<id>            photo, lines with checker marks, the model's diagnosis as an editable form
/sheet/<id>/<idx>      POST: approve (with edits)
/image/<id>            the photo
/report/<id>           the student report as it would be sent now
"""

from __future__ import annotations

import time
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from .bank import Bank
from .models import Diagnosis
from .recommend import recommend
from .report import CSS, render_sheet
from .store import Store
from .taxonomy import ERROR_TYPES

MARK = {"ok": "ok", "broken": "BROKEN", "suspect": "suspect", "unparsed": "", "skipped": ""}


def _page(title: str, body: str) -> bytes:
    return (f"<!doctype html><html lang=ko><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{escape(title)}</title><style>{CSS} .grid{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:24px}}"
            f"main{{max-width:1280px}} img{{width:100%;border:1px solid var(--line)}} textarea,input,select{{width:100%;font:inherit;"
            f"background:var(--paper);color:var(--ink);border:1px solid var(--line);padding:6px}} code{{white-space:pre-wrap;font-family:Consolas,monospace}}"
            f".broken{{font-weight:700}} button{{font:inherit;padding:6px 16px;margin-top:8px}}"
            f"@media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}</style></head><body><main>{body}</main></body></html>").encode()


def make_handler(store: Store, bank: Bank):
    class H(BaseHTTPRequestHandler):
        def _send(self, body: bytes, ctype="text/html; charset=utf-8", code=200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):  # quiet
            pass

        def do_GET(self):
            parts = [p for p in self.path.split("/") if p]
            if not parts:
                rows = "".join(
                    f"<tr><td><a href='/sheet/{r['sheet_id']}'>{escape(r['sheet_id'])}</a></td><td>{escape(r['student'])}</td>"
                    f"<td>{time.strftime('%m-%d %H:%M', time.localtime(r['created']))}</td><td>{r['pending']} / {r['problems']} waiting</td></tr>"
                    for r in store.sheets())
                return self._send(_page("Review queue", f"<h1>Review queue</h1><table>{rows or '<tr><td>No sheets yet.</td></tr>'}</table>"))
            if parts[0] == "image" and len(parts) == 2:
                r = store.sheet(parts[1])
                if not r:
                    return self._send(b"not found", "text/plain", 404)
                p = Path(r.image_path)
                ctype = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
                return self._send(p.read_bytes(), ctype)
            if parts[0] == "report" and len(parts) == 2:
                r = store.sheet(parts[1])
                return self._send(render_sheet(r, store, bank).encode()) if r else self._send(b"not found", "text/plain", 404)
            if parts[0] == "sheet" and len(parts) == 2:
                return self._send(self._sheet(parts[1]))
            self._send(b"not found", "text/plain", 404)

        def _sheet(self, sid: str) -> bytes:
            r = store.sheet(sid)
            if not r:
                return _page("Not found", "<p>Not found</p>")
            reviews = store.reviews(sid)
            blocks = []
            for i, (p, rv) in enumerate(zip(r.problems, reviews)):
                d = Diagnosis.model_validate_json(rv["final_json"] or rv["original_json"])
                checks = {c.n: c for c in p.checks}
                lines = "".join(
                    f"<div class='{checks[s.n].status if s.n in checks else ''}'><code>{s.n}. {escape(s.latex)} {escape(s.text)}"
                    f"{' [crossed out]' if s.crossed_out else ''}{' [' + s.legibility + ']' if s.legibility != 'clear' else ''}"
                    f"  {MARK.get(checks[s.n].status, '') if s.n in checks else ''} {escape(checks[s.n].detail) if s.n in checks and checks[s.n].status in ('broken', 'suspect') else ''}</code></div>"
                    for s in p.transcription.steps)
                opts = "".join(f"<option value='{k}' {'selected' if d.error_type == k else ''}>{escape(v)}</option>"
                               for k, v in ERROR_TYPES.items())
                item = bank.get(p.bank_item_id)
                why = "".join(f"<li>{escape(x)}</li>" for x in p.route_reasons) or "<li>none</li>"
                state = {"pending": "waiting for review", "approved": "approved", "auto": "sent without review"}[rv["status"]]
                blocks.append(f"""<section><h2>Problem {escape(p.label)} <span class=meta>{state}</span></h2>
<p class=meta>Bank: {escape(item.exam + ' ' + str(item.number) + '번, answer ' + item.answer) if item else 'no match'}.
Marked answer: {escape(p.transcription.final_answer or 'none')}, matches key: {p.answer_matches_key}. Model confidence {d.confidence:.2f}.</p>
<p class=meta>Why it was routed here:</p><ul class=meta>{why}</ul>{lines}
<form method=post action='/sheet/{sid}/{i}'>
<label>Correct <select name=is_correct><option value=0 {'selected' if not d.is_correct else ''}>no</option><option value=1 {'selected' if d.is_correct else ''}>yes</option></select></label>
<label>First wrong line <input name=first_wrong_step value='{d.first_wrong_step or ''}'></label>
<label>Error type <select name=error_type><option value=''>none</option>{opts}</select></label>
<label>Skill tags (comma separated) <input name=skill_tags value='{escape(', '.join(d.skill_tags))}'></label>
<label>What went wrong <textarea name=what_went_wrong rows=2>{escape(d.what_went_wrong)}</textarea></label>
<label>Corrected line (LaTeX) <input name=corrected_line value='{escape(d.corrected_line)}'></label>
<label>Feedback to student <textarea name=feedback rows=6>{escape(d.feedback)}</textarea></label>
<label>Habit <input name=habit value='{escape(d.habit)}'></label>
<label>Note (not sent) <input name=note></label>
<button>Approve</button></form></section>""")
            banner = ("<p class=meta><b>SAMPLE data.</b> Problems, sheet and diagnosis are written for this repo; "
                      "the checker, routing and recommendations ran for real.</p>") if r.model.startswith("SAMPLE") else ""
            body = (f"{banner}<p><a href='/'>Queue</a> <a href='/report/{sid}'>Student report</a></p><h1>{escape(r.student)} {escape(sid)}</h1>"
                    f"<p class=meta>{escape(r.page_notes)} {r.usage.get('calls')} calls, ${r.usage.get('cost_usd')}, {r.seconds}s</p>"
                    f"<div class=grid><div><img src='/image/{sid}' alt='Student photo'></div><div>{''.join(blocks)}</div></div>")
            return _page(f"Review {sid}", body)

        def do_POST(self):
            parts = [p for p in self.path.split("/") if p]
            if len(parts) != 3 or parts[0] != "sheet":
                return self._send(b"not found", "text/plain", 404)
            sid, idx = parts[1], int(parts[2])
            n = int(self.headers.get("Content-Length", 0))
            f = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode(), keep_blank_values=True).items()}
            r = store.sheet(sid)
            orig = Diagnosis.model_validate_json(store.reviews(sid)[idx]["original_json"])
            final = orig.model_copy(update={
                "is_correct": f.get("is_correct") == "1",
                "first_wrong_step": int(f["first_wrong_step"]) if f.get("first_wrong_step", "").strip().isdigit() else None,
                "error_type": f.get("error_type") or None,
                "skill_tags": [t.strip() for t in f.get("skill_tags", "").split(",") if t.strip()],
                "what_went_wrong": f.get("what_went_wrong", ""), "corrected_line": f.get("corrected_line", ""),
                "feedback": f.get("feedback", ""), "habit": f.get("habit", ""),
            })
            store.decide(sid, idx, final, f.get("note", ""))
            # Tags may have changed, so pick follow-up problems again from the approved diagnosis.
            p = r.problems[idx]
            given = store.given(r.student) - {x.item_id for x in p.recommendations}
            p.recommendations = recommend(bank, final, bank.get(p.bank_item_id), given)
            store.replace_sheet(r)
            self.send_response(303)
            self.send_header("Location", f"/sheet/{sid}")
            self.end_headers()

    return H


def serve(store: Store, bank: Bank, port: int = 8765) -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(store, bank))
    print(f"Review queue on http://127.0.0.1:{port}")
    srv.serve_forever()
