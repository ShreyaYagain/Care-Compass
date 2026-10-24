import unittest
from app.schemas import TriageRequest, Location, ChatMessage
from app.core.pipeline import run_triage_pipeline


class TestTriageLevels(unittest.TestCase):
    def setUp(self):
        self.default_loc = Location(lat=28.54, lng=77.27)

    def test_papa_bukhar_khansi(self):
        # "papa ko do din se bukhar hai aur khansi bhi" -> paramedic_home_visit, same_day, not emergency
        req = TriageRequest(
            user_input="papa ko do din se bukhar hai aur khansi bhi",
            location=self.default_loc,
        )
        resp = run_triage_pipeline(req)
        self.assertNotEqual(resp.urgency, "emergency")
        self.assertNotEqual(resp.care_type, "emergency_112")
        self.assertEqual(resp.red_flags, [])
        self.assertEqual(resp.care_type, "paramedic_home_visit")
        self.assertEqual(resp.urgency, "same_day")
        self.assertTrue(len(resp.matched_caregivers) > 0)
        self.assertEqual(resp.emergency_steps, [])

    def test_headache_kal_se(self):
        # "mujhe sir dard hai kal se" -> teleconsultation, same_day, not emergency
        req = TriageRequest(
            user_input="mujhe sir dard hai kal se",
            location=self.default_loc,
        )
        resp = run_triage_pipeline(req)
        self.assertNotEqual(resp.urgency, "emergency")
        self.assertNotEqual(resp.care_type, "emergency_112")
        self.assertEqual(resp.red_flags, [])
        self.assertEqual(resp.care_type, "teleconsultation")
        self.assertEqual(resp.urgency, "same_day")
        self.assertEqual(resp.emergency_steps, [])

    def test_child_mild_fever(self):
        # "bachhe ko halka bukhar hai" -> vague, asks follow-up, never emergency
        req = TriageRequest(
            user_input="bachhe ko halka bukhar hai",
            location=self.default_loc,
        )
        resp = run_triage_pipeline(req)
        self.assertNotEqual(resp.urgency, "emergency")
        self.assertNotEqual(resp.care_type, "emergency_112")
        self.assertIsNotNone(resp.follow_up_question)
        self.assertIsNone(resp.care_type)
        self.assertIsNone(resp.urgency)
        self.assertEqual(resp.red_flags, [])
        self.assertEqual(resp.emergency_steps, [])

    def test_stomach_pain_3_days(self):
        # "pet mein dard hai 3 din se" -> vague, asks follow-up, never emergency
        req = TriageRequest(
            user_input="pet mein dard hai 3 din se",
            location=self.default_loc,
        )
        resp = run_triage_pipeline(req)
        self.assertNotEqual(resp.urgency, "emergency")
        self.assertNotEqual(resp.care_type, "emergency_112")
        self.assertIsNotNone(resp.follow_up_question)
        self.assertIsNone(resp.care_type)
        self.assertIsNone(resp.urgency)
        self.assertEqual(resp.red_flags, [])
        self.assertEqual(resp.emergency_steps, [])

    def test_tabiyat_theek_nahi_vague(self):
        # "tabiyat theek nahi" -> follow_up_question, no decision
        req = TriageRequest(
            user_input="tabiyat theek nahi",
            location=self.default_loc,
        )
        resp = run_triage_pipeline(req)
        self.assertIsNotNone(resp.follow_up_question)
        self.assertIsNone(resp.care_type)
        self.assertIsNone(resp.urgency)
        self.assertEqual(resp.emergency_steps, [])

    def test_empty_string_input(self):
        # "" -> follow_up_question, no decision
        req = TriageRequest(
            user_input="",
            location=self.default_loc,
        )
        resp = run_triage_pipeline(req)
        self.assertIsNotNone(resp.follow_up_question)
        self.assertIsNone(resp.care_type)
        self.assertIsNone(resp.urgency)
        self.assertEqual(resp.emergency_steps, [])

    def test_dadi_chest_pain_breathlessness(self):
        # "dadi ko seene mein dard hai aur saans nahi aa rahi" -> emergency_112, emergency
        req = TriageRequest(
            user_input="dadi ko seene mein dard hai aur saans nahi aa rahi",
            location=self.default_loc,
        )
        resp = run_triage_pipeline(req)
        self.assertEqual(resp.care_type, "emergency_112")
        self.assertEqual(resp.urgency, "emergency")
        self.assertTrue(len(resp.emergency_steps) > 0)
        self.assertEqual(resp.matched_caregivers, [])

    def test_maa_unconscious(self):
        # "meri maa behosh ho gayi hai" -> emergency_112, emergency
        req = TriageRequest(
            user_input="meri maa behosh ho gayi hai",
            location=self.default_loc,
        )
        resp = run_triage_pipeline(req)
        self.assertEqual(resp.care_type, "emergency_112")
        self.assertEqual(resp.urgency, "emergency")
        self.assertTrue(len(resp.emergency_steps) > 0)
        self.assertEqual(resp.matched_caregivers, [])

    def test_fever_breathing_answered_no(self):
        # "fever" + breathing question answered "No" -> not emergency
        hist = [
            ChatMessage(role="user", text="fever"),
            ChatMessage(role="assistant", text="Kya saans lene mein dikkat hai?"),
        ]
        req = TriageRequest(
            user_input="No",
            location=self.default_loc,
            conversation_history=hist,
        )
        resp = run_triage_pipeline(req)
        self.assertNotEqual(resp.urgency, "emergency")
        self.assertNotEqual(resp.care_type, "emergency_112")
        self.assertEqual(resp.red_flags, [])
        self.assertEqual(resp.emergency_steps, [])

    def test_fever_breathing_answered_yes(self):
        # "fever" + breathing question answered "Yes" -> emergency_112, emergency
        hist = [
            ChatMessage(role="user", text="fever"),
            ChatMessage(role="assistant", text="Kya saans lene mein dikkat hai?"),
        ]
        req = TriageRequest(
            user_input="Yes",
            location=self.default_loc,
            conversation_history=hist,
        )
        resp = run_triage_pipeline(req)
        self.assertEqual(resp.care_type, "emergency_112")
        self.assertEqual(resp.urgency, "emergency")
        self.assertTrue(len(resp.emergency_steps) > 0)
        self.assertEqual(resp.matched_caregivers, [])


if __name__ == "__main__":
    unittest.main()
