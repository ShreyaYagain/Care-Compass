"""Regenerate ml/data/redflag_tests.csv with an expanded, review-pending test set.

Categories (all reviewed_by_human=false — see ml/data/REVIEW_GUIDE.md):
  - 12+ positive phrases per red flag (en/hi/hinglish, typos, family phrasing) -> emergency_112
  - 40 negated phrases (red-flag words present but negated) -> non-emergency
  - 40 near-miss non-emergencies (mild, similar-sounding) -> non-emergency
  - 20 emergencies hidden inside longer narrative text -> emergency_112

The original 9 handwritten/synthetic rows are preserved at the top.
"""
import csv
from pathlib import Path

OUT = Path(__file__).resolve().parent / "redflag_tests.csv"

F = "false"

# ---------------------------------------------------------------------------
# Positive phrases: 12 per flag. (text, language)
# ---------------------------------------------------------------------------
POSITIVES = {
    "chest_pain": [
        ("I have crushing chest pain that won't go away", "en"),
        ("My father has severe chest pressure and is sweating a lot", "en"),
        ("severe cheest pain radiating down my left arm", "en"),
        ("grandmother complains of a heavy squeezing feeling in her chest", "en"),
        ("मेरे सीने में बहुत तेज़ दर्द हो रहा है", "hi"),
        ("पापा के सीने में दर्द है और ठंडा पसीना आ रहा है", "hi"),
        ("दादी को सीने में भारीपन और दबाव महसूस हो रहा है", "hi"),
        ("mere seene me bahut tez dard ho raha hai", "hinglish"),
        ("seene me dard hai aur paseena aa raha hai", "hinglish"),
        ("chest me bahot pain hai aur saans atak rahi hai", "hinglish"),
        ("dil me dard ho raha hai bhaiya, left hand sunn ho raha hai", "hinglish"),
        ("papa ko seene me jalan aur dabav ho raha hai subah se", "hinglish"),
    ],
    "breathlessness": [
        ("I can't breathe properly, my chest feels tight", "en"),
        ("mother is gasping for air and her lips look bluish", "en"),
        ("I am shorness of breath just walking to the kitchen", "en"),
        ("grandfather says he feels like he is suffocating", "en"),
        ("सांस बिल्कुल नहीं आ रही है", "hi"),
        ("माँ को साँस लेने में बहुत दिक्कत हो रही है", "hi"),
        ("दादा जी का दम घुट रहा है", "hi"),
        ("saans nahi aa rahi hai, bahut dikkat ho rahi hai", "hinglish"),
        ("sans lene me bahut takleef hai aur hoth neele ho rahe hain", "hinglish"),
        ("mummy ko saans phool rahi hai raat se", "hinglish"),
        ("breathing me bahot problem hai, chest tight lag raha hai", "hinglish"),
        ("papa ko saans lene me itni dikkat hai ki bol nahi pa rahe", "hinglish"),
    ],
    "unconsciousness": [
        ("My father suddenly fainted and is not responding", "en"),
        ("grandmother passed out and won't wake up", "en"),
        ("my brother is unconscious after falling off the stairs", "en"),
        ("the patient collapsed and is unresponsive", "en"),
        ("पापा अचानक बेहोश हो गए और कोई जवाब नहीं दे रहे", "hi"),
        ("दादी बेहोश हो गई हैं और होश नहीं आ रहा", "hi"),
        ("मरीज़ गिर कर बेहोश हो गया है", "hi"),
        ("papa behosh ho gaye hain aur uth nahi rahe", "hinglish"),
        ("dadi ko hosh nahi aa raha, kal se behosh hain", "hinglish"),
        ("bhaiya beosh ho gaye hain aur respond nahi kar rahe", "hinglish"),
        ("patient hosh kho kar gir gaya hai, awaaz nahi de raha", "hinglish"),
        ("mummy ne behosh ho kar gira aur ab kuch bol nahi rahi", "hinglish"),
    ],
    "severe_bleeding": [
        ("Heavy bleeding from a leg wound that won't stop", "en"),
        ("my father is vomiting blood this morning", "en"),
        ("bleeding from the nose and it will not stop", "en"),
        ("mother has bleeding that soaked through the bandage", "en"),
        ("खून बहना बंद नहीं हो रहा है", "hi"),
        ("पापा को खून की उल्टी हो रही है", "hi"),
        ("ज़ख्म से बहुत तेज़ खून बह रहा है", "hi"),
        ("khoon band nahi ho raha hai ghaav se", "hinglish"),
        ("papa ko khoon ki ulti ho rahi hai subah se", "hinglish"),
        ("bleeding bahut ho rahi hai aur ruk nahi rahi", "hinglish"),
        ("mummy ka khoon nikal raha hai aur band nahi ho raha", "hinglish"),
        ("zakhm se tez khoon beh raha hai aur bandage bheeg gaya", "hinglish"),
    ],
    "stroke_symptoms": [
        ("My grandfather's face is drooping on one side", "en"),
        ("father suddenly cannot speak and his mouth is twisted", "en"),
        ("one side of my body is weak and I slur my words", "en"),
        ("my mother's face is numb and she cannot lift her arm", "en"),
        ("दादा जी का मुँह टेढ़ा हो गया है और बोल नहीं पा रहे", "hi"),
        ("पापा की एक तरफ कमज़ोरी आ गई है", "hi"),
        ("माँ का चेहरा टेढ़ा हो गया है", "hi"),
        ("dada ji ka muh tedha ho gaya hai aur bol nahi pa rahe", "hinglish"),
        ("papa ki ek side kamzor ho gayi hai", "hinglish"),
        ("mummy ka face tedha ho gaya aur awaz ladkhada rahi hai", "hinglish"),
        ("chehra jhuk gaya hai aur haath nahi uth raha", "hinglish"),
        ("dada ko lakwa jaisa lag raha hai, ek side sunn hai", "hinglish"),
    ],
    "seizure": [
        ("My son is having continuous seizures and shaking", "en"),
        ("father had a fit and his body is jerking", "en"),
        ("patient is convulsing and has foam at the mouth", "en"),
        ("my brother fell and is shaking uncontrollably", "en"),
        ("बच्चे को दौरे पड़ रहे हैं", "hi"),
        ("पापा को दौरा पड़ा और मुँह से झाग आ रहा है", "hi"),
        ("मरीज़ को झटके आ रहे हैं", "hi"),
        ("bache ko daure pad rahe hain", "hinglish"),
        ("papa ko daura pada aur muh se jhaag aa raha hai", "hinglish"),
        ("bhaiya ke jhatke aa rahe hain aur haath pair akad rahe hain", "hinglish"),
        ("patient ke fits aa rahe hain ruk nahi rahe", "hinglish"),
        ("mummy ko mirgi ka daura aa raha hai baar baar", "hinglish"),
    ],
    "high_fever_infant": [
        ("My 2-month-old baby has a fever of 104", "en"),
        ("newborn has high fever and won't feed", "en"),
        ("my infant is burning up with a fever", "en"),
        ("baby under 3 months has a very high temperature", "en"),
        ("2 महीने के बच्चे को 104 बुखार है", "hi"),
        ("नवजात शिशु को तेज़ बुखार है और दूध नहीं पी रहा", "hi"),
        ("छोटे बच्चे को बहुत तेज़ बुखार है", "hi"),
        ("2 mahine ke bache ko 104 bukhar hai", "hinglish"),
        ("newborn ko tez bukhar hai aur doodh nahi pi raha", "hinglish"),
        ("chote bacche ko bahut tez bukhar hai raat se", "hinglish"),
        ("navjat shishu ko bukhar hai aur rona band nahi kar raha", "hinglish"),
        ("3 mahine ke bacche ko high fever hai", "hinglish"),
    ],
    "suicidal_ideation": [
        ("I want to end my life tonight", "en"),
        ("my son keeps saying he wants to die", "en"),
        ("patient is expressing thoughts of killing himself", "en"),
        ("she said she has a plan to hurt herself", "en"),
        ("मैं अपनी जान देना चाहता हूँ", "hi"),
        ("मेरा बेटा बार-बार कह रहा है कि वह मरना चाहता है", "hi"),
        ("मरीज़ आत्महत्या की बात कर रहा है", "hi"),
        ("main apni jaan dena chahta hoon", "hinglish"),
        ("mera beta baar baar keh raha hai ki wo marna chahta hai", "hinglish"),
        ("patient aatmahatya ki baat kar raha hai", "hinglish"),
        ("wo khud ko chot pahunchana chahti hai", "hinglish"),
        ("mujhe jeene ka mann nahi hai, sab khatam karna hai", "hinglish"),
    ],
    "severe_dehydration": [
        ("My grandmother has sunken eyes and no urine for a day", "en"),
        ("child is extremely weak and cannot keep water down", "en"),
        ("father is dehydrated with no urine output", "en"),
        ("baby has sunken fontanelle and no tears", "en"),
        ("आँखें धंस गई हैं और पेशाब बिल्कुल नहीं आ रहा", "hi"),
        ("बच्चे को पानी की बहुत कमी हो गई है", "hi"),
        ("मरीज़ को उल्टी-दस्त से पानी की कमी हो गई है", "hi"),
        ("aankhen dhas gayi hain aur peshab bilkul nahi aa raha", "hinglish"),
        ("bache ko ulti dast se paani ki bahut kami ho gayi hai", "hinglish"),
        ("dadi ki aankhen dhasi hui hain aur peshab nahi aa raha", "hinglish"),
        ("patient ko bahut weakness hai aur paani nahi ruk raha", "hinglish"),
        ("mummy ko severe dehydration hai, 2 din se peshab nahi", "hinglish"),
    ],
}

