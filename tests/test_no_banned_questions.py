"""Repo-wide guard tests for the follow-up question policy.

Ensures that:
1. No banned question patterns (service / treatment / scheduling / medicines /
   severity) exist anywhere in app/, android/ (kt/xml) or docs/.
2. Every follow-up question emitted by the pipeline comes from the closed bank.
3. The hard turn cap is enforced in code (<= 2 assistant turns, then decide).
4. A 12-input multi-turn pipeline run never asks a banned question, never asks
   more than 2 follow-ups, and always decides by the 3rd turn.
"""
import unittest
from pathlib import Path

from app.schemas import TriageRequest, Location, ChatMessage
from app.core.pipeline import run_triage_pipeline
from app.core.intake import (
    is_bank_question,
    count_assistant_turns,
    needs_more_info,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

BANNED_PHRASES = [
    "service type",
    "treatment type",
    "what service do you want",
    "which service",
    "kis prakaar ki service",
    "when do you want",
    "kab chahiye",
    "kis time chahiye",
    "consult or give",
    "give meds",
    "kya karna chahiye",
    "how severe",
    "how bad is it",
    "kitni takleef",
    "takleef kitni",
]

# Words that must never appear in a follow-up question.
BANNED_QUESTION_WORDS = [
    "service", "treatment", "medicine", "meds", "prescrib",
    "when do you want", "kab chahiye",
]

TEXT_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".kt", ".xml", ".md", ".txt", ".csv"}


def _scan_dir(base: Path, banned: list[str]):
    hits = []
    for path in sorted(base.rglob("*")):
        if path.is_dir():
            continue
        if "__pycache__" in path.parts:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore").lower()
        except Exception:
            continue
        for phrase in banned:
            if phrase in content:
                hits.append((str(path.relative_to(REPO_ROOT)), phrase))
    return hits


