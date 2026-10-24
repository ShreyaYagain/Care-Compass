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
│  Stage 2: Model A Calibrated Classifier      │
│  ├── Character N-Grams (2–5) TF-IDF Vectorizer│
│  ├── Balanced Logistic Regression (C=2.0)    │
│  └── Sigmoid Calibration (CalibratedCV)      │
└──────────────────────┬───────────────────────┘
                       │ (Calibrated probabilities sum strictly to 1.0)
                       ▼
┌──────────────────────────────────────────────┐
│  Stage 3: Decision Gate & Explainability     │
│  ├── P(emergency_112) >= 0.50 check          │
│  ├── Confidence fallback (conf < 0.60)       │
│  ├── Top-5 contributing words / n-grams      │
│  └── 3 Nearest Training Examples (TF-IDF Cos)│
└──────────────────────────────────────────────┘
```

---

### Benchmarking & Selection Decision Rationale
Selected strictly per the project model selection rules documented in [MODEL_COMPARISON.md](MODEL_COMPARISON.md) and recorded in `ml/results/comparison.json`:

1. **Qualification Rule Check**:
   - Model C (Ensemble of TF-IDF + multilingual-e5-small) was required to beat Model A on both grouped cross-validation Macro-F1 AND on the 30 unseen handwritten benchmark tests.
   - **Grouped CV Macro-F1**: Model A scored **0.364 ± 0.190**, while Model C scored **0.178 ± 0.142**.
   - **Unseen Tests Macro-F1**: Model A scored **0.863**, while Model C scored **0.828**.
   - Model C **failed to qualify**, establishing Model A as the winning classifier.
2. **Deterministic Safety Invariant**:
   - Both with and without rules, emergency triage was evaluated. With the 9-flag clinical safety rule layer, Model A delivers **1.000 (100%) recall** across all gold emergency benchmark tests (`ml/data/redflag_tests.csv`).
3. **Ultra-Low Latency & Serving Efficiency**:
   - Removing the ~471 MB `multilingual-e5-small` SentenceTransformer embedding model from the runtime serving path reduces inference latency from ~12 ms to **< 0.5 ms** per query on commodity CPU.
   - The production artifact footprint drops from >472 MB to **1.2 MB**, allowing immediate zero-warmup container starts and minimal memory consumption.
4. **Code-Mixed Language Robustness**:
   - Character n-grams (2–5) capture phonetic vernacular variations in transliterated Hinglish (`bukhar`, `buhar`, `bukhaar`), Hindi Devanagari morphology, and clinical English keywords without tokenization mismatch.
5. **Explainability via Linear Sparse Representations**:
   - Exact feature contribution weights ($w_i \cdot x_i$) are calculated instantaneously.
   - 3 nearest training cases are retrieved via fast sparse cosine similarity against official reference examples.

---

### Verified Benchmark Performance Metrics
Extracted from `ml/results/comparison.json`:
- **Grouped CV Macro-F1 (Holdout Templates)**: 0.364 ± 0.190
- **Unseen Tests Macro-F1 (30 Hand-written Queries)**: 0.863
- **Emergency Benchmark Recall (with Rules)**: 1.000 (100%)
- **Emergency Recall (Classifier alone on holdout templates)**: 0.607
- **Per-Language F1 (Grouped CV)**:
  - English: 0.37
  - Hindi: 0.34
  - Hinglish: 0.38
- **Per-Class Recall (Classifier alone on holdout templates)**:
  - `emergency_112`: 0.61
  - `home_nursing`: 0.48
  - `teleconsultation`: 0.29
  - `lab_test_home`: 0.22
  - `paramedic_home_visit`: 0.00 (handled via keyword and safety rule layer fallback)
- **CPU Inference Latency**: < 0.5 ms / request
- **Model Size on Disk**: 1.2 MB
- **Hardware Requirements**: Commodity CPU (Zero GPU requirement)

---

### Baseline Model Comparisons (Summary)
- **Model B (multilingual-e5-small alone)**: CV Macro-F1 0.203, Unseen F1 0.723, Size 471 MB.
- **Model C (Ensemble A + B)**: CV Macro-F1 0.178, Unseen F1 0.828, Size 472.2 MB.
- **Model C_stack (Concatenation)**: CV Macro-F1 0.336, Unseen F1 0.898, Size 472.5 MB.
- **Model D (LightGBM on E5)**: CV Macro-F1 0.152, Unseen F1 0.478, Size 474.5 MB.
- **Model E (Fine-tuned MuRIL)**: `NOT RUN (Skipped on CPU; no CUDA GPU available)`.
- **Model F (Zero-shot Groq LLM)**: Unseen F1 0.861, Latency 1,668 ms (API model with external cloud dependency).
- **Model G (Rule/Keyword Baseline)**: CV Macro-F1 0.596 (on training templates), Unseen F1 0.491.

---

### Training Data & Validation Protocol
- **Dataset**: `ml/data/official/triage_dataset.jsonl` (Sanocare synthetic care-triage dataset v1, IIIT-Delhi Hackathon).
- **Validation**: Strict 5-Fold `StratifiedGroupKFold` grouped by near-duplicate connected components (E5 cosine $\ge 0.88$ or char-TF-IDF cosine $\ge 0.90$). Whole template families and translations are held out together.
- **Zero Data Leakage**: No synthetic LLM-augmented or pseudo-labelled data was included in validation folds.