# ---------------------------------------------------------------------------
# Negated phrases (red-flag words present but negated) -> non-emergency
# ---------------------------------------------------------------------------
NEGATED = [
    ("no chest pain, just a mild cough", "en", "teleconsultation"),
    ("I do not have shortness of breath, only a sore throat", "en", "teleconsultation"),
    ("my father is NOT unconscious, he is just sleeping deeply", "en", "teleconsultation"),
    ("there is no heavy bleeding, just a small cut", "en", "teleconsultation"),
    ("no stroke signs, just a mild headache", "en", "teleconsultation"),
    ("he is not having a seizure, just shivering from the cold", "en", "teleconsultation"),
    ("the baby does not have a high fever, just a mild temperature", "en", "teleconsultation"),
    ("I am not suicidal, just feeling a bit sad today", "en", "teleconsultation"),
    ("no dehydration, she is drinking water normally", "en", "teleconsultation"),
    ("chest pain nahi hai, sirf halki khansi hai", "hinglish", "teleconsultation"),
    ("saans ki koi dikkat nahi hai, bas halka bukhar hai", "hinglish", "teleconsultation"),
    ("papa behosh nahi hain, bas gehri neend me hain", "hinglish", "teleconsultation"),
    ("khoon nahi beh raha, bas choti si kharoch hai", "hinglish", "teleconsultation"),
    ("stroke ke koi lakshan nahi, sirf halka sar dard hai", "hinglish", "teleconsultation"),
    ("daura nahi pad raha, sirf thand se kaap raha hai", "hinglish", "teleconsultation"),
    ("bache ko tez bukhar nahi hai, bas halka sa garam hai", "hinglish", "teleconsultation"),
    ("mujhe aatmahatya ka koi vichar nahi, bas thoda udaas hoon", "hinglish", "teleconsultation"),
    ("dehydration nahi hai, pani theek se pee rahi hai", "hinglish", "teleconsultation"),
    ("सीने में दर्द नहीं है, बस हल्की खांसी है", "hi", "teleconsultation"),
    ("सांस की कोई दिक्कत नहीं है, बस हल्का बुखार है", "hi", "teleconsultation"),
    ("पापा बेहोश नहीं हैं, गहरी नींद में हैं", "hi", "teleconsultation"),
    ("खून नहीं बह रहा, बस छोटी सी खरोंच है", "hi", "teleconsultation"),
    ("दौरा नहीं पड़ा, बस ठंड से काँप रहा है", "hi", "teleconsultation"),
    ("बच्चे को तेज़ बुखार नहीं है, बस हल्का सा गरम है", "hi", "teleconsultation"),
    ("no difficulty breathing, just a runny nose", "en", "teleconsultation"),
    ("no unconsciousness, he is awake and talking", "en", "teleconsultation"),
    ("no bleeding now, the cut already stopped", "en", "teleconsultation"),
    ("no chest pressure, only acidity", "en", "teleconsultation"),
    ("nahi, saans theek hai, sirf jukam hai", "hinglish", "teleconsultation"),
    ("seene me dard nahi hai, sirf gas hai", "hinglish", "teleconsultation"),
    ("behosh nahi hua, sirf chakkar aaya tha", "hinglish", "teleconsultation"),
    ("bleeding band ho gayi hai, ab dard nahi hai", "hinglish", "teleconsultation"),
    ("daura nahi, sirf neend me jhatka laga", "hinglish", "teleconsultation"),
    ("bachhe ko bukhar nahi hai, sirf halki khansi hai", "hinglish", "teleconsultation"),
    ("koi chest pain nahi, bas thakaan hai", "en", "teleconsultation"),
    ("my child does not have dehydration, he is urinating fine", "en", "teleconsultation"),
    ("she has no suicidal thoughts now", "en", "teleconsultation"),
    ("no stroke, just a pinched nerve in the arm", "en", "teleconsultation"),
    ("the bleeding has stopped completely", "en", "teleconsultation"),
    ("he woke up fine, no fainting today", "en", "teleconsultation"),
]

