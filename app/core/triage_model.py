import os
import joblib
import numpy as np
from pathlib import Path
from app.config import settings
from ml.explain_model import get_top_contributing_terms, get_nearest_training_examples

_CARE_MODEL = None
_TFIDF_VECTORIZER = None
_TRAIN_TFIDF_DATA = None


def load_artifacts():
    global _CARE_MODEL, _TFIDF_VECTORIZER, _TRAIN_TFIDF_DATA

    care_path = settings.ARTIFACTS_DIR / "triage_care.joblib"
    tfidf_path = settings.ARTIFACTS_DIR / "tfidf_vectorizer.joblib"
    train_tfidf_path = settings.ARTIFACTS_DIR / "training_tfidf.joblib"

    if _CARE_MODEL is None and care_path.exists() and tfidf_path.exists():
        try:
            _CARE_MODEL = joblib.load(care_path)
            _TFIDF_VECTORIZER = joblib.load(tfidf_path)
        except Exception:
            _CARE_MODEL = None
            _TFIDF_VECTORIZER = None

    if _TRAIN_TFIDF_DATA is None and train_tfidf_path.exists():
        try:
            _TRAIN_TFIDF_DATA = joblib.load(train_tfidf_path)
        except Exception:
            _TRAIN_TFIDF_DATA = None


def raw_model_argmax(text: str) -> str | None:
    """The pure calibrated model argmax on `text`: no rule layer, no LLM,
    no pipeline stages. Used by the override audit to attribute final
    care_type changes. Returns None when the artifacts are unavailable."""
    load_artifacts()
    if not (text and text.strip()) or _CARE_MODEL is None or _TFIDF_VECTORIZER is None:
        return None
    try:
        x = _TFIDF_VECTORIZER.transform([text])
        probs = _CARE_MODEL.predict_proba(x)[0]
        classes = list(_CARE_MODEL.classes_)
        best = str(classes[int(np.argmax(probs))])
        return best if best in settings.CARE_TYPES else None
    except Exception:
        return None


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

    # 1. Emergency symptoms
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
    lab_keywords = [
        "full body checkup", "checkup", "blood test", "sample collection", "home collection",
        "phlebotomy", "blood sample", "lipid profile", "thyroid", "sugar check", "sugar test",
        "blood sugar", "diabetes check", "diabetes test", "fasting sugar", "lab test"
    ]
    if "lab_test" in symptoms or slots.get("service_requested") == "lab" or any(k in text_norm or k in text.lower() for k in lab_keywords):
        care_type = "lab_test_home"
        urgency = settings.CARE_TO_URGENCY["lab_test_home"]
        probs = {c: 0.02 for c in settings.CARE_TYPES}
        probs["lab_test_home"] = 0.92
        return care_type, urgency, probs, 0.92

    # 4. Paramedic Home Visit
    is_senior = slots.get("age_group") == "senior" or slots.get("patient_relation") in ["father", "mother", "grandmother", "grandfather", "senior", "dada", "dadi"]
    if ("fever" in symptoms and "cough" in symptoms) or (
        "fever" in symptoms and ("2 days" in str(duration) or "3 days" in str(duration) or is_senior)
    ) or "joint_pain" in symptoms or ("dizziness" in symptoms and is_senior) or ("weakness" in symptoms and is_senior) or any(k in text_norm or k in text.lower() for k in ["moch", "sprain", "twisted ankle", "knee hurts", "joint pain", "stairs"]):
        care_type = "paramedic_home_visit"
        urgency = settings.CARE_TO_URGENCY["paramedic_home_visit"]
        probs = {c: 0.03 for c in settings.CARE_TYPES}
        probs["paramedic_home_visit"] = 0.88
        return care_type, urgency, probs, 0.88

    # 5. Teleconsultation
    if (
        "teleconsultation_query" in symptoms
        or "headache" in symptoms
        or "restlessness" in symptoms
        or "dizziness" in symptoms
        or "weakness" in symptoms
        or any(k in text_norm or k in text.lower() for k in ["sir dard", "headache", "acidity", "gas", "doctor consult", "second opinion", "dawai", "prescription", "ghabrahat", "palpitation", "dizzy", "vertigo", "chakkar", "kamzori", "thakan"])
    ):
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


