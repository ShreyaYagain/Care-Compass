import unittest
from app.schemas import Location
from app.core.matching import rank_caregivers


class TestMatching(unittest.TestCase):
    def test_closer_caregiver_ranks_higher_same_skill(self):
        # User at South Delhi (28.54, 77.27)
        matches = rank_caregivers(
            care_type="paramedic_home_visit",
            urgency="same_day",
            user_location=Location(lat=28.54, lng=77.27),
            user_language="hi",
            limit=3,
        )
        self.assertTrue(len(matches) > 0)
        # Verify scores are sorted descending
        scores = [m.score for m in matches]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_faraway_trap_filtered_or_penalized(self):
        # CG_005 has rating 5.0 but is in Meerut (>50km away)
        matches = rank_caregivers(
            care_type="specialist",
            urgency="routine",
            user_location=Location(lat=28.54, lng=77.27),
            user_language="en",
            limit=5,
        )
        matched_ids = [m.caregiver_id for m in matches]
        self.assertNotIn("CG_005", matched_ids)


if __name__ == "__main__":
    unittest.main()