# ---------------------------------------------------------------------------
# Near-miss non-emergencies (mild, similar-sounding) -> non-emergency
# ---------------------------------------------------------------------------
NEAR_MISS = [
    ("mild chest discomfort after eating spicy food", "en", "teleconsultation"),
    ("slight cough and a runny nose for two days", "en", "paramedic_home_visit"),
    ("a bit dizzy but fully awake and walking", "en", "teleconsultation"),
    ("small paper cut that already clotted", "en", "teleconsultation"),
    ("numb pinky finger after sleeping on my arm", "en", "teleconsultation"),
    ("muscle twitch in my eyelid", "en", "teleconsultation"),
    ("my 6-year-old has a mild fever and is playing", "en", "paramedic_home_visit"),
    ("feeling a little low and tired lately", "en", "teleconsultation"),
    ("mild thirst after a long walk", "en", "teleconsultation"),
    ("halka seene me jalan khaana khaane ke baad", "hinglish", "teleconsultation"),
    ("halki khansi aur jukam do din se", "hinglish", "paramedic_home_visit"),
    ("thoda chakkar aaya tha par ab theek hoon", "hinglish", "teleconsultation"),
    ("choti si kata hua hai jo band ho gaya", "hinglish", "teleconsultation"),
    ("so kar utha to haath sunn tha", "hinglish", "teleconsultation"),
    ("aankh ke upar halka sa fadakna", "hinglish", "teleconsultation"),
    ("6 saal ke bache ko halka bukhar hai aur khel raha hai", "hinglish", "paramedic_home_visit"),
    ("thoda udaas hoon par koi khatra nahi", "hinglish", "teleconsultation"),
    ("chakar aane par halki pyaas lagi thi", "hinglish", "teleconsultation"),
    ("छाती में हल्की जलन खाने के बाद", "hi", "teleconsultation"),
    ("हल्की खांसी और जुकाम दो दिन से", "hi", "paramedic_home_visit"),
    ("थोड़ा चक्कर आया था पर अब ठीक हूँ", "hi", "teleconsultation"),
    ("छोटी सी कटी हुई है जो बंद हो गई", "hi", "teleconsultation"),
    ("सो कर उठा तो हाथ सुन्न था", "hi", "teleconsultation"),
    ("6 साल के बच्चे को हल्का बुखार है और खेल रहा है", "hi", "paramedic_home_visit"),
    ("mild acid reflux, no chest pain", "en", "teleconsultation"),
    ("occasional dry cough only at night", "en", "teleconsultation"),
    ("stood up too fast and felt lightheaded for a second", "en", "teleconsultation"),
    ("minor nosebleed from dry air that stopped", "en", "teleconsultation"),
    ("arm fell asleep from sitting on it", "en", "teleconsultation"),
    ("eye twitching from lack of sleep", "en", "teleconsultation"),
    ("my toddler has a low-grade fever but is active", "en", "paramedic_home_visit"),
    ("felt sad for a few days but no self-harm thoughts", "en", "teleconsultation"),
    ("slightly dry mouth after exercise", "en", "teleconsultation"),
    ("halki khansi hai par saans bilkul theek hai", "hinglish", "teleconsultation"),
    ("pet me halka dard hai par vomit nahi hua", "hinglish", "teleconsultation"),
    ("thoda kamzor mehsoos ho raha hai par kha pee raha hoon", "hinglish", "teleconsultation"),
    ("halka sar dard hai subah se", "hinglish", "teleconsultation"),
    ("pair me halki moch hai, chal sakta hoon", "hinglish", "teleconsultation"),
    ("halka gas aur acidity hai", "hinglish", "teleconsultation"),
    ("slight sneezing and watery eyes, seasonal allergy", "en", "teleconsultation"),
]

