"""Pregnancy risk layer tests.

40 cases: 20 positive (escalation happens), 10 negated (no escalation),
10 mild (pregnant + mild complaint -> at least same_day, never scheduled,
never a follow-up question).
"""
import unittest

from app.schemas import TriageRequest, Location
from app.core.pipeline import run_triage_pipeline
from app.core.pregnancy import detect_pregnancy

LOC = Location(lat=28.54, lng=77.27)


def _triage(text: str):
    return run_triage_pipeline(TriageRequest(user_input=text, language="hinglish", location=LOC, conversation_history=[]))


class TestPregnancyPositive(unittest.TestCase):
    """Danger signs in pregnancy escalate immediately (no question)."""

    def _assert_emergency(self, text: str, flag: str):
        resp = _triage(text)
        self.assertEqual(resp.care_type, "emergency_112", f"expected emergency_112 for: {text!r}")
        self.assertEqual(resp.urgency, "emergency")
        self.assertIsNone(resp.follow_up_question, f"no question allowed for: {text!r}")
        self.assertEqual(resp.matched_caregivers, [])
        if flag:
            self.assertIn(flag, resp.red_flags, f"expected red flag {flag} for: {text!r}")

    def _assert_same_day(self, text: str):
        resp = _triage(text)
        self.assertIsNone(resp.follow_up_question, f"no question allowed for: {text!r}")
        self.assertNotEqual(resp.urgency, "scheduled", f"must not be scheduled: {text!r}")
        self.assertNotEqual(resp.care_type, "lab_test_home", f"must not be a scheduled lab test: {text!r}")
        self.assertEqual(resp.urgency, "same_day")

    def test_01_self_pregnant_bleeding(self):
        self._assert_emergency("mai pregnant hu aur khoon aa raha hai", "severe_bleeding")

    def test_02_wife_pregnant_bleeding(self):
        self._assert_emergency("meri wife pregnant hai aur bleeding ho rahi hai", "severe_bleeding")

    def test_03_garbhvati_bleeding(self):
        self._assert_emergency("garbhvati hu, khoon nikal raha hai", "severe_bleeding")

    def test_04_english_pregnant_spotting(self):
        self._assert_emergency("I am pregnant and spotting", "severe_bleeding")

    def test_05_months_pregnant_bleeding(self):
        self._assert_emergency("3 months pregnant and blood loss", "severe_bleeding")

    def test_06_pregnant_fits(self):
        self._assert_emergency("pregnant hu aur fits aa rahe hain", "seizure")

    def test_07_expecting_convulsions(self):
        self._assert_emergency("expecting, daura pad raha hai", "seizure")

    def test_08_pregnant_unconscious(self):
        self._assert_emergency("pregnant hu aur behosh ho gayi", "unconsciousness")

    def test_09_garbhvati_behoshi(self):
        self._assert_emergency("garbhvati hu, hosh nahi hai", "unconsciousness")

    def test_10_pregnant_severe_headache_blurred_vision(self):
        self._assert_emergency("pregnant, severe headache and blurred vision", "stroke_symptoms")

    def test_11_garbhvati_tez_sar_dard_dhundhla(self):
        self._assert_emergency("garbhvati hu, tez sar dard aur dhundhla dikh raha hai", "stroke_symptoms")

    def test_12_pregnant_chest_pain(self):
        self._assert_emergency("pregnant hu, chest pain ho raha hai", "chest_pain")

    def test_13_pregnant_cant_breathe(self):
        self._assert_emergency("pregnant hu, saans nahi aa rahi", "breathlessness")

    def test_14_bahu_pregnant_severe_abdominal_pain(self):
        # No official flag maps; escalates through the pregnancy risk modifier.
        resp = _triage("bahu pregnant hai, pet me bahut tez dard hai")
        self.assertEqual(resp.care_type, "emergency_112")
        self.assertEqual(resp.urgency, "emergency")
        self.assertIsNone(resp.follow_up_question)

    def test_15_pregnant_water_broke(self):
        self._assert_same_day("pregnant hu aur paani toot gaya")

    def test_16_pregnant_baby_not_moving(self):
        self._assert_same_day("pregnant hu, bacha hil nahi raha hai")

    def test_17_pregnant_labour_pains(self):
        self._assert_same_day("pregnant hu, labour pain shuru ho gaya")

    def test_18_pregnant_severe_fever(self):
        # "tez bukhar" is a severe fever in pregnancy: emergency via the risk
        # modifier (no official flag exists for this combination).
        resp = _triage("garbhvati hu, tez bukhar hai")
        self.assertEqual(resp.care_type, "emergency_112")
        self.assertEqual(resp.urgency, "emergency")
        self.assertIsNone(resp.follow_up_question)

    def test_19_wife_expecting_khoon(self):
        self._assert_emergency("wife is expecting, khoon aa raha hai", "severe_bleeding")

    def test_20_pregnancy_week_bleeding(self):
        self._assert_emergency("8 weeks pregnant, heavy bleeding", "severe_bleeding")


