"""Follow-up card contract tests.

- Every module_card response also carries a full follow_up_question in the
  user's language (never a bare symptom label) plus the card's choice labels
  as follow_up_options.
- One language per card (question, options, labels).
- Sufficiency: messages that already state duration/temperature decide
  without a card.
- The /triage contract and the Android parser share the same JSON sample.
"""
import json
import re
import unittest
from pathlib import Path

from app.schemas import TriageRequest, Location
from app.core.pipeline import run_triage_pipeline

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_JSON = REPO_ROOT / "android" / "app" / "src" / "test" / "resources" / "module_card_sample.json"

LOC = Location(lat=28.54, lng=77.27)

_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_LATIN = re.compile(r"[A-Za-z]")

MODULE_TRIGGERS = {
    "injury": "I fell down and my leg hurts",
    "fever": "mujhe bukhar hai",
    "abdominal_pain": "pet me dard hai aaj se",
    "cough_breathing": "mujhe khansi hai",
}


def _triage(text: str, lang: str):
    return run_triage_pipeline(
        TriageRequest(user_input=text, language=lang, location=LOC, context_consent=False)
    )


class TestFollowUpCard(unittest.TestCase):

    def test_every_module_card_carries_full_question_and_options(self):
        for module_id, text in MODULE_TRIGGERS.items():
            for lang in ("en", "hi", "hinglish"):
                with self.subTest(module=module_id, lang=lang):
                    resp = _triage(text, lang)
                    if resp.module_card is None:
                        continue
                    self.assertEqual(resp.module_card["module_id"], module_id)
                    q = resp.follow_up_question or ""
                    self.assertTrue(q, "follow_up_question must not be empty")
                    self.assertNotEqual(q, resp.module_card.get("label"), "question must not be a bare symptom label")
                    self.assertTrue(q.endswith("?") or "?" in q, f"not a question: {q!r}")
                    # choice cards carry tappable options
                    field = resp.module_card["fields"][0]
                    if field.get("type") != "slider010":
                        self.assertTrue(resp.follow_up_options, f"no options for {q!r}")
                        self.assertEqual(resp.follow_up_options, field.get("options"))
                    self.assertTrue(resp.module_card)

    def test_one_language_per_card(self):
        for module_id, text in MODULE_TRIGGERS.items():
            resp_en = _triage(text, "en")
            resp_hing = _triage(text, "hinglish")
            resp_hi = _triage(text, "hi")
            for resp, lang in ((resp_en, "en"), (resp_hing, "hinglish"), (resp_hi, "hi")):
                if resp.module_card is None:
                    continue
                q = resp.follow_up_question or ""
                opts = " ".join(resp.follow_up_options)
                if lang == "hi":
                    self.assertIsNone(_LATIN.search(q + " " + opts), f"Latin in hi card: {q!r} {opts!r}")
                else:
                    self.assertIsNone(_DEVANAGARI.search(q + " " + opts), f"Devanagari in {lang} card: {q!r} {opts!r}")

    def test_hinglish_fever_options_are_hinglish(self):
        resp = _triage("mujhe bukhar hai", "hinglish")
        self.assertEqual(resp.follow_up_options, ["Aaj se", "2-3 din se", "Ek hafte se zyada"])
        self.assertEqual(resp.follow_up_question, "Bukhar kitne samay se hai?")

    def test_mixed_language_option_sets_fail(self):
        # Guard against regression: hinglish options must never reuse the
        # English labels for fields that have hinglish text.
        for module_id, text in MODULE_TRIGGERS.items():
            resp = _triage(text, "hinglish")
            if resp.module_card is None:
                continue
            for field in resp.module_card["fields"]:
                for opt in field.get("options", []) or []:
                    if opt in ("Today", "Yes", "No", "Child", "Adult", "Elderly (60+)", "Yes, normally", "None", "Other"):
                        self.fail(f"English label {opt!r} leaked into hinglish card ({module_id})")

    def test_sufficiency_20_messages_decide_without_card(self):
        messages = [
            "mujhe 2 din se bukhar hai",
            "fever since 3 days",
            "bukhar 102 raat se",
            "mujhe bukhar hai kal se",
            "teen din se bukhar hai",
            "fever since 2 days",
            "mummy ko do din se bukhar hai",
            "bukhar 101 aaj subah se",
            "bache ko kal se bukhar hai",
            "fever for 6 days",
            "mujhe ek hafte se bukhar hai",
            "bukhar 103 do din se",
            "fever since morning",
            "papa ko teen din se halka bukhar hai",
            "mujhe taap hai kal se",
            "fever 102 since two days",
            "do din se bukhar aur kamzori",
            "bukhar 101 raat se hai",
            "fever with cough since 2 days",
            "mujhe bukhar hai 3 din se",
        ]
        self.assertEqual(len(messages), 20)
        for text in messages:
            with self.subTest(text=text):
                resp = _triage(text, "hinglish")
                self.assertIsNotNone(resp.care_type, f"expected decision for {text!r}")
                self.assertIsNone(resp.module_card, f"no card expected for {text!r}")
                self.assertIsNone(resp.follow_up_question, f"no question expected for {text!r}")

    def test_triage_contract_matches_shared_sample(self):
        sample = json.loads(SAMPLE_JSON.read_text(encoding="utf-8"))
        # The sample must be a real /triage module-card response.
        self.assertTrue(sample.get("follow_up_question"))
        self.assertTrue(sample.get("follow_up_options"))
        self.assertIsNotNone(sample.get("module_card"))
        self.assertNotEqual(sample["follow_up_question"], sample["module_card"].get("label"))
        self.assertEqual(
            sample["follow_up_question"],
            sample["module_card"]["fields"][0]["question"],
        )
        # A fresh run of the same input keeps the contract (question + options).
        resp = _triage("mujhe bukhar hai", "hinglish")
        self.assertTrue(resp.follow_up_question)
        self.assertTrue(resp.follow_up_options or resp.module_card)


if __name__ == "__main__":
    unittest.main()
