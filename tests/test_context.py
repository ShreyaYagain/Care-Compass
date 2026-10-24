import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from app.core.context import (
    get_north_india_season,
    parse_client_time,
    get_context,
    local_time_str,
)
from app.schemas import TriageRequest, Location, PatientProfile
from app.core.pipeline import run_triage_pipeline


class TestContextIntegration(unittest.TestCase):

    def test_north_india_season_derivation(self):
        tz = timezone(timedelta(hours=5, minutes=30))
        # Winter: Dec - Feb
        self.assertEqual(get_north_india_season(datetime(2026, 1, 15, tzinfo=tz)), "winter")
        self.assertEqual(get_north_india_season(datetime(2026, 12, 10, tzinfo=tz)), "winter")
        # Summer: Mar - mid-Jun
        self.assertEqual(get_north_india_season(datetime(2026, 4, 1, tzinfo=tz)), "summer")
        self.assertEqual(get_north_india_season(datetime(2026, 6, 10, tzinfo=tz)), "summer")
        # Monsoon: mid-Jun - Sep
        self.assertEqual(get_north_india_season(datetime(2026, 6, 20, tzinfo=tz)), "monsoon")
        self.assertEqual(get_north_india_season(datetime(2026, 7, 15, tzinfo=tz)), "monsoon")
        self.assertEqual(get_north_india_season(datetime(2026, 9, 30, tzinfo=tz)), "monsoon")
        # Post-monsoon: Oct - Nov
        self.assertEqual(get_north_india_season(datetime(2026, 10, 15, tzinfo=tz)), "post_monsoon")

    def test_context_consent_false_bypasses_context(self):
        req = TriageRequest(
            user_input="papa ko do din se bukhar hai aur khansi bhi",
            client_time="2026-07-15T14:30:00+05:30",
            location=Location(lat=28.54, lng=77.27),
            context_consent=False,
        )
        resp = run_triage_pipeline(req)
        self.assertIsNone(resp.context_used)
        self.assertEqual(resp.care_type, "paramedic_home_visit")
        self.assertEqual(resp.urgency, "same_day")

    @patch("app.core.pipeline.get_context")
    def test_heatwave_senior_escalation_rule(self, mock_ctx):
        mock_ctx.return_value = {
            "season": "summer",
            "local_hour": 14,
            "is_night": False,
            "temperature_c": 42.5,
            "humidity": 30,
            "aqi": 90,
            "tags": ["heat_wave"],
            "summary": "Summer · 43°C",
        }
        req = TriageRequest(
            user_input="dada ji ko bukhar aur tez ghabrahat ho rahi hai",
            client_time="2026-05-20T14:00:00+05:30",
            location=Location(lat=28.54, lng=77.27),
            patient=PatientProfile(age=72),
            context_consent=True,
        )
        resp = run_triage_pipeline(req)
        self.assertEqual(resp.care_type, "emergency_112")
        self.assertEqual(resp.urgency, "emergency")
        self.assertIsNotNone(resp.context_used)
        self.assertIn("heat_wave", resp.context_used.get("tags", []))
        self.assertTrue(len(resp.emergency_steps) > 0)

    @patch("app.core.pipeline.get_context")
    def test_night_time_soft_adjustment_rule(self, mock_ctx):
        mock_ctx.return_value = {
            "season": "monsoon",
            "local_hour": 23,
            "is_night": True,
            "temperature_c": 28.0,
            "humidity": 85,
            "aqi": 80,
            "tags": ["monsoon_season", "night_time"],
            "summary": "Monsoon · 28°C",
        }
        req = TriageRequest(
            user_input="papa ko do din se bukhar hai aur khansi bhi",
            client_time="2026-07-15T23:30:00+05:30",
            location=Location(lat=28.54, lng=77.27),
            context_consent=True,
        )
        resp = run_triage_pipeline(req)
        # Should be softly adjusted to teleconsultation (same_day) due to night time
        self.assertEqual(resp.care_type, "teleconsultation")
        self.assertEqual(resp.urgency, "same_day")
        self.assertIsNotNone(resp.context_used)
        # Context is shown as one short localized sentence on the card, in the
        # user's language (Hinglish here) — never the English word "night".
        self.assertIsNotNone(resp.card_lines)
        self.assertIn("raat ka time", (resp.card_lines.get("context_line") or "").lower())
        self.assertIn("raat ka time", (resp.context_used.get("reason") or "").lower())
        self.assertNotIn(" night ", resp.reasoning.lower())
        # The soft adjustment must never LOWER urgency: paramedic (same_day)
        # becomes teleconsultation (same_day), never "scheduled".
        self.assertNotEqual(resp.urgency, "scheduled")
        self.assertIn("112", resp.reasoning)

    @patch("app.core.pipeline.get_context")
    def test_result_includes_weather_time_and_location(self, mock_ctx):
        mock_ctx.return_value = {
            "season": "post_monsoon",
            "local_hour": 22,
            "is_night": False,
            "local_time_str": "10:30 PM",
            "location_name": "Noida, Uttar Pradesh",
            "temperature_c": 22.0,
            "humidity": 50,
            "precipitation_mm": 0.0,
            "aqi": 190,
            "tags": [],
            "summary": "Noida, Uttar Pradesh · Post-monsoon · 22°C · AQI 190",
        }
        req = TriageRequest(
            user_input="mujhe sir dard hai kal se",
            client_time="2026-10-24T22:30:00+05:30",
            location=Location(lat=28.54, lng=77.27),
            context_consent=True,
        )
        resp = run_triage_pipeline(req, debug=True)
        # Weather/time/location always accompany a result, not only on escalation.
        self.assertIsNotNone(resp.context_used)
        self.assertEqual(resp.context_used.get("location"), "Noida, Uttar Pradesh")
        self.assertEqual(resp.context_used.get("time"), "10:30 PM")
        self.assertEqual(resp.context_used.get("weather"), "22°C")
        self.assertEqual(resp.context_used.get("season"), "Post-monsoon")
        self.assertEqual(resp.context_used.get("aqi"), 190)
        # Weather/location/AQI never appear on the card text itself; they stay
        # in context_used (API + debug) only.
        self.assertNotIn("22°C", resp.reasoning)
        self.assertNotIn("Noida", resp.reasoning)
        self.assertNotIn("AQI 190", resp.reasoning)
        # The same raw values are available in the debug trace.
        self.assertIsNotNone(resp.debug)
        ctx_info = resp.debug.get("context_info") or {}
        self.assertEqual(ctx_info.get("temperature_c"), 22.0)
        self.assertEqual(ctx_info.get("aqi"), 190)
        self.assertEqual(ctx_info.get("local_time_str"), "10:30 PM")
        self.assertEqual(ctx_info.get("location_name"), "Noida, Uttar Pradesh")

    def test_local_time_str_format(self):
        self.assertEqual(local_time_str(datetime(2026, 10, 24, 22, 30)), "10:30 PM")
        self.assertEqual(local_time_str(datetime(2026, 10, 24, 9, 5)), "9:05 AM")


if __name__ == "__main__":
    unittest.main()
