import unittest
from app.schemas import TriageRequest, Location, ChatMessage, PatientProfile
from app.core.pipeline import run_triage_pipeline


class TestTriagePipeline(unittest.TestCase):
    def test_emergency_chest_pain_bypasses_matching(self):
        req = TriageRequest(
            user_input="Severe chest pain and difficulty breathing",
            location=Location(lat=28.54, lng=77.27),
        )
        resp = run_triage_pipeline(req)
        self.assertEqual(resp.care_type, "emergency_referral")
        self.assertEqual(resp.urgency, "immediate")
        self.assertTrue(len(resp.emergency_steps) > 0)
        self.assertTrue(any("112" in step for step in resp.emergency_steps))
        self.assertEqual(len(resp.matched_caregivers), 0)

    def test_follow_up_on_vague_symptom(self):
        req = TriageRequest(
            user_input="papa ko bukhar hai",
            conversation_history=[],
        )
        resp = run_triage_pipeline(req)
        self.assertIsNotNone(resp.follow_up_question)
        self.assertTrue(len(resp.follow_up_options) > 0)
        self.assertIsNone(resp.care_type)
        self.assertEqual(resp.emergency_steps, [])

    def test_final_decision_paramedic_home_visit(self):
        # Case from problem statement PDF: "Papa ko do din se bukhar hai aur khansi bhi" + answered breathing difficulty
        hist = [
            ChatMessage(role="user", text="papa ko do din se bukhar hai aur khansi bhi"),
            ChatMessage(role="assistant", text="Is there any difficulty in breathing?"),
        ]
        req = TriageRequest(
            user_input="nahi saans me koi dikkat nahi hai",
            location=Location(lat=28.54, lng=77.27),
            conversation_history=hist,
            patient=PatientProfile(relation="father", age=68, conditions=["diabetes"]),
        )
        resp = run_triage_pipeline(req)
        self.assertIsNone(resp.follow_up_question)
        self.assertEqual(resp.care_type, "paramedic_home_visit")
        self.assertEqual(resp.urgency, "same_day")
        self.assertTrue(len(resp.matched_caregivers) > 0)
        self.assertIsNotNone(resp.reasoning)
        self.assertEqual(resp.emergency_steps, [])


if __name__ == "__main__":
    unittest.main()
