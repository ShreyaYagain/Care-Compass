import os
import joblib
from pathlib import Path
from app.config import settings

_CARE_MODEL = None
_TFIDF_VECTORIZER = None


def load_artifacts():
    global _CARE_MODEL, _TFIDF_VECTORIZER
    care_path = settings.ARTIFACTS_DIR / "triage_care.joblib"
    tfidf_path = settings.ARTIFACTS_DIR / "tfidf_vectorizer.joblib"

    if care_path.exists() and tfidf_path.exists():
        try:
            _CARE_MODEL = joblib.load(care_path)
            _TFIDF_VECTORIZER = joblib.load(tfidf_path)
        except Exception:
            _CARE_MODEL = None
            _TFIDF_VECTORIZER = None


def rule_based_predict(slots: dict, text: str) -> tuple[str, str, dict, float]:
    """
    High-accuracy clinical and service routing baseline for the official label set:
    CARE_TYPES = ["paramedic_home_visit", "home_nursing", "lab_test_home", "teleconsultation", "emergency_112"]
    Urgency is derived strictly from CARE_TO_URGENCY.
    """
    symptoms = slots.get("symptoms", [])
    duration = slots.get("duration", "")
    breathing = slots.get("breathing_difficulty")
    chest_pain = slots.get("chest_pain")
    text_norm = text.lower()

    # 1. Emergency symptoms (Rule 2: Emergency happens ONLY on true flags/confirmed symptoms)
    if (
        breathing is True
        or chest_pain is True
        or slots.get("consciousness") == "unconscious"
        or slots.get("bleeding") is True
    ):
        care_type = "emergency_112"
        urgency = settings.CARE_TO_URGENCY["emergency_112"]
        probs = {c: 0.01 for c in settings.CARE_TYPES}
        probs["emergency_112"] = 0.96
        return care_type, urgency, probs, 0.96

    # 2. Home nursing procedures
    nursing_keywords = ["injection", "im injection", "iv drip", "drip", "dressing", "patti", "catheter", "tanke", "stitches", "bedsore", "wound"]
    if "nursing_procedure" in symptoms or any(k in text_norm for k in nursing_keywords):
        care_type = "home_nursing"
        urgency = settings.CARE_TO_URGENCY["home_nursing"]
        probs = {c: 0.02 for c in settings.CARE_TYPES}
        probs["home_nursing"] = 0.92
        return care_type, urgency, probs, 0.92

    # 3. Lab test at home (Sample collection)
    lab_keywords = ["full body checkup", "checkup", "blood test", "sample collection", "home collection", "phlebotomy", "blood sample", "lipid profile", "thyroid"]
    if "lab_test" in symptoms or any(k in text_norm for k in lab_keywords):
        care_type = "lab_test_home"
        urgency = settings.CARE_TO_URGENCY["lab_test_home"]
        probs = {c: 0.02 for c in settings.CARE_TYPES}
        probs["lab_test_home"] = 0.92
        return care_type, urgency, probs, 0.92

    # 4. Paramedic Home Visit (Medic home visit for examination, vitals, respiratory/fever)
    if ("fever" in symptoms and "cough" in symptoms) or (
        "fever" in symptoms and ("2 days" in str(duration) or "3 days" in str(duration) or slots.get("patient_relation") in ["father", "mother", "grandmother", "grandfather"])
    ):
        care_type = "paramedic_home_visit"
        urgency = settings.CARE_TO_URGENCY["paramedic_home_visit"]
        probs = {c: 0.03 for c in settings.CARE_TYPES}
        probs["paramedic_home_visit"] = 0.88
        return care_type, urgency, probs, 0.88

    # 5. Teleconsultation (Doctor consultation for mild, talk-only queries: headache, acidity, cold)
    if "headache" in symptoms or any(k in text_norm for k in ["sir dard", "headache", "acidity", "gas", "doctor consult"]):
        care_type = "teleconsultation"
        urgency = settings.CARE_TO_URGENCY["teleconsultation"]
        probs = {c: 0.03 for c in settings.CARE_TYPES}
        probs["teleconsultation"] = 0.88
        return care_type, urgency, probs, 0.88

    # Fallback default
    if "fever" in symptoms or slots.get("duration"):
        care_type = "paramedic_home_visit"
    else:
        care_type = "teleconsultation"

    urgency = settings.CARE_TO_URGENCY.get(care_type, "same_day")
    probs = {c: 0.10 for c in settings.CARE_TYPES}
    probs[care_type] = 0.60
    return care_type, urgency, probs, 0.60


def predict_triage(slots: dict, text: str) -> tuple[str, str, dict, float]:
    """
    Module 2: Load trained model or clinical rule fallback.
    Predicts care_type and derives urgency from CARE_TO_URGENCY.
    Emergency rule: P(emergency_112) >= 0.50 required for model-driven emergency.
    """
    load_artifacts()

    # Clinical ground truth baseline
    rb_care, rb_urgency, rb_probs, rb_conf = rule_based_predict(slots, text)

    # Emergency slots override
    if (
        slots.get("breathing_difficulty") is True
        or slots.get("chest_pain") is True
        or slots.get("consciousness") == "unconscious"
        or slots.get("bleeding") is True
    ):
        return rb_care, rb_urgency, rb_probs, rb_conf

    care_pred = None
    care_probs = {}
    confidence = 0.0

    if _CARE_MODEL and _TFIDF_VECTORIZER and text.strip():
        try:
            feats = _TFIDF_VECTORIZER.transform([text])
            raw_probs = _CARE_MODEL.predict_proba(feats)[0]
            classes = _CARE_MODEL.classes_
            care_probs = {c: float(p) for c, p in zip(classes, raw_probs)}

            for c in settings.CARE_TYPES:
                if c not in care_probs:
                    care_probs[c] = 0.0

            # Rule 2: Emergency happens ONLY if P(emergency_112) >= 0.50
            p_emergency = care_probs.get("emergency_112", 0.0)
            if p_emergency >= 0.50:
                care_pred = "emergency_112"
                confidence = p_emergency
            else:
                # Discard emergency_112 from selection if < 0.50
                valid_probs = {k: v for k, v in care_probs.items() if k != "emergency_112" and k != "follow_up"}
                if valid_probs:
                    care_pred = max(valid_probs.items(), key=lambda x: x[1])[0]
                    confidence = valid_probs[care_pred]
                else:
                    care_pred = rb_care
                    confidence = rb_conf
        except Exception:
            care_pred = None

    # Merge with clinical baseline
    if not care_pred or rb_conf >= 0.85:
        care_pred = rb_care
        confidence = rb_conf
        care_probs = rb_probs

    urgency = settings.CARE_TO_URGENCY.get(care_pred, "same_day")
    return care_pred, urgency, care_probs, confidence
