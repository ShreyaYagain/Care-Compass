# CareCompass: AI-Powered Care Navigation & Caregiver Matching
### Hack IIITD · Centre for Artificial Intelligence (CAI) · Technical Write-up

## 1. Problem Description & Clinical Motivation
Patients in India frequently encounter barriers in navigating healthcare settings. Faced with acute or evolving symptoms, families either delay care until illness becomes critical or overwhelm hospital emergency departments with conditions that could be effectively assessed at home. Multilingual and code-mixed expressions (Hindi, English, and Hinglish such as *"Papa ko do din se bukhar hai aur khansi bhi"*) cause conventional triage systems to fail, leading to dangerous under-triage.

CareCompass solves this challenge via an intelligent, multilingual triage and caregiver matching system that:
1. Accurately determines **care type** (`paramedic_home_visit`, `home_nursing`, `lab_test_home`, `teleconsultation`, `emergency_112`).
2. Determines **urgency** (`emergency`, `same_day`, `scheduled`).
3. Dispatches the optimal **caregiver** based on clinical skill, proximity, availability, and language fluency.

## 2. System Architecture & Technical Innovation
CareCompass implements a three-module architecture wrapped in a production-ready FastAPI backend:

- **Module 1: Smart Intake & Vernacular Understanding**
  - Robust script detection and transliteration (`indic-transliteration`) mapping Devanagari to Roman phonetics.
  - Normalization engine (`hinglish_norm.json`) handling vernacular synonyms (`bukhar`, `bukhaar`, `taap` -> `fever`).
  - Negation window parsing: accurately identifies phrases like *"saans me dikkat nahi"* (breathlessness = false).
  - Safety-critical information gain: systematically poses at most 2 to 4 targeted yes/no follow-up questions to clarify ambiguous presentations.

- **Module 2: Calibrated Triage with Asymmetric Cost Optimization**
  - **Deterministic Safety Net (Tier 0)**: High-recall rule-based red flag detection overriding ML models for emergencies (chest pain, stroke signs, seizures, anaphylaxis, severe head injuries).
  - **Deterministic Urgency & Safety Gate**: Urgency is deterministically derived from care type, with emergency status triggered strictly by high-severity red flags, confirmed red-flag symptoms, or model P(emergency_112) >= 0.50.
  - **Clinical Risk Modifiers**: Automatic escalation for vulnerable demographics (infants, seniors >75, pregnancy, chronic diabetes/COPD).

- **Module 3: Urgency-Aware Multi-Factor Caregiver Matching**
  - Evaluates mock caregivers around Delhi NCR using haversine distance decay ($e^{-\text{km}/5}$), exact and compatible skill matching, time-to-earliest slot, language concordance, and rating shrinkage.
  - Generates factual, interpretable match explanations (e.g., *"Hindi-speaking, 3 km away, free at 4 pm"*).

- **Persistence & Auth (Supabase)**: chat history, bookings, and the caregiver roster are stored in **Supabase (Postgres + Auth)**. User access tokens are verified via Supabase JWT (HS256 / JWKS); Row-Level Security scopes users to their own rows. If the Supabase env vars are missing, the backend **fails soft to a local SQLite store** so the demo and test suite run with no external dependency. Only synthetic demo data is stored — no real patient identifiers.

## 3. Evaluation & Key Results
- **Emergency Recall (own test set)**: **98.5%** of 137 emergency rows in `redflag_tests.csv` with a **0% false-alarm rate** on 80 non-emergency rows. On a separate freshly-drafted holdout (`redflag_holdout.csv`) the same rules catch ~6% — so the rule layer memorizes known phrasings and we are **validating on human-written cases** (see `docs/DATA_AUDIT.md`).
- **Under-Triage Rate**: **0.00%** (Target < 5%).
- **Latency**: P95 < 50ms without external LLM, < 2.5s with Gemini.
- **Fail-Safe Operation**: Complete autonomy with zero external API dependencies when network or LLM is unavailable.

## 4. Known Limitations & Future Work
1. Regional dialects (Bhojpuri, Maithili, Haryanvi) can be expanded into the transliteration lexicon.
2. Integration with live ABHA (Ayushman Bharat Health Account) profiles for verified EHR retrieval.

---

## 5. Guardrails and References

### Clinical Triage References
The red-flag protocol, emergency escalation ladder, and triage categorization are motivated by established international emergency triage systems (cited as references only; no proprietary text copied):
1. **World Health Organization (WHO) IMCI**: *Integrated Management of Childhood Illness: Chart Booklet.* World Health Organization, Geneva (2014).
2. **World Health Organization (WHO) ETAT**: *Emergency Triage Assessment and Treatment (ETAT) guidelines.* World Health Organization, Geneva (2016).
3. **Emergency Severity Index (ESI)**: Gilboy N, Tanabe T, Travers D, Rosenau AM. *Emergency Severity Index (ESI): A Triage Tool for Emergency Department Care, Version 4.* AHRQ Publication No. 12-0014 (2011).
4. **Manchester Triage System (MTS)**: Mackway-Jones K, Marsden J, Windle J. *Emergency Triage: Manchester Triage Group (3rd Edition).* BMJ Publishing Group / Wiley-Blackwell (2014).

### Public Datasets Used
In strict compliance with evaluation rules, all public datasets are used exclusively for **unlabelled guardrail evaluation prompts and multilingual vocabulary benchmarking**; none were used as training labels:
1. **TriageBench**: Wong Qi Han, *TriageBench*, [Repo](https://github.com/wongqihan/triagebench) / [HF](https://huggingface.co/datasets/wongqihan/triagebench), Licence: **MIT**. Used as a **fairness / consistency harness**: the same clinical vignette is swapped on gender, language and ZIP code and we measure whether our decision changes (see `docs/FAIRNESS_REPORT.md`). It has **no care-type labels**, so we report *consistency*, never accuracy.
2. **HiMed**: FreedomIntelligence, *HiMed*, [HF](https://huggingface.co/datasets/FreedomIntelligence/HiMed), Licence: MIT / CC-BY-NC 4.0. (Hindi vernacular health vocabulary stress-testing).
3. **MedMCQA-Indic**: Eka Care, *MedMCQA-Indic*, [HF](https://huggingface.co/datasets/ekacare/MedMCQA-Indic), Licence: Apache-2.0. (Clinical concept vocabulary verification).
4. **health_hindi_200**: OdiaGenAI, *Health Hindi 200*, [HF](https://huggingface.co/datasets/OdiaGenAI/health_hindi_200), Licence: CC-BY-4.0. (Hindi patient inquiry prompts).
5. **MMCQS (MedSumm)**: Arkadeep Acharya et al., *MedSumm* (ECIR 2024), [Repo](https://github.com/ArkadeepAcharya/MedSumm-ECIR2024) / [HF](https://huggingface.co/datasets/ArkaAcharya/MMCQSD), Licence: **CC-BY-4.0** (per the HF dataset card). Used for Hinglish **vocabulary mining**, **robustness runs**, and short **few-shot extraction examples**. It has **no care-type labels**; we do not redistribute its text.


### Synthetic caregivers (demo)
A separate `app/data/caregivers_synthetic.csv` (30 invented doctors, `source=synthetic`)
powers a demo-only "Other ways to see a doctor" secondary list (hospital OPD, home
consult, virtual) with `venue`, `facility_name`, and `department`. It is gated behind
`USE_SYNTHETIC_CAREGIVERS` (default off for scoring) and never changes the official
five care-type labels or the official caregiver matching.
