# Care Type Model Comparison and Benchmarks

> **Provider note**: the "Groq LLM" rows below (Model F, Hybrid) are **previous provider** numbers — the LLM is now DeepSeek (`LLM_PROVIDER=deepseek`) and is a second opinion, not the primary classifier.

### 1. Cross-Validation Range and Bound Hierarchy Analysis
The official triage dataset (`ml/data/official/triage_dataset.jsonl`) contains 301 labeled rows but only 54 unique normalized strings (82.1% of rows have an identical duplicate elsewhere). This templated, synthetic structure means grouped-CV is a **lower/upper bound range**, not a single number:
1. **Exact-Text Grouped CV (Main Figure)**: groups identical normalized strings into one fold; zero identical strings cross folds (Model A $0.879$, Model B $0.736$). **This is the metric used for model selection.**
2. **Strict Loose-Cluster Holdout (Stress Test)**: broad semantic-topic clusters (TF-IDF $\ge 0.20$); no near-duplicate leaks — the most pessimistic bound (see Section 4).
3. **Naive Random Split (Leaky)**: unconstrained `StratifiedKFold(shuffle=True)`; identical strings leak across folds (Model A $1.000$). **Not used for selection.**
4. **Small-Cluster Grouped CV (Leaky)**: complete-linkage intra-class clustering (capped at size 3, $\le 8$) (Model A $0.974 \pm 0.033$). ~95.8% of held-out clusters have an exact duplicate in training. **Not used for selection.**

### Table 1: Cross-Validation Benchmarks (5-Fold Grouped CV on Official Dataset, N=301)
Evaluates cross-validation performance strictly across the official dataset splits. Models evaluated strictly within CV folds.

| Model | Exact-Text Grouped CV (Main Figure) | Naive Random Split (Leaky) | Small-Cluster CV (Leaky) | CV Accuracy | Per-Class CV Recall (eme, hom, lab, par, tel) | emergency_112 recall (alone) | emergency recall (w/ Rules) | English / Hindi / Hinglish F1 | CPU ms / req | Model size | Needs GPU? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Model A: TF-IDF Char (2-5) + LR** | **0.879** | 1.000 | 0.974 ± 0.033 | 0.977 | eme:0.93, hom:1.00, lab:1.00, par:1.00, tel:0.94 | 0.929 | **1.000** | English: 0.98 / Hindi: 0.96 / Hinglish: 0.98 | < 0.5 ms | 1.2 MB | No |
| **Model B: multilingual-e5-small + LR** | **0.736** | 0.990 | 0.968 ± 0.031 | 0.970 | eme:0.93, hom:0.99, lab:1.00, par:0.98, tel:0.94 | 0.929 | **1.000** | English: 0.97 / Hindi: 0.95 / Hinglish: 0.98 | 12.0 ms | 471.0 MB | No |
| **Model C: Ensemble (A + B) Calibrated** | **0.841** | 1.000 | 0.974 ± 0.033 | 0.977 | eme:0.93, hom:1.00, lab:1.00, par:1.00, tel:0.94 | 0.929 | **1.000** | English: 0.98 / Hindi: 0.96 / Hinglish: 0.98 | 12.1 ms | 472.2 MB | No |
| **Model C_stack: Feature Concatenation (TF-IDF + E5)** | **0.841** | 1.000 | 0.984 ± 0.032 | 0.987 | eme:0.93, hom:1.00, lab:1.00, par:1.00, tel:1.00 | 0.929 | **1.000** | English: 0.99 / Hindi: 0.97 / Hinglish: 0.99 | 12.0 ms | 472.5 MB | No |
| **Model D: LightGBM on e5** | **0.405** | 0.997 | 0.948 ± 0.063 | 0.950 | eme:0.88, hom:0.99, lab:1.00, par:0.91, tel:0.94 | 0.875 | **1.000** | English: 0.94 / Hindi: 0.95 / Hinglish: 0.95 | 12.0 ms | 474.5 MB | No |
| **Model E: Fine-tuned MuRIL (BERT)** | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | Yes (CUDA GPU required) |
| **Model F: Zero-shot Groq LLM (API Model)** | n/a (unseen_tests only) | n/a (unseen_tests only) | n/a (unseen_tests only) | n/a (unseen_tests only) | n/a (unseen_tests only) | n/a (unseen_tests only) | n/a (unseen_tests only) | Evaluated on unseen | 2149.6 ms | 0.0 MB | Cloud API (External) |
| **Model G: Rule/Keyword Baseline** | **0.578** | 0.578 | 0.578 ± 0.059 | 0.631 | eme:0.16, hom:0.78, lab:0.71, par:0.40, tel:1.00 | 0.161 | **1.000** | English: 0.59 / Hindi: 0.64 / Hinglish: 0.54 | 0.4 ms | 0.05 MB | No |
| **Model Hybrid: Model A + Groq Low-Conf** | n/a (unseen_tests only) | n/a (unseen_tests only) | n/a (unseen_tests only) | n/a (unseen_tests only) | n/a (unseen_tests only) | n/a (unseen_tests only) | n/a (unseen_tests only) | Evaluated on unseen | 73.6 ms | 1.2 MB | No (Groq API fallback) |

