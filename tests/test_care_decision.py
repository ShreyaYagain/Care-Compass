"""DECISION_POLICY=weighted: ML+LLM care-type blending (pure logic, no LLM)."""
import unittest

from app.config import settings
from app.core.care_decision import weighted_care_type

PROBS = {
    "paramedic_home_visit": 0.50,
    "home_nursing": 0.20,
    "lab_test_home": 0.10,
    "teleconsultation": 0.15,
    "emergency_112": 0.05,
}


class TestWeightedCareDecision(unittest.TestCase):

    def test_llm_disagree_can_flip_when_ml_not_confident(self):
        # ML top = paramedic (0.5 < 0.90); LLM teleconsultation conf 0.9.
        # score(tele) = 0.4*0.15 + 0.6*0.9 = 0.60; score(paramedic) = 0.20 -> tele.
        chosen, meta = weighted_care_type(PROBS, {"care_type": "teleconsultation", "confidence": 0.9, "reason": "mild"})
        self.assertEqual(chosen, "teleconsultation")
        self.assertEqual(meta["used"], "weighted")
        self.assertFalse(meta["agreed"])

    def test_ml_wins_when_top_prob_at_least_0_90(self):
        probs = {"paramedic_home_visit": 0.92, "home_nursing": 0.03, "lab_test_home": 0.02,
                 "teleconsultation": 0.02, "emergency_112": 0.01}
        chosen, meta = weighted_care_type(probs, {"care_type": "teleconsultation", "confidence": 0.95, "reason": "x"})
        self.assertEqual(chosen, "paramedic_home_visit")
        self.assertEqual(meta["used"], "ml")

    def test_llm_none_uses_ml(self):
        chosen, meta = weighted_care_type(PROBS, None)
        self.assertEqual(chosen, "paramedic_home_visit")
        self.assertEqual(meta["used"], "ml")
        self.assertIsNone(meta["llm"])

    def test_agreed_when_same_type(self):
        chosen, meta = weighted_care_type(PROBS, {"care_type": "paramedic_home_visit", "confidence": 0.6, "reason": "x"})
        self.assertEqual(chosen, "paramedic_home_visit")
        self.assertTrue(meta["agreed"])
        self.assertEqual(meta["used"], "ml")

    def test_llm_confidence_bounded_and_enum_only(self):
        from app.core.care_decision import CareDecision
        d = CareDecision.model_validate({"care_type": "EMERGENCY_112", "confidence": 5.0, "reason": "x"})
        self.assertEqual(d.care_type, "emergency_112")
        self.assertEqual(d.confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
