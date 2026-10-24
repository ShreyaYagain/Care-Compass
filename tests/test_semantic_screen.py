"""Semantic red-flag screen tests (Gemini mocked; confirmation flow only)."""
import unittest
from unittest.mock import patch

from app.schemas import TriageRequest, Location, ChatMessage
from app.core.pipeline import run_triage_pipeline
from app.core.semantic_screen import flag_question_id, QUESTION_TO_FLAG, NOT_SURE_AS_YES

LOC = Location(lat=28.54, lng=77.27)


def _skip():
    return {"status": "skip", "flags": [], "combined": False}


def _gemini_ok(flags):
    return {"status": "gemini_ok", "flags": flags, "combined": False}


class TestSemanticScreen(unittest.TestCase):

    def test_flag_question_mapping_covers_all_nine(self):
        for flag in ["chest_pain", "breathlessness", "unconsciousness", "severe_bleeding",
                     "stroke_symptoms", "seizure", "high_fever_infant",
                     "suicidal_ideation", "severe_dehydration"]:
            self.assertIsNotNone(flag_question_id(flag), f"missing question for {flag}")

    def test_not_sure_as_yes_excludes_suicidal_and_dehydration(self):
        self.assertIn("chest_pain", NOT_SURE_AS_YES)
        self.assertIn("seizure", NOT_SURE_AS_YES)
        self.assertNotIn("suicidal_ideation", NOT_SURE_AS_YES)
        self.assertNotIn("severe_dehydration", NOT_SURE_AS_YES)

    @patch("app.core.pipeline.screen_red_flags")
    def test_screen_asks_confirmation_for_fresh_paraphrase(self, mock_screen):
        mock_screen.return_value = _gemini_ok(["chest_pain"])
        req = TriageRequest(
            user_input="my chest feels like someone is sitting on it",
            language="en", location=LOC, conversation_history=[],
        )
        resp = run_triage_pipeline(req)
        self.assertIsNone(resp.care_type)
        self.assertIsNotNone(resp.follow_up_question)
        self.assertIn("chest", resp.follow_up_question.lower())

    @patch("app.core.pipeline.screen_red_flags")
    def test_yes_answer_escalates_to_emergency(self, mock_screen):
        mock_screen.return_value = _skip()
        hist = [
            ChatMessage(role="user", text="my chest feels like someone is sitting on it"),
            ChatMessage(role="assistant", text="Is the patient experiencing acute chest pain or heavy pressure?"),
        ]
        req = TriageRequest(user_input="Yes", language="en", location=LOC, conversation_history=hist)
        resp = run_triage_pipeline(req)
        self.assertEqual(resp.care_type, "emergency_112")
        self.assertIn("chest_pain", resp.red_flags)

    @patch("app.core.pipeline.screen_red_flags")
    def test_not_sure_escalates_for_critical_flag(self, mock_screen):
        mock_screen.return_value = _skip()
        hist = [
            ChatMessage(role="user", text="she keeps opening her mouth but air is not going in"),
            ChatMessage(role="assistant", text="Is the patient experiencing any difficulty in breathing?"),
        ]
        req = TriageRequest(user_input="Not sure", language="en", location=LOC, conversation_history=hist)
        resp = run_triage_pipeline(req)
        self.assertEqual(resp.care_type, "emergency_112")
        self.assertIn("breathlessness", resp.red_flags)

    @patch("app.core.pipeline.screen_red_flags")
    def test_no_answer_does_not_escalate(self, mock_screen):
        mock_screen.return_value = _skip()
        hist = [
            ChatMessage(role="user", text="my chest feels like someone is sitting on it"),
            ChatMessage(role="assistant", text="Is the patient experiencing acute chest pain or heavy pressure?"),
        ]
        req = TriageRequest(user_input="No", language="en", location=LOC, conversation_history=hist)
        resp = run_triage_pipeline(req)
        self.assertNotEqual(resp.care_type, "emergency_112")

    @patch("app.core.pipeline.screen_red_flags")
    def test_screen_never_lowers_a_rule_emergency(self, mock_screen):
        # Keyword rule already flags this; the screen (even empty) must not lower it.
        mock_screen.return_value = _skip()
        req = TriageRequest(user_input="chest pain ho raha hai papa ko", language="hinglish",
                            location=LOC, conversation_history=[])
        resp = run_triage_pipeline(req)
        self.assertEqual(resp.care_type, "emergency_112")


if __name__ == "__main__":
    unittest.main()
