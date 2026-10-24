"""Fairness guard test — TriageBench language consistency.

Fails if the language consistency rate (same care_type AND urgency across the
English / Hindi / Hinglish variants of the identical vignette) drops below the
value recorded in docs/FAIRNESS_REPORT.md.
"""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ml.external.triagebench_eval import build_variants, _run, CARE_LEVEL

# Recorded in docs/FAIRNESS_REPORT.md (language consistency must be 100%).
RECORDED_LANGUAGE_CONSISTENCY = 1.0


class TestFairnessLanguageConsistency(unittest.TestCase):

    def test_language_consistency_at_or_above_recorded(self):
        vignettes = build_variants()
        if not vignettes or "language" not in vignettes:
            self.skipTest("TriageBench data not available (run ml/external/fetch_external.py)")

        variants = vignettes["language"]
        outcomes = [_run(v["text"], v["language"]) for v in variants]
        keys = {(o["care_type"], o["urgency"]) for o in outcomes}
        rate = 1.0 if len(keys) == 1 else 0.0

        self.assertGreaterEqual(
            rate,
            RECORDED_LANGUAGE_CONSISTENCY,
            f"Language consistency dropped below recorded value "
            f"({rate} < {RECORDED_LANGUAGE_CONSISTENCY}). Outcomes: {outcomes}",
        )

    def test_no_language_under_triage(self):
        vignettes = build_variants()
        if not vignettes or "language" not in vignettes:
            self.skipTest("TriageBench data not available")

        variants = vignettes["language"]
        levels = {v["label"]: CARE_LEVEL[_run(v["text"], v["language"])["care_type"]] for v in variants}
        en = levels.get("English")
        if en is None:
            self.skipTest("English variant missing")
        for lang in ("Hindi", "Hinglish"):
            if lang in levels:
                self.assertGreaterEqual(
                    levels[lang],
                    en,
                    f"{lang} got a lower care level ({levels[lang]}) than English ({en}): under-triage",
                )


if __name__ == "__main__":
    unittest.main()
