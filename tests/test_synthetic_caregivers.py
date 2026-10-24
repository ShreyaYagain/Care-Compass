"""Synthetic caregivers tests (demo 'other ways to see a doctor' list)."""
import unittest

from app.config import settings
from app.core.synthetic import (
    load_synthetic_caregivers,
    synthetic_caregivers,
    secondary_doctor_options,
    adjust_by_doctor_availability,
)
from app.core.matching import rank_caregivers
from app.schemas import Location

LOC = Location(lat=28.54, lng=77.27)


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

    # --- synthetic roster in care-type matching ---

    def test_matching_flag_off_is_official_only(self):
        settings.USE_SYNTHETIC_CAREGIVERS = False
        matched = rank_caregivers("paramedic_home_visit", "same_day", user_location=LOC, user_language="hinglish", limit=10)
        self.assertTrue(matched)
        for m in matched:
            self.assertIsNone(m.venue)
            self.assertIsNone(m.department)
            self.assertIsNone(m.facility_name)

    def test_matching_paramedic_includes_home_consult_doctors(self):
        settings.USE_SYNTHETIC_CAREGIVERS = True
        try:
            matched = rank_caregivers("paramedic_home_visit", "same_day", user_location=LOC, user_language="hinglish", limit=10)
            home_docs = [m for m in matched if m.venue == "home"]
            self.assertTrue(home_docs, "home-consult doctors should join medic matching")
            for m in home_docs:
                self.assertEqual(m.role, "doctor")
                self.assertIn(m.department, ("orthopaedics", "general_medicine", "paediatrics", "gynaecology"))
            # official medics still present
            self.assertTrue(any(m.venue is None for m in matched))
        finally:
            settings.USE_SYNTHETIC_CAREGIVERS = False

    def test_matching_teleconsultation_includes_virtual_doctors(self):
        settings.USE_SYNTHETIC_CAREGIVERS = True
        try:
            matched = rank_caregivers("teleconsultation", "same_day", user_location=LOC, user_language="hinglish", limit=10)
            virtual = [m for m in matched if m.venue == "virtual"]
            self.assertTrue(virtual, "virtual doctors should join teleconsultation matching")
            for m in virtual:
                self.assertEqual(m.role, "doctor")
                self.assertIn("video consult", m.reason)
        finally:
            settings.USE_SYNTHETIC_CAREGIVERS = False

    def test_matching_hospital_opd_never_matched(self):
        settings.USE_SYNTHETIC_CAREGIVERS = True
        try:
            for care_type in ("paramedic_home_visit", "home_nursing", "teleconsultation", "lab_test_home"):
                matched = rank_caregivers(care_type, "same_day", user_location=LOC, user_language="hinglish", limit=20)
                self.assertFalse(any(m.venue == "hospital" for m in matched), care_type)
        finally:
            settings.USE_SYNTHETIC_CAREGIVERS = False

    def test_availability_adjustment_flag_off_noop(self):
        settings.USE_SYNTHETIC_CAREGIVERS = False
        ct, note = adjust_by_doctor_availability("paramedic_home_visit", "same_day", LOC, "hinglish")
        self.assertEqual(ct, "paramedic_home_visit")
        self.assertEqual(note, "")

    def test_availability_adjustment_home_full_virtual_full(self):
        settings.USE_SYNTHETIC_CAREGIVERS = True
        try:
            from app.core import synthetic as S
            orig_home = S.home_consult_available
            orig_virtual = S.virtual_consult_available
            S.home_consult_available = lambda *a, **k: True
            S.virtual_consult_available = lambda *a, **k: True
            try:
                ct, note = adjust_by_doctor_availability("paramedic_home_visit", "same_day", LOC, "hinglish")
                self.assertEqual(ct, "paramedic_home_visit")
            finally:
                S.home_consult_available = orig_home
                S.virtual_consult_available = orig_virtual
        finally:
            settings.USE_SYNTHETIC_CAREGIVERS = False

    def test_availability_adjustment_home_empty_virtual_full(self):
        settings.USE_SYNTHETIC_CAREGIVERS = True
        try:
            from app.core import synthetic as S
            orig_home = S.home_consult_available
            orig_virtual = S.virtual_consult_available
            S.home_consult_available = lambda *a, **k: False
            S.virtual_consult_available = lambda *a, **k: True
            try:
                ct, note = adjust_by_doctor_availability("paramedic_home_visit", "same_day", LOC, "hinglish")
                self.assertEqual(ct, "teleconsultation")
                self.assertTrue(note)
            finally:
                S.home_consult_available = orig_home
                S.virtual_consult_available = orig_virtual
        finally:
            settings.USE_SYNTHETIC_CAREGIVERS = False

    def test_store_resolves_synthetic_caregiver(self):
        settings.USE_SYNTHETIC_CAREGIVERS = True
        try:
            from app.db import store
            cg = store.get_caregiver("SYN_015")
            self.assertIsNotNone(cg)
            self.assertEqual(cg["name"], "Nikhil Pillai")
            self.assertEqual(cg.get("venue"), "home")
            self.assertEqual(cg.get("department"), "general_medicine")
            self.assertTrue(cg.get("free_from"))
        finally:
            settings.USE_SYNTHETIC_CAREGIVERS = False


if __name__ == "__main__":
    unittest.main()
