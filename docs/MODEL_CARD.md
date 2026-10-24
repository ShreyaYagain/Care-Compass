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
│  Stage 3: Decision Gate & Optional Hybrid    │
│  ├── P(emergency_112) >= 0.50 check          │
│  ├── If conf < 0.60: Groq fallback (top-2)   │
│  ├── Top-5 contributing words / n-grams      │
│  └── 3 Nearest Training Examples (TF-IDF Cos)│
└──────────────────────────────────────────────┘
```

---

### Benchmarking & Selection Decision Rationale
Selected strictly per the project model selection rules documented in [MODEL_COMPARISON.md](MODEL_COMPARISON.md) and recorded in `ml/results/comparison.json`:

1. **Qualification Rule Check**:
   - Model C (Ensemble of TF-IDF + multilingual-e5-small) was required to beat Model A on both grouped cross-validation Macro-F1 AND on the 30 unseen benchmark tests.
   - **Small-Cluster CV Macro-F1**: Model A scored **0.978 ± 0.027**, while Model C scored **0.948 ± 0.037**.
   - **Unseen Tests Macro-F1**: Model A scored **0.866**, while Model C scored **0.828**.
   - Model C **failed to qualify**, establishing Model A as the winning classifier.
2. **Deterministic Safety Invariant**:
   - With the 9-flag clinical safety rule layer, Model A delivers **1.000 (100%) recall** across all gold emergency benchmark tests (`ml/data/redflag_tests.csv`).
3. **Ultra-Low Latency & Serving Efficiency**:
   - Removing the ~471 MB `multilingual-e5-small` SentenceTransformer embedding model from the runtime serving path reduces inference latency from ~12 ms to **< 0.5 ms** per query on commodity CPU.
   - The production artifact footprint is **1.2 MB**, allowing immediate zero-warmup container starts and minimal memory consumption.
4. **Hybrid Decision Enhancement**:
   - For ambiguous queries where Model A's calibrated confidence drops below 0.60, an optional Groq LLM verification step restricted strictly to Model A's top-2 predictions elevates unseen Macro-F1 from **0.866** to **0.931**.
5. **Code-Mixed Language Robustness**:
   - Character n-grams (2–5) capture phonetic vernacular variations in transliterated Hinglish (`bukhar`, `buhar`, `bukhaar`), Hindi Devanagari morphology, and clinical English keywords without tokenization mismatch.

---

### Verified Benchmark Performance Metrics
Extracted from `ml/results/comparison.json`:
- **Naive Random Split (Optimistic Upper Bound)**: 1.000
- **Small-Cluster CV Macro-F1 (Main Grouped Figure)**: 0.978 ± 0.027
- **Exact-Text Grouped CV (Strict Template Holdout)**: 0.875
- **Unseen Tests Macro-F1 (Model A alone, All n=30)**: 0.866
- **Unseen Tests Macro-F1 (Reviewed-only, n=0)**: `n/a (0 reviewed)`
- **Unseen Tests Macro-F1 (Hybrid with Groq)**: 0.931
- **Emergency Benchmark Recall (with Rules)**: 1.000 (100%)
- **Emergency Recall (Classifier alone on validation folds)**: 0.946
- **Leave-One-Cluster-Out (Small Clusters, n=118)**: Mean Recall = 1.000 (Mean max cosine sim to train = 0.970, 95.8% exact duplicates in train)
- **Strict Loose-Cluster LOCO (Broad Semantic Topics, n=31)**: Macro-F1 = 0.694, Macro-Recall = 0.659 (Mean max cosine sim to train = 0.238)
- **Per-Language F1 (Grouped CV)**:
  - English: 0.97
  - Hindi: 1.00
  - Hinglish: 0.97
- **Per-Class Recall (Classifier alone on validation folds)**:
  - `emergency_112`: 0.95
  - `home_nursing`: 1.00
  - `lab_test_home`: 1.00
  - `paramedic_home_visit`: 1.00
  - `teleconsultation`: 0.94
- **Calibrated Confidence Distribution**: Mean: 0.851, Median: 0.897, Confident ($\ge 0.60$): 92.4%
- **CPU Inference Latency**: < 0.5 ms / request
- **Model Size on Disk**: 1.2 MB
- **Hardware Requirements**: Commodity CPU (Zero GPU requirement)

---

### Baseline Model Comparisons (Summary)
- **Model B (multilingual-e5-small alone)**: CV Macro-F1 0.922, Unseen F1 0.723, Size 471 MB.
- **Model C (Ensemble A + B)**: CV Macro-F1 0.948, Unseen F1 0.828, Size 472.2 MB.
- **Model C_stack (Concatenation)**: CV Macro-F1 0.990, Unseen F1 0.898, Size 472.5 MB (Difference vs Model A is within 1 std of 0.027; Model A selected due to 400x smaller size, 24x faster latency, zero PyTorch dependencies).
- **Model D (LightGBM on E5)**: CV Macro-F1 0.904, Unseen F1 0.478, Size 474.5 MB.
- **Model E (Fine-tuned MuRIL)**: `NOT RUN (Skipped on CPU; no CUDA GPU available)`.
- **Model F (Zero-shot Groq LLM)**: Unseen F1 0.861, Latency ~2,559 ms (API model with external cloud dependency).
- **Model G (Rule/Keyword Baseline)**: CV Macro-F1 0.573 (grouped folds), Unseen F1 0.491.
- **Model Hybrid (Model A + Groq on Low Confidence)**: Unseen F1 0.931.

---

### Training Data & Validation Protocol
- **Dataset**: `ml/data/official/triage_dataset.jsonl` (Sanocare synthetic care-triage dataset v1, IIIT-Delhi Hackathon).
- **Validation**: Strict 5-Fold `StratifiedGroupKFold` grouped by complete-linkage agglomerative clustering ($E5 \ge 0.88$ or $TF \ge 0.90$ within language, $E5 \ge 0.92$ cross-language; max cluster size 3 $\le 8$; $\ge 15$ groups per class).
- **Human Clinical Review Requirement**: The evaluation sets `unseen_tests.csv` and `redflag_tests.csv` carry a `reviewed_by_human` column (currently `false`), documented in `ml/data/README.md` for clinical validation by the medical team.
- **Zero Data Leakage**: No synthetic LLM-augmented or pseudo-labelled data was included in validation folds.
