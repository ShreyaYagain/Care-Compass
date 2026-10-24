import unittest
import pandas as pd
from app.schemas import Location
from app.core.matching import rank_caregivers
from app.config import settings


class TestMatching(unittest.TestCase):
    def test_inactive_caregiver_excluded(self):
        # CG_007, CG_008, CG_009, etc. are active == False
        matches = rank_caregivers(
            care_type="paramedic_home_visit",
            urgency="same_day",
            user_location=Location(lat=28.54, lng=77.27),
            user_language="hi",
            limit=50,
        )
        matched_ids = [m.caregiver_id for m in matches]
        inactive_ids = ["CG_007", "CG_008", "CG_009", "CG_013", "CG_031", "CG_036", "CG_047", "CG_058"]
        for i_id in inactive_ids:
            self.assertNotIn(i_id, matched_ids, f"Inactive caregiver {i_id} should be excluded")

    def test_out_of_radius_excluded_for_physical_visits(self):
        # Location in Mumbai (19.0760, 72.8777), Delhi caregivers should not match
        matches = rank_caregivers(
            care_type="paramedic_home_visit",
            urgency="same_day",
            user_location=Location(lat=19.076, lng=72.877),
            user_language="hi",
            limit=5,
        )
        self.assertEqual(len(matches), 0, "Out-of-radius caregivers should be excluded for physical visits")

    def test_distance_ignored_for_teleconsultation(self):
        # Location far away (Mumbai), but teleconsultation doctors should still match
        matches = rank_caregivers(
            care_type="teleconsultation",
            urgency="same_day",
            user_location=Location(lat=19.076, lng=72.877),
            user_language="en",
            limit=3,
        )
        self.assertTrue(len(matches) > 0, "Teleconsultation should match doctors regardless of user location")
        # Check that matched caregivers are doctors
        df = pd.read_csv(settings.CAREGIVERS_CSV_FILE)
        roles = df.set_index("caregiver_id")["role"].to_dict()
        for m in matches:
            self.assertEqual(roles.get(m.caregiver_id), "doctor")

    def test_emergency_returns_empty(self):
        matches = rank_caregivers(
            care_type="emergency_112",
            urgency="emergency",
            user_location=Location(lat=28.54, lng=77.27),
            user_language="hi",
            limit=5,
        )
        self.assertEqual(matches, [], "Emergency must return empty caregiver matches")

    def test_caregiver_overlap_against_official_dataset(self):
        csv_path = settings.OFFICIAL_DATA_DIR / "triage_dataset_flat.csv"
        df = pd.read_csv(csv_path)
        non_empty = df[df["matched_caregiver_ids"].notna() & (df["matched_caregiver_ids"] != "")]

        total = 0
        any_overlap = 0

        for _, row in non_empty.iterrows():
            c_type = row["care_type"]
            urgency = row["urgency"]
            lat = float(row["lat"]) if pd.notna(row["lat"]) else 28.54
            lng = float(row["lng"]) if pd.notna(row["lng"]) else 77.27
            lang = str(row["detected_language"]) or "English"
            u_lang = "en" if "eng" in lang.lower() else ("hi" if "hin" in lang.lower() else "hinglish")

            ref_ids = set(str(row["matched_caregiver_ids"]).split(";"))
            ranked = rank_caregivers(
                care_type=c_type,
                urgency=urgency,
                user_location=Location(lat=lat, lng=lng),
                user_language=u_lang,
                limit=3,
            )
            ranked_ids = set(m.caregiver_id for m in ranked)

            total += 1
            if len(ref_ids.intersection(ranked_ids)) > 0:
                any_overlap += 1

        overlap_rate = (any_overlap / total) * 100 if total > 0 else 0.0
        print(f"\n[Matching Test] Reference caregiver overlap rate in top-3: {any_overlap}/{total} ({overlap_rate:.2f}%)")
        self.assertGreaterEqual(overlap_rate, 75.0, f"Overlap rate {overlap_rate}% should be at least 75%")


if __name__ == "__main__":
    unittest.main()
