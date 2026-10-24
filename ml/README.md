# CareCompass Machine Learning & Triage Pipeline

## Pipeline Architecture
1. **Intake & Normalisation (`core/language.py`)**: Script detection (Devanagari vs Latin), transliteration to Roman script, spelling variant normalization (`hinglish_norm.json`), and negation scope detection.
2. **Deterministic Safety Net (`core/red_flags.py`)**: High-recall pattern matching for emergencies (chest pain, breathlessness, stroke, anaphylaxis, etc.) across English, Hindi, and Hinglish. Overrides ML models.
3. **Smart Intake Slot Extraction (`core/intake.py`)**: Structured slot extraction with Gemini LLM (strict JSON) and deterministic fallback. Prioritizes safety-critical follow-ups.
4. **Triage Classification (`core/triage_model.py`)**: Predicts `care_type` and `urgency`. Applies an asymmetric cost matrix at decision time to penalize under-triage heavily (`cost[immediate][routine] = 10.0`).
5. **Clinical Risk Modifiers (`core/risk_modifiers.py`)**: Age, pregnancy, and chronic condition escalation rules.
6. **Caregiver Matching (`core/matching.py`)**: Multi-factor scoring across skill compatibility, haversine distance (`exp(-km / 5)`), urgency availability, language fluency, and rating.

## Training & Evaluation
```bash
python -m ml.prepare_data
python -m ml.train_triage
python -m ml.evaluate
python -m ml.predict_test
```
