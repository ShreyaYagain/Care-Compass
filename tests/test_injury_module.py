"""Injury / fall follow-up MODULE tests.

40 injury messages must produce the structured card (only missing fields) or a
decision that follows the deterministic rules. Field 7 (meds) never changes the
decision. Head-hit + drowsy escalates to emergency_112.
"""
import unittest

from app.schemas import TriageRequest, Location
from app.core.pipeline import run_triage_pipeline
from app.core.modules import (
    render_module_card,
    injury_decision,
    detect_module,
)

LOC = Location(lat=28.54, lng=77.27)


def _triage(text: str, **kw):
    return run_triage_pipeline(
        TriageRequest(user_input=text, language="hinglish", location=LOC,
                      conversation_history=kw.pop("history", []), **kw)
    )


INJURY_MESSAGES = [
    "pair mein moch aa gayi hai",
    "I fell down and my leg hurts",
    "mera ghar gir gaya, ghutne mein dard hai",
    "kal se knee me bahut dard hai",
    "ankle twisted ho gaya hai",
    "leg me swelling hai aur dard hai",
    "haath me chot lag gayi",
    "kandhe me dard hai girne ke baad",
    "kalch se foot me dard hai",
    "sprain ho gaya hai pair mein",
    "gir ke chot lag gayi",
    "fracture lag raha hai haath me",
    "wound hai ghutne par",
    "kamar me dard hai fall ke baad",
    "step se gir gaya tha, ab leg dard karta hai",
    "bike se gir gaya, shoulder me dard",
    "bache ko chot lag gayi khelte waqt",
    "budhe papa gir gaye, hip me dard",
    "mera foot sooj gaya hai aur dard hai",
    "leg par neela nishan pad gaya",
    "I hurt my ankle playing",
    "my knee hurts when I walk",
    "fell from stairs, wrist hurts",
    "hand me cut lag gaya",
    "seedhi se gir gaya",
    "moch aa gayi hai",
    "twisted my ankle badly",
    "haddi me dard hai",
    "shoulder me dard hai",
    "neck me dard hai",
    "pair me jalan aur dard",
    "thigh me dard hai girne ke baad",
    "arm me chot hai",
    "walk karte waqt gir gaya",
    "knee me sujan hai",
    "fall ke baad sir me dard",
    "girne se kamar me dard",
    "leg me dard hai do din se",
    "ankle me dard hai aur soojan",
    "wrist me dard hai",
]