# ---------------------------------------------------------------------------
# Emergencies hidden inside longer narrative text -> emergency_112
# ---------------------------------------------------------------------------
HIDDEN = [
    ("I was cooking dinner and my father suddenly sat down and said he has crushing chest pain and can't breathe", "en", "chest_pain;breathlessness"),
    ("my mother slipped in the bathroom and now she is unconscious and there is blood on the floor", "en", "unconsciousness;severe_bleeding"),
    ("he was watching TV when suddenly his face drooped and he couldn't lift his arm or speak", "en", "stroke_symptoms"),
    ("my daughter has been having a fever since morning and just now she started shaking and jerking uncontrollably", "en", "seizure"),
    ("we were on a call and mid-sentence my grandfather said his chest hurts, then he collapsed and stopped responding", "en", "chest_pain;unconsciousness"),
    ("after the accident he has a deep cut on his leg and the bleeding won't stop even with a cloth on it", "en", "severe_bleeding"),
    ("my wife just gave birth two weeks ago and she says she wants to hurt herself and end everything", "en", "suicidal_ideation"),
    ("the 2-month-old has not been feeding and now has a very high fever and is limp", "en", "high_fever_infant"),
    ("grandmother has had vomiting and diarrhoea all day and now her eyes look sunken and she has not passed urine", "en", "severe_dehydration"),
    ("I have a history of asthma and right now I feel like I am suffocating and my lips are turning blue", "en", "breathlessness"),
    ("papa raat se saans nahi le pa rahe the, ab seene me bhi dard hai aur paseena aa raha hai", "hinglish", "chest_pain;breathlessness"),
    ("bathroom me mummy gir gayi aur ab behosh hai aur sar se khoon beh raha hai", "hinglish", "unconsciousness;severe_bleeding"),
    ("TV dekh raha tha aur achanak muh tedha ho gaya aur haath nahi uth raha tha", "hinglish", "stroke_symptoms"),
    ("bache ko subah se bukhar tha aur ab jhatke aa rahe hain aur muh se jhaag nikal raha hai", "hinglish", "seizure;high_fever_infant"),
    ("call pe baat karte waqt dada ji ne kaha seene me dard hai, phir wo behosh ho gaye", "hinglish", "chest_pain;unconsciousness"),
    ("accident ke baad pair me gehri chot hai aur khoon ruk hi nahi raha", "hinglish", "severe_bleeding"),
    ("didi bol rahi thi ki ab jeene ka mann nahi hai aur sab khatam karna hai", "hinglish", "suicidal_ideation"),
    ("2 mahine ka bacha doodh nahi pi raha aur tez bukhar me tap raha hai", "hinglish", "high_fever_infant"),
    ("dadi ko subah se ulti aur dast hai, ab aankhen dhasi hui hain aur peshab nahi aa raha", "hinglish", "severe_dehydration"),
    ("पापा को रात से सांस नहीं आ रही थी, अब सीने में दर्द और पसीना भी आ रहा है", "hi", "chest_pain;breathlessness"),
]