class TestPregnancyNegated(unittest.TestCase):
    """Negated pregnancy / negated danger signs must NOT escalate."""

    def _assert_not_emergency(self, text: str):
        resp = _triage(text)
        self.assertNotEqual(resp.care_type, "emergency_112", f"must not be emergency for: {text!r}")

    def test_n01_not_pregnant(self):
        self._assert_not_emergency("mai pregnant nahi hu")
        self.assertFalse(detect_pregnancy("mai pregnant nahi hu"))

    def test_n02_wife_not_pregnant(self):
        self._assert_not_emergency("meri wife pregnant nahi hai, sirf bukhar hai")

    def test_n03_pregnant_no_bleeding(self):
        self._assert_not_emergency("pregnant hu lekin bleeding nahi ho rahi")

    def test_n04_garbhvati_khoon_nahi(self):
        self._assert_not_emergency("garbhvati hu, khoon nahi aa raha")

    def test_n05_pregnant_no_bleeding_en(self):
        self._assert_not_emergency("I am pregnant, no bleeding")

    def test_n06_pregnant_breathing_fine(self):
        self._assert_not_emergency("pregnant hu, saans me koi dikkat nahi")

    def test_n07_not_pregnant_khoon(self):
        self._assert_not_emergency("mai pregnant nahi hu, khoon aa raha hai")
        self.assertFalse(detect_pregnancy("mai pregnant nahi hu, khoon aa raha hai"))

    def test_n08_garbhavati_nahi(self):
        self._assert_not_emergency("garbhavati nahi hu")
        self.assertFalse(detect_pregnancy("garbhavati nahi hu"))

    def test_n09_pregnancy_nahi_khansi(self):
        self._assert_not_emergency("pregnancy nahi hai, sirf khansi hai")

    def test_n10_pregnant_mild_headache_no_vision(self):
        # Headache WITHOUT blurred vision/swelling is not stroke_symptoms.
        resp = _triage("pregnant hu, halka sar dard hai")
        self.assertNotEqual(resp.care_type, "emergency_112")
        self.assertNotIn("stroke_symptoms", resp.red_flags)


class TestPregnancyMild(unittest.TestCase):
    """Pregnant + mild complaint: same_day at minimum, no question, no scheduled."""

    MILD_INPUTS = [
        "pregnant hu, halka bukhar hai",
        "pregnant hu, khansi hai",
        "garbhvati hu, sar dard hai",
        "pregnant, ulti ho rahi hai",
        "pregnant hu, pet me halka dard hai",
        "I am pregnant, feeling tired",
        "pregnant, body pain",
        "garbhvati hu, bhookh nahi lagti",
        "pregnant hu, neend nahi aa rahi",
        "expecting, mild nausea",
    ]

    def test_mild_pregnancy_cases(self):
        for text in self.MILD_INPUTS:
            with self.subTest(text=text):
                resp = _triage(text)
                self.assertIsNone(resp.follow_up_question, f"no question expected for: {text!r}")
                self.assertIsNotNone(resp.care_type)
                self.assertNotEqual(resp.urgency, "scheduled", f"must not be scheduled: {text!r}")
                self.assertNotEqual(resp.care_type, "lab_test_home", f"must not be a scheduled lab test: {text!r}")
                self.assertEqual(resp.urgency, "same_day")


if __name__ == "__main__":
    unittest.main()
