# First wrong step

A tutor photographs a student's handwritten math solutions. This tool finds the first line where each solution goes wrong, writes CSAT-level feedback on that line, and picks follow-up problems from past exams that train the same skill. A teacher sees every case the system is unsure about before the student does.

Built for Korean 고3 students preparing for the CSAT math section (2015 revised curriculum: 수학I, 수학II, 미적분, 확률과 통계, 기하).

## What it does differently

Most photo-solvers read the problem and solve it. They grade the answer, not the student. This tool grades the work.

1. **The first wrong line, not the final answer.** The photo is transcribed line by line with the mistakes kept. The diagnosis names the line number and one of eight error types (concept, missed condition, missed case, algebra, arithmetic, logic gap, misread, incomplete). Later lines that only carry the error forward are not counted.
2. **A checker that does not trust the model.** SymPy re-checks every line it can parse: arithmetic, identities written as `a = b = c`, and whether an equation keeps its solution set from one line to the next. The official answer key, not the model, decides whether the final answer is right. The model sees these results and must explain any disagreement.
3. **A teacher between the model and the student.** A problem is sent out on its own only if the handwriting is clear, the problem matched the bank, the checker and the model agree, and the model is confident. Everything else waits in a review queue where the teacher edits and approves. The student report shows released feedback only.
4. **Follow-ups from real past exams, chosen by skill and level.** Exam PDFs and their answer keys become a bank tagged with a closed list of curriculum skills. After a miss the student gets one easier item on the same skill, one at the same level, then one harder. Items a student already received are never repeated.
5. **Measured, and the measurement grows with use.** `fws eval` scores a hand-labelled set line by line. The number it leads with is how many wrong diagnoses went to a student without review. Every teacher edit in the queue is stored next to the model's original, so `fws eval --from-reviews` reports how often teachers had to correct it in real use.
6. **Fits how tutors already work.** Input is a folder of phone photos (JPG, PNG, HEIC, rotated or not). Output is a one-page printable report per student. It runs on one laptop: SQLite, a standard-library web server, no account system.

## Pipeline

```
photo
  -> transcribe (Claude, vision)               fws/pipeline.py  TRANSCRIBE_SYSTEM
  -> match to a bank item (label map or hint)  fws/bank.py      Bank.find_by_hint
  -> check lines and answer (SymPy, key)       fws/verify.py
  -> diagnose and write feedback (Claude)      fws/pipeline.py  DIAGNOSE_SYSTEM
  -> route: auto or teacher review             fws/pipeline.py  route()
  -> pick follow-up problems                   fws/recommend.py
  -> store, review, report                     fws/store.py, fws/review.py, fws/report.py
```

All model output is JSON validated against Pydantic schemas (`fws/models.py`). Skill tags and error types come from closed lists (`fws/taxonomy.py`); an unknown tag sends the problem to review.

## Setup

```
python -m venv .venv
.venv\Scripts\pip install -e .[dev]
set ANTHROPIC_API_KEY=...
```

Model and effort default to `claude-opus-5-5` at `high`. Override with `FWS_MODEL`, `FWS_EFFORT`. Server-side refusal fallback is on; `FWS_FALLBACKS=0` turns it off. Data goes to `./data` or `FWS_DATA`.

## Use

Build the bank from an exam PDF and its answer key. The answer always comes from the CSV, never from the model.

```
fws bank import --pdf 2025-csat-common.pdf --exam-id 2025-11-csat-common ^
  --exam-name "2025학년도 대학수학능력시험 수학 공통" --answers answers.csv
fws bank stats
```

`answers.csv` has the columns `number,answer` and optionally `correct_rate` (0 to 1 or a percent). Choice-subject papers (미적분, 확률과 통계, 기하) reuse problem numbers 23 to 30, so import each as its own exam id.

Diagnose a photo or a folder of photos, then review:

```
fws run --student s01 --photos photos\s01 --map 21=2025-11-csat-common-21 22=2025-11-csat-common-22
fws review            # http://127.0.0.1:8765
fws report --sheet <sheet id>
```

Use an alias for `--student`, never a real name.

## Measure

```
fws eval --labels eval/labels.jsonl --out eval/result.json
fws eval --from-reviews
```

Label format is in [eval/README.md](eval/README.md). No labelled set is in this repository yet, so there are no accuracy numbers to report.

## Tests

```
.venv\Scripts\python -m pytest -q
```

The tests cover the checker, recommendation, routing, hint matching and an offline end-to-end run with a fake API client. They test the plumbing, not the model's judgement; that is what `fws eval` is for.

## Limits

- The checker reads single-variable equations, identities and arithmetic. It skips inequalities, implications, graphs and words, which is where many CSAT mistakes live. There the model is on its own, and confidence and the teacher are the safeguard.
- A changed solution set can be a correct rejection of a root (for example `x > 0`). The checker marks it; the model has to decide.
- Exam PDFs, answer keys, student photos and the database stay out of git (`.gitignore`). Past CSAT and mock exam problems belong to KICE and the education offices; check their terms before sharing a bank.

## License

MIT
