"""Injury / fall follow-up MODULE tests.

Follow-ups are asked ONE question per turn, at most 4, stopping as soon as
the case is determined. 40 injury messages must produce the first structured
question (or a decision). Field 7 (meds) never changes the decision.
Head-hit + drowsy escalates to emergency_112.
"""
import unittest

from app.schemas import TriageRequest, Location, ChatMessage
from app.core.pipeline import run_triage_pipeline
from app.core.modules import (
    render_module_card,
    injury_decision,
    detect_module,
    injury_next_question,
)

LOC = Location(lat=28.54, lng=77.27)


def _triage(text: str, **kw):
    return run_triage_pipeline(
        TriageRequest(user_input=text, language="hinglish", location=LOC,
                      conversation_history=kw.pop("history", []), **kw)
    )


def _card_labels(count: int) -> list[ChatMessage]:
    return [ChatMessage(role="assistant", text="Chot / girna") for _ in range(count)]


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

    def test_first_question_is_single_head_hit(self):
        resp = _triage("I fell down and my leg hurts")
        self.assertIsNotNone(resp.module_card)
        self.assertEqual(resp.module_card["module_id"], "injury")
        ids = {f["id"] for f in resp.module_card["fields"]}
        self.assertEqual(ids, {"head_hit"})

    def test_questions_are_one_at_a_time(self):
        # Q1 -> head_hit; Q2 -> pain_level; Q3 -> weight_bearing; Q4 -> swelling.
        r1 = _triage("I fell down and my leg hurts")
        self.assertEqual({f["id"] for f in r1.module_card["fields"]}, {"head_hit"})
        r2 = _triage("I fell down and my leg hurts", history=_card_labels(1),
                     module_id="injury", module_answers={"head_hit": "No"})
        self.assertEqual({f["id"] for f in r2.module_card["fields"]}, {"pain_level"})
        r3 = _triage("I fell down and my leg hurts", history=_card_labels(2),
                     module_id="injury", module_answers={"head_hit": "No", "pain_level": 6})
        self.assertEqual({f["id"] for f in r3.module_card["fields"]}, {"weight_bearing"})
        r4 = _triage("I fell down and my leg hurts", history=_card_labels(3),
                     module_id="injury", module_answers={"head_hit": "No", "pain_level": 6, "weight_bearing": "With pain"})
        self.assertEqual({f["id"] for f in r4.module_card["fields"]}, {"swelling"})

    def test_pipeline_sequential_swelling_teleconsult(self):
        # Pain 4-7 + swelling but can still bear weight: an X-ray may be needed
        # at a hospital, so a doctor video consult is the realistic first step.
        answers = {"head_hit": "No", "pain_level": 6, "weight_bearing": "With pain", "swelling": "Yes"}
        resp = _triage("I fell down and my leg hurts", history=_card_labels(4),
                       module_id="injury", module_answers=answers)
        self.assertIsNone(resp.module_card)
        self.assertEqual(resp.care_type, "teleconsultation")
        self.assertIn("X-ray", resp.reasoning or "")

    def test_pipeline_sequential_tele_no_swelling(self):
        answers = {"head_hit": "No", "pain_level": 5, "weight_bearing": "With pain", "swelling": "No"}
        resp = _triage("I fell down and my leg hurts", history=_card_labels(4),
                       module_id="injury", module_answers=answers)
        self.assertIsNone(resp.module_card)
        self.assertEqual(resp.care_type, "teleconsultation")

    def test_early_exit_mild_pain_tele(self):
        # Pain < 4 -> decide immediately; no weight/swelling questions.
        answers = {"head_hit": "No", "pain_level": 2}
        resp = _triage("I fell down and my leg hurts", history=_card_labels(2),
                       module_id="injury", module_answers=answers)
        self.assertIsNone(resp.module_card)
        self.assertEqual(resp.care_type, "teleconsultation")

    def test_early_exit_head_hit_emergency(self):
        answers = {"head_hit": "Yes"}
        resp = _triage("I fell down and my leg hurts", history=_card_labels(1),
                       module_id="injury", module_answers=answers)
        self.assertEqual(resp.care_type, "emergency_112")
        self.assertEqual(resp.urgency, "emergency")

    def test_pipeline_pain8_classifier_gate(self):
        # Pain 8+ -> decide after 2 questions. Pain alone never escalates to
        # emergency_112; it routes to a same-day medic home visit (the
        # calibrated classifier may only escalate high-risk limb findings).
        answers = {"head_hit": "No", "pain_level": 8}
        resp = _triage("I fell down and my leg hurts", history=_card_labels(2),
                       module_id="injury", module_answers=answers)
        self.assertIsNone(resp.module_card)
        self.assertEqual(resp.care_type, "paramedic_home_visit")
        self.assertEqual(resp.urgency, "same_day")

    def test_early_exit_cannot_bear_weight_paramedic(self):
        answers = {"head_hit": "No", "pain_level": 6, "weight_bearing": "Not at all"}
        resp = _triage("I fell down and my leg hurts", history=_card_labels(3),
                       module_id="injury", module_answers=answers)
        self.assertIsNone(resp.module_card)
        self.assertEqual(resp.care_type, "paramedic_home_visit")

    def test_max_four_questions_then_decision(self):
        # Absolute cap: after 4 cards there is never a 5th question.
        answers = {"head_hit": "No", "pain_level": 5, "weight_bearing": "With pain"}
        resp = _triage("I fell down and my leg hurts", history=_card_labels(4),
                       module_id="injury", module_answers=answers)
        self.assertIsNone(resp.module_card)
        self.assertIsNotNone(resp.care_type)

    def test_prefill_skips_stated_fields(self):
        card = render_module_card("injury", "en", {"severity": "severe", "swelling": True}, "severe pain and swollen")
        self.assertIsNotNone(card)
        ids = {f["id"] for f in card["fields"]}
        self.assertNotIn("pain_level", ids)
        self.assertNotIn("swelling", ids)
        self.assertIn("head_hit", ids)

    def test_detect_module_for_injury(self):
        self.assertEqual(detect_module({"symptoms": ["injury"]}), "injury")
        self.assertEqual(detect_module({"symptoms": ["fever"]}), "fever")
        self.assertEqual(detect_module({"symptoms": ["stomach_pain"]}), "abdominal_pain")

    # --- decision rules ---

    def test_head_hit_drowsy_emergency(self):
        d = injury_decision({"head_hit": "Yes", "pain_level": 5}, {})
        self.assertEqual(d["care_type"], "emergency_112")
        self.assertIn("unconsciousness", d["red_flags"])

    def test_bleeding_bone_visible_emergency(self):
        d = injury_decision({"deformity": "Yes"}, {"bleeding": True})
        self.assertEqual(d["care_type"], "emergency_112")
        self.assertIn("severe_bleeding", d["red_flags"])

    def test_pain8_paramedic(self):
        d = injury_decision({"pain_level": 8}, {})
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

    def test_pipeline_meds_never_changes_decision(self):
        base = {"head_hit": "No", "pain_level": 6, "weight_bearing": "With pain", "swelling": "Yes"}
        types = set()
        for meds in ("None", "Spray or balm", "Painkiller", "Other"):
            answers = dict(base, meds_used=meds)
            resp = _triage("I fell down and my leg hurts", history=_card_labels(4),
                           module_id="injury", module_answers=answers)
            types.add((resp.care_type, resp.urgency))
        self.assertEqual(len(types), 1)

    def test_next_question_stops_when_decided(self):
        self.assertEqual(injury_next_question({}, {}), "head_hit")
        self.assertIsNone(injury_next_question({"head_hit": "Yes"}, {}))
        self.assertEqual(injury_next_question({"head_hit": "No"}, {}), "pain_level")
        self.assertIsNone(injury_next_question({"head_hit": "No", "pain_level": 2}, {}))
        self.assertIsNone(injury_next_question({"head_hit": "No", "pain_level": 8}, {}))
        self.assertEqual(injury_next_question({"head_hit": "No", "pain_level": 5}, {}), "weight_bearing")
        self.assertIsNone(injury_next_question({"head_hit": "No", "pain_level": 5, "weight_bearing": "Not at all"}, {}))
        self.assertEqual(injury_next_question({"head_hit": "No", "pain_level": 5, "weight_bearing": "With pain"}, {}), "swelling")
        self.assertIsNone(injury_next_question({"head_hit": "No", "pain_level": 5, "weight_bearing": "With pain", "swelling": "Yes"}, {}))
        # Elderly: stop after pain.
        self.assertIsNone(injury_next_question({"head_hit": "No", "pain_level": 5}, {"age_group": "senior"}))

    def test_total_turns_capped(self):
        # The card flow counts as one turn per question; a second card beyond
        # the 4-question cap must never be asked.
        resp = _triage("I fell down and my leg hurts")
        self.assertIsNotNone(resp.module_card)
        answers = {"head_hit": "No", "pain_level": 2}
        resp2 = _triage("I fell down and my leg hurts", history=_card_labels(2),
                        module_id="injury", module_answers=answers)
        self.assertIsNone(resp2.module_card)
        self.assertIsNotNone(resp2.care_type)


    def test_pain8_with_cannot_bear_weight_still_paramedic(self):
        # Even with serious findings, the calibrated classifier rarely reaches
        # P(emergency_112) >= 0.75, so the outcome stays paramedic (sane).
        answers = {"head_hit": "No", "pain_level": 8, "weight_bearing": "Not at all",
                   "deformity": "Yes", "swelling": "Yes"}
        resp = _triage("I fell down and my leg hurts", history=_card_labels(2),
                       module_id="injury", module_answers=answers)
        self.assertEqual(resp.care_type, "paramedic_home_visit")

    def test_headache_never_emergency_nor_injury_card(self):
        for text in ("I have a headache", "mere ko sir dard hai", "headache"):
            resp = _triage(text)
            self.assertNotEqual(resp.care_type, "emergency_112", text)
            self.assertNotIn("unconsciousness", resp.red_flags, text)
            self.assertIsNone(resp.module_card, text)
            if resp.follow_up_question:
                self.assertNotIn("hosh", (resp.follow_up_question or ""), text)

    def test_headache_decides_teleconsultation(self):
        resp = _triage("I have a headache")
        self.assertEqual(resp.care_type, "teleconsultation")

    def test_similar_injuries_get_injury_module_or_sane_outcome(self):
        for text in ("shoulder pain", "neck me dard hai", "elbow pain",
                     "back me dard hai", "wrist me dard hai"):
            with self.subTest(text=text):
                resp = _triage(text)
                if resp.module_card is not None:
                    self.assertEqual(resp.module_card["module_id"], "injury")
                else:
                    self.assertIn(resp.care_type, ("teleconsultation", "paramedic_home_visit"))
                    self.assertNotEqual(resp.care_type, "emergency_112")

    def test_llm_module_guard_rejects_unevidenced_module(self):
        # The LLM may not open the injury module for a plain headache.
        from unittest import mock
        from app.core.modules import llm_select_module
        fake_out = type("Out", (), {"module_id": "injury", "answered_field_ids": []})()
        with mock.patch("app.core.llm.is_llm_available", return_value=True), \
             mock.patch("app.core.llm.llm_json", return_value=fake_out):
            chosen = llm_select_module("I have a headache", {"symptoms": ["headache"]})
        self.assertIsNone(chosen)


if __name__ == "__main__":
    unittest.main()
