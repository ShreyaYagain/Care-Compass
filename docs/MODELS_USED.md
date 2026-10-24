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

## 2. Gemini LLM & Speech AI (Cloud Acceleration)
- **Gemini (`gemini-2.5-flash`)**:
  - Used strictly for structured intake slot extraction (symptoms, service requested, relation, duration, age group).
  - Out-of-dataset mapping: canonicalizes unfamiliar medical queries (physiotherapy, dental, vaccinations, certificates) to the 5 official care types without inventing labels.
  - Follow-up question generation: enforces the zero-severity-question policy (never asks the user to rate discomfort), eliminates duplicate questions, and prioritizes screening of ambiguous red flags.
  - Semantic red-flag screening (`app/core/semantic_screen.py`): meaning-based detection of the nine official red flags, gated on evidence quotes present in the user's message.
  - Fallback order: Gemini $\rightarrow$ deterministic rule/regex layer (never crashes).
- **Gemini Audio Transcription (`gemini-2.5-flash`)**:
  - Cloud STT endpoint at `/transcribe` accepting `.m4a`, `.wav`, `.mp3`, `.ogg`, `.webm`, `.flac` (multimodal audio input).
  - Tuned with Hindi/English medical vocabulary prompt hints (`bukhar, khansi, dard, saans, ulti, injection, dressing, checkup, fever, cough`).
  - Timeout bounded (min 10s deadline) with clean 503 fallback.

---

## 3. Real-Time Environmental Context & Weather API
- **Open-Meteo Forecast & Air Quality APIs (`api.open-meteo.com`)**:
  - Current temperature, relative humidity, precipitation, weather code, and US AQI / PM2.5.
  - Free and open API requiring no credential storage; cached in-memory for 30 minutes keyed by coordinate grid.
  - Deterministic North India seasonal derivation (`winter`, `summer`, `monsoon`, `post_monsoon`) from client ISO timestamp.
  - **Safety Invariants**:
    - Context **never** lowers urgency.
    - Context only escalates urgency under two clinical emergencies:
      1. `heat_wave` ($\ge 40^\circ\text{C}$) + senior ($\ge 65$) + fever/dizziness $\rightarrow$ `emergency_112`.
      2. `poor_air` ($\text{AQI} \ge 200$) + asthma patient + respiratory symptoms $\rightarrow$ `emergency_112`.
    - Soft adjustment within `same_day`: night-time / heavy rain shifts `paramedic_home_visit` to immediate `teleconsultation` with home visit scheduled for morning.
    - Full privacy control: if `context_consent` is false, all context lookups are skipped (`context_used = null`).

---

## 3b. Supabase (Postgres + Auth) — chat history & bookings
- **Service**: [Supabase](https://supabase.com) — hosted Postgres + GoTrue auth (JWT).
- **What it stores**: `chat_sessions`, `chat_steps`, `bookings`, and a `caregivers` roster (schema in `supabase/schema.sql`).
- **Keys**: `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` are read from environment variables only (never committed). `SUPABASE_JWT_SECRET` (or `SUPABASE_JWKS_URL`) verifies user tokens.
- **Fallback**: when the env vars are absent, the backend **fails soft to SQLite** (no-key demo and tests run unchanged). `GET /health` reports the active store.
- **Privacy**: the dataset is synthetic; the app stores only a first name, a masked contact phone, and a session summary for bookings — no real patient identifiers. RLS restricts users to their own rows; the service role filters by `user_id` itself.

---

## 4. Machine Learning Architecture & Classification
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

## 5. Safety Layer & Red Flag Engine
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

## 6. Caregiver Matching Engine
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

## 7. Speech, Transliteration, and UI
- **Android On-Device `SpeechRecognizer`**: Native speech-to-text supporting `hi-IN` and `en-IN` live speech input with pulsing microphone state and partial transcription.
- **Transliteration & Normalization**: Custom medical Hinglish normalizer maps colloquial terms (`sar dard`, `pet dard`, `ulti`) to standardized clinical concepts.

---

## 8. Guardrails and References

### Clinical Triage Citations
The emergency red-flag taxonomy and escalation triggers are grounded in peer-reviewed clinical triage standards:
1. **WHO IMCI**: World Health Organization. *Integrated Management of Childhood Illness (IMCI).* WHO Guidelines Approved by the Guidelines Review Committee (2014).
2. **WHO ETAT**: World Health Organization. *Updated Guideline: Paediatric Emergency Triage, Assessment and Treatment.* WHO Guidelines (2016).
3. **Emergency Severity Index (ESI) v4**: Agency for Healthcare Research and Quality (AHRQ). *ESI Implementation Handbook.* AHRQ Pub. 12-0014 (2011).
4. **Manchester Triage System (MTS)**: Mackway-Jones K. et al. *Emergency Triage (3rd Edition).* Wiley-Blackwell (2014).

### Public Datasets Used for Guardrails & Vocabulary Benchmarking
All public datasets are cited below. In accordance with competition rules, they are utilized strictly as **unlabelled evaluation test prompts and linguistic vocabulary benchmarking**, never as training labels:
1. **TriageBench**: Wong Qi Han, *TriageBench*, [Repo](https://github.com/wongqihan/triagebench) / [Hugging Face](https://huggingface.co/datasets/wongqihan/triagebench), Licence: **MIT**. Used as a **fairness / consistency harness only**: the same clinical vignette is repeated with one irrelevant detail (gender, language, ZIP) swapped, and we measure whether our decision changes. It has **no care-type labels**, so results are reported as *consistency*, never accuracy (see `docs/FAIRNESS_REPORT.md`).
2. **HiMed**: FreedomIntelligence, *HiMed: A Large-scale Hindi Medical Question-Answering Dataset*, [Hugging Face](https://huggingface.co/datasets/FreedomIntelligence/HiMed), Licence: MIT / CC-BY-NC 4.0. (Hindi patient inquiry evaluation).
3. **MedMCQA-Indic**: Eka Care, *MedMCQA-Indic: Multi-language Indic Medical MCQs*, [Hugging Face](https://huggingface.co/datasets/ekacare/MedMCQA-Indic), Licence: Apache-2.0. (Multilingual clinical vocabulary testing).
4. **health_hindi_200**: OdiaGenAI, *Health Hindi 200 Question-Answer Dataset*, [Hugging Face](https://huggingface.co/datasets/OdiaGenAI/health_hindi_200), Licence: CC-BY-4.0. (Hindi health question prompts).
5. **MMCQS (MedSumm)**: Arkadeep Acharya et al., *MedSumm: A Multimodal Approach to Summarizing Code-Mixed Hindi-English Clinical Queries* (ECIR 2024), [Repo](https://github.com/ArkadeepAcharya/MedSumm-ECIR2024) / [Hugging Face](https://huggingface.co/datasets/ArkaAcharya/MMCQSD), Licence: **CC-BY-4.0** (per the HF dataset card; not stated in the repo). Used for Hinglish **vocabulary mining** (human-reviewed, never auto-merged), **robustness runs**, and short **few-shot extraction examples**. It has **no care-type labels**. We do not redistribute its text.

### BibTeX
```bibtex
@misc{wong2026gender,
  title  = {Gender-Dependent Diagnostic Substitution in LLM Medical Triage: Same Symptoms, Unequal Urgency},
  author = {Wong, Qi Han},
  year   = {2026},
  eprint = {2606.03641},
  archivePrefix = {arXiv}
}
```

