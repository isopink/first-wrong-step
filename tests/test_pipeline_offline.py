"""End to end without the network: a fake client returns fixed JSON, so this checks the
plumbing (schemas, routing, store, review server, report), not the model's judgement."""

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

from PIL import Image

from fws.bank import Bank
from fws.llm import LLM, strict_schema
from fws.models import BankItem, Diagnosis
from fws.pipeline import process_sheet
from fws.report import render_sheet
from fws.review import make_handler
from fws.store import Store

TRANSCRIPTION = {"page_notes": "", "problems": [{"label": "1", "source_hint": None, "final_answer": "1, 6", "steps": [
    {"n": 1, "latex": "x^2-5x+6=0", "text": "", "legibility": "clear", "crossed_out": False},
    {"n": 2, "latex": "(x-1)(x-6)=0", "text": "", "legibility": "clear", "crossed_out": False},
    {"n": 3, "latex": "x=1, 6", "text": "", "legibility": "clear", "crossed_out": False}]}]}
DIAGNOSIS = {"is_correct": False, "first_wrong_step": 2, "error_type": "algebra", "skill_tags": ["지수와 로그의 성질"],
             "what_went_wrong": "2번째 줄 인수분해", "corrected_line": "(x-2)(x-3)=0", "feedback": "f", "habit": "h", "confidence": 0.9}


class FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        body = TRANSCRIPTION if "transcribe" in kw["system"][0]["text"][:40] else DIAGNOSIS
        return SimpleNamespace(stop_reason="end_turn", model=kw["model"], content=[SimpleNamespace(type="text", text=json.dumps(body))],
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=0))


def test_schema_is_closed():
    s = strict_schema(Diagnosis)
    assert s["additionalProperties"] is False and set(s["required"]) == set(s["properties"])


def test_end_to_end(tmp_path):
    photo = tmp_path / "p.jpg"
    Image.new("RGB", (3000, 2000), "white").save(photo)
    fake = FakeMessages()
    client = SimpleNamespace(beta=SimpleNamespace(messages=fake), messages=fake)
    llm = LLM(model="claude-opus-5-5", client=client)

    bank = Bank(tmp_path / "bank.jsonl")
    for i, rate in ((1, 0.5), (2, 0.8)):
        it = BankItem(item_id=f"t-{i}", exam="TEST", number=i, subject="수학I", unit="지수함수와 로그함수",
                      skills=["지수와 로그의 성질"], text_latex="fixture $x$", choices=[], answer="2, 3", correct_rate=rate)
        bank.items[it.item_id] = it

    r = process_sheet(photo, "s01", bank, llm, {"1": "t-1"}, set(), log=lambda *_: None)
    p = r.problems[0]
    assert [c.status for c in p.checks][:2] == ["ok", "broken"]
    assert p.answer_matches_key is False
    assert p.route == "auto" and p.recommendations[0].item_id == "t-2"
    assert r.usage["calls"] == 2 and r.usage["cost_usd"] == round(2 * (1000 * 4 + 200 * 20) / 1e6, 5)
    assert fake.calls[0]["fallbacks"] == "default"

    store = Store(tmp_path / "db.sqlite")
    store.add_sheet(r)
    html = render_sheet(r, store, bank)
    assert "2번째 줄부터" in html and "TEST 2번: 2, 3" in html

    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store, bank))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    assert "s01" in urllib.request.urlopen(base + "/").read().decode()
    assert "BROKEN" in urllib.request.urlopen(f"{base}/sheet/{r.sheet_id}").read().decode()
    form = "is_correct=0&first_wrong_step=1&error_type=concept&skill_tags=%EC%A7%80%EC%88%98%EC%99%80+%EB%A1%9C%EA%B7%B8%EC%9D%98+%EC%84%B1%EC%A7%88&feedback=new&habit=h&what_went_wrong=w&corrected_line=&note="
    urllib.request.urlopen(urllib.request.Request(f"{base}/sheet/{r.sheet_id}/0", data=form.encode(), method="POST"))
    srv.shutdown()
    final = store.final_diagnoses(r.sheet_id)[0]
    assert final.first_wrong_step == 1 and final.error_type == "concept" and final.feedback == "new"
    assert store.profile("s01")["errors"] == {"concept": 1}

    # The teacher's correction comes back as a few-shot example on the next sheet with the same skill.
    assert store.corrections(["지수와 로그의 성질"])[0]["teacher"]["error_type"] == "concept"
    process_sheet(photo, "s02", bank, llm, {"1": "t-1"}, set(), log=lambda *_: None, fewshot="teacher", store=store)
    last = fake.calls[-1]
    assert "Worked examples" in last["system"][0]["text"]
    assert any("Teacher corrected to" in c.get("text", "") for c in last["messages"][0]["content"])
    process_sheet(photo, "s03", bank, llm, {"1": "t-1"}, set(), log=lambda *_: None, fewshot="off", store=store)
    assert "Worked examples" not in fake.calls[-1]["system"][0]["text"]
