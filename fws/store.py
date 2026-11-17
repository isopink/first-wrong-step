"""SQLite store: sheets, the teacher's review of each problem, and what each student was given.

Teacher edits are kept next to the model's original output. They are the eval set
that grows with use: `fws eval --from-reviews` measures how often teachers had to
change the first wrong line or the error type.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .models import Diagnosis, SheetResult

SCHEMA = """
create table if not exists sheets (
  sheet_id text primary key, student text not null, created real not null, result_json text not null
);
create table if not exists reviews (
  sheet_id text not null, idx integer not null, status text not null,
  original_json text not null, final_json text, reviewer_note text, decided real,
  primary key (sheet_id, idx)
);
create table if not exists given (
  student text not null, item_id text not null, sheet_id text not null, primary key (student, item_id)
);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def add_sheet(self, r: SheetResult) -> None:
        with self.db:
            self.db.execute("insert into sheets values (?,?,?,?)", (r.sheet_id, r.student, time.time(), r.model_dump_json()))
            for i, p in enumerate(r.problems):
                status = "pending" if p.route == "review" else "auto"
                final = p.diagnosis.model_dump_json() if status == "auto" else None
                self.db.execute("insert into reviews values (?,?,?,?,?,?,?)",
                                (r.sheet_id, i, status, p.diagnosis.model_dump_json(), final, None, None))
                for rec in p.recommendations:
                    self.db.execute("insert or ignore into given values (?,?,?)", (r.student, rec.item_id, r.sheet_id))

    def sheet(self, sheet_id: str) -> SheetResult | None:
        row = self.db.execute("select result_json from sheets where sheet_id=?", (sheet_id,)).fetchone()
        return SheetResult.model_validate_json(row[0]) if row else None

    def sheets(self, student: str | None = None) -> list[sqlite3.Row]:
        q = "select s.sheet_id, s.student, s.created, " \
            "sum(r.status='pending') pending, count(r.idx) problems from sheets s join reviews r using(sheet_id) "
        q += ("where s.student=? " if student else "") + "group by s.sheet_id order by s.created desc"
        return self.db.execute(q, (student,) if student else ()).fetchall()

    def replace_sheet(self, r: SheetResult) -> None:
        with self.db:
            self.db.execute("update sheets set result_json=? where sheet_id=?", (r.model_dump_json(), r.sheet_id))
            for p in r.problems:
                for rec in p.recommendations:
                    self.db.execute("insert or ignore into given values (?,?,?)", (r.student, rec.item_id, r.sheet_id))

    def reviews(self, sheet_id: str) -> list[sqlite3.Row]:
        return self.db.execute("select * from reviews where sheet_id=? order by idx", (sheet_id,)).fetchall()

    def decide(self, sheet_id: str, idx: int, final: Diagnosis, note: str = "") -> None:
        with self.db:
            self.db.execute("update reviews set status='approved', final_json=?, reviewer_note=?, decided=? "
                            "where sheet_id=? and idx=?", (final.model_dump_json(), note, time.time(), sheet_id, idx))

    def final_diagnoses(self, sheet_id: str) -> list[Diagnosis | None]:
        """What the student may see: approved or auto-routed diagnoses only."""
        return [Diagnosis.model_validate_json(r["final_json"]) if r["final_json"] else None for r in self.reviews(sheet_id)]

    def given(self, student: str) -> set[str]:
        return {r[0] for r in self.db.execute("select item_id from given where student=?", (student,))}

    def profile(self, student: str) -> dict:
        """Counts of error types and skill tags over all released diagnoses for one student."""
        errors: dict[str, int] = {}
        skills: dict[str, int] = {}
        solved = wrong = 0
        rows = self.db.execute("select r.final_json from reviews r join sheets s using(sheet_id) "
                               "where s.student=? and r.final_json is not null", (student,))
        for (fj,) in rows:
            d = json.loads(fj)
            solved += 1
            if not d["is_correct"]:
                wrong += 1
                if d["error_type"]:
                    errors[d["error_type"]] = errors.get(d["error_type"], 0) + 1
                for t in d["skill_tags"]:
                    skills[t] = skills.get(t, 0) + 1
        return {"problems": solved, "wrong": wrong,
                "errors": dict(sorted(errors.items(), key=lambda kv: -kv[1])),
                "skills": dict(sorted(skills.items(), key=lambda kv: -kv[1]))}

    def corrections(self, skills: list[str], k: int = 3) -> list[dict]:
        """Approved reviews where the teacher changed the verdict, the line or the error type,
        most skill overlap first, then newest. Used as few-shot examples."""
        rows = self.db.execute("select sheet_id, idx, original_json, final_json, decided from reviews "
                               "where status='approved' order by decided desc").fetchall()
        want = set(skills)
        found = []
        for r in rows:
            o, f = json.loads(r["original_json"]), json.loads(r["final_json"])
            if all(o[x] == f[x] for x in ("is_correct", "first_wrong_step", "error_type")):
                continue
            sheet = self.sheet(r["sheet_id"])
            if not sheet or r["idx"] >= len(sheet.problems):
                continue
            steps = [s.model_dump() for s in sheet.problems[r["idx"]].transcription.steps]
            overlap = len(want & set(f["skill_tags"]))
            found.append((overlap, r["decided"], {"steps": steps, "model": o, "teacher": f}))
        found.sort(key=lambda t: (-t[0], -t[1]))
        return [c for _, _, c in found[:k]]

    def review_edits(self) -> list[tuple[dict, dict]]:
        rows = self.db.execute("select original_json, final_json from reviews where status='approved'")
        return [(json.loads(o), json.loads(f)) for o, f in rows]
