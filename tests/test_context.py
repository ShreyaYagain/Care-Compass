import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from app.core.context import (
    get_north_india_season,
    parse_client_time,
    get_context,
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
        self.assertIn("night", resp.context_used.get("reason", "").lower())
        self.assertIn("112", resp.reasoning)


if __name__ == "__main__":
    unittest.main()
