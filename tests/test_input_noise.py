"""Input-noise rule tests (Groq mocked).

Covers the four input-noise rules:
  1. Gibberish/unrelated input -> symptom question, no care_type, no slots;
     third empty attempt -> low-confidence teleconsultation, never emergency.
  2. Noise mixed with a real symptom -> identical result to the clean version,
     and no noise token leaks into the explanation.
  3. Bare numbers are not durations; number+unit is; fever temperature and age
     vs duration are kept apart.
  4. Red-flag emergencies are preserved even with noise around them.
"""
import re
import unittest
from unittest.mock import patch

from app.schemas import TriageRequest, Location, ChatMessage
from app.core.pipeline import run_triage_pipeline
from app.core.intake import extract_slots, get_question_by_id

LOC = Location(lat=28.54, lng=77.27)

# The semantic screen is a separate (Groq) concern; these tests isolate the
# input-noise rules, so the screen is stubbed to "skip".
SKIP_SCREEN = {"status": "skip", "flags": [], "combined": False}

SYMPTOM_Q_EN, _ = get_question_by_id("main_symptom_buttons", "en")


def _triage(text, history=None, lang="hinglish", debug=True):
    with patch("app.core.pipeline.screen_red_flags", return_value=SKIP_SCREEN):
        return run_triage_pipeline(
            TriageRequest(
                user_input=text,
                language=lang,
                location=LOC,
                conversation_history=history or [],
            ),
            debug=debug,
        )


class TestGibberish(unittest.TestCase):
    """Rule 1: unrelated / gibberish input must never be guessed at."""

    GIBBERISH = [
        "asdf", "hello there lol", "banana 77", "what is the weather",
        "qwerty", "12345", "lol haha bro", "zzzz", "xyzzy", "good morning",
        "hi there", "hey yaar", "random stuff 99", "blah blah", "woohoo",
    ]

    def test_15_gibberish_ask_symptom_question_with_no_decision(self):
        self.assertEqual(len(self.GIBBERISH), 15)
        for text in self.GIBBERISH:
            with self.subTest(text=text):
                resp = _triage(text, lang="en")
                self.assertIsNotNone(resp.follow_up_question, f"no symptom question for {text!r}")
                self.assertIsNone(resp.care_type, f"decided care_type for {text!r}")
                self.assertIsNone(resp.urgency, f"decided urgency for {text!r}")

                slots = resp.debug["slots"]
                self.assertEqual(slots.get("symptoms", []), [], f"symptoms set for {text!r}")
                self.assertIsNone(slots.get("duration"), f"duration set for {text!r}")
                self.assertIsNone(slots.get("fever_temp"), f"temperature set for {text!r}")
                self.assertIsNone(slots.get("age_group"), f"age_group set for {text!r}")

    def test_second_empty_attempt_adds_pick_closest_hint(self):
        history = [
            ChatMessage(role="user", text="asdf"),
            ChatMessage(role="assistant", text=SYMPTOM_Q_EN),
        ]
        resp = _triage("hello there lol", history=history, lang="en")
        self.assertIsNotNone(resp.follow_up_question)
        self.assertIsNone(resp.care_type)
        self.assertIn("pick the closest one", resp.follow_up_question.lower())

    def test_third_empty_attempt_teleconsultation_low_confidence(self):
        history = [
            ChatMessage(role="user", text="asdf"),
            ChatMessage(role="assistant", text=SYMPTOM_Q_EN),
            ChatMessage(role="user", text="hello there lol"),
            ChatMessage(role="assistant", text=SYMPTOM_Q_EN),
        ]
        resp = _triage("banana 77", history=history, lang="en")
        self.assertIsNone(resp.follow_up_question)
        self.assertEqual(resp.care_type, "teleconsultation")
        self.assertNotEqual(resp.care_type, "emergency_112")
        self.assertEqual(resp.urgency, "same_day")
        self.assertIsNotNone(resp.confidence)
        self.assertLess(resp.confidence, 0.5, "gibberish fallback must be low confidence")
        self.assertIn("not enough information", resp.debug["reasons"])


class TestNoiseIgnored(unittest.TestCase):
    """Rule 2: noise around a real symptom must not change the result."""

    NOISE_TOKENS = ("lol", "haha", "yaar", "plz", "bro")

    PAIRS = [
        ("lol bro bukhar hai haha", "bukhar hai"),
        ("yaar khansi ho rahi hai plz", "khansi ho rahi hai"),
        ("lol my head hurts since morning haha", "my head hurts since morning"),
        ("bro chakkar aa raha hai lol", "chakkar aa raha hai"),
        ("plz pet me dard hai yaar", "pet me dard hai"),
        ("haha do din se bukhar bro", "do din se bukhar"),
        ("lol papa ko bukhar hai lol", "papa ko bukhar hai"),
        ("yaar kamzori bahut hai plz", "kamzori bahut hai"),
        ("bro ghabrahat ho rahi hai lol", "ghabrahat ho rahi hai"),
        ("lol seene me dard hai yaar", "seene me dard hai"),
        ("plz saans lene me dikkat hai bro", "saans lene me dikkat hai"),
        ("haha injection lagwana hai ghar pe lol", "injection lagwana hai ghar pe"),
        ("yaar sugar check karna hai plz", "sugar check karna hai"),
        ("lol sir dard hai kal se bro", "sir dard hai kal se"),
        ("bro ulti ho rahi hai haha", "ulti ho rahi hai"),
        ("lol bache ko halka bukhar hai yaar", "bache ko halka bukhar hai"),
        ("plz ghutne me dard hai bro", "ghutne me dard hai"),
        ("haha pregnant hu bukhar hai lol", "pregnant hu bukhar hai"),
        ("yaar diabetes hai aur bukhar hai plz", "diabetes hai aur bukhar hai"),
        ("lol chot lag gayi hai bro", "chot lag gayi hai"),
    ]

    def _assert_no_noise(self, text):
        for tok in self.NOISE_TOKENS:
            self.assertNotRegex(
                text.lower(),
                rf"\b{re.escape(tok)}\b",
                f"noise token {tok!r} leaked into explanation: {text!r}",
            )

    def test_20_noisy_messages_match_clean(self):
        self.assertEqual(len(self.PAIRS), 20)
        for noisy, clean in self.PAIRS:
            with self.subTest(noisy=noisy, clean=clean):
                r_noisy = _triage(noisy)
                r_clean = _triage(clean)
                self.assertEqual(r_noisy.care_type, r_clean.care_type)
                self.assertEqual(r_noisy.urgency, r_clean.urgency)
                self.assertEqual(r_noisy.follow_up_question, r_clean.follow_up_question)
                self.assertEqual(
                    (r_noisy.debug["slots"].get("symptoms")),
                    (r_clean.debug["slots"].get("symptoms")),
                )
                if r_noisy.reasoning:
                    self._assert_no_noise(r_noisy.reasoning)

    def test_noise_never_appears_in_explanation(self):
        resp = _triage("lol bro my head hurts since morning haha", lang="en")
        self.assertIsNotNone(resp.reasoning)
        self._assert_no_noise(resp.reasoning)
        self.assertNotIn("lol", resp.reasoning.lower())


