"""ML-first second-opinion tests.

The LLM is a second opinion: it can only RAISE severity (agree -> confidence up,
more severe -> one confirmation question), never lower a decision or remove a
red flag. When the LLM is off/unavailable, the ML result stands unchanged.
"""
import unittest
from unittest.mock import patch

from app.schemas import TriageRequest, Location
from app.core.pipeline import run_triage_pipeline
from app.core.second_opinion import reconcile

LOC = Location(lat=28.54, lng=77.27)


def _opinion(care_type="teleconsultation", red_flags=None, reason=""):
    return {"care_type": care_type, "red_flags": red_flags or [], "reason": reason}


class TestReconcile(unittest.TestCase):
    def test_agree(self):
        recon = reconcile("teleconsultation", [], _opinion("teleconsultation", []))
        self.assertTrue(recon["agrees"])
        self.assertFalse(recon["ask"])

    def test_llm_more_severe_asks(self):
        recon = reconcile("teleconsultation", [], _opinion("emergency_112", ["chest_pain"]))
        self.assertTrue(recon["ask"])
        self.assertFalse(recon["agrees"])

    def test_llm_less_severe_ignored(self):
        recon = reconcile("emergency_112", ["chest_pain"], _opinion("teleconsultation", []))
        self.assertFalse(recon["agrees"])
        self.assertFalse(recon["ask"])
        self.assertEqual(recon["note"], "less_severe_ignored")

    def test_llm_unavailable_stands(self):
        recon = reconcile("teleconsultation", [], None)
        self.assertFalse(recon["ask"])


class TestSecondOpinionPipeline(unittest.TestCase):

    @patch("app.core.pipeline.run_second_opinion")
    def test_llm_never_lowers_emergency(self, mock_so):
        # Rules/ML decide emergency_112; the LLM says teleconsultation -> ignored.
        mock_so.return_value = _opinion("teleconsultation", [])
        resp = run_triage_pipeline(TriageRequest(user_input="severe chest pain", language="en", location=LOC))
        self.assertEqual(resp.care_type, "emergency_112")
        self.assertEqual(resp.urgency, "emergency")
        self.assertIn("chest_pain", resp.red_flags)

    @patch("app.core.pipeline.run_second_opinion")
    def test_llm_never_removes_a_red_flag(self, mock_so):
        mock_so.return_value = _opinion("teleconsultation", [])
        resp = run_triage_pipeline(TriageRequest(user_input="severe chest pain", language="en", location=LOC))
        self.assertIn("chest_pain", resp.red_flags)

    @patch("app.core.pipeline.run_second_opinion")
    def test_llm_off_gives_same_routing_as_agree(self, mock_so):
        text = "mujhe sir dard hai kal se"
        mock_so.return_value = _opinion("teleconsultation", [])
        resp_agree = run_triage_pipeline(TriageRequest(user_input=text, language="hinglish", location=LOC))
        mock_so.return_value = None
        resp_off = run_triage_pipeline(TriageRequest(user_input=text, language="hinglish", location=LOC))
        # Routing is unchanged; the agreeing opinion only raises confidence.
        self.assertEqual(resp_agree.care_type, resp_off.care_type)
        self.assertEqual(resp_agree.urgency, resp_off.urgency)
        self.assertIsNotNone(resp_agree.second_opinion)
        self.assertTrue(resp_agree.second_opinion["agrees"])
        self.assertGreaterEqual(resp_agree.confidence, resp_off.confidence)

    @patch("app.core.pipeline.run_second_opinion")
    def test_llm_more_severe_asks_one_confirmation(self, mock_so):
        mock_so.return_value = _opinion("emergency_112", ["chest_pain"], reason="possible heart emergency")
        resp = run_triage_pipeline(TriageRequest(user_input="mujhe sir dard hai kal se", language="hinglish", location=LOC))
        # ML decides teleconsultation, LLM is more severe -> ask, never decide.
        self.assertIsNone(resp.care_type)
        self.assertIsNotNone(resp.follow_up_question)
        self.assertIsNotNone(resp.second_opinion)
        self.assertFalse(resp.second_opinion["agrees"])


if __name__ == "__main__":
    unittest.main()
