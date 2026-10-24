"""LLM-down failsafe, question budget, and parallel-screen tests.

Unit level: semantic_screen.screen_red_flags with Gemini mocked to fail.
Pipeline level: the combined failsafe question, escalation flows, and the
two-question budget (conftest neutralises the screen by default; these tests
override it with app.core.pipeline.screen_red_flags).
"""
import asyncio
import unittest
from unittest.mock import patch

from app.schemas import TriageRequest, Location, ChatMessage
from app.core.pipeline import run_triage_pipeline, run_triage_pipeline_async
from app.core.intake import get_question_by_id
from app.core.semantic_screen import (
    screen_red_flags,
    get_screen_status,
    COMBINED_QUESTION_ID,
    WHICH_ONE_QUESTION_ID,
)

LOC = Location(lat=28.54, lng=77.27)

COMBINED_TEXT, _ = get_question_by_id(COMBINED_QUESTION_ID, "en")
WHICH_ONE_TEXT, _ = get_question_by_id(WHICH_ONE_QUESTION_ID, "en")


def _failsafe():
    return {"status": "failsafe_question", "flags": [], "combined": True}


class TestScreenFailsafeUnit(unittest.TestCase):
    """The screen itself (Gemini mocked to fail) must never decide silently."""

    def test_gemini_mocked_failure_returns_failsafe_combined(self):
        with patch("app.core.semantic_screen.is_llm_available", return_value=True), \
             patch("app.core.semantic_screen.llm_json", return_value=None):
            res = screen_red_flags("my dad feels weird and sweaty")
        self.assertEqual(res["status"], "failsafe_question")
        self.assertEqual(res["flags"], [])
        self.assertTrue(res["combined"])

    def test_no_key_unavailable_path_returns_failsafe_combined(self):
        # conftest clears GEMINI_API_KEY: Gemini unavailable.
        res = screen_red_flags("my dad feels weird and sweaty")
        self.assertEqual(res["status"], "failsafe_question")
        self.assertTrue(res["combined"])

    def test_pure_service_request_no_failsafe(self):
        with patch("app.core.semantic_screen.is_llm_available", return_value=True), \
             patch("app.core.semantic_screen.llm_json", return_value=None):
            res = screen_red_flags("need a nurse for an injection")
        self.assertNotEqual(res["status"], "failsafe_question")
        self.assertFalse(res["combined"])

    def test_gemini_failure_retries_once_before_falling_back(self):
        with patch("app.core.semantic_screen.is_llm_available", return_value=True), \
             patch("app.core.semantic_screen.llm_json", return_value=None) as mock_llm:
            screen_red_flags("my dad feels weird and sweaty")
        # The screen delegates the retry to llm_json (retries=1 = one extra attempt).
        self.assertEqual(mock_llm.call_count, 1)
        self.assertEqual(mock_llm.call_args.kwargs.get("retries"), 1)

    def test_screen_status_tracker_and_health(self):
        with patch("app.core.semantic_screen.is_llm_available", return_value=True), \
             patch("app.core.semantic_screen.llm_json", return_value=None):
            screen_red_flags("my dad feels weird and sweaty")
        self.assertEqual(get_screen_status(), "failsafe_question")

        from app.api.health import get_health
        health = get_health()
        self.assertIn(health.screen_status, ["llm_ok", "fallback_local", "failsafe_question", "skip"])


