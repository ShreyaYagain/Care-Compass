import os
import joblib
from pathlib import Path
from app.config import settings

_CARE_MODEL = None
_URGENCY_MODEL = None
_TFIDF_VECTORIZER = None


def load_artifacts():
    global _CARE_MODEL, _URGENCY_MODEL, _TFIDF_VECTORIZER
    care_path = settings.ARTIFACTS_DIR / "triage_care.joblib"
    urgency_path = settings.ARTIFACTS_DIR / "triage_urgency.joblib"
    tfidf_path = settings.ARTIFACTS_DIR / "tfidf_vectorizer.joblib"

    if care_path.exists() and urgency_path.exists():
        try:
            _CARE_MODEL = joblib.load(care_path)
            _URGENCY_MODEL = joblib.load(urgency_path)
            if tfidf_path.exists():
                _TFIDF_VECTORIZER = joblib.load(tfidf_path)
        except Exception:
            _CARE_MODEL = None
            _URGENCY_MODEL = None


def apply_urgency_cost_matrix(urgency_probs: dict[str, float]) -> str:
    """
    Pick urgency class minimising expected cost under asymmetric penalties.
    Rule D: Apply it only to choose between routine and same_day (and immediate only if rule A.3 holds).
    Under-triage penalty may raise routine -> same_day, never same_day -> immediate.
    Rule A.3: Calibrated P(immediate) >= 0.50 is required for immediate.
    """
    p_immediate = urgency_probs.get("immediate", 0.0)
    if p_immediate >= 0.50:
        return "immediate"

    p_routine = urgency_probs.get("routine", 0.0)
    p_same_day = urgency_probs.get("same_day", 0.0)

    # Expected cost comparing routine vs same_day under asymmetric under-triage penalty
    # settings.URGENCY_COST_MATRIX:
    # Cost(true=same_day, pred=routine) = 4.0
    # Cost(true=routine, pred=same_day) = 1.0
    cost_routine = p_same_day * 4.0
    cost_same_day = p_routine * 1.0

    # Under-triage penalty may raise routine -> same_day only when there is substantial same-day probability
    if cost_same_day < cost_routine and p_same_day >= 0.35:
        return "same_day"
    return "routine"


def rule_based_predict(slots: dict, text: str) -> tuple[str, str, dict, float]:
    """
    High-accuracy clinical routing baseline adhering to Rules A, B, C.
    Returns: (care_type, urgency, probabilities, confidence)
    """
    symptoms = slots.get("symptoms", [])
    duration = slots.get("duration", "")
    breathing = slots.get("breathing_difficulty")
    chest_pain = slots.get("chest_pain")
    conditions = slots.get("chronic_conditions", [])
    relation = slots.get("patient_relation")
    severity = slots.get("severity")
    age_group = slots.get("age_group")
    text_norm = text.lower()

    # 1. Emergency symptoms (Rule A.1 / A.2)
    if (
        breathing is True
        or chest_pain is True
        or slots.get("consciousness") == "unconscious"
        or slots.get("bleeding") is True
    ):
        care_type = "emergency_referral"
        urgency = "immediate"
        urgency_probs = {"routine": 0.01, "same_day": 0.04, "immediate": 0.95}
        return care_type, urgency, urgency_probs, 0.95

    # 2. Headache / Mild conditions (Rule B: routine)
    if "headache" in symptoms or any("sir dard" in s for s in symptoms) or "headache" in text_norm or "sir dard" in text_norm:
        care_type = "gp_teleconsult"
        urgency = "routine"
        urgency_probs = {"routine": 0.80, "same_day": 0.18, "immediate": 0.02}
        return care_type, urgency, urgency_probs, 0.85

    # 3. Fever & cough (Rule B & C)
    # Problem statement PDF & Step 4: "papa ko do din se bukhar hai aur khansi bhi" -> paramedic_home_visit, same_day
    if "fever" in symptoms and "cough" in symptoms:
        care_type = "paramedic_home_visit"
        urgency = "same_day"
        urgency_probs = {"routine": 0.15, "same_day": 0.80, "immediate": 0.05}
        return care_type, urgency, urgency_probs, 0.85

    # 4. Fever (mild / child / duration)
    if "fever" in symptoms or "bukhar" in text_norm:
        if severity == "mild" or "halka" in text_norm:
            care_type = "gp_teleconsult"
            urgency = "routine"
            urgency_probs = {"routine": 0.75, "same_day": 0.22, "immediate": 0.03}
            return care_type, urgency, urgency_probs, 0.80
        if "2 days" in str(duration) or "3 days" in str(duration) or ">" in str(duration) or relation in ["father", "mother", "grandmother", "grandfather"] or age_group == "senior":
            care_type = "paramedic_home_visit"
            urgency = "same_day"
            urgency_probs = {"routine": 0.20, "same_day": 0.75, "immediate": 0.05}
            return care_type, urgency, urgency_probs, 0.82
        else:
            care_type = "gp_teleconsult"
            urgency = "routine"
            urgency_probs = {"routine": 0.75, "same_day": 0.22, "immediate": 0.03}
            return care_type, urgency, urgency_probs, 0.80

    # 5. Stomach / abdominal pain
    if "stomach_pain" in symptoms or "abdominal_pain" in symptoms or "vomiting" in symptoms or "pet" in text_norm:
        if "3 days" in str(duration) or ">" in str(duration):
            care_type = "paramedic_home_visit"
            urgency = "same_day"
            urgency_probs = {"routine": 0.25, "same_day": 0.70, "immediate": 0.05}
            return care_type, urgency, urgency_probs, 0.80
        else:
            care_type = "gp_teleconsult"
            urgency = "routine"
            urgency_probs = {"routine": 0.70, "same_day": 0.25, "immediate": 0.05}
            return care_type, urgency, urgency_probs, 0.75

    # 6. Wounds / dressing / injections (Rule C)
    if any(s in symptoms for s in ["wound", "injury", "stitches", "dressing"]):
        care_type = "nurse_home_visit"
        urgency = "same_day"
        urgency_probs = {"routine": 0.20, "same_day": 0.75, "immediate": 0.05}
        return care_type, urgency, urgency_probs, 0.82

    # 7. Specialist conditions (Rule C)
    if any(s in symptoms for s in ["joint_pain", "skin_rash", "migraine"]):
        care_type = "specialist"
        urgency = "routine"
        urgency_probs = {"routine": 0.80, "same_day": 0.18, "immediate": 0.02}
        return care_type, urgency, urgency_probs, 0.80

    # Fallback
    care_type = "gp_teleconsult"
    urgency = "routine"
    urgency_probs = {"routine": 0.70, "same_day": 0.25, "immediate": 0.05}
    return care_type, urgency, urgency_probs, 0.70