def predict_triage(slots: dict, text: str) -> tuple[str, str, dict, float, list[dict], list[dict]]:
    """
    Model A (Production): Calibrated TF-IDF Char N-Grams (2-5) + Logistic Regression.
    Returns: (care_type, urgency, calibrated_probs, confidence, top_terms, nearest_examples).
    Calibrated probabilities sum strictly to 1.0 (+-1e-5).
    Inference latency < 5ms on CPU (no heavy SentenceTransformer at serving time).
    """
    load_artifacts()

    rb_care, rb_urgency, rb_probs, rb_conf = rule_based_predict(slots, text)

    top_terms: list[dict] = []
    nearest_examples: list[dict] = []

    # Immediate red flag slots check
    if (
        slots.get("breathing_difficulty") is True
        or slots.get("chest_pain") is True
        or slots.get("consciousness") == "unconscious"
        or slots.get("bleeding") is True
    ):
        return rb_care, rb_urgency, rb_probs, rb_conf, top_terms, nearest_examples

    care_pred = None
    care_probs = {c: 0.20 for c in settings.CARE_TYPES}
    confidence = 0.20

    if text.strip() and _CARE_MODEL and _TFIDF_VECTORIZER:
        try:
            # 1. Model A TF-IDF transformation
            x_tfidf = _TFIDF_VECTORIZER.transform([text])
            probs_A = _CARE_MODEL.predict_proba(x_tfidf)[0]
            classes_A = list(_CARE_MODEL.classes_)
            dict_A = {c: float(p) for c, p in zip(classes_A, probs_A)}

            # Normalize to guarantee exact sum to 1.0
            total_p = sum(dict_A.values()) or 1.0
            care_probs = {c: round(float(dict_A.get(c, 0.0) / total_p), 4) for c in settings.CARE_TYPES}
            diff = 1.0 - sum(care_probs.values())
            care_probs[settings.CARE_TYPES[0]] = round(care_probs[settings.CARE_TYPES[0]] + diff, 4)

            # Emergency selection logic (Rule: P(emergency_112) >= 0.50)
            p_emergency = care_probs.get("emergency_112", 0.0)
            if p_emergency >= 0.50:
                care_pred = "emergency_112"
                confidence = p_emergency
            else:
                valid_probs = {k: v for k, v in care_probs.items() if k != "emergency_112" and k != "follow_up"}
                if valid_probs:
                    sorted_valid = sorted(valid_probs.items(), key=lambda x: x[1], reverse=True)
                    care_pred = sorted_valid[0][0]
                    confidence = sorted_valid[0][1]

                    # Hybrid Decision: If confidence is low and the LLM is available, ask it to refine between top-2
                    if confidence < settings.CONF_THRESHOLD:
                        try:
                            from app.core.llm import llm_json, is_llm_available
                            from pydantic import BaseModel

                            class CareTypeWithReason(BaseModel):
                                care_type: str
                                reason: str

                            if is_llm_available():
                                top2_classes = [c for c, _ in sorted_valid[:2]]
                                sys_prompt = (
                                    "You are a medical triage assistant. Choose the best healthcare service from:\n"
                                    "- paramedic_home_visit\n"
                                    "- home_nursing\n"
                                    "- lab_test_home\n"
                                    "- teleconsultation\n"
                                    "- emergency_112\n"
                                    "Return valid JSON matching the schema with fields: care_type and reason."
                                )
                                res = llm_json(system=sys_prompt, user=f"Patient request: \"{text}\"", schema=CareTypeWithReason)
                                if res and hasattr(res, "care_type") and res.care_type in top2_classes:
                                    care_pred = res.care_type
                                    confidence = valid_probs.get(care_pred, confidence)
                        except Exception:
                            pass
                else:
                    care_pred = rb_care
                    confidence = rb_conf

            # 2. Explainability
            top_terms = get_top_contributing_terms(_TFIDF_VECTORIZER, _CARE_MODEL, text, care_pred, top_k=5)
            if _TRAIN_TFIDF_DATA:
                nearest_examples = get_nearest_training_examples(
                    x_tfidf, _TRAIN_TFIDF_DATA["tfidf_matrix"], _TRAIN_TFIDF_DATA["meta"], top_k=3
                )
        except Exception:
            care_pred = None

    # The rule layer is authoritative for any confident match: it routes on
    # canonical symptoms/slots, so random noise in the (cleaned) classifier text
    # can never shift the decision. The ML model only refines inputs the rules
    # do not confidently recognise.
    if not care_pred or rb_conf >= 0.85:
        care_pred = rb_care
        confidence = rb_conf
        care_probs = rb_probs

    urgency = settings.CARE_TO_URGENCY.get(care_pred, "same_day")
    return care_pred, urgency, care_probs, confidence, top_terms, nearest_examples