class TestScreenFailsafePipeline(unittest.TestCase):
    """Pipeline integration of the combined question (screen patched)."""

    @patch("app.core.pipeline.screen_red_flags")
    def test_combined_question_asked_never_silent(self, mock_screen):
        mock_screen.return_value = _failsafe()
        req = TriageRequest(
            user_input="my dad feels weird and sweaty",
            language="en", location=LOC, conversation_history=[],
        )
        resp = run_triage_pipeline(req, debug=True)
        self.assertIsNone(resp.care_type, "must never silently decide when the screen is down")
        self.assertEqual(resp.follow_up_question, COMBINED_TEXT)
        self.assertEqual(resp.debug["screen_status"], "failsafe_question")
        self.assertTrue(resp.debug["semantic_screen"]["combined"])

    @patch("app.core.pipeline.screen_red_flags")
    def test_combined_yes_asks_which_one_then_escalates(self, mock_screen):
        mock_screen.return_value = _failsafe()
        r1 = run_triage_pipeline(TriageRequest(
            user_input="my dad feels weird and sweaty", language="en",
            location=LOC, conversation_history=[]))
        self.assertEqual(r1.follow_up_question, COMBINED_TEXT)

        mock_screen.return_value = {"status": "skip", "flags": [], "combined": False}
        r2 = run_triage_pipeline(TriageRequest(
            user_input="Yes", language="en", location=LOC,
            conversation_history=[
                ChatMessage(role="user", text="my dad feels weird and sweaty"),
                ChatMessage(role="assistant", text=COMBINED_TEXT),
            ]))
        self.assertIsNone(r2.care_type)
        self.assertEqual(r2.follow_up_question, WHICH_ONE_TEXT)

        r3 = run_triage_pipeline(TriageRequest(
            user_input="Trouble breathing", language="en", location=LOC,
            conversation_history=[
                ChatMessage(role="user", text="my dad feels weird and sweaty"),
                ChatMessage(role="assistant", text=COMBINED_TEXT),
                ChatMessage(role="user", text="Yes"),
                ChatMessage(role="assistant", text=WHICH_ONE_TEXT),
            ]))
        self.assertEqual(r3.care_type, "emergency_112")
        self.assertIn("breathlessness", r3.red_flags)

    @patch("app.core.pipeline.screen_red_flags")
    def test_combined_yes_with_named_symptom_escalates_directly(self, mock_screen):
        mock_screen.return_value = {"status": "skip", "flags": [], "combined": False}
        req = TriageRequest(
            user_input="Yes, chest pain", language="en", location=LOC,
            conversation_history=[
                ChatMessage(role="user", text="my dad feels weird and sweaty"),
                ChatMessage(role="assistant", text=COMBINED_TEXT),
            ],
        )
        resp = run_triage_pipeline(req)
        self.assertEqual(resp.care_type, "emergency_112")
        self.assertIn("chest_pain", resp.red_flags)
        self.assertIsNone(resp.follow_up_question)

    @patch("app.core.pipeline.screen_red_flags")
    def test_combined_not_sure_escalates(self, mock_screen):
        mock_screen.return_value = {"status": "skip", "flags": [], "combined": False}
        req = TriageRequest(
            user_input="Not sure", language="en", location=LOC,
            conversation_history=[
                ChatMessage(role="user", text="my dad feels weird and sweaty"),
                ChatMessage(role="assistant", text=COMBINED_TEXT),
            ],
        )
        resp = run_triage_pipeline(req)
        self.assertEqual(resp.care_type, "emergency_112")

    @patch("app.core.pipeline.screen_red_flags")
    def test_combined_no_continues_normal_flow(self, mock_screen):
        mock_screen.return_value = {"status": "skip", "flags": [], "combined": False}
        req = TriageRequest(
            user_input="No", language="en", location=LOC,
            conversation_history=[
                ChatMessage(role="user", text="my dad feels weird and sweaty"),
                ChatMessage(role="assistant", text=COMBINED_TEXT),
            ],
        )
        resp = run_triage_pipeline(req)
        self.assertNotEqual(resp.care_type, "emergency_112")
        self.assertNotEqual(resp.follow_up_question, COMBINED_TEXT)

    def test_combined_skipped_when_red_flag_question_already_answered(self):
        with patch("app.core.pipeline.screen_red_flags") as mock_screen:
            mock_screen.return_value = {"status": "llm_ok", "flags": ["chest_pain"], "combined": False}
            r1 = run_triage_pipeline(TriageRequest(
                user_input="my chest feels like someone is sitting on it",
                language="en", location=LOC, conversation_history=[]))
            self.assertIsNotNone(r1.follow_up_question)
            conf_text = r1.follow_up_question

            run_triage_pipeline(TriageRequest(
                user_input="No", language="en", location=LOC,
                conversation_history=[
                    ChatMessage(role="user", text="my chest feels like someone is sitting on it"),
                    ChatMessage(role="assistant", text=conf_text),
                ]))

            mock_screen.return_value = _failsafe()
            r3 = run_triage_pipeline(TriageRequest(
                user_input="now he is feeling weak and restless", language="en", location=LOC,
                conversation_history=[
                    ChatMessage(role="user", text="my chest feels like someone is sitting on it"),
                    ChatMessage(role="assistant", text=conf_text),
                    ChatMessage(role="user", text="No"),
                ]))
            self.assertNotEqual(r3.follow_up_question, COMBINED_TEXT)

    @patch("app.core.pipeline.screen_red_flags")
    def test_max_two_questions_in_combined_flow(self, mock_screen):
        mock_screen.return_value = _failsafe()
        r1 = run_triage_pipeline(TriageRequest(
            user_input="my dad feels weird and sweaty", language="en",
            location=LOC, conversation_history=[]))
        self.assertEqual(r1.follow_up_question, COMBINED_TEXT)

        mock_screen.return_value = {"status": "skip", "flags": [], "combined": False}
        r2 = run_triage_pipeline(TriageRequest(
            user_input="Yes", language="en", location=LOC,
            conversation_history=[
                ChatMessage(role="user", text="my dad feels weird and sweaty"),
                ChatMessage(role="assistant", text=COMBINED_TEXT),
            ]))
        self.assertEqual(r2.follow_up_question, WHICH_ONE_TEXT)

        r3 = run_triage_pipeline(TriageRequest(
            user_input="Chest pain or pressure", language="en", location=LOC,
            conversation_history=[
                ChatMessage(role="user", text="my dad feels weird and sweaty"),
                ChatMessage(role="assistant", text=COMBINED_TEXT),
                ChatMessage(role="user", text="Yes"),
                ChatMessage(role="assistant", text=WHICH_ONE_TEXT),
            ]))
        self.assertEqual(r3.care_type, "emergency_112")
        self.assertIsNone(r3.follow_up_question)

    @patch("app.core.pipeline.screen_red_flags")
    def test_screen_skipped_on_second_followup_answer(self, mock_screen):
        mock_screen.return_value = {"status": "skip", "flags": [], "combined": False}
        one_turn = [
            ChatMessage(role="user", text="mummy ko fever hai"),
            ChatMessage(role="assistant", text="How long has the fever been going on?"),
        ]
        two_turns = one_turn + [
            ChatMessage(role="user", text="2 din se"),
            ChatMessage(role="assistant", text="How severe is the pain on a scale of 1 to 10?"),
        ]
        # Answer to the first follow-up (history_turns == 1): screen still runs.
        run_triage_pipeline(TriageRequest(user_input="halka hai", language="hinglish",
                                          location=LOC, conversation_history=one_turn))
        self.assertEqual(mock_screen.call_count, 1)
        # Answer to the second follow-up (history_turns == 2): screen skipped.
        run_triage_pipeline(TriageRequest(user_input="halka hai", language="hinglish",
                                          location=LOC, conversation_history=two_turns))
        self.assertEqual(mock_screen.call_count, 1)

    @patch("app.core.pipeline.screen_red_flags")
    @patch("app.core.pipeline.extract_slots")
    def test_async_path_runs_screen_and_extraction_in_parallel(self, mock_extract, mock_screen):
        mock_screen.return_value = {"status": "llm_ok", "flags": [], "combined": False}
        mock_extract.return_value = {"symptoms": ["fever"], "service_requested": "none",
                                     "age_group": "adult", "patient_relation": "self",
                                     "consciousness": "alert", "severity": None, "duration": None}
        req = TriageRequest(user_input="mujhe bukhar hai", language="hinglish",
                            location=LOC, conversation_history=[])
        resp = asyncio.run(run_triage_pipeline_async(req))
        self.assertTrue(mock_screen.called)
        self.assertTrue(mock_extract.called)
        self.assertIn(resp.care_type, ["teleconsultation", "paramedic_home_visit", "lab_test_home", "home_nursing", "emergency_112"])

    @patch("app.core.pipeline.screen_red_flags")
    def test_async_path_skips_parallel_for_bare_answers(self, mock_screen):
        req = TriageRequest(user_input="No", language="en", location=LOC,
                            conversation_history=[])
        asyncio.run(run_triage_pipeline_async(req))
        self.assertFalse(mock_screen.called)


if __name__ == "__main__":
    unittest.main()
