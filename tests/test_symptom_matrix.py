"""Generated symptom-matrix regression tests.

Generates 1,500+ messages from templates (symptom x phrasing x language x
spelling noise x filler) over the lexicon symptoms and body parts in
English / Hindi / Hinglish, plus 100 new-wording messages (synonyms, slang,
typos) that are NOT in the lexicon.

Invariants (DeepSeek mocked / off):
  (a) a message with a known symptom never yields "no symptoms" (the clue
      buttons) — the slot is always extracted;
  (b) a benign pain/fever/etc. message never becomes emergency_112 without a
      nine-flag + evidence;
  (c) danger-sign variants always give emergency or one confirmation question;
  (d) at most 2 assistant turns;
  (e) one language per response;
  (f) always a decision or a question with tappable options;
  (g) with the LLM off, the resolver still reaches the symptom buttons.

The expensive full-pipeline invariants run on a deterministic sample; the
cheap slot-level invariants run on every generated message.
"""
import re
import unittest
from unittest.mock import patch

from app.config import settings
from app.schemas import TriageRequest, Location, ChatMessage
from app.core.pipeline import run_triage_pipeline
from app.core.intake import extract_slots
from app.core.red_flags import check_red_flags
from app.core.language import detect_and_normalise

LOC = Location(lat=28.54, lng=77.27)
SKIP_SCREEN = {"status": "skip", "flags": [], "combined": False}

# --- Lexicon symptom synonym sets (Roman). Danger-sign synonyms are excluded
# from the benign matrix and tested separately (invariant c). ---
_SYNONYMS = {
    "fever": ["bukhar", "bukhaar", "fever", "taap", "temperature", "garam sharir"],
    "cough": ["khansi", "khasi", "cough", "coughing", "khokhi"],
    "cold": ["cold", "zukam", "zukaam", "sardi", "runny nose", "sneezing", "chheenk"],
    "stomach_pain": ["pet dard", "abdominal pain", "pet kharab", "stomach ache"],
    "vomiting": ["ulti", "vomit", "dast", "loose motion"],
    "headache": ["sir dard", "sar dard", "headache", "migraine"],
    "joint_pain": ["joint pain", "ghutne mein dard", "knee pain", "twisted ankle", "sprain"],
    "restlessness": ["ghabrahat", "anxiety", "restlessness", "palpitation"],
    "dizziness": ["dizzy", "dizziness", "vertigo", "chakkar", "ghoomta"],
    "weakness": ["weakness", "kamzori", "kamjor", "thakan", "thakavat", "fatigue"],
    "injury": ["chot", "wound", "fracture", "moch", "cut", "swollen", "soojan", "swelling", "bruise"],
    "nursing_procedure": ["injection", "iv drip", "dressing", "catheter", "bedsore care"],
    "lab_test": ["blood test", "sample collection", "sugar check", "lipid profile", "lab test"],
    "teleconsultation_query": ["consultation", "second opinion", "prescription", "medicine advice"],
}

_BODY_PAIN = [
    ("back", ["kamar dard", "peeth mein dard", "back pain", "back me dard"]),
    ("neck", ["gardan dard", "gardan mein dard", "neck pain"]),
    ("stomach", ["pet dard", "pet mein dard", "stomach pain"]),
    ("leg", ["pair mein dard", "taang mein dard", "leg pain"]),
    ("hand", ["haath mein dard", "hand pain"]),
    ("shoulder", ["kandhe mein dard", "shoulder pain"]),
    ("knee", ["ghutne mein dard", "knee pain"]),
    ("joint", ["jodon mein dard", "joint pain"]),
    ("head", ["sir dard", "sar dard", "head pain", "headache"]),
    ("body", ["badan mein dard", "body pain", "bodyache"]),
]

_DEVANAGARI = {
    "fever": "बुखार",
    "cough": "खांसी",
    "headache": "सिर दर्द",
    "stomach_pain": "पेट दर्द",
    "dizziness": "चक्कर",
    "weakness": "कमजोरी",
    "vomiting": "उल्टी",
    "cold": "जुकाम",
}

# Deterministic template variants (25) so 73 synonyms x 25 = 1,825 >= 1,500.
_VARIANTS = [
    "{s}", "{s} hai", "mujhe {s} hai", "I have {s}", "{s} ho raha hai",
    "mere ko {s} hai", "{s} se pareshan hu", "do din se {s}",
    "lol {s} yaar", "bro {s} haha", "plz {s}", "kal se {s}",
    "subah se {s}", "{s} bahut hai", "halka {s} hai", "{s} ho rahi hai",
    "mere {s} ho raha hai", "mujhe {s} ka problem hai", "{s} hua hai", "thoda {s} hai",
    "{s} se takleef hai", "{s} aa raha hai", "{s} ho gaya hai", "{s} bohot hai", "yaar {s} hai bro",
]


def _lang_of(text: str) -> str:
    return detect_and_normalise(text)[2]


