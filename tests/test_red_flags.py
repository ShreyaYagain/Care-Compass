import unittest
from app.core.red_flags import check_red_flags


class TestRedFlags(unittest.TestCase):
    def test_red_flag_chest_pain_en(self):
        flags, severity, is_emergency = check_red_flags("The patient has severe chest pain and sweating")
        self.assertIn("chest_pain", flags)
        self.assertEqual(severity, "high")
        self.assertTrue(is_emergency)

    def test_red_flag_chest_pain_hinglish(self):
        flags, severity, is_emergency = check_red_flags("mere papa ko seene me dard ho raha hai")
        self.assertIn("chest_pain", flags)
        self.assertTrue(is_emergency)

    def test_red_flag_breathlessness_hi(self):
        flags, severity, is_emergency = check_red_flags("मरीज को सांस लेने में बहुत तकलीफ हो रही है")
        self.assertIn("severe_breathlessness", flags)
        self.assertTrue(is_emergency)

    def test_red_flag_unconscious_hinglish(self):
        flags, severity, is_emergency = check_red_flags("wo achanak behosh ho gaye hain")
        self.assertIn("unconsciousness", flags)
        self.assertTrue(is_emergency)

    def test_red_flag_negation(self):
        # Negation: should NOT trigger chest pain emergency
        flags, severity, is_emergency = check_red_flags("fever for 2 days but no chest pain and no breathing problem")
        self.assertNotIn("chest_pain", flags)
        self.assertNotIn("severe_breathlessness", flags)
        self.assertFalse(is_emergency)

    def test_red_flag_stroke(self):
        flags, severity, is_emergency = check_red_flags("chehra tedha ho gaya hai aur awaz ladkhada rahi hai")
        self.assertIn("stroke_signs", flags)
        self.assertTrue(is_emergency)

    def test_red_flag_suicide(self):
        flags, severity, is_emergency = check_red_flags("I want to end my life, please help")
        self.assertIn("suicide_crisis", flags)
        self.assertTrue(is_emergency)

    def test_routine_fever_no_red_flag(self):
        flags, severity, is_emergency = check_red_flags("halka bukhar hai kal se")
        self.assertEqual(len(flags), 0)
        self.assertFalse(is_emergency)


if __name__ == "__main__":
    unittest.main()