class TestNumbers(unittest.TestCase):
    """Rule 3: bare numbers are not durations/temperatures/ages."""

    # (text, expected_duration, expected_fever_temp, expected_age_group)
    BARE = [
        ("7", None, None, None),
        ("102", None, None, None),
        ("bukhar 2", None, None, None),
        ("55", None, None, None),
        ("ek", None, None, None),
        ("do", None, None, None),
        ("teen", None, None, None),
        ("100", None, None, None),
        ("3", None, None, None),
        ("99", None, None, None),
    ]
    DURATIONS = [
        ("2 din se bukhar", "2 days"),
        ("do din se bukhar", "2 days"),
        ("teen din se bukhar", "3 days"),
        ("3 din se dard", "3 days"),
        ("since 3 days", "3 days"),
        ("ek hafte se", ">5 days"),
        ("5 din se", ">5 days"),
        ("2 saal se dard", ">5 days"),
        ("kal se", "1 day"),
        ("subah se", "today"),
    ]
    TEMPS = [
        ("bukhar 102", 102.0, "F"),
        ("fever 101", 101.0, "F"),
    ]
    AGES = [
        ("70 saal ke papa", "senior"),
        ("age 70", "senior"),
        ("2 saal ka bacha", "child"),
    ]

    def test_25_number_messages(self):
        total = len(self.BARE) + len(self.DURATIONS) + len(self.TEMPS) + len(self.AGES)
        self.assertEqual(total, 25)

        for text, dur, temp, age in self.BARE:
            with self.subTest(case="bare", text=text):
                slots = extract_slots(text, [])
                self.assertIsNone(slots["duration"], f"bare number {text!r} set duration")
                self.assertIsNone(slots["fever_temp"], f"bare number {text!r} set temperature")
                self.assertIsNone(slots["age_group"], f"bare number {text!r} set age")

        for text, dur in self.DURATIONS:
            with self.subTest(case="duration", text=text):
                slots = extract_slots(text, [])
                self.assertEqual(slots["duration"], dur, f"{text!r} -> duration")

        for text, val, unit in self.TEMPS:
            with self.subTest(case="temp", text=text):
                slots = extract_slots(text, [])
                self.assertEqual(slots["fever_temp"], val, f"{text!r} -> temperature")
                self.assertEqual(slots["fever_temp_unit"], unit)
                self.assertIsNone(slots["duration"], f"{text!r} should not set duration")

        for text, age in self.AGES:
            with self.subTest(case="age", text=text):
                slots = extract_slots(text, [])
                self.assertEqual(slots["age_group"], age, f"{text!r} -> age")
                self.assertIsNone(slots["duration"], f"{text!r} should be age, not duration")

    def test_age_not_confused_with_duration(self):
        # "2 saal se dard" is duration, "70 saal ke papa" is age.
        dur_slots = extract_slots("2 saal se dard", [])
        self.assertIsNotNone(dur_slots["duration"])
        self.assertIsNone(dur_slots["age_group"])

        age_slots = extract_slots("70 saal ke papa", [])
        self.assertIsNone(age_slots["duration"])
        self.assertEqual(age_slots["age_group"], "senior")


class TestRedFlagNoise(unittest.TestCase):
    """Rule 2/4: red-flag emergencies survive noise (detected on the raw text)."""

    def test_noisy_breathlessness_still_emergency(self):
        resp = run_triage_pipeline(
            TriageRequest(user_input="lol papa cant breathe haha", language="hinglish", location=LOC)
        )
        self.assertEqual(resp.care_type, "emergency_112")
        self.assertEqual(resp.urgency, "emergency")

    def test_noisy_chest_pain_still_emergency(self):
        resp = run_triage_pipeline(
            TriageRequest(user_input="bro seene me dard hai yaar", language="hinglish", location=LOC)
        )
        self.assertEqual(resp.care_type, "emergency_112")

    def test_noisy_bleeding_still_emergency(self):
        resp = run_triage_pipeline(
            TriageRequest(user_input="plz khoon ruk nahi raha lol", language="hinglish", location=LOC)
        )
        self.assertEqual(resp.care_type, "emergency_112")


if __name__ == "__main__":
    unittest.main()
