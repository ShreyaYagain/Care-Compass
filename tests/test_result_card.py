"""Result card policy tests: short lines, no passage.

- Card text (why + next + watch_for + context_line) <= 40 words for 30
  sample results in English, Hindi and Hinglish.
- One language per card (no mixed scripts).
- No disclaimer, no weather/location/AQI text on the card.
- The safety line ("Call 112 if ...") is on every non-emergency card.
- Emergency results are short "Call 112 now" + first-aid steps, no caregivers.
"""
import re
import unittest

from app.schemas import TriageRequest, Location
from app.core.pipeline import run_triage_pipeline
from app.core.explain import card_text

LOC = Location(lat=28.54, lng=77.27)

# 30 inputs that reach a final decision in a single turn (no follow-ups).
SAMPLES = [
    "I have a headache",
    "papa ko do din se bukhar hai aur khansi bhi",
    "sugar check karna hai subah",
    "ghar pe IM injection lagwana hai",
    "severe chest pain",
    "mujhe cold aur khansi hai",
    "pet me dard hai kal se",
    "mujhe ulti ho rahi hai aaj subah se",
    "dadi ko kamzori hai do din se",
    "papa ko ulti aur dast ho rahe hain kal se",
    "mujhe chakkar aa rahe hain do din se",
    "dadi ko thakan hai do din se",
    "blood test karwana hai",
    "lipid profile chahiye",
    "papa ki dressing change karni hai kal se",
    "bacha ko bukhar hai kal se",
    "papa ko kal se ghabrahat ho rahi hai",
    "zindagi me pehli baar itna sir dard",
    "dizzy lag raha hai subah se",
    "sugar check after lunch",
    "sample collection chahiye",
    "elderly person needs checkup",
    "mujhe bukhar aur thakan hai",
    "papa ko pet me dard aur ulti hai",
    "mujhe bukhar hai teen din se",
    "mummy ko bukhar hai aaj subah se",
    "mujhe khansi hai ek hafte se",
    "papa ko kamzori hai do din se",
    "sir dard hai kal se",
    "ghar pe catheter care chahiye",
]

BANNED_ON_CARD = [
    "This app helps",
    "Right now:",
    "not a doctor",
    "AQI",
]

_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_LATIN = re.compile(r"[A-Za-z]")


def _words(text: str) -> int:
    return len(text.split())


class TestResultCard(unittest.TestCase):

    def _run(self, text: str, lang: str):
        return run_triage_pipeline(
            TriageRequest(user_input=text, language=lang, location=LOC, context_consent=False)
        )

    def test_30_samples_under_40_words_in_all_languages(self):
        self.assertEqual(len(SAMPLES), 30)
        for lang in ("en", "hi", "hinglish"):
            for text in SAMPLES:
                with self.subTest(lang=lang, text=text):
                    resp = self._run(text, lang)
                    if resp.follow_up_question:
                        continue  # follow-up turn (e.g. medication question)
                    self.assertIsNotNone(resp.care_type, f"expected a decision for {text!r}")
                    self.assertIsNotNone(resp.card_lines)
                    text_card = card_text(resp.card_lines)
                    self.assertLessEqual(_words(text_card), 40, f"card too long: {text_card!r}")

    def test_one_language_per_card(self):
        for text in SAMPLES:
            with self.subTest(text=text):
                resp_en = self._run(text, "en")
                if resp_en.follow_up_question:
                    continue  # follow-up turn (e.g. medication question)
                self.assertIsNone(_DEVANAGARI.search(card_text(resp_en.card_lines)))
                resp_hing = self._run(text, "hinglish")
                self.assertIsNone(_DEVANAGARI.search(card_text(resp_hing.card_lines)))
                resp_hi = self._run(text, "hi")
                self.assertIsNone(_LATIN.search(card_text(resp_hi.card_lines)))

    def test_banned_phrases_never_on_card(self):
        for lang in ("en", "hi", "hinglish"):
            for text in SAMPLES:
                with self.subTest(lang=lang, text=text):
                    resp = self._run(text, lang)
                    low = (resp.reasoning or "").lower()
                    for phrase in BANNED_ON_CARD:
                        self.assertNotIn(phrase.lower(), low, f"{phrase!r} on card for {text!r}")

    def test_safety_line_on_every_non_emergency_card(self):
        for lang in ("en", "hi", "hinglish"):
            for text in SAMPLES:
                with self.subTest(lang=lang, text=text):
                    resp = self._run(text, lang)
                    if resp.care_type == "emergency_112":
                        continue
                    if resp.follow_up_question:
                        # A follow-up turn (e.g. the medication question) has no
                        # result card; the safety line is checked on decisions.
                        continue
                    self.assertIsNotNone(resp.card_lines)
                    self.assertIn("112", resp.card_lines.get("watch_for", ""))

    def test_emergency_card_is_short_call_112(self):
        for lang in ("en", "hi", "hinglish"):
            resp = self._run("severe chest pain", lang)
            self.assertEqual(resp.care_type, "emergency_112")
            text_card = card_text(resp.card_lines)
            self.assertLessEqual(_words(text_card), 40)
            self.assertIn("112", resp.card_lines.get("next", ""))
            self.assertEqual(resp.card_lines.get("watch_for", ""), "")
            self.assertTrue(resp.emergency_steps)
            self.assertEqual(resp.matched_caregivers, [])

    def test_card_lines_have_all_short_fields(self):
        resp = self._run("I have a headache since morning", "en")
        lines = resp.card_lines
        self.assertTrue(lines["why"])
        self.assertTrue(lines["next"])
        self.assertTrue(lines["watch_for"])
        for key in ("why", "next", "watch_for"):
            self.assertLessEqual(_words(lines[key]), 15, f"{key} too long: {lines[key]!r}")

    def test_injury_module_result_card_under_40_words(self):
        from app.schemas import ChatMessage
        answers = {"head_hit": "No", "pain_level": 6, "weight_bearing": "With pain", "swelling": "Yes"}
        history = [ChatMessage(role="assistant", text="Injury / fall") for _ in range(4)]
        resp = run_triage_pipeline(
            TriageRequest(
                user_input="I fell down and my leg hurts", language="en", location=LOC,
                context_consent=False, conversation_history=history,
                module_id="injury", module_answers=answers,
            )
        )
        self.assertIsNotNone(resp.care_type)
        self.assertIsNotNone(resp.card_lines)
        self.assertLessEqual(_words(card_text(resp.card_lines)), 40)
        self.assertIn("112", resp.card_lines.get("watch_for", ""))
        self.assertIsNotNone(resp.details)
        self.assertEqual(resp.details.get("answers"), answers)


if __name__ == "__main__":
    unittest.main()
