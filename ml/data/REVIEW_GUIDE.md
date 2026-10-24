# Red-Flag Test Set — Review Guide

`ml/data/redflag_tests.csv` is the safety benchmark for the deterministic red-flag
rule layer. It was **drafted with AI assistance** and is **not yet clinically
reviewed**: every row has `reviewed_by_human = false`.

## Who reviews this
A clinician / medical-operations reviewer (not the ML engineer). The reviewer's
job is only to confirm that each row is labelled the way a human triage
coordinator would answer it.

## What to check, row by row
For each row, confirm two things:
1. **`care_type` / `urgency` is right.**
   - A row with a real red flag must be `emergency_112` / `emergency`.
   - A negated or near-miss row must **not** be `emergency_112`.
2. **`red_flags` lists exactly the official flag(s) triggered.**
   Official flags: `chest_pain`, `breathlessness`, `unconsciousness`,
   `severe_bleeding`, `stroke_symptoms`, `seizure`, `high_fever_infant`,
   `suicidal_ideation`, `severe_dehydration`.

## The four groups and what to look for

| id prefix | group | what to verify |
|---|---|---|
| `VIG_*` | original handwritten/synthetic (9 rows) | keep or correct as-is |
| `RF_<flag>_*` | positive per flag (12 × 9) | each really is that red flag; typos are intentional but must stay understandable |
| `RF_NEG_*` | negated (40) | the negation really cancels the red flag → non-emergency |
| `RF_NEAR_*` | near-miss non-emergency (40) | genuinely NOT an emergency (mild, self-limiting) |
| `RF_HID_*` | emergency hidden in long text (20) | the emergency is really present and must be caught |

## How to approve
- Set `reviewed_by_human` to `true` once a row is verified (edit the CSV, last column).
- If a label is wrong, **fix the row** (the `red_flags` / `care_type` columns), then set `reviewed_by_human = true`.
- Do not delete rows you disagree with — correct them and approve.

## Why this matters
`ml/compare_models.py` reports rule-layer and classifier metrics **separately for
reviewed vs unreviewed rows**. Until these rows are reviewed, the safety numbers
are provisional (they are reported with `reviewed_by_human=false` and shown as
"n/a" for the reviewed-only split). The emergency recall / false-alarm report is
in `docs/DATA_AUDIT.md`.
