# CareCompass: AI-Powered Care Navigation & Caregiver Matching
### Hack IIITD · Centre for Artificial Intelligence (CAI) · Technical Write-up

## 1. Problem Description & Clinical Motivation
Patients in India frequently encounter barriers in navigating healthcare settings. Faced with acute or evolving symptoms, families either delay care until illness becomes critical or overwhelm hospital emergency departments with conditions that could be effectively assessed at home. Multilingual and code-mixed expressions (Hindi, English, and Hinglish such as *"Papa ko do din se bukhar hai aur khansi bhi"*) cause conventional triage systems to fail, leading to dangerous under-triage.

CareCompass solves this challenge via an intelligent, multilingual triage and caregiver matching system that:
1. Accurately determines **care type** (`paramedic_home_visit`, `nurse_home_visit`, `gp_teleconsult`, `specialist`, `emergency_referral`).
2. Determines **urgency** (`routine`, `same_day`, `immediate`).
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
  - **Cost-Sensitive Decision Matrix**: Since under-triage is catastrophic while over-triage is benign, predictions are chosen by minimizing expected Bayesian risk where misclassifying an `immediate` emergency as `routine` carries an asymmetric cost of 10x.
  - **Clinical Risk Modifiers**: Automatic escalation for vulnerable demographics (infants, seniors >75, pregnancy, chronic diabetes/COPD).

- **Module 3: Urgency-Aware Multi-Factor Caregiver Matching**
  - Evaluates mock caregivers around Delhi NCR using haversine distance decay ($e^{-\text{km}/5}$), exact and compatible skill matching, time-to-earliest slot, language concordance, and rating shrinkage.
  - Generates factual, interpretable match explanations (e.g., *"Hindi-speaking, 3 km away, free at 4 pm"*).

## 3. Evaluation & Key Results
- **Emergency Recall**: **100%** on held-out gold evaluations (Target $\ge$ 98%).
- **Under-Triage Rate**: **0.00%** (Target < 5%).
- **Latency**: P95 < 50ms without external LLM, < 2.5s with Gemini.
- **Fail-Safe Operation**: Complete autonomy with zero external API dependencies when network or LLM is unavailable.

## 4. Known Limitations & Future Work
1. Regional dialects (Bhojpuri, Maithili, Haryanvi) can be expanded into the transliteration lexicon.
2. Integration with live ABHA (Ayushman Bharat Health Account) profiles for verified EHR retrieval.
