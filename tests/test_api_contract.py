import unittest
from app.schemas import (
    TriageRequest,
    TriageResponse,
    Location,
    ChatMessage,
    PatientProfile,
    BookingRequest,
    MatchRequest,
)
from app.core.pipeline import run_triage_pipeline
from app.core.matching import rank_caregivers
from app.api.health import get_health
from app.api.booking import create_booking


class TestApiContract(unittest.TestCase):
    def test_response_always_contains_required_fields(self):
        req = TriageRequest(
            user_input="papa ko do din se bukhar hai aur khansi bhi",
            language="auto",
            location=Location(lat=28.54, lng=77.27),
            conversation_history=[],
        )
        resp = run_triage_pipeline(req)
        resp_dict = resp.model_dump() if hasattr(resp, "model_dump") else resp.dict()

        # Required fields in every response
        required_keys = [
            "follow_up_question",
            "care_type",
            "urgency",
            "red_flags",
            "reasoning",
            "matched_caregivers",
            "emergency_steps",
        ]
        for key in required_keys:
            self.assertIn(key, resp_dict, f"Missing required contract field: {key}")

        # Ensure old 'emergency' object field is completely removed
        self.assertNotIn("emergency", resp_dict, "Old 'emergency' object field must be removed")

    def test_chat_message_content_and_text_validation(self):
        # (a.1) History sent with only 'content'
        msg1 = ChatMessage(role="user", content="Hello doctor")
        self.assertEqual(msg1.text, "Hello doctor")
        self.assertEqual(msg1.content, "Hello doctor")
        self.assertEqual(msg1.role, "user")

        # (a.2) History sent with only 'text'
        msg2 = ChatMessage(role="assistant", text="How can I help?")
        self.assertEqual(msg2.text, "How can I help?")
        self.assertEqual(msg2.content, "How can I help?")
        self.assertEqual(msg2.role, "assistant")

        # (a.3) History sent with both 'text' and 'content' -> uses 'text'
        msg3 = ChatMessage(role="user", text="Text version", content="Content version")
        self.assertEqual(msg3.text, "Text version")

        # (a.4) Extra unknown keys are ignored instead of failing
        msg4 = ChatMessage(role="user", text="Valid text", timestamp=12345678, extra_metadata={"source": "app"})
        self.assertEqual(msg4.text, "Valid text")

        # (a.5) Reject when neither text nor content is present
        with self.assertRaises(ValueError):
            ChatMessage(role="user")

        # (a.6) Reject role other than 'user' or 'assistant'
        with self.assertRaises(ValueError):
            ChatMessage(role="system", text="System message")

    def test_emergency_triggers_care_type_emergency_112(self):
        req = TriageRequest(
            user_input="Severe chest pain and difficulty breathing",
            location=Location(lat=28.54, lng=77.27),
        )
        resp = run_triage_pipeline(req)
        self.assertEqual(resp.urgency, "emergency")
        self.assertEqual(resp.care_type, "emergency_112")
        self.assertTrue(len(resp.emergency_steps) > 0, "emergency_steps must be non-empty on emergency")
        self.assertEqual(resp.matched_caregivers, [], "Caregiver matching must be skipped on emergency")

    def test_non_emergency_returns_empty_red_flags(self):
        req = TriageRequest(
            user_input="mujhe sir dard hai kal se",
            location=Location(lat=28.54, lng=77.27),
            conversation_history=[],
        )
        resp = run_triage_pipeline(req)
        self.assertEqual(resp.red_flags, [])
        self.assertEqual(resp.emergency_steps, [])

    def test_smoke_test_cases(self):
        # (d.1) Case 1: Fever with relation context -> sufficiency rule decides,
        # no follow-up question is asked.
        req1 = TriageRequest(user_input="papa ko bukhar hai", conversation_history=[])
        resp1 = run_triage_pipeline(req1)
        self.assertIsNone(resp1.follow_up_question)
        self.assertIsNotNone(resp1.care_type)
        self.assertEqual(resp1.emergency_steps, [])

        # (d.2) Case 2: Chest pain Hinglish -> emergency_112 + emergency + high red flag
        req2 = TriageRequest(
            user_input="papa ko seene me tez dard hai aur paseena aa raha hai",
            conversation_history=[]
        )
        resp2 = run_triage_pipeline(req2)
        self.assertEqual(resp2.care_type, "emergency_112")
        self.assertEqual(resp2.urgency, "emergency")
        self.assertIn("chest_pain", resp2.red_flags)
        self.assertTrue(len(resp2.emergency_steps) > 0)
        self.assertEqual(resp2.matched_caregivers, [])

        # (d.3) Case 3: Negation handling (Fever with NO breathing problem)
        req3 = TriageRequest(
            user_input="saans me koi dikkat nahi hai",
            language="hinglish",
            conversation_history=[
                ChatMessage(role="user", text="papa ko do din se bukhar hai aur khansi bhi"),
                ChatMessage(role="assistant", text="Kya saans lene mein dikkat hai?"),
            ],
            location=Location(lat=28.54, lng=77.27),
        )
        resp3 = run_triage_pipeline(req3)
        self.assertEqual(resp3.care_type, "paramedic_home_visit")
        self.assertEqual(resp3.urgency, "same_day")
        self.assertTrue(len(resp3.matched_caregivers) > 0)
        self.assertEqual(resp3.emergency_steps, [])

        # (d.4) Case 4: Caregiver matching standalone
        matches = rank_caregivers(
            care_type="paramedic_home_visit",
            urgency="same_day",
            user_location=Location(lat=28.54, lng=77.27),
            user_language="hi",
            limit=3,
        )
        self.assertTrue(len(matches) > 0)
        self.assertTrue(hasattr(matches[0], "caregiver_id"))
        self.assertTrue(hasattr(matches[0], "score"))
        self.assertTrue(hasattr(matches[0], "reason"))

        # (d.5) Case 5: Booking
        b_resp = create_booking(BookingRequest(
            caregiver_id="CG_014",
            slot="today_afternoon",
            user_name="Rohan Gupta",
            phone="+919876543210",
            triage_summary="Fever check"
        ), db=None)
        self.assertTrue(b_resp.booking_id.startswith("BK_"))
        self.assertEqual(b_resp.status, "confirmed")

    def test_health_endpoint(self):
        h = get_health()
        self.assertEqual(h.status, "ok")
        self.assertTrue(hasattr(h, "model_version"))


if __name__ == "__main__":
    unittest.main()
