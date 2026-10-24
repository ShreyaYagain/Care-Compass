# CareCompass Data Audit

Every dataset the classifier and the safety layer depend on, its source, size,
review status, and how it is used. Last regenerated from `ml/eval_redflag_rules.py`
and `ml/compare_models.py` runs.

## 1. Data inventory

| Dataset | Rows | Source | Labels | Review status |
|---|---|---|---|---|
| `ml/data/official/triage_dataset.jsonl` | 340 (301 labeled + 39 follow-up) | Official Sanocare synthetic dataset (IIIT-Delhi) | Official care types | Official (no review needed) |
| `ml/data/official/caregivers.csv` | 60 | Official | — | Official |
| `ml/data/redflag_tests.csv` | 217 | Handwritten (9) + AI-drafted (208) | emergency / non-emergency | **All `reviewed_by_human=false`** |
| `ml/data/unseen_tests.csv` | 30 | AI-drafted | Care types | **All `reviewed_by_human=false`** |
| `ml/external/raw/triagebench_hf.jsonl` | 14 | TriageBench (MIT) | none (consistency only) | n/a |
| `ml/external/raw/mmcqs_hf.jsonl` | 3015 | MMCQS (CC-BY-4.0) | none (vocabulary) | n/a |
| `ml/data/augment_review.csv` | (generated) | Groq paraphrases | pseudo (review-only) | **10% spot-check pending** |

The official triage dataset is heavily templated: 301 labeled rows collapse to
**54 unique normalized strings** (82.1% of rows have an identical duplicate).
This is why exact-text grouped CV is the main validation figure and why naive
splits are marked "leaky".

## 2. Human review requirement

- `redflag_tests.csv` (217 rows), `unseen_tests.csv` (30 rows) and the
  augmentation review sample were **drafted with AI assistance** and carry
  `reviewed_by_human=false`. The clinical/medical-operations team must review
  them — see `ml/data/REVIEW_GUIDE.md` for the row-by-row procedure.
- Every metric below is reported on the **unreviewed** rows and is provisional
  until the review is done (`reviewed_by_human=true`). `ml/compare_models.py`
  already reports a separate "reviewed-only" split (currently `n/a (0 reviewed)`).

## 3. Red-flag rule layer evaluation

Evaluated on the expanded `redflag_tests.csv`: 137 emergency rows (9 original +
108 positives + 20 hidden) and 80 non-emergency rows (40 negated + 40 near-miss).

**Before the fixes** (patterns as previously committed):

| flag | recall | tp/total |
|---|---|---|
| overall | **0.453** | 62/137 |
| false-alarm rate | 0.062 | 5/80 |

**After fixing `red_flags.yaml` + `red_flags.py`** (word-boundary matching for
en/hi/hinglish, clause-boundary-aware negation, Devanagari `नहीं→nahim` negation,
expanded patterns incl. matra/nukta variants):

| flag | recall | tp/total | Wilson 95% CI |
|---|---|---|---|
| chest_pain | 0.947 | 18/19 | [0.754, 0.991] |
| breathlessness | 0.941 | 16/17 | [0.730, 0.990] |
| unconsciousness | 1.000 | 18/18 | [0.824, 1.000] |
| severe_bleeding | 1.000 | 19/19 | [0.832, 1.000] |
| stroke_symptoms | 1.000 | 15/15 | [0.796, 1.000] |
| seizure | 1.000 | 15/15 | [0.796, 1.000] |
| high_fever_infant | 0.933 | 14/15 | [0.702, 0.988] |
| suicidal_ideation | 1.000 | 14/14 | [0.785, 1.000] |
| severe_dehydration | 1.000 | 14/14 | [0.785, 1.000] |
| **overall** | **0.985** | 135/137 | — |
| **false-alarm rate** | **0.000** | 0/80 | — |

**⚠ Overfitting caveat — fresh-holdout generalization.** `ml/data/redflag_holdout.csv`
(53 rows: 35 positives in fresh, unseen phrasings + 18 non-emergency) was drafted
separately and the rules were run ONCE, unchanged:

| metric | own test set (tuned) | fresh holdout (never tuned) |
|---|---|---|
| emergency recall | 0.985 | **0.057** (2/35) |
| false-alarm rate | 0.000 | 0.000 (0/18) |

