"""Language consistency tests: every user-facing string follows the user's
language (hi / hinglish / en).

- caregiver `reason` strings are localised (no mixed scripts).
- module_card responses expose the real question text as follow_up_question
  and the choice labels as follow_up_options.
- option sets never mix languages.
"""
import re
import unittest

from app.schemas import TriageRequest, Location
from app.core.pipeline import run_triage_pipeline
from app.core.modules import load_modules, module_ids, render_module_card

LOC = Location(lat=28.54, lng=77.27)

_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_LATIN = re.compile(r"[A-Za-z]")
# Allowed Latin fragments inside hi options: temperature units only.
_UNITS = re.compile(r"\d+\s*°?\s*[FfCc]|\d+-\d+\s*°?\s*[FfCc]")


class TestLanguageConsistency(unittest.TestCase):

    def test_caregiver_reasons_follow_user_language(self):
        text = "papa ko do din se bukhar hai aur khansi bhi"

        resp_en = run_triage_pipeline(TriageRequest(user_input=text, language="en", location=LOC))
        for m in resp_en.matched_caregivers:
            self.assertTrue(m.reason)
            self.assertIsNone(_DEVANAGARI.search(m.reason), m.reason)
            self.assertIn("-speaking", m.reason)

        resp_hing = run_triage_pipeline(TriageRequest(user_input=text, language="hinglish", location=LOC))
        for m in resp_hing.matched_caregivers:
            self.assertTrue(m.reason)
            self.assertIsNone(_DEVANAGARI.search(m.reason), m.reason)
            self.assertIn("bolne wale", m.reason)

        resp_hi = run_triage_pipeline(TriageRequest(user_input=text, language="hi", location=LOC))
        for m in resp_hi.matched_caregivers:
            self.assertTrue(m.reason)
            self.assertIsNone(_LATIN.search(m.reason), f"Latin script in hi reason: {m.reason!r}")

    def test_module_card_exposes_real_question_and_options(self):
        resp = run_triage_pipeline(
            TriageRequest(user_input="mujhe bukhar hai", language="hinglish", location=LOC)
        )
        self.assertIsNotNone(resp.module_card)
        self.assertEqual(resp.follow_up_question, "Bukhar kitne samay se hai?")
        self.assertEqual(resp.follow_up_options, ["Aaj se", "2-3 din se", "Ek hafte se zyada"])

        resp_hi = run_triage_pipeline(
            TriageRequest(user_input="mujhe bukhar hai", language="hi", location=LOC)
        )
        self.assertEqual(resp_hi.follow_up_question, "बुखार कितने समय से है?")
        for opt in resp_hi.follow_up_options:
            self.assertTrue(opt)
            self.assertIsNone(_LATIN.search(opt), f"Latin script in hi option: {opt!r}")

        resp_en = run_triage_pipeline(
            TriageRequest(user_input="I have a fever", language="en", location=LOC)
        )
        self.assertEqual(resp_en.follow_up_question, "How long has the fever lasted?")
        for opt in resp_en.follow_up_options:
            self.assertIsNone(_DEVANAGARI.search(opt), f"Devanagari in en option: {opt!r}")

    def test_option_sets_never_mix_languages(self):
        for mid in module_ids():
            for lang in ("en", "hi", "hinglish"):
                with self.subTest(module=mid, lang=lang):
                    card = render_module_card(mid, lang, {})
                    self.assertIsNotNone(card, f"module {mid!r} did not render for {lang}")
                    for field in card.get("fields", []) or []:
                        question = field.get("question", "")
                        if lang == "hi":
                            stripped_q = _UNITS.sub(" ", question)
                            self.assertIsNone(
                                _LATIN.search(stripped_q),
                                f"Latin script in hi question of {mid}: {question!r}",
                            )
                        else:
                            self.assertIsNone(
                                _DEVANAGARI.search(question),
                                f"Devanagari in {lang} question of {mid}: {question!r}",
                            )
                        for opt in field.get("options", []) or []:
                            if lang == "hi":
                                stripped = _UNITS.sub(" ", opt)
                                self.assertIsNone(
                                    _LATIN.search(stripped),
                                    f"Latin script in hi option of {mid}: {opt!r}",
                                )
                            else:
                                self.assertIsNone(
                                    _DEVANAGARI.search(opt),
                                    f"Devanagari in {lang} option of {mid}: {opt!r}",
                                )

    def test_card_lines_follow_user_language(self):
        text = "mujhe 2 din se bukhar hai"
        for lang, regex in (("hi", _LATIN), ("hinglish", _DEVANAGARI), ("en", _DEVANAGARI)):
            with self.subTest(lang=lang):
                resp = run_triage_pipeline(
                    TriageRequest(user_input=text, language=lang, location=LOC)
                )
                self.assertIsNotNone(resp.card_lines)
                joined = " ".join(resp.card_lines.values())
                self.assertIsNone(regex.search(joined), joined)


if __name__ == "__main__":
    unittest.main()
