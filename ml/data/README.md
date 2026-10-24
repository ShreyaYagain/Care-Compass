# CareCompass Evaluation & Benchmark Datasets

This directory contains evaluation benchmarks for CareCompass triage routing and emergency red-flag detection.

### Datasets

1. **`unseen_tests.csv`** (30 rows):
   - Out-of-distribution evaluation set with balanced representation (6 queries per class) across English (`en`), Hindi (`hi`), and Hinglish (`hinglish`).
   - Covers: `emergency_112`, `paramedic_home_visit`, `home_nursing`, `lab_test_home`, and `teleconsultation`.

2. **`redflag_tests.csv`** (9 rows):
   - High-severity emergency benchmark cases covering core red flags: chest pain, breathlessness, seizures, unconsciousness, severe bleeding, and acute stroke symptoms.

### IMPORTANT NOTE: Human Clinical Review
- Both `unseen_tests.csv` and `redflag_tests.csv` were drafted with AI assistance.
- **Action Required**: The clinical and medical operations team must review each test row for clinical validity, appropriate modality assignment, and urgency levels.
- The `reviewed_by_human` column is set to `false` by default. Once a human clinician or medical validator verifies an entry, change this flag to `true`.
- The benchmark harness in `ml/compare_models.py` separates results for human-reviewed rows and unreviewed rows.
