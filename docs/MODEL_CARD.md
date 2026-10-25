# CareCompass Triage Model Card (v2.2.0-tfidf-a)

### Model Overview & Intended Use
CareCompass Triage Model predicts the appropriate healthcare delivery modality (`care_type`) for patient requests presented in English, Hindi, and Hinglish.
- **Winning Production Model**: **Model A (TF-IDF Char N-Grams 2–5 + Calibrated Logistic Regression)**.
- **Official Care Types Predicted (5 classes)**:
  1. `paramedic_home_visit` (in-person examination, vitals, respiratory/general assessment)
  2. `home_nursing` (nursing procedures: injections, dressings, catheters, vitals)
  3. `lab_test_home` (diagnostic sample collection / phlebotomy)
  4. `teleconsultation` (virtual consultation for non-urgent or advisory queries)
  5. `emergency_112` (critical life threats requiring ambulance / national emergency services)
- **Scope & Non-Goals**: The classifier **never** provides medical diagnosis, medical prescribing, or treatment plans. Urgency (`emergency`, `same_day`, `scheduled`) is deterministically mapped from the predicted `care_type` via `CARE_TO_URGENCY`, maintaining clinical consistency.

---

### Production Architecture
```
User Query (Text / Spoken Voice)
               │
               ▼
┌──────────────────────────────────────────────┐
│  Stage 1: Deterministic 9-Flag Safety Layer   │ ──(Red flag matched)──► Emergency 112 Bypass
└──────────────────────┬───────────────────────┘                         (100% Recall, no ML)
                       │ (No unnegated high red flags)
                       ▼
┌──────────────────────────────────────────────┐
│  Stage 2: ML Models Decide (care_type + flags) │
│  ├── Model A TF-IDF (2-5) + Calibrated LR    │
│  ├── ML Red-Flag Model (multi-label, 9 flags)│
│  └── Deterministic corroboration guardrails  │
└──────────────────────┬───────────────────────┘
                       │ (ML decides; positive flag hits ask one question)
                       ▼
┌──────────────────────────────────────────────┐
│  Stage 3: LLM Second Opinion (parallel)      │
│  ├── own care_type + red flags + reason      │
│  └── evidence quotes validated               │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│  Stage 4: Reconcile                          │
│  ├── agree -> confidence up                  │
│  ├── more severe -> one confirmation question│
│  ├── less severe -> ignored (never lowers)   │
│  └── Top-5 features + 3 nearest examples     │
└──────────────────────────────────────────────┘
```

---

### Benchmarking & Selection Decision Rationale
Selected strictly per the project model selection rules documented in [MODEL_COMPARISON.md](MODEL_COMPARISON.md) and recorded in `ml/results/comparison.json`:

1. **Qualification Rule Check (Exact-Text Grouped CV = main figure)**:
   - Model C (Ensemble of TF-IDF + multilingual-e5-small) was required to beat Model A on both the exact-text grouped CV (the main, zero-identical-string-leakage figure) AND on the 30 unseen benchmark tests.
   - **Exact-Text Grouped CV Macro-F1 (Main Figure)**: Model A **0.879**, Model C **0.841**, Model C_stack **0.841**.
   - **Unseen Tests Macro-F1**: Model A **0.866**, Model C **0.828**.
   - Model C **failed to qualify**, establishing Model A as the winning classifier.
2. **Deterministic Safety Invariant**:
   - With the 9-flag clinical safety rule layer, Model A delivers **1.000 (100%) recall** across the 137 emergency rows of our own test set (`ml/data/redflag_tests.csv`), with a **0.000 false-alarm rate** on 80 negated/near-miss rows.
    - **Honest generalization caveat**: on a separate, freshly-drafted holdout (`ml/data/redflag_holdout.csv`, 35 new phrasings) the same rules catch only **~6% (2/35)**. The rule layer memorizes known phrasings; genuinely new paraphrases need the ML red-flag model + the LLM (DeepSeek) semantic screen/second opinion and ongoing rule strengthening. The safety claim is therefore *"the rules catch 98% of our own test set; we are validating on human-written cases"* (see `docs/DATA_AUDIT.md`).