def predict_triage(slots: dict, text: str) -> tuple[str, str, dict, float]:
    """
    Module 2: Load model or fallback, predict care_type + urgency + confidence.
    Adheres strictly to Rules A, B, C, D:
    - Emergency referral only when urgency is immediate
    - Immediate only when Rule A holds (P(immediate) >= 0.50 or emergency slot)
    - Routine and same_day mapped according to clinical presentation
    """
    load_artifacts()

    # Clinical rule baseline
    rb_care, rb_urgency, rb_probs, rb_conf = rule_based_predict(slots, text)

    # Rule A emergency slot check
    is_emergency_slot = (
        slots.get("breathing_difficulty") is True
        or slots.get("chest_pain") is True
        or slots.get("consciousness") == "unconscious"
        or slots.get("bleeding") is True
    )
    if is_emergency_slot:
        return "emergency_referral", "immediate", {"routine": 0.01, "same_day": 0.04, "immediate": 0.95}, 0.95

    # If ML model artifacts are trained and loaded
    care_pred = None
    urgency_pred = None
    urgency_probs = None
    confidence = 0.0

    if _CARE_MODEL and _URGENCY_MODEL and _TFIDF_VECTORIZER and text.strip():
        try:
            feats = _TFIDF_VECTORIZER.transform([text])
            raw_care = _CARE_MODEL.predict(feats)[0]
            raw_probs = _URGENCY_MODEL.predict_proba(feats)[0]
            classes = _URGENCY_MODEL.classes_

            urgency_probs = {c: float(p) for c, p in zip(classes, raw_probs)}
            for c in settings.URGENCIES:
                if c not in urgency_probs:
                    urgency_probs[c] = 0.0

            # Rule D: Under-triage penalty, immediate only if P(immediate) >= 0.50
            urgency_pred = apply_urgency_cost_matrix(urgency_probs)
            care_pred = raw_care
            confidence = float(max(urgency_probs.values()))
        except Exception:
            care_pred = None

    # Merge / validate against clinical rules
    if not urgency_pred or urgency_pred != "immediate":
        # Slot-grounding safety override: if user explicitly confirmed NO breathing difficulty
        # and no acute chest pain / unconsciousness / bleeding
        if (
            slots.get("breathing_difficulty") is False
            and slots.get("chest_pain") is not True
            and not slots.get("bleeding")
            and slots.get("consciousness") != "unconscious"
        ):
            if urgency_pred == "immediate":
                urgency_pred = "same_day" if ("fever" in slots.get("symptoms", []) or slots.get("duration")) else "routine"

        # If ML model predicted emergency_referral but urgency is not immediate (Rule C violation)
        if care_pred == "emergency_referral" or not care_pred:
            care_pred = rb_care
        if not urgency_pred:
            urgency_pred = rb_urgency
            urgency_probs = rb_probs
            confidence = rb_conf

        # For clear clinical slot matches (fever+cough, headache, etc.), respect clinical ground truth
        if rb_conf >= 0.80:
            care_pred = rb_care
            urgency_pred = rb_urgency
            urgency_probs = rb_probs
            confidence = rb_conf

    # Enforce Rule C: emergency_referral ONLY when urgency is immediate
    if urgency_pred != "immediate" and care_pred == "emergency_referral":
        care_pred = rb_care if rb_care != "emergency_referral" else "gp_teleconsult"

    return care_pred, urgency_pred, urgency_probs or rb_probs, confidence or rb_conf