def _rows():
    rows = []
    seq = 1

    def add(uid, text, lang, care_type, urgency, red_flags, source):
        nonlocal seq
        rows.append({
            "id": uid, "user_input": text, "language": lang, "age": "",
            "sex": "", "conditions": "", "care_type": care_type, "urgency": urgency,
            "red_flags": red_flags, "source": source, "reviewed_by_human": F,
        })
        seq += 1

    # Preserve the original 9 rows verbatim (handwritten_gold / synthetic).
    original = [
        ("VIG_022", "Severe crushing chest pain radiating to left arm with cold sweat", "en", "55", "male", "hypertension", "emergency_112", "emergency", "chest_pain", "handwritten_gold"),
        ("VIG_023", "Papa ko seene me tez dard hai aur paseena aa raha hai saans nahi le pa rahe", "hinglish", "60", "male", "diabetes", "emergency_112", "emergency", "chest_pain;breathlessness", "handwritten_gold"),
        ("VIG_024", "मरीज अचानक बेहोश होकर गिर पड़ा और कोई जवाब नहीं दे रहा है", "hi", "50", "male", "", "emergency_112", "emergency", "unconsciousness", "synthetic"),
        ("VIG_025", "Face drooping on right side and suddenly unable to speak or move right arm", "en", "72", "female", "hypertension", "emergency_112", "emergency", "stroke_symptoms", "synthetic"),
        ("VIG_026", "Khoon ki ulti ho rahi hai aur behoshi jaisi halat hai", "hinglish", "45", "male", "", "emergency_112", "emergency", "severe_bleeding", "handwritten_gold"),
        ("VIG_027", "Pregnant woman in 8th month with heavy vaginal bleeding and severe pain", "en", "27", "female", "pregnant", "emergency_112", "emergency", "severe_bleeding", "synthetic"),
        ("VIG_028", "Bachhe ne galti se floor cleaner ya poison pi liya hai", "hinglish", "4", "male", "", "emergency_112", "emergency", "unconsciousness", "handwritten_gold"),
        ("VIG_029", "Heavy bleeding from leg wound after bike accident, not stopping with pressure", "en", "24", "male", "", "emergency_112", "emergency", "severe_bleeding", "synthetic"),
        ("VIG_030", "Patient is having continuous epileptic seizures and shaking violently", "en", "19", "male", "epilepsy", "emergency_112", "emergency", "seizure", "synthetic"),
    ]
    for (uid, text, lang, age, sex, cond, ct, urg, rf, src) in original:
        rows.append({
            "id": uid, "user_input": text, "language": lang, "age": age, "sex": sex,
            "conditions": cond, "care_type": ct, "urgency": urg, "red_flags": rf,
            "source": src, "reviewed_by_human": F,
        })

    # Positives (12 per flag).
    for flag, phrases in POSITIVES.items():
        for i, (text, lang) in enumerate(phrases, 1):
            add(f"RF_{flag}_{i:02d}", text, lang, "emergency_112", "emergency", flag, "ai_drafted")

    # Negated.
    for i, (text, lang, ct) in enumerate(NEGATED, 1):
        add(f"RF_NEG_{i:02d}", text, lang, ct, "same_day", "", "ai_drafted")

    # Near-miss.
    for i, (text, lang, ct) in enumerate(NEAR_MISS, 1):
        add(f"RF_NEAR_{i:02d}", text, lang, ct, "same_day", "", "ai_drafted")

    # Hidden emergencies.
    for i, (text, lang, rf) in enumerate(HIDDEN, 1):
        add(f"RF_HID_{i:02d}", text, lang, "emergency_112", "emergency", rf, "ai_drafted")

    return rows


def main():
    rows = _rows()
    fields = ["id", "user_input", "language", "age", "sex", "conditions",
              "care_type", "urgency", "red_flags", "source", "reviewed_by_human"]
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    n_pos = sum(1 for r in rows if r["care_type"] == "emergency_112")
    n_neg = sum(1 for r in rows if r["id"].startswith("RF_NEG"))
    n_near = sum(1 for r in rows if r["id"].startswith("RF_NEAR"))
    n_hid = sum(1 for r in rows if r["id"].startswith("RF_HID"))
    print(f"Wrote {len(rows)} rows to {OUT}")
    print(f"  positives(emergency): {n_pos}, negated: {n_neg}, near-miss: {n_near}, hidden: {n_hid}")


if __name__ == "__main__":
    main()
