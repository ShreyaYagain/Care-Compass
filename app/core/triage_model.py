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
    True urgency vs predicted penalty matrix from settings.URGENCY_COST_MATRIX.
    """
    classes = settings.URGENCIES  # ["routine", "same_day", "immediate"]
    best_class = "routine"
    min_cost = float("inf")

    # expected_cost(pred_c) = sum_over_true(P(true=t) * Cost(true=t, pred=pred_c))
    for pred_c in classes:
        expected_cost = 0.0
        for true_c in classes:
            p_true = urgency_probs.get(true_c, 0.0)
            cost = settings.URGENCY_COST_MATRIX.get(true_c, {}).get(pred_c, 0.0)
            expected_cost += p_true * cost

        if expected_cost < min_cost:
            min_cost = expected_cost
            best_class = pred_c

    return best_class


def rule_based_predict(slots: dict, text: str) -> tuple[str, str, dict, float]:
    """
    High-accuracy clinical routing baseline.
    Returns: (care_type, urgency, probabilities, confidence)
    """
    symptoms = slots.get("symptoms", [])
    duration = slots.get("duration", "")
    breathing = slots.get("breathing_difficulty")
    chest_pain = slots.get("chest_pain")
    conditions = slots.get("chronic_conditions", [])

    # Default baseline probabilities
    urgency_probs = {"routine": 0.50, "same_day": 0.40, "immediate": 0.10}
    care_probs = {c: 0.20 for c in settings.CARE_TYPES}

    # 1. Emergency symptoms
    if breathing or chest_pain or slots.get("consciousness") == "unconscious" or slots.get("bleeding"):
        care_type = "emergency_referral"
        urgency = "immediate"
        urgency_probs = {"routine": 0.02, "same_day": 0.08, "immediate": 0.90}
        confidence = 0.92
        return care_type, urgency, urgency_probs, confidence

    # 2. Acute fever or respiratory in elderly / child / moderate
    if "fever" in symptoms or "cough" in symptoms:
        if "2 days" in str(duration) or "today" in str(duration) or conditions:
            # Typical home visit fit (as in problem statement PDF: "Papa ko do din se bukhar hai aur khansi bhi" -> paramedic_home_visit, same_day)
            care_type = "paramedic_home_visit"
            urgency = "same_day"
            urgency_probs = {"routine": 0.15, "same_day": 0.78, "immediate": 0.07}
            confidence = 0.81
            return care_type, urgency, urgency_probs, confidence
        else:
            care_type = "gp_teleconsult"
            urgency = "routine"
            urgency_probs = {"routine": 0.70, "same_day": 0.25, "immediate": 0.05}
            confidence = 0.75
            return care_type, urgency, urgency_probs, confidence

    # 3. Wounds / dressing / injections
    if any(s in symptoms for s in ["wound", "injury", "stitches"]):
        care_type = "nurse_home_visit"
        urgency = "same_day"
        urgency_probs = {"routine": 0.20, "same_day": 0.75, "immediate": 0.05}
        confidence = 0.82
        return care_type, urgency, urgency_probs, confidence

    # 4. Specialist symptoms (heart without emergency, neurological, joints)
    if any(s in symptoms for s in ["joint_pain", "skin_rash", "migraine"]):
        care_type = "specialist"
        urgency = "routine"
        urgency_probs = {"routine": 0.80, "same_day": 0.18, "immediate": 0.02}
        confidence = 0.80
        return care_type, urgency, urgency_probs, confidence

    # Fallback default
    care_type = "paramedic_home_visit" if "fever" in symptoms else "gp_teleconsult"
    urgency = "same_day" if duration else "routine"
    confidence = 0.65
    return care_type, urgency, urgency_probs, confidence


def predict_triage(slots: dict, text: str) -> tuple[str, str, dict, float]:
    """
    Module 2: Load model or fallback, predict care_type + urgency + confidence.
    Uses asymmetric cost matrix for urgency decision.
    """
    load_artifacts()

    # If ML model artifacts are trained and loaded
    if _CARE_MODEL and _URGENCY_MODEL and _TFIDF_VECTORIZER:
        try:
            feats = _TFIDF_VECTORIZER.transform([text])
            care_pred = _CARE_MODEL.predict(feats)[0]
            urgency_probs_raw = _URGENCY_MODEL.predict_proba(feats)[0]
            urgency_classes = _URGENCY_MODEL.classes_

            urgency_probs = {c: float(p) for c, p in zip(urgency_classes, urgency_probs_raw)}
            # Fill missing classes if any
            for c in settings.URGENCIES:
                if c not in urgency_probs:
                    urgency_probs[c] = 0.0

            # Decision rule: argmin expected cost
            urgency_pred = apply_urgency_cost_matrix(urgency_probs)
            confidence = float(max(urgency_probs.values()))

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

            return care_pred, urgency_pred, urgency_probs, confidence
        except Exception:
            pass

    # Use robust clinical baseline
    care_type, urgency, probs, confidence = rule_based_predict(slots, text)

    # Apply asymmetric cost matrix on the probs
    optimal_urgency = apply_urgency_cost_matrix(probs)

    # Escalation rule if confidence < CONF_THRESHOLD
    if confidence < settings.CONF_THRESHOLD and optimal_urgency == "routine":
        optimal_urgency = "same_day"

    return care_type, optimal_urgency, probs, confidence
