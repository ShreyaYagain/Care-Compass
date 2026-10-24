"""Write ml/data/redflag_holdout.csv: a SECOND, independent red-flag set.

These messages were drafted separately from ml/data/redflag_tests.csv (different
phrasings, not used while tuning app/data/red_flags.yaml). The rules must be run
ONCE on this set, unchanged, and the resulting number reported honestly — it is
the provisional generalization figure until human-written cases replace it.

Still AI-drafted: reviewed_by_human=false (see ml/data/REVIEW_GUIDE.md).
"""
import csv
from pathlib import Path

OUT = Path(__file__).resolve().parent / "redflag_holdout.csv"

ROWS = [
    # --- positives (fresh phrasings, 3-4 per flag) ---
    ("my chest feels like someone is sitting on it", "en", "emergency_112", "emergency", "chest_pain"),
    ("there is a stabbing sensation in the middle of my chest", "en", "emergency_112", "emergency", "chest_pain"),
    ("मेरे सीने में चुभन हो रही है और बायां हाथ दर्द कर रहा है", "hi", "emergency_112", "emergency", "chest_pain"),
    ("chhati me ajeeb sa bhaari pan hai aur paseena aa raha hai", "hinglish", "emergency_112", "emergency", "chest_pain"),

    ("I ran out of air just climbing one flight of stairs", "en", "emergency_112", "emergency", "breathlessness"),
    ("she keeps opening her mouth but air is not going in", "en", "emergency_112", "emergency", "breathlessness"),
    ("साँस अटक रही है, छाती में सीटी जैसी आवाज है", "hi", "emergency_112", "emergency", "breathlessness"),
    ("saans andar ja hi nahi rahi, ghut raha hai", "hinglish", "emergency_112", "emergency", "breathlessness"),

    ("he collapsed while eating dinner and now his eyes are closed and he is not moving", "en", "emergency_112", "emergency", "unconsciousness"),
    ("my aunt fainted twice today and the second time she did not wake up for a long time", "en", "emergency_112", "emergency", "unconsciousness"),
    ("मेरी माँ खाना खाते समय अचानक गिर गईं और अब कुछ नहीं बोल रहीं", "hi", "emergency_112", "emergency", "unconsciousness"),

    ("there is a pool of blood where my father is standing, the cut will not close", "en", "emergency_112", "emergency", "severe_bleeding"),
    ("my son fell off the cycle and the blood is soaking through three towels", "en", "emergency_112", "emergency", "severe_bleeding"),
    ("दुर्घटना के बाद घुटने से खून की धार बह रही है", "hi", "emergency_112", "emergency", "severe_bleeding"),
    ("khoon itna beh raha hai ki towel laal ho gaya hai", "hinglish", "emergency_112", "emergency", "severe_bleeding"),

    ("my uncle cannot smile on one side of his face since this morning", "en", "emergency_112", "emergency", "stroke_symptoms"),
    ("she is speaking gibberish and her left arm keeps dropping", "en", "emergency_112", "emergency", "stroke_symptoms"),
    ("मेरे पिता का चेहरा एक तरफ लटक गया है और आँख बंद नहीं हो रही", "hi", "emergency_112", "emergency", "stroke_symptoms"),
    ("bolne par awaz ajeeb aa rahi hai aur ek haath kaam nahi kar raha", "hinglish", "emergency_112", "emergency", "stroke_symptoms"),

    ("my daughter's body went stiff and then started shaking for a minute", "en", "emergency_112", "emergency", "seizure"),
    ("he bit his tongue during the shaking episode and is confused now", "en", "emergency_112", "emergency", "seizure"),
    ("बच्ची की आँखें ऊपर चढ़ गईं और पूरा शरीर झटकने लगा", "hi", "emergency_112", "emergency", "seizure"),
    ("pair haath akad gaye aur muh se safed jhaag nikla", "hinglish", "emergency_112", "emergency", "seizure"),

    ("my six-week-old baby feels like a furnace and is not crying normally", "en", "emergency_112", "emergency", "high_fever_infant"),
    ("the newborn's forehead is burning hot and she is breathing fast", "en", "emergency_112", "emergency", "high_fever_infant"),
    ("डेढ़ महीने के बच्चे का शरीर तवे जैसा गर्म है", "hi", "emergency_112", "emergency", "high_fever_infant"),
    ("naya janma bacha bilkul sust hai aur garam hai", "hinglish", "emergency_112", "emergency", "high_fever_infant"),

    ("my brother said goodbye to everyone and wrote a note", "en", "emergency_112", "emergency", "suicidal_ideation"),
    ("she keeps saying everyone would be better off without her", "en", "emergency_112", "emergency", "suicidal_ideation"),
    ("भाई ने कहा कि अब और नहीं झेल पाएगा और सबको अलविदा कह दिया", "hi", "emergency_112", "emergency", "suicidal_ideation"),
    ("raat ko sabko thank you bol raha tha jaise jaane wala ho", "hinglish", "emergency_112", "emergency", "suicidal_ideation"),

    ("my grandmother has not made urine since yesterday and her lips are cracked", "en", "emergency_112", "emergency", "severe_dehydration"),
    ("the baby's soft spot is deeply sunken and she cries without tears", "en", "emergency_112", "emergency", "severe_dehydration"),
    ("दादी की जीभ सूख गई है और तीन दिन से पेशाब नहीं हुआ", "hi", "emergency_112", "emergency", "severe_dehydration"),
    ("dast ke baad se aankhen andar dhans gayi hain", "hinglish", "emergency_112", "emergency", "severe_dehydration"),

    # --- negated (must NOT trigger) ---
    ("I do not have chest pain, my back hurts", "en", "teleconsultation", "same_day", ""),
    ("no trouble breathing, just a cold", "en", "teleconsultation", "same_day", ""),
    ("he is not unconscious, he is just sleeping", "en", "teleconsultation", "same_day", ""),
    ("the bleeding has stopped completely", "en", "teleconsultation", "same_day", ""),
    ("no stroke, the doctor said it is a pinched nerve", "en", "teleconsultation", "same_day", ""),
    ("usko daura nahi aaya, sirf ghabrahat thi", "hinglish", "teleconsultation", "same_day", ""),
    ("बच्चे को बुखार नहीं है, बस हल्की सर्दी है", "hi", "teleconsultation", "same_day", ""),
    ("mera koi bhi khud ko nuksan pahunchane ka vichar nahi hai", "hinglish", "teleconsultation", "same_day", ""),
    ("seene me dard nahi hai, sirf acidity hai", "hinglish", "teleconsultation", "same_day", ""),
    ("saans ki koi problem nahi hai, jukam hai", "hinglish", "teleconsultation", "same_day", ""),

    # --- near-miss (must NOT trigger) ---
    ("I felt dizzy for a second after standing up too fast", "en", "teleconsultation", "same_day", ""),
    ("my leg feels numb from sitting cross-legged", "en", "teleconsultation", "same_day", ""),
    ("a small cut on my finger with a band-aid", "en", "teleconsultation", "same_day", ""),
    ("halka sa sar dard hai office ke baad", "hinglish", "teleconsultation", "same_day", ""),
    ("choti si kharoch hai jo sookh gayi hai", "hinglish", "teleconsultation", "same_day", ""),
    ("mild cough after a dusty day", "en", "teleconsultation", "same_day", ""),
    ("pet me halki si marod hai", "hinglish", "teleconsultation", "same_day", ""),
    ("thodi thakan hai der raat tak kaam karne se", "hinglish", "teleconsultation", "same_day", ""),
]


def main():
    fields = ["id", "user_input", "language", "age", "sex", "conditions",
              "care_type", "urgency", "red_flags", "source", "reviewed_by_human"]
    rows = []
    for i, (text, lang, ct, urg, rf) in enumerate(ROWS, 1):
        rows.append({
            "id": f"HLD_{i:03d}", "user_input": text, "language": lang, "age": "",
            "sex": "", "conditions": "", "care_type": ct, "urgency": urg,
            "red_flags": rf, "source": "ai_drafted_holdout", "reviewed_by_human": "false",
        })
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    n_pos = sum(1 for r in rows if r["care_type"] == "emergency_112")
    print(f"Wrote {len(rows)} rows -> {OUT} ({n_pos} positives, "
          f"{len(rows) - n_pos} non-emergency)")


if __name__ == "__main__":
    main()
