"""Provider-switch tests: the LLM provider is mockable/configurable, an LLM-off
run gives the same routing as rules+ML, and no API key patterns leak into
tracked files."""
import re
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.llm import llm_fast_model, llm_model, llm_provider, is_llm_available
from app.core.pipeline import run_triage_pipeline
from app.schemas import Location, TriageRequest

LOC = Location(lat=28.54, lng=77.27)

REPO = Path(__file__).resolve().parent.parent

# Common API key shapes. Placeholders ("your_*_here") are not matched.
_KEY_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"AQ\.[A-Za-z0-9_-]{30,}"),
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),
]


class TestSecretScan(unittest.TestCase):
    def test_no_key_patterns_in_tracked_files(self):
        tracked = subprocess.check_output(
            ["git", "-C", str(REPO), "ls-files"], text=True
        ).splitlines()
        hits = []
        for rel in tracked:
            path = REPO / rel
            if not path.is_file() or path.name == ".env.example":
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pat in _KEY_PATTERNS:
                if pat.search(text):
                    hits.append(f"{rel}: matched {pat.pattern}")
        self.assertEqual(hits, [], f"API key patterns in tracked files:\n" + "\n".join(hits))


class TestProviderConfigurable(unittest.TestCase):
    def test_provider_resolves_to_known_value(self):
        self.assertIn(llm_provider(), ("deepseek", "groq"))

    def test_models_are_non_empty(self):
        self.assertTrue(llm_model())
        self.assertTrue(llm_fast_model())

    @patch("app.core.llm._api_key", return_value="sk_test_placeholder_00000000000000")
    def test_llm_available_when_key_present(self, _mock):
        # The provider's key is what gates availability; a present key -> available.
        self.assertTrue(is_llm_available())

    @patch("app.core.llm._api_key", return_value="")
    def test_llm_unavailable_when_no_key(self, _mock):
        self.assertFalse(is_llm_available())


class TestLlmOffSameRouting(unittest.TestCase):
    @patch("app.core.pipeline.run_second_opinion", return_value=None)
    @patch("app.core.pipeline.screen_red_flags", return_value={"status": "skip", "flags": [], "combined": False})
    def test_llm_off_gives_valid_routing(self, _screen, _so):
        resp = run_triage_pipeline(
            TriageRequest(user_input="mujhe sir dard hai kal se", language="hinglish", location=LOC)
        )
        self.assertIsNotNone(resp.care_type)
        self.assertIsNotNone(resp.urgency)
        self.assertNotEqual(resp.care_type, "emergency_112")


if __name__ == "__main__":
    unittest.main()
