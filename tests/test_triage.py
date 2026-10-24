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
        self.assertEqual(resp.care_type, "emergency_112")
        self.assertEqual(resp.urgency, "emergency")
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
        hist = [
            ChatMessage(role="user", text="papa ko do din se bukhar hai aur khansi bhi"),
            ChatMessage(role="assistant", text="Kya saans lene mein dikkat hai?"),
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

    def test_validation_prediction_distribution_under_60_percent(self):
        import csv
        import joblib
        from collections import Counter
        from app.config import BASE_DIR, settings
        from app.core.language import normalise_text

        val_file = BASE_DIR / "ml" / "data" / "val.csv"
        vec = joblib.load(settings.ARTIFACTS_DIR / "tfidf_vectorizer.joblib")
        clf = joblib.load(settings.ARTIFACTS_DIR / "triage_care.joblib")

        val_texts = []
        with open(val_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                val_texts.append(r["norm_input"] or normalise_text(r["user_input"]))

        X_val = vec.transform(val_texts)
        preds = clf.predict(X_val)
        counts = Counter(preds)
        total = len(preds)
        for cls, cnt in counts.items():
            pct = (cnt / total) * 100
            self.assertLessEqual(pct, 60.0, f"Class {cls} has {pct:.1f}% predictions, which exceeds 60%")

    def test_problem1_inputs_give_different_correct_results(self):
        loc = Location(lat=28.54, lng=77.27)

        # 1. "ghar pe IM injection lagwana hai" -> home_nursing / same_day
        r1 = run_triage_pipeline(TriageRequest(user_input="ghar pe IM injection lagwana hai", location=loc))
        self.assertEqual(r1.care_type, "home_nursing")
        self.assertEqual(r1.urgency, "same_day")

        # 2. "full body checkup home collection" -> lab_test_home / scheduled
        r2 = run_triage_pipeline(TriageRequest(user_input="full body checkup home collection", location=loc))
        self.assertEqual(r2.care_type, "lab_test_home")
        self.assertEqual(r2.urgency, "scheduled")

        # 3. "papa ko do din se bukhar hai aur khansi bhi" -> paramedic_home_visit / same_day
        r3 = run_triage_pipeline(TriageRequest(user_input="papa ko do din se bukhar hai aur khansi bhi", location=loc))
        self.assertEqual(r3.care_type, "paramedic_home_visit")
        self.assertEqual(r3.urgency, "same_day")

        # 4. "second opinion chahiye bache ki dawai par" -> teleconsultation / same_day
        r4 = run_triage_pipeline(TriageRequest(user_input="second opinion chahiye bache ki dawai par", location=loc))
        self.assertEqual(r4.care_type, "teleconsultation")
        self.assertEqual(r4.urgency, "same_day")

        # 5. "chest pain ho raha hai papa ko" -> emergency_112 / emergency, no caregivers
        r5 = run_triage_pipeline(TriageRequest(user_input="chest pain ho raha hai papa ko", location=loc))
        self.assertEqual(r5.care_type, "emergency_112")
        self.assertEqual(r5.urgency, "emergency")
        self.assertEqual(r5.matched_caregivers, [])

        # 6. "doctor chahiye" -> follow-up (null, null)
        r6 = run_triage_pipeline(TriageRequest(user_input="doctor chahiye", location=loc))
        self.assertIsNotNone(r6.follow_up_question)
        self.assertIsNone(r6.care_type)
        self.assertIsNone(r6.urgency)


if __name__ == "__main__":
    unittest.main()