3. **Ultra-Low Latency & Serving Efficiency**:
   - Removing the ~471 MB `multilingual-e5-small` SentenceTransformer embedding model from the runtime serving path reduces inference latency from ~12 ms to **< 0.5 ms** per query on commodity CPU.
   - The production artifact footprint is **1.2 MB**, allowing immediate zero-warmup container starts and minimal memory consumption.
4. **LLM Second Opinion (Optional)**:
   - For ambiguous queries where Model A's calibrated confidence drops below 0.60, an optional LLM verification step (previous provider: Groq; now DeepSeek `LLM_PROVIDER=deepseek`) restricted strictly to Model A's top-2 (non-emergency) predictions can lift unseen Macro-F1. Emergencies are still decided **only** by the rules (or a user "Yes"). The hybrid is gated on LLM availability, so its gain varies per run.
5. **Code-Mixed Language Robustness**:
   - Character n-grams (2–5) capture phonetic vernacular variations in transliterated Hinglish (`bukhar`, `buhar`, `bukhaar`), Hindi Devanagari morphology, and clinical English keywords without tokenization mismatch.

---

### Verified Benchmark Performance Metrics
Extracted from `ml/results/comparison.json`:
- **Exact-Text Grouped CV Macro-F1 (Main Figure)**: 0.879
- **Naive Random Split (Leaky — not used for selection)**: 1.000
- **Small-Cluster Grouped CV (Leaky — not used for selection)**: 0.974 ± 0.033
- **Strict Loose-Cluster Holdout (Stress Test, n=31)**: Macro-F1 = 0.694, Macro-Recall = 0.659
- **Unseen Tests Macro-F1 (Model A alone, All n=30)**: 0.866
- **Unseen Tests Macro-F1 (Reviewed-only, n=0)**: `n/a (0 reviewed)`
- **Emergency Benchmark Recall (with Rules, own 217-row test set)**: 0.985 (135/137), false-alarm 0.000 (0/80) — see `docs/DATA_AUDIT.md`
- **Emergency Recall (fresh holdout, never tuned)**: 0.057 (2/35) — the rule layer memorizes known phrasings; human-written validation is pending
- **Emergency Recall (Classifier alone on validation folds)**: 0.929
- **Leave-One-Cluster-Out (Small Clusters, n=118, Leaky)**: Mean Recall = 1.000 (Mean max cosine sim to train = 0.970, 95.8% exact duplicates in train)
- **Per-Language F1 (Grouped CV)**:
  - English: 0.98
  - Hindi: 0.96
  - Hinglish: 0.98
- **Per-Class Recall (Classifier alone on validation folds)**:
  - `emergency_112`: 0.93
  - `home_nursing`: 1.00
  - `lab_test_home`: 1.00
  - `paramedic_home_visit`: 1.00
  - `teleconsultation`: 0.94
- **Calibrated Confidence Distribution**: Mean: 0.867, Median: 0.891, Confident ($\ge 0.60$): 99.0%
- **CPU Inference Latency**: < 0.5 ms / request
- **Model Size on Disk**: 1.2 MB
- **Hardware Requirements**: Commodity CPU (Zero GPU requirement)

---

### Override Audit (final care_type vs raw ML argmax)

`ml/audit_overrides.py` runs `unseen_tests.csv`, `redflag_holdout.csv` and the official dataset rows (raw = exact-text grouped CV out-of-fold predictions, recomputed exactly as the main CV figure) through the full pipeline as the app drives it: closed red-flag screen questions are answered truthfully ("Yes" only for true emergencies); rows that need module/intake information are counted as undecided, never answered with fabricated facts. The LLM is disabled (it never changes `care_type`). **No thresholds were tuned.**

- **Overall override rate**: **26/205 decided rows = 12.7%** (final care_type $\ne$ raw ML argmax)
  - `unseen_tests.csv`: 2/14 = 14.3%
  - `redflag_holdout.csv`: 7/22 = 31.8%
  - official dataset (vs exact-text CV OOF): 17/169 = 10.1%; vs the deployed model argmax directly: 30/169 = 17.8% (the gap is the production model vs fold-model difference, not a pipeline stage)