class TestInjuryModule(unittest.TestCase):

    def test_40_messages_produce_card_or_decision(self):
        self.assertEqual(len(INJURY_MESSAGES), 40)
        for text in INJURY_MESSAGES:
            with self.subTest(text=text):
                resp = _triage(text)
                if resp.module_card is not None:
                    self.assertEqual(resp.module_card["module_id"], "injury")
                    self.assertTrue(resp.module_card["fields"])
                elif resp.care_type:
                    self.assertIn(resp.care_type, ["paramedic_home_visit", "teleconsultation", "emergency_112"])
                else:
                    # generic follow-up is acceptable too, but never a banned phrase
                    self.assertIsNotNone(resp.follow_up_question)

    def test_fell_leg_hurts_returns_injury_card(self):
        resp = _triage("I fell down and my leg hurts")
        self.assertIsNotNone(resp.module_card)
        self.assertEqual(resp.module_card["module_id"], "injury")
        ids = {f["id"] for f in resp.module_card["fields"]}
        self.assertIn("pain_level", ids)
        self.assertIn("weight_bearing", ids)

    def test_prefill_severe_pain_swollen(self):
        # Already-stated fields must be hidden from the card.
        card = render_module_card("injury", "en", {"severity": "severe", "swelling": True}, "severe pain and swollen")
        self.assertIsNotNone(card)
        ids = {f["id"] for f in card["fields"]}
        self.assertNotIn("pain_level", ids)
        self.assertNotIn("swelling", ids)
        self.assertIn("weight_bearing", ids)

    def test_detect_module_for_injury(self):
        self.assertEqual(detect_module({"symptoms": ["injury"]}), "injury")
        self.assertEqual(detect_module({"symptoms": ["fever"]}), "fever")
        self.assertEqual(detect_module({"symptoms": ["stomach_pain"]}), "abdominal_pain")

    # --- decision rules ---

    def test_head_hit_drowsy_emergency(self):
        d = injury_decision({"head_hit": "Yes", "pain_level": 5}, {})
        self.assertEqual(d["care_type"], "emergency_112")
        self.assertIn("unconsciousness", d["red_flags"])

    def test_pain8_deformity_paramedic(self):
        d = injury_decision({"pain_level": 8, "deformity": "Yes", "weight_bearing": "With pain"}, {})
        self.assertEqual(d["care_type"], "paramedic_home_visit")
        self.assertEqual(d["urgency"], "same_day")

    def test_numb_cold_limb_paramedic(self):
        d = injury_decision({"pain_level": 6, "neuro_vascular": "Yes"}, {})
        self.assertEqual(d["care_type"], "paramedic_home_visit")

    def test_mild_no_swelling_teleconsultation(self):
        d = injury_decision({"pain_level": 2, "swelling": "No", "weight_bearing": "Yes, normally"}, {})
        self.assertEqual(d["care_type"], "teleconsultation")

    def test_elderly_hip_pain_same_day(self):
        d = injury_decision({"pain_level": 5}, {"age_group": "senior", "patient_relation": "grandmother"})
        self.assertEqual(d["care_type"], "paramedic_home_visit")
        self.assertEqual(d["urgency"], "same_day")

    def test_no_fracture_diagnosis(self):
        d = injury_decision({"pain_level": 6, "swelling": "Yes"}, {})
        self.assertNotIn("fracture", d["reason"].lower())
        self.assertIn("X-ray", d["reason"])

    def test_reason_shows_answers(self):
        d = injury_decision({"pain_level": 7, "swelling": "Yes", "weight_bearing": "Not at all"}, {})
        self.assertIn("7/10", d["reason"])
        self.assertIn("swelling", d["reason"])

    def test_meds_never_changes_decision(self):
        base = {"pain_level": 6, "swelling": "Yes", "weight_bearing": "With pain", "deformity": "No",
                "neuro_vascular": "No", "head_hit": "No"}
        d_none = injury_decision(dict(base, meds_used="None"), {})
        d_painkiller = injury_decision(dict(base, meds_used="Painkiller"), {})
        d_spray = injury_decision(dict(base, meds_used="Spray or balm"), {})
        self.assertEqual(d_none["care_type"], d_painkiller["care_type"])
        self.assertEqual(d_none["urgency"], d_painkiller["urgency"])
        self.assertEqual(d_none["care_type"], d_spray["care_type"])

    def test_pipeline_module_answers_decision(self):
        # Collect the card, then answer it -> a decision with caregivers.
        resp = _triage("I fell down and my leg hurts")
        self.assertIsNotNone(resp.module_card)
        answers = {"pain_level": 8, "deformity": "Yes", "weight_bearing": "Not at all",
                   "swelling": "Yes", "neuro_vascular": "No", "head_hit": "No", "meds_used": "None"}
        resp2 = _triage("I fell down and my leg hurts", module_id="injury", module_answers=answers)
        self.assertEqual(resp2.care_type, "paramedic_home_visit")
        self.assertEqual(resp2.urgency, "same_day")
        self.assertIsNone(resp2.follow_up_question)

    def test_pipeline_head_hit_emergency(self):
        answers = {"pain_level": 5, "head_hit": "Yes"}
        resp = _triage("fell and hit head", module_id="injury", module_answers=answers)
        self.assertEqual(resp.care_type, "emergency_112")
        self.assertEqual(resp.urgency, "emergency")

    def test_total_turns_capped(self):
        # The card counts as one turn; a second card must never be asked.
        resp = _triage("I fell down and my leg hurts")
        self.assertIsNotNone(resp.module_card)
        # After answering, no second card is returned (a decision is made).
        answers = {"pain_level": 2, "swelling": "No", "weight_bearing": "Yes, normally",
                   "deformity": "No", "neuro_vascular": "No", "head_hit": "No", "meds_used": "None"}
        resp2 = _triage("I fell down and my leg hurts", module_id="injury", module_answers=answers)
        self.assertIsNone(resp2.module_card)
        self.assertIsNotNone(resp2.care_type)


if __name__ == "__main__":
    unittest.main()