### Table 2: Unseen Tests Benchmark (Held-out Generalization Test, N=30)
Evaluates ALL models on the identical 30 hand-written unseen test cases across en/hi/hinglish. Every metric in this table is computed strictly on unseen_tests.csv.

| Model | Unseen Macro-F1 (All, n=30) | Unseen Macro-F1 (Reviewed-only, n=0) | Unseen Accuracy (All, n=30) | Unseen Per-Class Recall (low n, n=6 per class) | emergency_112 recall (alone) | emergency recall (w/ Rules) | Latency (ms) | Notes |
|---|---|---|---|---|---|---|---|---|
| **Model A: TF-IDF Char (2-5) + LR** | 0.866 | n/a (0 reviewed) | 0.867 | eme:1.00 (low n), hom:1.00 (low n), lab:0.83 (low n), par:0.67 (low n), tel:0.83 (low n) | 1.000 | **1.000** | < 0.5 ms | Production Model |
| **Model B: multilingual-e5-small + LR** | 0.723 | n/a (0 reviewed) | 0.700 | eme:1.00 (low n), hom:0.67 (low n), lab:0.83 (low n), par:0.50 (low n), tel:0.50 (low n) | 1.000 | **1.000** | 12.0 ms | Dense Embedding Baseline |
| **Model C: Ensemble (A + B) Calibrated** | 0.828 | n/a (0 reviewed) | 0.833 | eme:1.00 (low n), hom:1.00 (low n), lab:1.00 (low n), par:0.50 (low n), tel:0.67 (low n) | 1.000 | **1.000** | 12.1 ms | Probability Ensemble |
| **Model C_stack: Feature Concatenation (TF-IDF + E5)** | 0.898 | n/a (0 reviewed) | 0.900 | eme:1.00 (low n), hom:1.00 (low n), lab:0.83 (low n), par:0.67 (low n), tel:1.00 (low n) | 1.000 | **1.000** | 12.0 ms | Feature Stacking |
| **Model D: LightGBM on e5** | 0.478 | n/a (0 reviewed) | 0.467 | eme:0.67 (low n), hom:0.50 (low n), lab:0.67 (low n), par:0.33 (low n), tel:0.17 (low n) | 0.667 | **1.000** | 12.0 ms | Tree-based Baseline |
| **Model E: Fine-tuned MuRIL (BERT)** | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | Skipped on CPU |
| **Model F: Zero-shot Groq LLM (API Model)** | 0.126 | n/a (0 reviewed) | 0.233 | eme:0.17 (low n), hom:0.00 (low n), lab:0.00 (low n), par:0.00 (low n), tel:1.00 (low n) | 0.167 | **1.000** | 2149.6 ms | Zero-shot LLM |
| **Model G: Rule/Keyword Baseline** | 0.491 | n/a (0 reviewed) | 0.533 | eme:0.00 (low n), hom:0.83 (low n), lab:0.50 (low n), par:0.33 (low n), tel:1.00 (low n) | 0.000 | **1.000** | 0.4 ms | Rule/Keyword Baseline (deterministic; rule confidence, not calibrated) |
| **Model Hybrid: Model A + Groq Low-Conf** | 0.866 | n/a (0 reviewed) | 0.867 | eme:1.00 (low n), hom:1.00 (low n), lab:0.83 (low n), par:0.67 (low n), tel:0.83 (low n) | 1.000 | **1.000** | 73.6 ms | Inference Escalation |

