"""Synthetic caregivers tests (demo 'other ways to see a doctor' list)."""
import unittest

from app.config import settings
from app.core.synthetic import load_synthetic_caregivers, synthetic_caregivers, secondary_doctor_options


class TestSyntheticCaregivers(unittest.TestCase):

    def test_file_has_30_rows_and_columns(self):
        rows = load_synthetic_caregivers()
        self.assertEqual(len(rows), 30)
        for r in rows:
            self.assertEqual(r["source"], "synthetic")
            self.assertIn(r["venue"], ("hospital", "home", "virtual"))
            self.assertTrue(r["facility_name"] or r["venue"] != "hospital")
            self.assertTrue(r["department"])

    def test_venues_breakdown(self):
        rows = load_synthetic_caregivers()
        self.assertEqual(sum(1 for r in rows if r["venue"] == "hospital"), 10)
        self.assertEqual(sum(1 for r in rows if r["venue"] == "home"), 10)
        self.assertEqual(sum(1 for r in rows if r["venue"] == "virtual"), 10)

    def test_flag_off_returns_empty(self):
        settings.USE_SYNTHETIC_CAREGIVERS = False
        self.assertEqual(synthetic_caregivers(), [])
        self.assertEqual(secondary_doctor_options("teleconsultation", "hinglish"), [])

    def test_flag_on_filters(self):
        settings.USE_SYNTHETIC_CAREGIVERS = True
        try:
            docs = synthetic_caregivers(venue="virtual")
            self.assertTrue(docs)
            self.assertTrue(all(d["venue"] == "virtual" for d in docs))
            ortho = synthetic_caregivers(department="orthopaedics")
            self.assertTrue(all(d["department"] == "orthopaedics" for d in ortho))
        finally:
            settings.USE_SYNTHETIC_CAREGIVERS = False

    def test_secondary_options_demo_only(self):
        settings.USE_SYNTHETIC_CAREGIVERS = True
        try:
            opts = secondary_doctor_options("teleconsultation", "hinglish")
            self.assertTrue(opts)
            self.assertTrue(all(o["demo"] for o in opts))
            # No new care_type string; only the official labels appear.
            for o in opts:
                self.assertIn("department", o)
        finally:
            settings.USE_SYNTHETIC_CAREGIVERS = False


if __name__ == "__main__":
    unittest.main()