The 0.985 is largely memorization of the tuning set's phrasings; genuinely new
paraphrases ("my chest feels like someone is sitting on it", "blood soaking
through three towels") are mostly missed. **The safety claim for the demo and
write-up is therefore: "the rule layer catches 98% of our own test set; on
freshly-written cases it currently catches ~6% — we are validating on
human-written cases and strengthening the rules."** This holdout set is also
AI-drafted (`reviewed_by_human=false`) — the definitive figure is the
human-written set, still pending.

**Known remaining gaps (documented, not hidden):**
1. Intentional typos (`cheest` for chest, `shorness` for shortness) — 2 rows.
2. `bache ko ... bukhar ... jhatke` with **no age stated** — the `high_fever_infant`
   half of that row cannot be decided from the text; flagged for human review.

## 4. Classifier-only emergency recall

With the rule layer bypassed, Model A (TF-IDF char 2-5 + calibrated LR) alone
recalls **0.453 (62/137)** of the emergency rows and false-alarms on 21/80
non-emergency rows. This is the point of the two-layer design: the deterministic
rule layer (0.985 recall, 0 false alarms) is the safety floor, and the classifier
handles care-type routing for non-emergency inputs.

## 4b. Semantic red-flag screen (meaning-based safety net)

Because the keyword rules miss fresh paraphrases (0.057 on the holdout), a second
detector understands meaning: `app/core/semantic_screen.py` asks Groq (temperature 0,
strict JSON) to assess each of the nine flags with an `evidence_quote` that must be a
real substring of the message. A present flag becomes **one confirmation question** from
the closed bank — the LLM never decides an emergency by itself and never lowers a
rule decision. Yes (or "Not sure" for the 7 critical flags) → `emergency_112`; No → continue.

Fresh-holdout results (`ml/data/redflag_holdout.csv`, 35 positives / 18 non-emergency):

| mode | safety recall (positives) | false alarms (negatives) |
|---|---|---|
| rules only | 0.057 (2/35) | 0.000 |
| semantic screen only (Groq) | **~0.94 (33/35)** | 0.000 |
| local TF-IDF fallback (Groq down) | 0.029 (1/35) | 0.000 |
| full pipeline (rules + semantic) | ~0.94 (33/35 caught via confirm) | 0.000 |

- The **Groq screen is the layer that generalises** to unseen paraphrases
  ("chest feels like someone is sitting on it", "blood soaking through three
  towels", "he went limp") — 33/35 become confirmation questions.
- The **local TF-IDF fallback** (trained on the 217-row set) also overfits and is
  a weak stopgap; it keeps the app functional (ask, don't decide) when Groq is down,
  but its recall on fresh text is low and is a known weakness to improve.
- Re-run: `python ml/eval_semantic_screen.py` (with Groq enabled) and
  `GROQ_API_KEY= python ml/eval_semantic_screen.py` (fallback).

## 6. Groq paraphrase augmentation (training only, PRELIMINARY)

`ml/augment_synthetic.py` generates 40+ distinct Groq paraphrases per care type
per language from the official seeds (607 rows total, `ml/data/augment_paraphrases.csv`,
`source=synthetic_llm`). A 10% random sample (60 rows) is written to
`ml/data/augment_review.csv` for human spot-check (`reviewed_by_human=false`).

**Leakage answer**: the paraphrases were generated from the **WHOLE official
dataset** (not per-fold training texts), so the loose-cluster "after" figure is
contaminated by meaning-level leakage — the 0.50 wording filter catches surface
overlap, not meaning overlap. The loose-cluster after number must NOT be quoted.

**Clean comparison** (`ml/eval_augmentation.py`, on the independent handwritten
`unseen_tests.csv`, which has no overlap with the augmentation seeds):

| metric | before | after | delta |
|---|---|---|---|
| Unseen_tests macro-F1 (independent) | 0.863 | 0.869 | +0.006 |
| Classifier-only emergency recall (redflag_tests, AI-drafted) | 0.613 | 0.745 | +0.131 |
| Loose-cluster holdout macro-F1 (leaky, do not quote) | 0.724 | 0.961 | — |

**Keep rule**: unseen macro-F1 does not drop and emergency recall improves →
**provisionally kept**. The emergency-recall gain is itself measured on an
AI-drafted set, so the augmentation result is **preliminary** until
`augment_review.csv` and the red-flag sets are human-reviewed. The main
validation figure remains **0.879 (exact-text grouped CV)**.

Augmented rows are **training-only**: they never enter `unseen_tests.csv`,
`redflag_tests.csv`, or any validation fold. Production artifacts are retrained
with the augmentation only after the `augment_review.csv` spot-check is approved.

## 5. What each dataset is allowed to touch

- Training: `triage_dataset.jsonl` (deduplicated) + approved paraphrase
  augmentation (`source=synthetic_llm`) — **training only, never validation**.
- Validation: exact-text grouped CV (main figure), strict loose-cluster holdout
  (stress test), `unseen_tests.csv`, `redflag_tests.csv`.
- TriageBench / MMCQS: consistency / vocabulary / robustness only — **no labels**.
- Anything with `reviewed_by_human=false` is provisional and reported as such.

## 7. Regeneration commands

```bash
python ml/data/generate_redflag_tests.py   # rebuild redflag_tests.csv
python ml/eval_redflag_rules.py            # rule-layer recall / false-alarm / Wilson CI
python ml/augment_synthetic.py             # Groq paraphrase augmentation (training only)
python ml/eval_augmentation.py             # before/after holdout + emergency recall
```