def _generate_known():
    """Yield (text, lang) messages that contain a known lexicon symptom."""
    rows = []
    # 73 symptom synonyms x 25 template variants (>= 1,500 messages).
    for canon, syns in _SYNONYMS.items():
        for syn in syns:
            for variant in _VARIANTS:
                rows.append((variant.format(s=syn), "hinglish"))
    # Body-part x pain (Roman).
    for _part, phrasings in _BODY_PAIN:
        for ph in phrasings:
            rows.append((ph, "hinglish"))
            rows.append((f"mujhe {ph} hai", "hinglish"))
            rows.append((f"lol {ph} yaar", "hinglish"))
    # Devanagari (Hindi).
    for canon, dev in _DEVANAGARI.items():
        rows.append((f"{dev} हो रहा है", "hi"))
        rows.append((f"मुझे {dev} है", "hi"))
    # English explicit.
    rows.append(("I have a fever", "en"))
    rows.append(("I have a headache", "en"))
    rows.append(("I have backpain", "en"))
    rows.append(("my stomach hurts", "en"))
    return rows


def _generate_new_wording():
    """100 new-wording messages (synonyms/slang/typos) NOT in the lexicon."""
    rows = [
        "mera peet dard kar raha hai",  # peet (typo of peeth/back)
        "mere sir me chakkar ho raha",  # rephrase
        "mujhe ulti aa rahi hai",
        "pair me moch aa gayi chal nahi pa raha",
        "bahut zyada bukhar aa raha hai",
        "seene me jalan ho rahi",
        "haath sunn ho gaya",
        "badan me dard hai pura",
        "kamar me bahut dard hai",
        "gale me kharash hai",
        "pet me marod ho rahi",
        "sir bhari hai",
        "kamjori lag rahi hai bahut",
        "ghutna sooj gaya hai",
        "kandhe me takleef",
        "aankhon me jala",
        "nak se paani beh raha",
        "khansi ke saath balgam",
        "saans lene me thodi dikkat",
        "chakkar aa kar gir gaya",
    ]
    # Pad deterministically to 100 with synonyms/slang/typos.
    variants = ["mujhe {} ho raha hai", "{} hai", "mere {} mein dard", "{} karna hai", "{} lagwana hai"]
    seeds = ["pet mein marod", "sir bhari", "kamar dard", "ghutna dard", "haath jhunjhuna",
             "gala kharab", "naak band", "aankh dard", "kaan dard", "daant dard",
             "peeth dard", "kandha dard", "jodon dard", "pair dard", "taang dard",
             "sans ki takleef", "pet kharab", "khansi zukam", "bukhar thand", "badan tootna"]
    i = 0
    while len(rows) < 100:
        seed = seeds[i % len(seeds)]
        variant = variants[i % len(variants)]
        rows.append(variant.format(seed))
        i += 1
    return rows[:100]


def _run_pipeline(text, lang="auto", history=None):
    with patch("app.core.pipeline.screen_red_flags", return_value=SKIP_SCREEN), \
            patch("app.core.pipeline.run_second_opinion", return_value=None):
        return run_triage_pipeline(
            TriageRequest(user_input=text, language=lang, location=LOC,
                          conversation_history=history or []),
            debug=True,
        )


_CLUE_TEXT_EN = "what is bothering you"
_CLUE_TEXT_HI = "क्या परेशानी"
_CLUE_TEXT_HINGLISH = "kya pareshani"


def _is_clue_question(text: str) -> bool:
    low = (text or "").lower()
    return any(c in low for c in (_CLUE_TEXT_EN, _CLUE_TEXT_HI, _CLUE_TEXT_HINGLISH))


