import unittest
from app.schemas import TriageRequest, ChatMessage, Location
from app.core.pipeline import run_triage_pipeline
from app.core.intake import needs_more_info, select_follow_up_question, extract_slots
from app.config import settings


class TestFollowupPolicy(unittest.TestCase):

    FORBIDDEN_PHRASES = [
        "doctor home check",
        "nursing procedure",
        "lab test at home",
        "online doctor consult",
        "aapko kis prakaar ki service chahiye",
        "what type of healthcare service do you need",
        "kis prakaar ki service",
    ]

    def _assert_no_forbidden_phrases(self, resp):
        if resp.follow_up_question:
            q_lower = resp.follow_up_question.lower()
            for fp in self.FORBIDDEN_PHRASES:
                self.assertNotIn(fp, q_lower, f"Forbidden phrase '{fp}' found in follow_up_question: {resp.follow_up_question}")

        if resp.follow_up_options:
            for opt in resp.follow_up_options:
                opt_lower = opt.lower()
                for fp in self.FORBIDDEN_PHRASES:
                    self.assertNotIn(fp, opt_lower, f"Forbidden phrase '{fp}' found in follow_up_options: {opt}")

    def test_dada_ghabrahat_no_service_question(self):
        # "mere dada ji ko kal raat se ghabrahat ho rahi hai" -> has symptom (ghabrahat / anxiety / palpitation)
        # MUST NOT ask what service is needed. Either red-flag screen (breathing/chest pain) or direct decision.
        req = TriageRequest(
            user_input="mere dada ji ko kal raat se ghabrahat ho rahi hai",
            language="hinglish",
            location=Location(lat=28.61, lng=77.20),
            conversation_history=[],
        )
        resp = run_triage_pipeline(req)
        self._assert_no_forbidden_phrases(resp)

        if resp.follow_up_question:
            # If follow up asked, it must only be a red-flag screen (a) or duration (d)
            self.assertTrue(
                any(w in resp.follow_up_question.lower() for w in ["saans", "breathing", "chest", "seene", "kab se", "duration"]),
                f"Unexpected question: {resp.follow_up_question}",
            )
        else:
            self.assertIn(resp.care_type, ["teleconsultation", "paramedic_home_visit"])

    def test_pair_moch_decision_or_nonservice(self):
        # "pair mein moch aa gayi hai" -> sprain -> injury module card or a
        # paramedic/teleconsultation decision (never a service question).
        req = TriageRequest(
            user_input="pair mein moch aa gayi hai",
            language="hinglish",
            location=Location(lat=28.61, lng=77.20),
            conversation_history=[],
        )
        resp = run_triage_pipeline(req)
        self._assert_no_forbidden_phrases(resp)
        if resp.care_type:
            self.assertIn(resp.care_type, ["paramedic_home_visit", "teleconsultation"])
        else:
            # Injury module card: the follow-up question is the module label.
            self.assertIsNotNone(resp.module_card)
            self.assertEqual(resp.module_card["module_id"], "injury")
            self.assertTrue(resp.module_card["fields"])

    def test_sugar_check_decides_lab_test_home(self):
        # "sugar check karna hai subah" -> fasting blood sugar -> decide lab_test_home
        req = TriageRequest(
            user_input="sugar check karna hai subah",
            language="hinglish",
            location=Location(lat=28.61, lng=77.20),
            conversation_history=[],
        )
        resp = run_triage_pipeline(req)
        self._assert_no_forbidden_phrases(resp)
        self.assertEqual(resp.care_type, "lab_test_home")
        self.assertEqual(resp.urgency, "scheduled")
        self.assertIsNone(resp.follow_up_question)

    def test_knee_hurts_stairs_decision(self):
        # "my knee hurts when I climb stairs" -> joint pain -> decide teleconsultation or home visit
        req = TriageRequest(
            user_input="my knee hurts when I climb stairs",
            language="en",
            location=Location(lat=28.61, lng=77.20),
            conversation_history=[],
        )
        resp = run_triage_pipeline(req)
        self._assert_no_forbidden_phrases(resp)
        if resp.care_type:
            self.assertIn(resp.care_type, ["teleconsultation", "paramedic_home_visit"])

    def test_zero_health_info_returns_symptom_style_buttons(self):
        # "help chahiye" and "I need help" -> no health info at all -> return symptom-style clue buttons
        for text, lang in [("help chahiye", "hinglish"), ("I need help", "en"), ("मदद चाहिए", "hi")]:
            req = TriageRequest(
                user_input=text,
                language=lang,
                location=Location(lat=28.61, lng=77.20),
                conversation_history=[],
            )
            resp = run_triage_pipeline(req)
            self._assert_no_forbidden_phrases(resp)
            self.assertIsNotNone(resp.follow_up_question)
            self.assertTrue(len(resp.follow_up_options) >= 4)
            # Check for symptom-style clue buttons (in English, Hinglish, or Hindi Devanagari)
            options_text = " ".join(resp.follow_up_options).lower()
            self.assertTrue(
                any(w in options_text for w in ["fever", "bukhar", "pain", "dard", "wound", "ghaav", "lab", "weak", "buzurg", "बुखार", "दर्द", "घाव", "खून", "चोट"]),
                f"Options did not contain symptom clues: {resp.follow_up_options}",
            )

    def test_max_two_followups_strictly_respected(self):
        # After 2 turns (len(conversation_history) >= 2), system MUST decide. Never ask a 3rd question.
        # If still unclear, choose teleconsultation with reasoning containing:
        # "We could not be sure what you need, so a doctor video consult is the safest first step."
        history = [
            ChatMessage(role="user", text="I need help"),
            ChatMessage(role="assistant", text="Please tell us what main symptoms or health concern you are experiencing."),
            ChatMessage(role="user", text="Something else"),
            ChatMessage(role="assistant", text="Could you tell us more?"),
        ]
        req = TriageRequest(
            user_input="still not sure what I need",
            language="en",
            location=Location(lat=28.61, lng=77.20),
            conversation_history=history,
        )
        resp = run_triage_pipeline(req)
        self._assert_no_forbidden_phrases(resp)
        self.assertIsNone(resp.follow_up_question, "System asked a 3rd follow up question instead of deciding!")
        self.assertIsNotNone(resp.care_type)
        self.assertEqual(resp.care_type, "teleconsultation")
        self.assertEqual(resp.urgency, "same_day")
        self.assertIn(
            "We could not be sure what you need, so a doctor video consult is the safest first step.",
            resp.reasoning,
        )

    def test_trace_table_for_eight_earlier_inputs(self):
        inputs = [
            "papa ko do din se bukhar hai aur khansi bhi",
            "mujhe sir dard hai kal se",
            "fever",
            "bachhe ko halka bukhar hai",
            "dadi ko seene mein dard hai aur saans nahi aa rahi",
            "meri maa behosh ho gayi hai",
            "pet mein dard hai 3 din se",
            "tabiyat theek nahi",
        ]

        print("\n" + "=" * 120)
        print(f"{'#':<3} | {'INPUT':<45} | {'CARE TYPE':<22} | {'URGENCY':<12} | {'QUESTION / ACTION':<32}")
        print("-" * 120)

        for i, text in enumerate(inputs, 1):
            req = TriageRequest(
                user_input=text,
                language="hinglish",
                location=Location(lat=28.61, lng=77.20),
                conversation_history=[],
            )
            resp = run_triage_pipeline(req, debug=True)
            self._assert_no_forbidden_phrases(resp)

            care_str = resp.care_type or "None (Follow-up)"
            urg_str = resp.urgency or "None"
            action_str = resp.follow_up_question[:30] + "..." if resp.follow_up_question else "Decision Made"

            print(f"{i:<3} | {text:<45} | {care_str:<22} | {urg_str:<12} | {action_str:<32}")

        print("=" * 120 + "\n")


if __name__ == "__main__":
    unittest.main()
