# Care Type Model Comparison and Benchmarks

### 1. Cross-Validation Range and Bound Hierarchy Analysis
The official triage dataset (`ml/data/official/triage_dataset.jsonl`) contains 301 labeled rows but only 54 unique normalized strings (82.1% of rows have an identical duplicate elsewhere). This templated, synthetic structure means grouped-CV is a **lower/upper bound range**, not a single number:
1. **Naive Random Split (Optimistic Upper Bound)**: unconstrained `StratifiedKFold(shuffle=True)`; identical strings freely leak across folds (Model A $1.000$, Model B $0.990$).
2. **Small-Cluster Grouped CV (Main Figure)**: complete-linkage intra-class clustering (same-language TF-IDF/e5 $\ge 0.88$, cross-language e5 $\ge 0.92$, capped at size 8) (Model A $0.978 \pm 0.027$).
3. **Exact-Text Grouped CV (Strict Lower Bound)**: groups identical normalized strings into one fold; zero exact duplicates cross folds (Model A $0.875$, Model B $0.821$).

### Table 1: Cross-Validation Benchmarks (5-Fold Grouped CV on Official Dataset, N=301)
Evaluates cross-validation performance strictly across the official dataset splits. Models evaluated strictly within CV folds.

| Model | Naive Random Split (Optimistic Upper Bound) | Small-Cluster CV (Macro-F1) | Exact-Text Grouped CV | CV Accuracy | Per-Class CV Recall (eme, hom, lab, par, tel) | emergency_112 recall (alone) | emergency recall (w/ Rules) | English / Hindi / Hinglish F1 | CPU ms / req | Model size | Needs GPU? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Model A: TF-IDF Char (2-5) + LR** | 1.000 | 0.978 ± 0.027 | 0.875 | 0.980 | eme:0.95, hom:1.00, lab:1.00, par:1.00, tel:0.94 | 0.946 | **1.000** | English: 0.97 / Hindi: 1.00 / Hinglish: 0.97 | < 0.5 ms | 1.2 MB | No |
| **Model B: multilingual-e5-small + LR** | 0.990 | 0.922 ± 0.071 | 0.821 | 0.937 | eme:0.91, hom:0.99, lab:1.00, par:0.77, tel:0.94 | 0.911 | **1.000** | English: 0.92 / Hindi: 0.94 / Hinglish: 0.94 | 12.0 ms | 471.0 MB | No |
| **Model C: Ensemble (A + B) Calibrated** | 1.000 | 0.948 ± 0.037 | 0.862 | 0.953 | eme:0.86, hom:0.99, lab:1.00, par:0.95, tel:0.94 | 0.857 | **1.000** | English: 0.92 / Hindi: 0.99 / Hinglish: 0.94 | 12.1 ms | 472.2 MB | No |
| **Model C_stack: Feature Concatenation (TF-IDF + E5)** | 1.000 | 0.990 ± 0.019 | 0.871 | 0.990 | eme:1.00, hom:1.00, lab:1.00, par:1.00, tel:0.94 | 1.000 | **1.000** | English: 0.99 / Hindi: 1.00 / Hinglish: 0.98 | 12.0 ms | 472.5 MB | No |
| **Model D: LightGBM on e5** | 0.997 | 0.904 ± 0.065 | 0.593 | 0.920 | eme:0.91, hom:0.96, lab:1.00, par:0.72, tel:0.94 | 0.911 | **1.000** | English: 0.90 / Hindi: 0.94 / Hinglish: 0.90 | 12.0 ms | 474.5 MB | No |
| **Model E: Fine-tuned MuRIL (BERT)** | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | Yes (CUDA GPU required) |
| **Model F: Zero-shot Groq LLM (API Model)** | n/a (unseen_tests only) | n/a (unseen_tests only) | n/a (unseen_tests only) | n/a (unseen_tests only) | n/a (unseen_tests only) | n/a (unseen_tests only) | n/a (unseen_tests only) | Evaluated on unseen | 2558.6 ms | 0.0 MB | Cloud API (External) |
| **Model G: Rule/Keyword Baseline** | 0.573 | 0.573 ± 0.101 | 0.573 | 0.632 | eme:0.16, hom:0.78, lab:0.71, par:0.40, tel:1.00 | 0.161 | **1.000** | English: 0.62 / Hindi: 0.59 / Hinglish: 0.59 | 0.4 ms | 0.05 MB | No |
| **Model Hybrid: Model A + Groq Low-Conf** | n/a (unseen_tests only) | n/a (unseen_tests only) | n/a (unseen_tests only) | n/a (unseen_tests only) | n/a (unseen_tests only) | n/a (unseen_tests only) | n/a (unseen_tests only) | Evaluated on unseen | 1499.3 ms | 1.2 MB | No (Groq API fallback) |

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
| **Model F: Zero-shot Groq LLM (API Model)** | 0.861 | n/a (0 reviewed) | 0.867 | eme:0.67 (low n), hom:1.00 (low n), lab:1.00 (low n), par:0.67 (low n), tel:1.00 (low n) | 0.667 | **1.000** | 2558.6 ms | Zero-shot LLM |
| **Model G: Rule/Keyword Baseline** | 0.491 | n/a (0 reviewed) | 0.533 | eme:0.00 (low n), hom:0.83 (low n), lab:0.50 (low n), par:0.33 (low n), tel:1.00 (low n) | 0.000 | **1.000** | 0.4 ms | Rule/Keyword Baseline (deterministic; rule confidence, not calibrated) |
| **Model Hybrid: Model A + Groq Low-Conf** | 0.931 | n/a (0 reviewed) | 0.933 | eme:1.00 (low n), hom:1.00 (low n), lab:1.00 (low n), par:0.67 (low n), tel:1.00 (low n) | 1.000 | **1.000** | 1499.3 ms | Inference Escalation |

