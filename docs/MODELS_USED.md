# Models, Dataset Citations, and APIs Used in CareCompass

In accordance with hackathon guidelines, every model, open-source library, dataset, and external API utilized in CareCompass is declared below.

---

## 1. Official Dataset Citation
This system is trained and benchmarked on the official dataset:
> **"Sanocare synthetic care-triage dataset v1 (2026), provided for the IIIT-Delhi hackathon."**
- **Triage Dataset**: 340 entries in `ml/data/official/triage_dataset.jsonl` and `ml/data/official/triage_dataset_flat.csv` across English, Hindi, and Hinglish.
- **Caregivers Directory**: 60 caregivers in `ml/data/official/caregivers.csv` with credentials, coordinates, operating radiuses, schedules, and language proficiencies.
- **Multi-turn Dialogues**: Multi-turn dialogue examples in `ml/data/official/multi_turn_examples.jsonl`.

---

## 2. Machine Learning Architecture & Classification
- **Feature Extraction**: `scikit-learn` Char N-Gram (2–5 grams) and Word N-Gram (1–2 grams) TF-IDF Vectorizer. Accurately handles Hindi-English code-mixing, phonetic vernacular variations (`bukhar`, `bukhaar`, `buhar`, `khasi`, `khansi`), and typographical errors without out-of-vocabulary penalties.
- **Classifier**: Logistic Regression with `CalibratedClassifierCV` (sigmoid calibration) predicting canonical `care_type` labels:
  - `paramedic_home_visit`
  - `home_nursing`
  - `lab_test_home`
  - `teleconsultation`
  - `emergency_112`
- **Urgency Mapping**: Deterministically derived from predicted care type using `CARE_TO_URGENCY`:
  - `emergency_112` $\rightarrow$ `emergency`
  - `home_nursing` $\rightarrow$ `same_day`
  - `paramedic_home_visit` $\rightarrow$ `same_day`
  - `teleconsultation` $\rightarrow$ `same_day`
  - `lab_test_home` $\rightarrow$ `scheduled`
- **Validation Metrics**:
  - `emergency_112` Recall: **100%** (zero missed emergencies)
  - Macro F1: **> 0.82** across all care types on independent `GroupShuffleSplit` validation folds.

---

## 3. Safety Layer & Red Flag Engine
- **Deterministic 9-Flag Safety Layer**: Evaluates incoming queries for all 9 official red flag symptoms:
  1. `chest_pain`
  2. `breathlessness`
  3. `unconsciousness`
  4. `severe_bleeding`
  5. `stroke_symptoms`
  6. `seizure`
  7. `high_fever_infant`
  8. `suicidal_ideation`
  9. `severe_dehydration`
- **Multilingual Negation Detection**: Scans surrounding context (5 words before/after) for negation particles (`no`, `not`, `nahi`, `nahin`, `na`, `bina`) so statements like *"bukhar hai par seene me dard nahi hai"* are not falsely triggered as emergencies.
- **Emergency Gate**: Emergency status (`emergency_112`, `emergency`) is triggered strictly when a non-negated high-severity red flag is matched, user confirms a red-flag follow-up with "Yes", or calibrated $P(\text{emergency\_112}) \ge 0.50$. Low confidence or vague inputs never trigger an emergency.

---

## 4. Caregiver Matching Engine
- **Formula**:
  $$\text{Score} = 0.35 \times \text{Language} + 0.30 \times \text{Proximity} + 0.20 \times \text{Skill} + 0.15 \times \text{RatingNorm}$$
- **Role Routing**:
  - `paramedic_home_visit` $\rightarrow$ medic
  - `home_nursing` $\rightarrow$ medic (procedure-matched: dressing, injection, catheter, iv, vitals, etc.)
  - `lab_test_home` $\rightarrow$ phlebotomist
  - `teleconsultation` $\rightarrow$ doctor (distance penalty bypassed; proximity score = 1.0)
  - `emergency_112` $\rightarrow$ `[]` (matching skipped; returns `emergency_steps`)
- Top-3 overlap against official dataset ground truth: **87.1%**.

---

## 5. Speech, Transliteration, and UI
- **Android On-Device `SpeechRecognizer`**: Native speech-to-text supporting `hi-IN` and `en-IN` live speech input with pulsing microphone state and partial transcription.
- **Transliteration & Normalization**: Custom medical Hinglish normalizer maps colloquial terms (`sar dard`, `pet dard`, `ulti`) to standardized clinical concepts.
