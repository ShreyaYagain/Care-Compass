import unittest
from app.core.red_flags import check_red_flags


class TestRedFlags(unittest.TestCase):
    # 1. chest_pain
    def test_chest_pain_en(self):
        flags, severity, is_emergency = check_red_flags("The patient has severe chest pain and pressure")
        self.assertIn("chest_pain", flags)
        self.assertEqual(severity, "high")
        self.assertTrue(is_emergency)

    def test_chest_pain_hi(self):
        flags, severity, is_emergency = check_red_flags("सीने में तेज दर्द हो रहा है")
        self.assertIn("chest_pain", flags)
        self.assertTrue(is_emergency)

    def test_chest_pain_hinglish(self):
        flags, severity, is_emergency = check_red_flags("mere papa ko seene me dard ho raha hai")
        self.assertIn("chest_pain", flags)
        self.assertTrue(is_emergency)

    # 2. breathlessness
    def test_breathlessness_en(self):
        flags, severity, is_emergency = check_red_flags("Patient has severe shortness of breath and cannot breathe")
        self.assertIn("breathlessness", flags)
        self.assertTrue(is_emergency)

    def test_breathlessness_hi(self):
        flags, severity, is_emergency = check_red_flags("मरीज को सांस लेने में बहुत तकलीफ हो रही है")
        self.assertIn("breathlessness", flags)
        self.assertTrue(is_emergency)

    def test_breathlessness_hinglish(self):
        flags, severity, is_emergency = check_red_flags("dadi ko saans nahi aa rahi hai")
        self.assertIn("breathlessness", flags)
        self.assertTrue(is_emergency)

    # 3. unconsciousness
    def test_unconsciousness_en(self):
        flags, severity, is_emergency = check_red_flags("Patient collapsed and is unconscious")
        self.assertIn("unconsciousness", flags)
        self.assertTrue(is_emergency)

    def test_unconsciousness_hi(self):
        flags, severity, is_emergency = check_red_flags("मरीज अचानक बेहोश हो गया है")
        self.assertIn("unconsciousness", flags)
        self.assertTrue(is_emergency)

    def test_unconsciousness_hinglish(self):
        flags, severity, is_emergency = check_red_flags("meri maa behosh ho gayi hai aur hosh nahi hai")
        self.assertIn("unconsciousness", flags)
        self.assertTrue(is_emergency)

    # 4. severe_bleeding
    def test_severe_bleeding_en(self):
        flags, severity, is_emergency = check_red_flags("Deep cut with heavy bleeding that won't stop")
        self.assertIn("severe_bleeding", flags)
        self.assertTrue(is_emergency)

    def test_severe_bleeding_hi(self):
        flags, severity, is_emergency = check_red_flags("हाथ कट गया है और बहुत ज्यादा खून बह रहा है")
        self.assertIn("severe_bleeding", flags)
        self.assertTrue(is_emergency)

    def test_severe_bleeding_hinglish(self):
        flags, severity, is_emergency = check_red_flags("accident hua hai khoon band nahi ho raha")
        self.assertIn("severe_bleeding", flags)
        self.assertTrue(is_emergency)

    # 5. stroke_symptoms
    def test_stroke_symptoms_en(self):
        flags, severity, is_emergency = check_red_flags("Sudden face drooping and slurred speech")
        self.assertIn("stroke_symptoms", flags)
        self.assertTrue(is_emergency)

    def test_stroke_symptoms_hi(self):
        flags, severity, is_emergency = check_red_flags("चेहरा टेढ़ा हो गया है और आवाज लड़खड़ा रही है")
        self.assertIn("stroke_symptoms", flags)
        self.assertTrue(is_emergency)

    def test_stroke_symptoms_hinglish(self):
        flags, severity, is_emergency = check_red_flags("chehra tedha ho gaya hai aur awaz ladkhada rahi hai")
        self.assertIn("stroke_symptoms", flags)
        self.assertTrue(is_emergency)

    # 6. seizure
    def test_seizure_en(self):
        flags, severity, is_emergency = check_red_flags("He is having a violent seizure right now")
        self.assertIn("seizure", flags)
        self.assertTrue(is_emergency)

    def test_seizure_hi(self):
        flags, severity, is_emergency = check_red_flags("मरीज को मिर्गी का दौरा पड़ रहा है")
        self.assertIn("seizure", flags)
        self.assertTrue(is_emergency)

    def test_seizure_hinglish(self):
        flags, severity, is_emergency = check_red_flags("bhai ko achanak mirgi ke daure aa rahe hain")
        self.assertIn("seizure", flags)
        self.assertTrue(is_emergency)

    # 7. high_fever_infant
    def test_high_fever_infant_en(self):
        flags, severity, is_emergency = check_red_flags("Newborn fever with 104 temperature")
        self.assertIn("high_fever_infant", flags)
        self.assertTrue(is_emergency)

    def test_high_fever_infant_hi(self):
        flags, severity, is_emergency = check_red_flags("नवजात शिशु को बुखार और बहुत रो रहा है")
        self.assertIn("high_fever_infant", flags)
        self.assertTrue(is_emergency)

    def test_high_fever_infant_hinglish(self):
        flags, severity, is_emergency = check_red_flags("newborn ko bukhar hai aur 2 mahine ke bachhe ko bukhar hai")
        self.assertIn("high_fever_infant", flags)
        self.assertTrue(is_emergency)

    # 8. suicidal_ideation
    def test_suicidal_ideation_en(self):
        flags, severity, is_emergency = check_red_flags("I want to end my life, please help")
        self.assertIn("suicidal_ideation", flags)
        self.assertTrue(is_emergency)

    def test_suicidal_ideation_hi(self):
        flags, severity, is_emergency = check_red_flags("मैं आत्महत्या करना चाहता हूँ")
        self.assertIn("suicidal_ideation", flags)
        self.assertTrue(is_emergency)

    def test_suicidal_ideation_hinglish(self):
        flags, severity, is_emergency = check_red_flags("mujhe lagta hai marna chahta hu jaan dena chahta")
        self.assertIn("suicidal_ideation", flags)
        self.assertTrue(is_emergency)

    # 9. severe_dehydration
    def test_severe_dehydration_en(self):
        flags, severity, is_emergency = check_red_flags("Patient has sunken eyes and no urine for 24 hours")
        self.assertIn("severe_dehydration", flags)
        self.assertTrue(is_emergency)

    def test_severe_dehydration_hi(self):
        flags, severity, is_emergency = check_red_flags("मरीज को गंभीर डिहाइड्रेशन है और पेशाब बंद है")
        self.assertIn("severe_dehydration", flags)
        self.assertTrue(is_emergency)

    def test_severe_dehydration_hinglish(self):
        flags, severity, is_emergency = check_red_flags("paani ki bahut kami ho gayi hai peshab bilkul nahi aa raha")
        self.assertIn("severe_dehydration", flags)
        self.assertTrue(is_emergency)

    # Negations
    def test_negations_english(self):
        flags, severity, is_emergency = check_red_flags("Patient has fever and cough, but no chest pain and no difficulty breathing")
        self.assertNotIn("chest_pain", flags)
        self.assertNotIn("breathlessness", flags)
        self.assertFalse(is_emergency)

    def test_negations_hinglish(self):
        flags, severity, is_emergency = check_red_flags("bukhar hai par seene me dard nahi hai aur saans lene me koi dikkat nahi")
        self.assertNotIn("chest_pain", flags)
        self.assertNotIn("breathlessness", flags)
        self.assertFalse(is_emergency)

    def test_routine_fever_no_red_flag(self):
        flags, severity, is_emergency = check_red_flags("halka bukhar hai kal se")
        self.assertEqual(len(flags), 0)
        self.assertFalse(is_emergency)


if __name__ == "__main__":
    unittest.main()