*Note on Sample Sizes: Each care type has only n=6 cases in unseen_tests (total N=30). Any figure from fewer than 10 cases is marked as (low n).* 

### 4. Leave-One-Cluster-Out Generalization & Leakage Telemetry
1. **Small-Cluster LOCO Leakage Telemetry**: For the 118 small clusters, the mean maximum TF-IDF cosine similarity of held-out clusters to training rows is **0.970**, with **95.8%** of clusters having an exact duplicate (cosine sim $\ge 0.999$) in the training set. This high leakage explains why small-cluster LOCO recall reached **1.000**.
2. **Strict Loose-Cluster LOCO (Broad Semantic Topics)**: When clustering rows at a looser similarity threshold ($\ge 0.20$ / distance $\le 0.80$), 31 distinct semantic topic clusters are formed. The mean max TF-IDF cosine similarity to training rows drops to **0.238** (min 0.116, max 0.342). Under this strict zero-leakage evaluation, Model A achieves held-out **Macro-F1 = 0.694** and **Macro-Recall = 0.659**.

### 5. Selection Rule Discussion and Decision
- **Selected Production Model**: **Model A: TF-IDF Char (2-5) + LR**.
- **Model C Qualification Check**: Model A beats Model C on Small-Cluster CV Macro-F1 (0.978 vs 0.948) and unseen tests Macro-F1 (0.866 vs 0.828). Model C fails the qualification rule.
- **Model C_stack Evaluation**: Model C_stack scores 0.990 ± 0.019 vs Model A's 0.978 ± 0.027. The difference (+0.012) is strictly within 1 standard deviation (0.027). Model A is chosen because:
  1. **Model Size**: Model A is **1.2 MB** vs. Model C_stack's **472.5 MB** (~400x smaller footprint).
  2. **Latency**: Model A is **< 0.5 ms** CPU inference vs. Model C_stack's **12.0 ms** (~24x faster).
  3. **Operational Simplicity**: Model A requires zero PyTorch/Transformer dependencies and runs pure C-optimized scikit-learn without CUDA or heavy memory overhead.
- **Model Hybrid Escalation**: Escalating to Groq on low-confidence queries (< 0.60) constrained to Model A's top-2 predictions elevates unseen test Macro-F1 from **0.866** to **0.931**.

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