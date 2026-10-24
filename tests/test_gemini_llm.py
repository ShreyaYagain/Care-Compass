import unittest
from unittest.mock import patch, MagicMock
from app.core.intake import (
    extract_slots,
    needs_more_info,
    select_follow_up_question,
    SlotExtraction,
)
from app.schemas import TriageRequest, ChatMessage
from app.core.pipeline import run_triage_pipeline


class TestGeminiLLMAndIntake(unittest.TestCase):

    def test_never_asks_severity_question(self):
        # Even with various vague inputs and slots, select_follow_up_question must NEVER return severity question
        slots = {"symptoms": ["headache"], "service_requested": "none", "duration": "today", "patient_relation": "self", "age_group": "adult"}
        q_text, opts = select_follow_up_question(slots, lang="en")
        self.assertNotIn("how severe", q_text.lower())
        self.assertNotIn("takleef kitni", q_text.lower())
        self.assertNotIn("severe", [o.lower() for o in opts])

    def test_never_repeats_question_in_history(self):
        # If breathing was already asked in history, do not ask breathing again
        history = [
            {"role": "user", "text": "fever and cough"},
            {"role": "assistant", "text": "Is there any difficulty in breathing?"},
            {"role": "user", "text": "No"},
        ]
        slots = {"symptoms": ["fever", "cough"], "breathing_difficulty": False, "duration": None, "service_requested": "none", "patient_relation": "self", "age_group": None}
        q_text, opts = select_follow_up_question(slots, lang="en", history=history)
        self.assertNotIn("breathing", q_text.lower())
        self.assertNotIn("saans", q_text.lower())

    @patch("app.core.intake.llm_json")
    def test_out_of_dataset_unfamiliar_mapping(self, mock_llm):
        # e.g. physiotherapy mapped to paramedic_home_visit or teleconsultation
        mock_llm.return_value = SlotExtraction(
            symptoms=["knee pain", "difficulty walking"],
            service_requested="none",
            who_for="self",
            age_group="adult",
            duration="1 week",
            red_flag_candidates=[],
            language="en",
            confidence=0.85,
            unfamiliar_care_type_mapped="paramedic_home_visit",
            unfamiliar_reason="Physiotherapy / mobility assistance is served by in-person paramedic / physiotherapist visit.",
        )
        slots = extract_slots("I need physiotherapy at home for my knee", history=[])
        self.assertEqual(slots.get("unfamiliar_care_type_mapped"), "paramedic_home_visit")


if __name__ == "__main__":
    unittest.main()