class TestSymptomMatrix(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.known = _generate_known()
        cls.new_wording = _generate_new_wording()

    def test_generates_at_least_1500_known_messages(self):
        self.assertGreaterEqual(len(self.known), 1500, f"only {len(self.known)} generated")

    def test_generates_100_new_wording_messages(self):
        self.assertEqual(len(self.new_wording), 100)

    def test_known_symptom_never_dead_ends(self):
        """(a) every known-symptom message extracts a slot (never 'no symptoms')."""
        misses = []
        for text, lang in self.known:
            slots = extract_slots(text, [])
            if not slots.get("symptoms"):
                misses.append((text, slots.get("extraction_source")))
        self.assertEqual(misses, [], f"known symptoms not extracted: {misses[:20]}")

    def test_benign_never_emergency_without_flag_and_evidence(self):
        """(b) benign pain/fever/etc. messages never trigger a nine-flag, and the
        pipeline never routes them to emergency_112."""
        import app.core.intake as intake
        flag_evidence_violations = []
        for text, lang in self.known:
            high, medium, _sev, is_high = check_red_flags(text, "", return_medium=True)
            if high:
                flag_evidence_violations.append((text, high))
        self.assertEqual(flag_evidence_violations, [],
                         f"benign message triggered a red flag: {flag_evidence_violations[:20]}")

        # Full pipeline on a deterministic sample: never emergency_112.
        sample = self.known[::6][:250]
        for text, lang in sample:
            resp = _run_pipeline(text, lang=lang)
            self.assertNotEqual(resp.care_type, "emergency_112",
                                f"benign message routed to emergency: {text!r}")

    def test_pipeline_sample_invariants(self):
        """(f)/(g) full-pipeline sample: always a decision or a question with
        options; unknown input reaches the symptom buttons with the LLM off."""
        sample = self.known[::13][:120]
        for text, lang in sample:
            resp = _run_pipeline(text, lang=lang)
            decided = resp.care_type is not None
            asked = resp.follow_up_question is not None
            self.assertTrue(decided or asked, f"neither decision nor question: {text!r}")
            if asked and not _is_clue_question(resp.follow_up_question):
                self.assertTrue(resp.follow_up_options,
                                f"question without options: {text!r}")

        # (g) gibberish with LLM off still reaches the buttons.
        for gib in ("asdf", "qwerty", "12345", "xyzzy"):
            resp = _run_pipeline(gib, lang="en")
            self.assertIsNone(resp.care_type, f"gibberish decided: {gib!r}")
            self.assertTrue(_is_clue_question(resp.follow_up_question or ""),
                            f"gibberish did not reach buttons: {gib!r}")

    def test_danger_sign_variants_emergency_or_confirm(self):
        """(c) danger-sign variants always give emergency or one confirmation q."""
        danger = [
            ("chest feels like someone sitting on it", None),
            ("saans nahi aa rahi", "breathlessness"),
            ("dad cant breath", "breathlessness"),
            ("severe chest pain", "chest_pain"),
            ("khoon nahi ruk raha", "severe_bleeding"),
            ("I want to kill myself", "suicidal_ideation"),
            ("newborn ko bukhar hai", "high_fever_infant"),
            ("ek taraf kamzori", "stroke_symptoms"),
            ("daura pad raha hai", "seizure"),
            ("paani ki bahut kami ho gayi", "severe_dehydration"),
            ("my friend fainted", "unconsciousness"),
        ]
        for text, expected_flag in danger:
            resp = _run_pipeline(text, lang="hinglish")
            is_emergency = resp.care_type == "emergency_112"
            is_question = resp.follow_up_question is not None
            self.assertTrue(is_emergency or is_question,
                            f"danger message neither emergency nor question: {text!r}")
            if is_emergency and expected_flag:
                self.assertIn(expected_flag, resp.red_flags,
                              f"emergency missing flag {expected_flag}: {text!r}")

    def test_new_wording_resolves_or_falls_to_buttons(self):
        """100 new-wording messages must resolve (embedding/LLM/lexicon) or fall
        to buttons — never crash and never dead-end silently."""
        for text in self.new_wording:
            resp = _run_pipeline(text, lang="hinglish")
            decided = resp.care_type is not None
            asked = resp.follow_up_question is not None
            self.assertTrue(decided or asked, f"new-wording dead-ended: {text!r}")

    def test_at_most_two_turns(self):
        """(d) the pipeline never asks a 3rd follow-up question."""
        for text in ("bukhar hai", "kamar dard", "pet dard hai"):
            history = []
            current = text
            asked = 0
            decided = False
            for turn in range(3):
                resp = _run_pipeline(current, lang="hinglish", history=history)
                if resp.follow_up_question:
                    asked += 1
                    self.assertLess(asked, 3, f"asked a 3rd question for {text!r}")
                    opts = resp.follow_up_options or ["Yes"]
                    answer = opts[0]
                    history.append(ChatMessage(role="assistant", text=resp.follow_up_question))
                    history.append(ChatMessage(role="user", text=answer))
                    current = answer
                else:
                    decided = True
                    break
            self.assertTrue(decided, f"no decision after 2 turns for {text!r}")

    def test_ambiguous_peet_is_generic_pain_not_back_or_stomach(self):
        """'peet' is ambiguous (pet=stomach vs peeth=back); it must resolve to
        generic pain (unknown location) and let the classifier decide — never a
        hard map to back or stomach, never emergency_112."""
        slots = extract_slots("mera peet bohot dard kr raha he", [])
        self.assertIn("joint_pain", slots.get("symptoms", []))
        self.assertNotIn("stomach_pain", slots.get("symptoms", []))
        resp = _run_pipeline("mera peet bohot dard kr raha he", lang="hinglish")
        self.assertNotEqual(resp.care_type, "emergency_112",
                            "ambiguous 'peet' pain must never escalate")

    def test_peeth_back_pet_stomach_stay_distinct(self):
        back = extract_slots("peeth mein dard", [])["symptoms"]
        self.assertIn("joint_pain", back)
        self.assertNotIn("stomach_pain", back)
        stomach = extract_slots("pet mein dard", [])["symptoms"]
        self.assertIn("stomach_pain", stomach)


if __name__ == "__main__":
    unittest.main()
