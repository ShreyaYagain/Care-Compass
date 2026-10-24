import csv
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

VIGNETTES = [
    # --- Paramedic Home Visit: same_day ---
    {"id": "VIG_001", "user_input": "papa ko do din se bukhar hai aur khansi bhi", "language": "hinglish", "age": 68, "sex": "male", "conditions": "diabetes", "care_type": "paramedic_home_visit", "urgency": "same_day", "red_flags": "", "source": "handwritten_gold"},
    {"id": "VIG_002", "user_input": "dadi ko subah se tez bukhar hai aur badan dard kar raha hai", "language": "hinglish", "age": 75, "sex": "female", "conditions": "hypertension", "care_type": "paramedic_home_visit", "urgency": "same_day", "red_flags": "", "source": "synthetic"},
    {"id": "VIG_003", "user_input": "Father has had high fever and shivering since yesterday", "language": "en", "age": 62, "sex": "male", "conditions": "", "care_type": "paramedic_home_visit", "urgency": "same_day", "red_flags": "", "source": "synthetic"},
    {"id": "VIG_004", "user_input": "पिताजी को दो दिन से तेज बुखार और कमजोरी है", "language": "hi", "age": 65, "sex": "male", "conditions": "diabetes", "care_type": "paramedic_home_visit", "urgency": "same_day", "red_flags": "", "source": "synthetic"},
    {"id": "VIG_005", "user_input": "Mummy ko 3 din se bukhar hai, khansi hai par saans lene me koi dikkat nahi hai", "language": "hinglish", "age": 58, "sex": "female", "conditions": "", "care_type": "paramedic_home_visit", "urgency": "same_day", "red_flags": "", "source": "handwritten_gold"},
    {"id": "VIG_006", "user_input": "Elderly mother needs blood pressure and vitals check at home due to extreme fatigue", "language": "en", "age": 74, "sex": "female", "conditions": "hypertension", "care_type": "paramedic_home_visit", "urgency": "same_day", "red_flags": "", "source": "synthetic"},
    {"id": "VIG_007", "user_input": "bachhe ko 2 din se bukhar aur ulti ho rahi hai", "language": "hinglish", "age": 6, "sex": "male", "conditions": "", "care_type": "paramedic_home_visit", "urgency": "same_day", "red_flags": "", "source": "synthetic"},

    # --- Nurse Home Visit: routine & same_day ---
    {"id": "VIG_008", "user_input": "Grandmother needs surgical wound dressing changed at home", "language": "en", "age": 78, "sex": "female", "conditions": "diabetes", "care_type": "nurse_home_visit", "urgency": "same_day", "red_flags": "", "source": "synthetic"},
    {"id": "VIG_009", "user_input": "Papa ke pair me zakham hai jisme patti aur dressing karwani hai", "language": "hinglish", "age": 70, "sex": "male", "conditions": "diabetes", "care_type": "nurse_home_visit", "urgency": "same_day", "red_flags": "", "source": "handwritten_gold"},
    {"id": "VIG_010", "user_input": "दादी के टांके कटवाने हैं और इंजेक्शन लगवाना है", "language": "hi", "age": 80, "sex": "female", "conditions": "", "care_type": "nurse_home_visit", "urgency": "routine", "red_flags": "", "source": "synthetic"},
    {"id": "VIG_011", "user_input": "Need home nurse for urinary catheter flush and IV injection", "language": "en", "age": 82, "sex": "male", "conditions": "prostate", "care_type": "nurse_home_visit", "urgency": "same_day", "red_flags": "", "source": "synthetic"},
    {"id": "VIG_012", "user_input": "Bedridden patient needs bed sore dressing and insulin administration", "language": "en", "age": 85, "sex": "female", "conditions": "diabetes", "care_type": "nurse_home_visit", "urgency": "routine", "red_flags": "", "source": "synthetic"},

    # --- GP Teleconsult: routine ---
    {"id": "VIG_013", "user_input": "Mild sore throat and runny nose since morning, need general advice", "language": "en", "age": 28, "sex": "female", "conditions": "", "care_type": "gp_teleconsult", "urgency": "routine", "red_flags": "", "source": "synthetic"},
    {"id": "VIG_014", "user_input": "halka gala kharab hai aur thodi thakan lag rahi hai subah se", "language": "hinglish", "age": 32, "sex": "male", "conditions": "", "care_type": "gp_teleconsult", "urgency": "routine", "red_flags": "", "source": "handwritten_gold"},
    {"id": "VIG_015", "user_input": "पेट में हल्की गैस और अपच की शिकायत है", "language": "hi", "age": 40, "sex": "male", "conditions": "", "care_type": "gp_teleconsult", "urgency": "routine", "red_flags": "", "source": "synthetic"},
    {"id": "VIG_016", "user_input": "Doctor consultation for routine seasonal cold and prescription refill", "language": "en", "age": 45, "sex": "female", "conditions": "", "care_type": "gp_teleconsult", "urgency": "routine", "red_flags": "", "source": "synthetic"},
    {"id": "VIG_017", "user_input": "thoda sirdard hai subah se koi gharelu upay ya consultation chahiye", "language": "hinglish", "age": 25, "sex": "female", "conditions": "", "care_type": "gp_teleconsult", "urgency": "routine", "red_flags": "", "source": "synthetic"},

    # --- Specialist: routine ---
    {"id": "VIG_018", "user_input": "Skin rash on both arms with itching for 2 weeks, getting worse", "language": "en", "age": 35, "sex": "female", "conditions": "", "care_type": "specialist", "urgency": "routine", "red_flags": "", "source": "synthetic"},
    {"id": "VIG_019", "user_input": "Ghutno me purana dard hai chalne me dikkat hoti hai doctor ko dikhana hai", "language": "hinglish", "age": 63, "sex": "female", "conditions": "arthritis", "care_type": "specialist", "urgency": "routine", "red_flags": "", "source": "handwritten_gold"},
    {"id": "VIG_020", "user_input": "महीनों से सिरदर्द और माइग्रेन की पुरानी समस्या है, न्यूरोलॉजिस्ट से मिलना है", "language": "hi", "age": 38, "sex": "male", "conditions": "migraine", "care_type": "specialist", "urgency": "routine", "red_flags": "", "source": "synthetic"},
    {"id": "VIG_021", "user_input": "Chronic lower back ache for 2 months, need orthopaedic opinion", "language": "en", "age": 50, "sex": "male", "conditions": "", "care_type": "specialist", "urgency": "routine", "red_flags": "", "source": "synthetic"},

    # --- Emergency Referral: immediate (Red flags) ---
    {"id": "VIG_022", "user_input": "Severe crushing chest pain radiating to left arm with cold sweat", "language": "en", "age": 55, "sex": "male", "conditions": "hypertension", "care_type": "emergency_referral", "urgency": "immediate", "red_flags": "chest_pain", "source": "handwritten_gold"},
    {"id": "VIG_023", "user_input": "Papa ko seene me tez dard hai aur paseena aa raha hai saans nahi le pa rahe", "language": "hinglish", "age": 60, "sex": "male", "conditions": "diabetes", "care_type": "emergency_referral", "urgency": "immediate", "red_flags": "chest_pain;severe_breathlessness", "source": "handwritten_gold"},
    {"id": "VIG_024", "user_input": "मरीज अचानक बेहोश होकर गिर पड़ा और कोई जवाब नहीं दे रहा है", "language": "hi", "age": 50, "sex": "male", "conditions": "", "care_type": "emergency_referral", "urgency": "immediate", "red_flags": "unconsciousness", "source": "synthetic"},
    {"id": "VIG_025", "user_input": "Face drooping on right side and suddenly unable to speak or move right arm", "language": "en", "age": 72, "sex": "female", "conditions": "hypertension", "care_type": "emergency_referral", "urgency": "immediate", "red_flags": "stroke_signs", "source": "synthetic"},
    {"id": "VIG_026", "user_input": "Khoon ki ulti ho rahi hai aur behoshi jaisi halat hai", "language": "hinglish", "age": 45, "sex": "male", "conditions": "", "care_type": "emergency_referral", "urgency": "immediate", "red_flags": "vomiting_blood", "source": "handwritten_gold"},
    {"id": "VIG_027", "user_input": "Pregnant woman in 8th month with heavy vaginal bleeding and severe pain", "language": "en", "age": 27, "sex": "female", "conditions": "pregnant", "care_type": "emergency_referral", "urgency": "immediate", "red_flags": "pregnancy_emergency", "source": "synthetic"},
    {"id": "VIG_028", "user_input": "Bachhe ne galti se floor cleaner ya poison pi liya hai", "language": "hinglish", "age": 4, "sex": "male", "conditions": "", "care_type": "emergency_referral", "urgency": "immediate", "red_flags": "poisoning_overdose", "source": "handwritten_gold"},
    {"id": "VIG_029", "user_input": "Heavy bleeding from leg wound after bike accident, not stopping with pressure", "language": "en", "age": 24, "sex": "male", "conditions": "", "care_type": "emergency_referral", "urgency": "immediate", "red_flags": "uncontrolled_bleeding", "source": "synthetic"},
    {"id": "VIG_030", "user_input": "Patient is having continuous epileptic seizures and shaking violently", "language": "en", "age": 19, "sex": "male", "conditions": "epilepsy", "care_type": "emergency_referral", "urgency": "immediate", "red_flags": "seizure", "source": "synthetic"}
]


def prepare_datasets():
    train_file = DATA_DIR / "train.csv"
    gold_file = DATA_DIR / "gold.csv"

    fieldnames = [
        "id", "user_input", "language", "age", "sex", "conditions",
        "care_type", "urgency", "red_flags", "source"
    ]

    with open(train_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in VIGNETTES:
            writer.writerow(row)

    gold_rows = [r for r in VIGNETTES if "gold" in r["source"]]
    with open(gold_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in gold_rows:
            writer.writerow(row)

    print(f"Prepared {len(VIGNETTES)} train cases and {len(gold_rows)} gold evaluation cases.")


if __name__ == "__main__":
    prepare_datasets()
