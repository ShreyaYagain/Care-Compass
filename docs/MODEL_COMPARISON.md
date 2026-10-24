# Care Type Model Comparison and Benchmarks

Evaluated via 5-Fold StratifiedGroupKFold on deduplicated official data (`ml/data/official/triage_dataset.jsonl`), with groups formed by connected components of near-duplicate templates ($E5\ge0.88$ or $TFIDF\ge0.90$).

| Model | Macro-F1 (grouped CV, mean ± std) | Macro-F1 on unseen_tests | Accuracy | Recall per class | emergency_112 recall (classifier alone) | emergency recall with the rule layer on redflag_tests | English / Hindi / Hinglish F1 | CPU ms per request | Model size | Needs GPU? |
|---|---|---|---|---|---|---|---|---|---|---|
| **Model A: TF-IDF Char (2-5) + LR** | 0.364 ± 0.190 | 0.863 | 0.368 | eme:0.61, hom:0.48, lab:0.22, par:0.00, tel:0.29 | 0.607 | **1.000** | English: 0.37 / Hindi: 0.34 / Hinglish: 0.38 | 0.0 ms | 1.2 MB | No |
| **Model B: multilingual-e5-small + LR** | 0.203 ± 0.119 | 0.723 | 0.265 | eme:0.30, hom:0.35, lab:0.00, par:0.00, tel:0.48 | 0.304 | **1.000** | English: 0.23 / Hindi: 0.28 / Hinglish: 0.23 | 12.0 ms | 471.0 MB | No |
| **Model C: Ensemble (A + B) Calibrated** | 0.178 ± 0.142 | 0.828 | 0.199 | eme:0.30, hom:0.26, lab:0.00, par:0.00, tel:0.29 | 0.304 | **1.000** | English: 0.18 / Hindi: 0.22 / Hinglish: 0.17 | 12.1 ms | 472.2 MB | No |
| **Model C_stack: Feature Concatenation (TF-IDF + E5)** | 0.336 ± 0.162 | 0.898 | 0.375 | eme:0.55, hom:0.59, lab:0.16, par:0.00, tel:0.29 | 0.554 | **1.000** | English: 0.37 / Hindi: 0.35 / Hinglish: 0.40 | 12.0 ms | 472.5 MB | No |
| **Model D: LightGBM on e5** | 0.152 ± 0.130 | 0.478 | 0.176 | eme:0.32, hom:0.16, lab:0.00, par:0.00, tel:0.29 | 0.321 | **1.000** | English: 0.16 / Hindi: 0.13 / Hinglish: 0.16 | 12.0 ms | 474.5 MB | No |
| **Model E: Fine-tuned MuRIL (BERT)** | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | NOT RUN (Skipped on CPU; no CUDA GPU available) | Yes (CUDA GPU required) |
| **Model F: Zero-shot Groq LLM (API Model)** | 0.861 ± 0.000 | 0.861 | 0.867 | eme:0.67, hom:1.00, lab:1.00, par:0.67, tel:1.00 | 0.667 | **1.000** | Evaluated on unseen | 1668.6 ms | 0.0 MB | Cloud API (External) |
| **Model G: Rule/Keyword Baseline** | 0.596 ± 0.000 | 0.491 | 0.631 | eme:0.16, hom:0.78, lab:0.71, par:0.40, tel:1.00 | 0.161 | **1.000** | English: 0.77 / Hindi: 0.25 / Hinglish: 0.63 | 0.4 ms | 0.05 MB | No |

### Strict Selection Decision Logic:
1. **Winning Model**: **Model A: TF-IDF Char (2-5) + LR**.
2. **Rule Assessment**: Model C (Calibrated Ensemble) achieved CV Macro-F1 of 0.178 and unseen F1 of 0.828, failing to beat Model A (0.364 and 0.863 respectively). Per the evaluation rule, Model A is selected.
3. **Inference Latency & Efficiency**: Model A operates at **0.0 ms** per request on CPU with a **1.2 MB** artifact footprint, completely removing the ~471 MB SentenceTransformer dependency from the production serving path.
4. **Safety Verification**: 100% emergency recall is maintained on benchmark redflag tests via the deterministic rule layer running ahead of ML classification.

### Artifacts Generated:
- Comparison JSON: `ml/results/comparison.json`
- Confusion Matrix: `docs/confusion_matrix.png`
- Calibration Curve: `docs/calibration_plot.png`