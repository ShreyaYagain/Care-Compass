"""details.ml_features policy tests.

The explanation field must aggregate character n-grams back to whole words or
canonical symptom names ("fever", "headache"): each term shown once with its
weight, at most 5 terms, and never sub-word fragments. No feature term may be
shorter than 4 characters unless it is a lexicon word (canonical symptom name
or synonym from symptoms.yaml).
"""
import re
import unittest
import yaml

from app.config import settings
from app.schemas import TriageRequest, Location
from app.core.pipeline import run_triage_pipeline

LOC = Location(lat=28.54, lng=77.27)


def _lexicon_words() -> set[str]:
    with open(settings.SYMPTOMS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    words: set[str] = set()
    for canon, info in (data.get("symptoms_list") or {}).items():
        words.add(canon)
        words.update((info.get("synonyms") or []))
    return words


LEXICON = _lexicon_words()

SAMPLES = [
    "mujhe 2 din se bukhar hai",
    "I have a headache since morning",
    "papa ko do din se bukhar hai aur khansi bhi",
    "mujhe khansi hai ek hafte se",
    "sir dard hai kal se",
    "mujhe ulti ho rahi hai aaj subah se",
]


class TestMlFeatures(unittest.TestCase):

    def test_no_sub_word_fragments_short_terms_are_lexicon_only(self):
        for text in SAMPLES:
            with self.subTest(text=text):
                resp = run_triage_pipeline(
                    TriageRequest(user_input=text, language="auto", location=LOC)
                )
                features = (resp.details or {}).get("ml_features") or []
                if not features:
                    continue
                self.assertLessEqual(len(features), 5, f"more than 5 features for {text!r}")
                terms = [f.get("term", "") for f in features]
                # Each term shown exactly once.
                self.assertEqual(len(terms), len(set(terms)), f"duplicate terms for {text!r}: {terms}")
                for t in terms:
                    self.assertTrue(
                        len(t) >= 4 or t in LEXICON,
                        f"sub-word/short non-lexicon feature {t!r} for {text!r}",
                    )

    def test_features_aggregate_to_canonical_symptoms(self):
        resp = run_triage_pipeline(
            TriageRequest(user_input="mujhe 2 din se bukhar hai", language="auto", location=LOC)
        )
        features = (resp.details or {}).get("ml_features") or []
        terms = [f["term"] for f in features]
        self.assertIn("fever", terms)
        self.assertNotIn("fev", terms)
        self.assertNotIn("ver", terms)

        resp = run_triage_pipeline(
            TriageRequest(user_input="I have a headache since morning", language="auto", location=LOC)
        )
        features = (resp.details or {}).get("ml_features") or []
        terms = [f["term"] for f in features]
        self.assertIn("headache", terms)
        self.assertNotIn("ea", terms)
        self.assertNotIn("che", terms)

    def test_each_feature_has_weight(self):
        resp = run_triage_pipeline(
            TriageRequest(user_input="mujhe 2 din se bukhar hai", language="auto", location=LOC)
        )
        for f in (resp.details or {}).get("ml_features") or []:
            self.assertIn("term", f)
            self.assertIn("weight", f)
            self.assertIsInstance(f["weight"], float)


if __name__ == "__main__":
    unittest.main()
