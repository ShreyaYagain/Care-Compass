"""Explanation cleanliness tests.

Junk classifier n-gram fragments ("tin", "ting", "tes", "sub") must never
appear as symptoms or in the explanation. Every symptom name shown in an
explanation must be a canonical entry of symptoms.yaml, in the user's language.
"""
import unittest
import yaml
from pathlib import Path

from app.config import settings
from app.schemas import TriageRequest, Location
from app.core.pipeline import run_triage_pipeline
from app.core.intake import canonicalise_symptom, extract_slots
from app.core.explain import SYMPTOM_LABELS

LOC = Location(lat=28.54, lng=77.27)


def _yaml_symptoms() -> set[str]:
    data = yaml.safe_load(settings.SYMPTOMS_FILE.read_text(encoding="utf-8")) or {}
    return set((data.get("symptoms_list") or {}).keys())


def _triage(text: str, language: str = "hinglish", debug: bool = True):
    return run_triage_pipeline(
        TriageRequest(user_input=text, language=language, location=LOC, conversation_history=[]),
        debug=debug,
    )


class TestNoJunkSymptoms(unittest.TestCase):

    def test_tingling_hand_no_tin_ting(self):
        resp = _triage("tingling in my hand")
        slots = resp.debug["slots"]
        symptoms = slots.get("symptoms", [])
        self.assertNotIn("tin", symptoms)
        self.assertNotIn("ting", symptoms)
        self.assertNotIn("tingling", symptoms)
        if resp.reasoning:
            self.assertNotIn("tin", resp.reasoning.lower().split())
            self.assertNotIn("ting", resp.reasoning.lower().split())
            self.assertNotIn("because you mentioned tin", resp.reasoning.lower())

    def test_teen_din_bukhar_no_junk(self):
        resp = _triage("teen din se bukhar")
        slots = resp.debug["slots"]
        self.assertIn("fever", slots.get("symptoms", []))
        self.assertNotIn("tin", slots.get("symptoms", []))
        self.assertNotIn("ting", slots.get("symptoms", []))
        self.assertIsNotNone(resp.reasoning)
        self.assertNotIn("tin", resp.reasoning.lower().split())
        self.assertNotIn("ting", resp.reasoning.lower().split())
        # Canonical hinglish label for fever must appear.
        self.assertIn("bukhar", resp.reasoning.lower())

    def test_tin_ting_no_decision(self):
        # No valid symptom -> the one allowed follow-up question, NOT a
        # confident same-day decision.
        resp = _triage("tin ting")
        slots = resp.debug["slots"]
        self.assertEqual(slots.get("symptoms", []), [])
        self.assertIsNotNone(resp.follow_up_question)
        self.assertIsNone(resp.care_type)
        self.assertIsNone(resp.urgency)

    def test_canonicalise_rejects_junk(self):
        self.assertIsNone(canonicalise_symptom("tin"))
        self.assertIsNone(canonicalise_symptom("ting"))
        self.assertIsNone(canonicalise_symptom("tingling"))
        self.assertIsNone(canonicalise_symptom("tes"))
        self.assertIsNone(canonicalise_symptom("sub"))
        self.assertIsNone(canonicalise_symptom("garbledxyz"))

    def test_canonicalise_accepts_lexicon(self):
        self.assertEqual(canonicalise_symptom("fever"), "fever")
        self.assertEqual(canonicalise_symptom("bukhar"), "fever")
        self.assertEqual(canonicalise_symptom("chest pain"), "chest_pain")
        self.assertEqual(canonicalise_symptom("dizzy"), "dizziness")
        self.assertEqual(canonicalise_symptom("chakkar"), "dizziness")

    def test_all_extracted_symptoms_are_canonical(self):
        yaml_keys = _yaml_symptoms()
        inputs = [
            "tingling in my hand",
            "teen din se bukhar",
            "papa ko bukhar hai aur khansi",
            "ghabrahat ho rahi hai",
            "chakkar aa rahe hain",
            "seene me dard hai",
            "ghar pe injection lagwana hai",
            "sugar check karna hai",
            "pet me dard hai",
            "kamzori bahut hai",
        ]
        for text in inputs:
            with self.subTest(text=text):
                slots = extract_slots(text, [])
                for sym in slots.get("symptoms", []):
                    self.assertIn(sym, yaml_keys, f"non-canonical symptom {sym!r} for {text!r}")

    def test_explanation_symptom_labels_are_canonical(self):
        yaml_keys = _yaml_symptoms()
        for key in SYMPTOM_LABELS:
            self.assertIn(key, yaml_keys, f"SYMPTOM_LABELS key {key!r} missing from symptoms.yaml")

    def test_explanation_language_consistency(self):
        # English request -> English explanation; Hinglish -> Hinglish symptom names.
        resp_en = _triage("fever and cough since 2 days", language="en")
        self.assertIn("fever", resp_en.reasoning.lower())
        resp_hinglish = _triage("bukhar aur khansi do din se", language="hinglish")
        self.assertIn("bukhar", resp_hinglish.reasoning.lower())
        self.assertNotIn(" because you mentioned ", resp_hinglish.reasoning.lower())

    def test_no_because_without_symptoms(self):
        # Emergency path with no extracted symptoms must not claim a mention.
        resp = _triage("dad cant breath")
        self.assertEqual(resp.care_type, "emergency_112")
        self.assertIsNotNone(resp.reasoning)
        self.assertNotIn("because you mentioned", resp.reasoning.lower())


if __name__ == "__main__":
    unittest.main()
