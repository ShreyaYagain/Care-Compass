"""Third-person breathing and sticky red-flag tests.

Stopped/severe breathing ("dad can't breathe", "saans nahi aa rahi") must hit
emergency_112 immediately (no question), with typo tolerance
(breath/breathe/brethe). Milder breathing difficulty ("saans lene me dikkat",
"saans phool rahi") must instead get an immediate same-day doctor/medic visit.
Once a high-severity red flag is found in any turn it stays sticky across the
whole conversation.
"""
import unittest

from app.schemas import TriageRequest, ChatMessage, Location
from app.core.pipeline import run_triage_pipeline

LOC = Location(lat=28.54, lng=77.27)


def _triage(text: str, history=None):
    return run_triage_pipeline(
        TriageRequest(user_input=text, language="hinglish", location=LOC,
                      conversation_history=history or [])
    )


class TestThirdPersonBreathlessness(unittest.TestCase):

    EMERGENCY_CASES = [
        "dad cant breath",
        "papa ko saans nahi aa rahi",
        "mummy cant breathe",
        "dadi ko dum ghut raha hai",
        "baby is not able to breathe",
        "papa can't breath",
        "dad cant brethe",
        "maa saans nahi aa rahi hai",
        "bahu ko saans atak rahi hai",
        "dad is struggling to breath",
        "he has stopped breathing",
        "saans ruk gayi hai",
    ]

    DOCTOR_CASES = [
        "meri maa saans phool rahi hai",
        "wife ko breathing problem hai",
        "papa ko saans lene me dikkat hai",
        "I am finding difficulty to breath",
    ]

    def test_third_person_stopped_breathing_immediate_emergency(self):
        for text in self.EMERGENCY_CASES:
            with self.subTest(text=text):
                resp = _triage(text)
                self.assertEqual(resp.care_type, "emergency_112", f"not emergency for: {text!r}")
                self.assertEqual(resp.urgency, "emergency")
                self.assertIsNone(resp.follow_up_question, f"question asked for: {text!r}")
                self.assertEqual(resp.matched_caregivers, [])

    def test_breathing_difficulty_immediate_doctor_visit(self):
        for text in self.DOCTOR_CASES:
            with self.subTest(text=text):
                resp = _triage(text)
                self.assertEqual(resp.care_type, "paramedic_home_visit", f"not a doctor visit for: {text!r}")
                self.assertEqual(resp.urgency, "same_day")
                self.assertIsNone(resp.follow_up_question, f"question asked for: {text!r}")
                self.assertEqual(resp.red_flags, [])
                self.assertTrue(len(resp.matched_caregivers) > 0)

    def test_typo_brethe_matches(self):
        resp = _triage("dad cant brethe")
        self.assertEqual(resp.care_type, "emergency_112")
        self.assertIn("breathlessness", resp.red_flags)

    def test_two_turn_flow_dad_cant_breath(self):
        # Turn 1: immediate emergency, no question asked.
        resp1 = _triage("dad cant breath")
        self.assertEqual(resp1.care_type, "emergency_112")
        self.assertIsNone(resp1.follow_up_question)

    def test_two_turn_flow_old_person_cannot_lower(self):
        # Even if a question was asked and the next answer is "old person",
        # the sticky red flag from history must keep the emergency decision.
        history = [
            ChatMessage(role="user", text="dad cant breath"),
            ChatMessage(role="assistant", text="Who is this for?"),
        ]
        resp = _triage("old person", history=history)
        self.assertEqual(resp.care_type, "emergency_112")
        self.assertEqual(resp.urgency, "emergency")
        self.assertIn("breathlessness", resp.red_flags)

    def test_history_flag_sticky_for_chest_pain(self):
        history = [
            ChatMessage(role="user", text="papa ko seene me tez dard hai"),
            ChatMessage(role="assistant", text="How long has this been going on?"),
        ]
        resp = _triage("since yesterday", history=history)
        self.assertEqual(resp.care_type, "emergency_112")
        self.assertIn("chest_pain", resp.red_flags)

    def test_negated_breathing_not_emergency(self):
        resp = _triage("saans me koi dikkat nahi hai")
        self.assertNotEqual(resp.care_type, "emergency_112")

    def test_no_breathing_problem_not_emergency(self):
        resp = _triage("papa ko breathing problem nahi hai")
        self.assertNotEqual(resp.care_type, "emergency_112")


if __name__ == "__main__":
    unittest.main()
