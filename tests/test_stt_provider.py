"""Speech-to-text provider resolution tests.

Covers the "microphone cut off" regression: the STT provider must resolve to a
working path (on-device text when no server key is present) so voice input never
silently 503s / drops the user's message.
"""
import unittest

from app.core.stt import stt_provider, groq_whisper_available


class TestSttProvider(unittest.TestCase):

    def test_stt_provider_resolution(self):
        from app.config import settings
        prev = (settings.STT_PROVIDER, settings.GROQ_API_KEY)

        settings.GROQ_API_KEY = ""
        settings.STT_PROVIDER = ""
        self.assertEqual(stt_provider(), "android_only")

        settings.GROQ_API_KEY = "dummy-key"
        settings.STT_PROVIDER = ""
        self.assertEqual(stt_provider(), "groq_whisper")

        settings.STT_PROVIDER = "local_whisper"
        self.assertEqual(stt_provider(), "local_whisper")

        settings.STT_PROVIDER = "android_only"
        self.assertEqual(stt_provider(), "android_only")

        settings.STT_PROVIDER, settings.GROQ_API_KEY = prev

    def test_groq_whisper_available_only_with_key(self):
        from app.config import settings
        prev = settings.GROQ_API_KEY
        settings.GROQ_API_KEY = ""
        self.assertFalse(groq_whisper_available())
        settings.GROQ_API_KEY = "dummy-key"
        self.assertTrue(groq_whisper_available())
        settings.GROQ_API_KEY = prev


if __name__ == "__main__":
    unittest.main()