*Note on Sample Sizes: Each care type has only n=6 cases in unseen_tests (total N=30). Any figure from fewer than 10 cases is marked as (low n).* 

### 4. Leave-One-Cluster-Out Generalization & Leakage Telemetry
1. **Small-Cluster LOCO Leakage Telemetry (Leaky)**: For the 118 small clusters, the mean maximum TF-IDF cosine similarity of held-out clusters to training rows is **0.970**, with **95.8%** of clusters having an exact duplicate (cosine sim $\ge 0.999$) in the training set. This leakage is why the small-cluster figure is an upper bound and is **not used for selection**.
2. **Strict Loose-Cluster Holdout (Stress Test)**: When clustering rows at a looser similarity threshold ($\ge 0.20$ / distance $\le 0.80$), 31 distinct semantic topic clusters are formed. The mean max TF-IDF cosine similarity to training rows drops to **0.238** (min 0.116, max 0.342). Under this strict zero-leakage evaluation, Model A achieves held-out **Macro-F1 = 0.694** and **Macro-Recall = 0.659**. This is the most pessimistic bound.

### 5. Selection Rule Discussion and Decision
- **Selected Production Model**: **Model A: TF-IDF Char (2-5) + LR**.
- **Model C Qualification Check (Exact-Text Grouped CV = main figure)**: Model A beats Model C on Exact-Text CV Macro-F1 (0.879 vs 0.841) and unseen tests Macro-F1 (0.866 vs 0.828). Model C fails the qualification rule.
- **Model C_stack Evaluation**: On the main figure, Model C_stack scores 0.841 vs Model A's 0.879 (difference -0.037). Model A is chosen because:
  1. **Model Size**: Model A is **1.2 MB** vs. Model C_stack's **472.5 MB** (~400x smaller footprint).
  2. **Latency**: Model A is **< 0.5 ms** CPU inference vs. Model C_stack's **12.0 ms** (~24x faster).
  3. **Operational Simplicity**: Model A requires zero PyTorch/Transformer dependencies and runs pure C-optimized scikit-learn without CUDA or heavy memory overhead.
- **Model Hybrid Escalation**: Escalating to Groq on low-confidence queries (< 0.60) constrained to Model A's top-2 predictions elevates unseen test Macro-F1 from **0.866** to **0.866**.

### 6. Sample Size & Human Clinical Review Status
- **Unseen Tests (`ml/data/unseen_tests.csv`)**: 30 total rows | 0 reviewed by human | 30 unreviewed. Per-class distribution: emergency_112: n=6, paramedic_home_visit: n=6, home_nursing: n=6, lab_test_home: n=6, teleconsultation: n=6.
  - All rows ($n=30$): Macro-F1 reported above.
  - Reviewed-only ($n=0$): `n/a (0 reviewed)`.
- **Red-Flag Tests (`ml/data/redflag_tests.csv`)**: 9 total rows | 0 reviewed by human | 9 unreviewed.
  - All rows ($n=9$): Emergency recall = 1.000 (with safety rules).
  - Reviewed-only ($n=0$): `n/a (0 reviewed)`.
- Complete human clinical review guidelines and verification workflow are documented in [ml/data/README.md](file:///Users/shreyayagain/Desktop/Care-Compass/ml/data/README.md).

### 7. Artifacts Generated:
- Comparison Metrics JSON: `ml/results/comparison.json`
- Confusion Matrix: `docs/confusion_matrix.png`
- Calibration Curve: `docs/calibration_plot.png`