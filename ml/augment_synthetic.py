import csv
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
TRAIN_FILE = DATA_DIR / "train.csv"

SYNTHETIC_DATA = [
    # Paramedic Home Visit (Medic home visit)
    ("papa ko do din se bukhar hai aur khansi bhi", "Hinglish", "paramedic_home_visit", "same_day", ""),
    ("mummy ko 3 din se bukhar aur thakan hai", "Hinglish", "paramedic_home_visit", "same_day", ""),
    ("dadi ko bukhar aur ulti ho rahi hai ghar pe medic bhejo", "Hinglish", "paramedic_home_visit", "same_day", ""),
    ("Father is weak and has fever for 2 days need home visit", "English", "paramedic_home_visit", "same_day", ""),
    ("Elderly grandfather needs vitals monitoring and sugar BP check at home", "English", "paramedic_home_visit", "same_day", ""),
    ("पिताजी को दो दिन से तेज बुखार और कमजोरी है घर पर दिखाएं", "Hindi", "paramedic_home_visit", "same_day", ""),
    ("मम्मी को खांसी और बुखार है घर पर मेडिक भेजें", "Hindi", "paramedic_home_visit", "same_day", ""),
    ("bachhe ko bukhar hai aur badan dard ghar pe dekhna hai", "Hinglish", "paramedic_home_visit", "same_day", ""),
    ("bedridden patient vitals check at home", "English", "paramedic_home_visit", "same_day", ""),
    ("Senior citizen with high fever and chills needs in-person examination", "English", "paramedic_home_visit", "same_day", ""),

    # Home Nursing
    ("Doctor prescribed an injection, can someone come home", "English", "home_nursing", "same_day", ""),
    ("ghar pe IM injection lagwana hai", "Hinglish", "home_nursing", "same_day", ""),
    ("ghar par IV drip lagwane ke liye nurse chahiye", "Hinglish", "home_nursing", "same_day", ""),
    ("surgical wound dressing change at home", "English", "home_nursing", "same_day", ""),
    ("टांके कटवाने हैं और पट्टी बदलवानी है घर पर", "Hindi", "home_nursing", "same_day", ""),
    ("catheter change and bladder wash at home", "English", "home_nursing", "same_day", ""),
    ("bedsore dressing for elderly patient", "English", "home_nursing", "same_day", ""),
    ("home nursing for postoperative wound cleaning", "English", "home_nursing", "same_day", ""),
    ("insulin injection administration needed at home", "English", "home_nursing", "same_day", ""),
    ("dadi ke ghutne ke operation ke baad dressing karwani hai", "Hinglish", "home_nursing", "same_day", ""),

    # Lab Test Home
    ("full body checkup home collection", "English", "lab_test_home", "scheduled", ""),
    ("blood sample collection at home for diabetes test", "English", "lab_test_home", "scheduled", ""),
    ("ghar pe blood test ke liye sample lene wala chahiye", "Hinglish", "lab_test_home", "scheduled", ""),
    ("lipid profile and CBC test sample collection tomorrow", "English", "lab_test_home", "scheduled", ""),
    ("घर पर खून की जांच के लिए सैंपल कलेक्शन भेजना है", "Hindi", "lab_test_home", "scheduled", ""),
    ("thyroid test home phlebotomy needed", "English", "lab_test_home", "scheduled", ""),
    ("routine blood test at home for senior citizen", "English", "lab_test_home", "scheduled", ""),
    ("sugar test blood test home sample pick", "English", "lab_test_home", "scheduled", ""),
    ("ghar aakar khoon ki jaanch ka sample le jayein", "Hinglish", "lab_test_home", "scheduled", ""),

    # Teleconsultation
    ("doctor chahiye online baat karne ke liye", "Hinglish", "teleconsultation", "same_day", ""),
    ("want to consult a doctor online for acidity", "English", "teleconsultation", "same_day", ""),
    ("mild cold and sore throat doctor consult", "English", "teleconsultation", "same_day", ""),
    ("report review with doctor over video call", "English", "teleconsultation", "same_day", ""),
    ("doctor se online baat karni hai dawa ke liye", "Hinglish", "teleconsultation", "same_day", ""),
    ("डॉक्टर से ऑनलाइन परामर्श लेना है सिरदर्द के लिए", "Hindi", "teleconsultation", "same_day", ""),
    ("general doctor video consultation", "English", "teleconsultation", "same_day", ""),
    ("mujhe sir dard hai kal se doctor se consult karna hai", "Hinglish", "teleconsultation", "same_day", ""),
    ("skin allergy general doctor advice video", "English", "teleconsultation", "same_day", ""),

    # Emergency 112 (Covering all 9 official flags)
    ("chest pain ho raha hai papa ko", "Hinglish", "emergency_112", "emergency", "chest_pain"),
    ("severe crushing chest pain left arm sweating", "English", "emergency_112", "emergency", "chest_pain"),
    ("सीने में तेज दर्द और पसीना आ रहा है", "Hindi", "emergency_112", "emergency", "chest_pain"),

    ("saans nahi aa rahi dam ghut raha hai", "Hinglish", "emergency_112", "emergency", "breathlessness"),
    ("cannot breathe choking gasping for breath", "English", "emergency_112", "emergency", "breathlessness"),
    ("सांस फूल रही है और होंठ नीले पड़ रहे हैं", "Hindi", "emergency_112", "emergency", "breathlessness"),

    ("meri maa behosh ho gayi hai koi hosh nahi", "Hinglish", "emergency_112", "emergency", "unconsciousness"),
    ("patient fainted and completely unresponsive", "English", "emergency_112", "emergency", "unconsciousness"),
    ("अचानक बेहोश होकर गिर पड़ा कोई जवाब नहीं दे रहा", "Hindi", "emergency_112", "emergency", "unconsciousness"),

    ("accident ke baad heavy bleeding ruk nahi rahi", "Hinglish", "emergency_112", "emergency", "severe_bleeding"),
    ("spurting blood profuse arterial bleeding won't stop", "English", "emergency_112", "emergency", "severe_bleeding"),
    ("खून बहना बंद नहीं हो रहा बहुत ज्यादा खून निकल रहा है", "Hindi", "emergency_112", "emergency", "severe_bleeding"),

    ("chehra tedha ho gaya aur bol nahi pa raha", "Hinglish", "emergency_112", "emergency", "stroke_symptoms"),
    ("sudden face drooping and one sided arm paralysis stroke", "English", "emergency_112", "emergency", "stroke_symptoms"),
    ("लकवा मार गया आवाज लड़खड़ा रही है चेहरा टेढ़ा", "Hindi", "emergency_112", "emergency", "stroke_symptoms"),

    ("mirgi ka daura pad gaya jhatke aa rahe", "Hinglish", "emergency_112", "emergency", "seizure"),
    ("continuous violent seizure fits shaking violently", "English", "emergency_112", "emergency", "seizure"),
    ("दौरे पड़ रहे हैं मरीज जोर-जोर से कांप रहा है", "Hindi", "emergency_112", "emergency", "seizure"),

    ("2 mahine ke bachhe ko 104 bukhar hai", "Hinglish", "emergency_112", "emergency", "high_fever_infant"),
    ("newborn baby high fever 104 degrees lethargic", "English", "emergency_112", "emergency", "high_fever_infant"),
    ("नवजात शिशु को तेज बुखार है और सुस्त है", "Hindi", "emergency_112", "emergency", "high_fever_infant"),

    ("khud ko marna chahta hu suicide karna hai", "Hinglish", "emergency_112", "emergency", "suicidal_ideation"),
    ("suicidal ideation wanting to end life", "English", "emergency_112", "emergency", "suicidal_ideation"),
    ("जान देना चाहता हूँ खुदकुशी का विचार", "Hindi", "emergency_112", "emergency", "suicidal_ideation"),

    ("severe dehydration aankhen dhas gayi no urine 24 hours", "Hinglish", "emergency_112", "emergency", "severe_dehydration"),
    ("unresponsive severe dehydration sunken eyes no urine", "English", "emergency_112", "emergency", "severe_dehydration"),
    ("पानी की गंभीर कमी आंखें धंस गई पेशाब नहीं आ रहा", "Hindi", "emergency_112", "emergency", "severe_dehydration"),

    # Follow-up cases (short / vague)
    ("tabiyat theek nahi", "Hinglish", "follow_up", "", ""),
    ("kuch help chahiye", "Hinglish", "follow_up", "", ""),
    ("bimar hu", "Hinglish", "follow_up", "", ""),
    ("not feeling well", "English", "follow_up", "", ""),
    ("kripya madad karein", "Hinglish", "follow_up", "", ""),
    ("need assistance", "English", "follow_up", "", ""),
]


def augment():
    if not TRAIN_FILE.exists():
        print("train.csv not found. Run ml.prepare_data first.")
        return

    from app.core.language import normalise_text

    rows_to_add = []
    for i, (text, lang, care, urg, flags) in enumerate(SYNTHETIC_DATA):
        rows_to_add.append({
            "id": f"SYN_{i+1:04d}",
            "user_input": text,
            "norm_input": normalise_text(text),
            "language": lang,
            "care_type": care,
            "urgency": urg,
            "red_flags": flags,
            "follow_up_question": "What is the problem? Please tell us the main symptom." if care == "follow_up" else "",
            "source": "synthetic_llm",
        })

    fieldnames = [
        "id", "user_input", "norm_input", "language", "care_type",
        "urgency", "red_flags", "follow_up_question", "source"
    ]

    with open(TRAIN_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writerows(rows_to_add)

    print(f"Augmented {len(rows_to_add)} synthetic cases into {TRAIN_FILE} (source=synthetic_llm).")


if __name__ == "__main__":
    augment()