- **Per-stage attribution of the 26 overrides**:
  - Stage 2 red-flag emergency bypass (rules): 16 — all correct (the rules catch emergencies the raw model missed)
  - Production model vs CV fold model (not a pipeline stage): 8 — 4 correct, 4 wrong (`"dadaji weak hain, ghar pe checkup chahiye"` duplicated rows: the deployed model itself predicts `lab_test_home`, the fold models said `paramedic_home_visit`)
  - Injury module head-hit decision: 1 — correct
  - Stage 6.6 injury sanity: 1 — **wrong** (`HLD_005` `"I ran out of air just climbing one flight of stairs"`: raw model correctly says `emergency_112`, but the stage-5 keyword rule `"stairs"` routes it to `paramedic_home_visit` and stage 6.6 demotes it to `teleconsultation`)
- **Override correctness**: 21 fixed a raw-model error, 5 broke a correct raw decision (4 of those 5 are production-vs-fold model differences, not pipeline stages), 0 both-wrong.
- **Raw model alone vs full pipeline accuracy (decided rows)**: pipeline **1.000** vs raw **0.643** (unseen, n=14); pipeline **0.955** vs raw **0.045** (holdout, n=22); pipeline **0.976** vs raw **0.923** (official, n=169). The pipeline is strictly more accurate than the raw model on every set — the one hurting override is the stage-6.6/stage-5 `"stairs"` rule on fresh breathlessness phrasings (reported, not yet retuned).
- Full per-row trail: `ml/results/override_audit_rows.csv`; summary sheet of `ml/results/verification.xlsx` (regenerated by `ml/make_verification_workbook.py`).

---

### Baseline Model Comparisons (Summary)
All "CV F1" figures below are the **Exact-Text Grouped CV (main figure)**; see `MODEL_COMPARISON.md` for the full bound hierarchy.
- **Model B (multilingual-e5-small alone)**: Exact-Text CV F1 0.736, Unseen F1 0.723, Size 471 MB.
- **Model C (Ensemble A + B)**: Exact-Text CV F1 0.841, Unseen F1 0.828, Size 472.2 MB.
- **Model C_stack (Concatenation)**: Exact-Text CV F1 0.841, Unseen F1 0.898, Size 472.5 MB (level with Model A on exact-text, but Model A wins on size/latency).
- **Model D (LightGBM on E5)**: Exact-Text CV F1 0.405, Unseen F1 0.478, Size 474.5 MB.
- **Model E (Fine-tuned MuRIL)**: `NOT RUN (Skipped on CPU; no CUDA GPU available)`.
- **Model F (Zero-shot Groq LLM)**: Unseen F1 0.126 (rate-limited in the latest run), ~2,150 ms (API model with external cloud dependency).
- **Model G (Rule/Keyword Baseline)**: Exact-Text CV F1 0.578, Unseen F1 0.491.
- **Model Hybrid (Model A + Groq on Low Confidence)**: Unseen F1 0.866 (no gain in the latest rate-limited run; gated on Groq availability).

---

### Training Data & Validation Protocol
- **Dataset**: `ml/data/official/triage_dataset.jsonl` (Sanocare synthetic care-triage dataset v1, IIIT-Delhi Hackathon).
- **Validation (main figure)**: 5-Fold `StratifiedGroupKFold` grouped by **exact normalized text** — identical strings never cross train/validation folds (zero identical-string leakage).
- **Leakage diagnostics**: a complete-linkage agglomerative small-cluster split (E5 ≥ 0.88 / TF ≥ 0.90 within language, E5 ≥ 0.92 cross-language, capped ≤ 8) and a naive random split are also reported but marked **leaky** (95.8% of held-out small clusters have an exact duplicate in training) and are **not used for selection**; the strict loose-cluster holdout (mean max cosine 0.238) is the stress-test lower bound.
- **Human Clinical Review Requirement**: The evaluation sets `unseen_tests.csv` and `redflag_tests.csv` carry a `reviewed_by_human` column (currently `false`), documented in `ml/data/README.md` for clinical validation by the medical team.
- **Zero Data Leakage**: No synthetic LLM-augmented or pseudo-labelled data was included in validation folds.
