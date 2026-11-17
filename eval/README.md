# Eval set

One JSON object per line in `labels.jsonl`. Image paths are relative to this folder. Photos and labels stay out of git because they show students' work.

```json
{"image": "photos/s01-0001.jpg",
 "map": {"21": "2025-11-csat-common-21"},
 "problems": {"21": {"first_wrong_step": 4, "error_type": "condition"}}}
```

- `first_wrong_step`: the line number, counted the way the transcriber counts (one written line is one step, top to bottom), or `null` when the solution is right.
- `error_type`: a key from `fws/taxonomy.py`, or `null`.
- Label before looking at the model's output.

`fws eval` reports:

| Key | Meaning |
| --- | --- |
| `wrong_sent_unreviewed` | problems routed to the student without review whose first wrong line was wrong |
| `marked_correct_but_wrong` | wrong solutions the model called correct |
| `first_wrong_line_exact`, `first_wrong_line_within_1` | line localisation |
| `verdict_accuracy`, `error_type_accuracy` | right or wrong, and why |
| `auto_share` | share of problems that skipped review |
| `fewshot` | off, static or teacher; `--fewshot all` runs all three on the same labels |
| `cost_usd_per_sheet`, `seconds_per_sheet` | from the API usage fields and wall clock |