class TestNoBannedQuestions(unittest.TestCase):

    def test_no_banned_phrases_in_repo(self):
        hits = []
        hits += _scan_dir(REPO_ROOT / "app", BANNED_PHRASES)
        hits += _scan_dir(REPO_ROOT / "android" / "app" / "src" / "main", BANNED_PHRASES)
        hits += _scan_dir(REPO_ROOT / "docs", BANNED_PHRASES)
        self.assertEqual(hits, [], f"Banned follow-up patterns found:\n{hits}")

    def test_every_followup_question_is_from_bank(self):
        inputs = ["help chahiye", "doctor chahiye", "mujhe kuch chahiye", "bukhar hai"]
        for text in inputs:
            req = TriageRequest(
                user_input=text,
                language="hinglish",
                location=Location(lat=28.61, lng=77.20),
                conversation_history=[],
            )
            resp = run_triage_pipeline(req)
            if resp.follow_up_question:
                # Either a closed-bank question, or a structured module card whose
                # field questions/options never contain banned words.
                if resp.module_card is not None:
                    for field in resp.module_card.get("fields", []):
                        q = field.get("question", "").lower()
                        for word in BANNED_QUESTION_WORDS:
                            self.assertNotIn(word, q, f"banned word in module field: {field!r}")
                else:
                    self.assertIsNotNone(
                        is_bank_question(resp.follow_up_question),
                        f"Follow-up question not in bank: {resp.follow_up_question!r}",
                    )
                    for word in BANNED_QUESTION_WORDS:
                        self.assertNotIn(word, resp.follow_up_question.lower())

    def test_disclaimer_and_weather_never_on_result_card(self):
        # The app disclaimer lives in Settings/About and the first-run screen,
        # and the weather/location/AQI summary is API/debug-only: neither may
        # ever appear on the result card text.
        inputs = [
            "papa ko do din se bukhar hai aur khansi bhi",
            "I have a headache",
            "sugar check karna hai subah",
            "severe chest pain",
            "ghar pe IM injection lagwana hai",
        ]
        for text in inputs:
            for lang in ("en", "hi", "hinglish"):
                req = TriageRequest(
                    user_input=text, language=lang,
                    location=Location(lat=28.54, lng=77.27),
                )
                resp = run_triage_pipeline(req)
                if not resp.reasoning:
                    continue
                low = resp.reasoning.lower()
                self.assertNotIn("this app helps", low, text)
                self.assertNotIn("right now:", low, text)
                self.assertNotIn("it is not a doctor", low, text)
                self.assertNotIn("aqi", low, text)

    def test_hard_turn_cap_assistant_turns(self):
        # 0 and 1 assistant turns may still ask; 2+ assistant turns must decide.
        slot_sets = [
            {"symptoms": ["fever"], "service_requested": "none", "duration": None,
             "patient_relation": "self", "age_group": None,
             "breathing_difficulty": None, "chest_pain": None},
        ]
        for slots in slot_sets:
            h0 = []
            h1 = [
                {"role": "user", "text": "fever"},
                {"role": "assistant", "text": "Is the patient experiencing any difficulty in breathing?"},
            ]
            h2 = h1 + [
                {"role": "user", "text": "No"},
                {"role": "assistant", "text": "Who is this consultation for?"},
            ]
            h3 = h2 + [
                {"role": "user", "text": "Self"},
                {"role": "assistant", "text": "How long has this issue been going on?"},
            ]
            self.assertEqual(count_assistant_turns(h0), 0)
            self.assertEqual(count_assistant_turns(h1), 1)
            self.assertEqual(count_assistant_turns(h2), 2)
            self.assertEqual(count_assistant_turns(h3), 3)
            # 2+ assistant turns must never ask again
            self.assertFalse(needs_more_info(slots, 2, h2))
            self.assertFalse(needs_more_info(slots, 3, h3))

    def test_pipeline_12_inputs_bounded_followups(self):
        inputs = [
            "mujhe kuch chahiye",
            "help chahiye",
            "doctor chahiye",
            "bukhar hai",
            "ghabrahat ho rahi hai",
            "papa ko bukhar hai aur khansi",
            "pet mein dard hai",
            "ghar pe injection lagwana hai",
            "full body checkup chahiye",
            "sugar check karna hai",
            "pair mein moch aa gayi hai",
            "kuch samajh nahi aa raha",
        ]

        print("\n" + "=" * 100)
        for i, text in enumerate(inputs, 1):
            history = []
            user_input = text
            transcript = []
            decided = False

            for turn in range(3):
                req = TriageRequest(
                    user_input=user_input,
                    language="hinglish",
                    location=Location(lat=28.61, lng=77.20),
                    conversation_history=history,
                )
                resp = run_triage_pipeline(req)

                if resp.follow_up_question:
                    self.assertLess(turn, 2, f"Input {text!r}: asked a 3rd follow-up!")
                    # A structured module card is a valid follow-up turn too.
                    if resp.module_card is not None:
                        for field in resp.module_card.get("fields", []):
                            for word in BANNED_QUESTION_WORDS:
                                self.assertNotIn(word, field.get("question", "").lower())
                    else:
                        self.assertIsNotNone(is_bank_question(resp.follow_up_question))
                        for word in BANNED_QUESTION_WORDS:
                            self.assertNotIn(word, resp.follow_up_question.lower())
                    transcript.append(f"  Q{turn + 1}: {resp.follow_up_question}")
                    # Answer the first option every time
                    answer = resp.follow_up_options[0] if resp.follow_up_options else "Yes"
                    transcript.append(f"  A{turn + 1}: {answer}")
                    history.append(ChatMessage(role="assistant", text=resp.follow_up_question, content=resp.follow_up_question))
                    history.append(ChatMessage(role="user", text=answer, content=answer))
                    user_input = answer
                else:
                    decided = True
                    transcript.append(f"  DECISION: {resp.care_type} / {resp.urgency}")
                    break

            if turn == 2 and not decided:
                self.fail(f"Input {text!r}: no decision after 3 turns")

            print(f"[{i:>2}] {text!r}")
            print("\n".join(transcript))
            print("-" * 100)
        print("=" * 100 + "\n")


if __name__ == "__main__":
    unittest.main()
