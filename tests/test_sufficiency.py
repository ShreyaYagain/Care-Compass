"""Follow-up sufficiency policy tests.

Symptom + context (severity / duration / age / relation / pregnancy / chronic)
=> immediate decision with zero questions. A question is only allowed when
there is no symptom at all, or as a single red-flag screening for symptoms
that could be serious (stomach pain, headache, dizziness).
"""
import unittest

from app.schemas import TriageRequest, ChatMessage, Location
from app.core.pipeline import run_triage_pipeline
from app.core.intake import needs_more_info, extract_slots

LOC = Location(lat=28.54, lng=77.27)


def _triage(text: str, history=None):
    return run_triage_pipeline(
        TriageRequest(user_input=text, language="hinglish", location=LOC,
                      conversation_history=history or [])
    )


class TestSufficiency(unittest.TestCase):
    """25 messages: a symptom plus context must return a decision, zero questions."""

    SYMPTOM_PLUS_CONTEXT = [
        # symptom + duration
        "papa ko do din se bukhar hai aur khansi bhi",
        "mujhe sir dard hai kal se",
        "pet mein dard hai 3 din se",
        "bukhar 5 din se hai",
        "khansi ek hafte se hai",
        # symptom + severity
        "halka bukhar hai",
        "tez sar dard hai",
        "bahut zyada bukhar hai",
        "mild headache and nausea",
        "severe body pain",
        # symptom + age group
        "bachhe ko bukhar hai",
        "buzurg ko khansi hai",
        "meri maa ko bukhar hai",
        "dada ko bukhar hai",
        "teen saal ke bache ko halka bukhar hai",
        # symptom + relation
        "papa ko bukhar hai",
        "meri beti ko pet dard hai",
        "pati ko sar dard hai",
        "meri mummy ko khansi hai",
        "bhai ko bukhar aur khansi hai",
        # symptom + pregnancy
        "pregnant hu, halka bukhar hai",
        # symptom + chronic condition
        "mujhe diabetes hai aur bukhar hai",
        "asthma patient, khansi ho rahi hai",
        # multi-symptom + duration
        "bukhar, khansi aur sar dard 2 din se hai",
        "ultti aur dast ho rahe hain do din se",
    ]

    def test_25_symptom_plus_context_decides(self):
        self.assertEqual(len(self.SYMPTOM_PLUS_CONTEXT), 25)
        for text in self.SYMPTOM_PLUS_CONTEXT:
            with self.subTest(text=text):
                resp = _triage(text)
                self.assertIsNone(resp.follow_up_question, f"question asked for: {text!r}")
                self.assertIsNotNone(resp.care_type, f"no decision for: {text!r}")
                self.assertIsNotNone(resp.urgency)

    def test_no_symptom_asks_clue_buttons(self):
        resp = _triage("help chahiye")
        self.assertIsNotNone(resp.follow_up_question)
        self.assertGreaterEqual(len(resp.follow_up_options), 4)

    def test_serious_symptom_single_screening_question(self):
        # Bare stomach pain (no context) may ask ONE screening question.
        resp = _triage("pet me dard hai")
        self.assertIsNotNone(resp.follow_up_question)

    def test_max_one_question_when_symptom_exists(self):
        # After the screening question has been asked once, answering must
        # decide rather than ask a second question.
        history = [
            ChatMessage(role="user", text="pet me dard hai"),
            ChatMessage(role="assistant", text="Yeh consultation kiske liye hai?"),
        ]
        resp = _triage("self", history=history)
        self.assertIsNone(resp.follow_up_question, "second question must not be asked")
        self.assertIsNotNone(resp.care_type)

    def test_question_not_repeated_when_answer_already_in_message(self):
        # Stomach pain with the who-for already stated must not ask it again.
        resp = _triage("mere papa ke pet me dard hai")
        self.assertIsNone(resp.follow_up_question)
        self.assertIsNotNone(resp.care_type)

    def test_pregnancy_never_asks(self):
        resp = _triage("pregnant hu, bas halki si takleef hai")
        self.assertIsNone(resp.follow_up_question)
        self.assertIsNotNone(resp.care_type)

    def test_service_request_decides_without_question(self):
        resp = _triage("sugar check karna hai subah")
        self.assertIsNone(resp.follow_up_question)
        self.assertIsNotNone(resp.care_type)

    def test_needs_more_info_false_with_symptom_and_context(self):
        slots = extract_slots("papa ko do din se bukhar hai", [])
        self.assertFalse(needs_more_info(slots, 0, []))
        self.assertFalse(needs_more_info(slots, 1, []))


if __name__ == "__main__":
    unittest.main()
