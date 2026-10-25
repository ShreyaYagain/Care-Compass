# CareCompass: AI-assisted care navigation in English, Hindi and Hinglish

**Team:** [TEAM NAME — fill in]
**GitHub:** https://github.com/ShreyaYagain/Care-Compass

---

**What it does.** A person types or speaks a message in English, Hindi or Hinglish. CareCompass picks one of five care types (`paramedic_home_visit`, `home_nursing`, `lab_test_home`, `teleconsultation`, `emergency_112`), derives the urgency, explains the choice in short lines, and matches and books a caregiver by language, distance, skill and rating. An Android app and a REST API serve the same pipeline.

**How it works.**
1. *Input guard:* masks personal details and blocks prompt injection.
2. *Safety rules:* deterministic red-flag rules for the nine official flags (chest pain, breathlessness, unconsciousness, severe bleeding, stroke symptoms, seizure, high fever in an infant, suicidal ideation, severe dehydration). Rules can only raise urgency.
3. *ML model:* a calibrated TF-IDF character n-gram logistic regression (1.2 MB, under 1 ms) chooses the care type. A separate ML red-flag model supports the rules.
4. *LLM (DeepSeek):* reads unfamiliar wording into a fixed symptom list, screens meaning-based red flags, and gives an independent care-type opinion. The final care type is a weighted vote (0.4 ML, 0.6 LLM; the weights were chosen by judgement, not tuned). The LLM can never lower an emergency.
5. *Emergency policy:* an emergency needs a nine-flag with a quoted piece of the user's text, or the user's "Yes" to a confirmation question. Vague text, "not sure", weather or the LLM alone never trigger one.
6. *Follow-ups:* at most two turns, from a closed bank of fact-gathering questions. Injury and fever cards ask one field at a time, skipping anything already stated in the message.
7. *Matching and output guard:* score = 0.35 language + 0.30 proximity + 0.20 skill + 0.15 rating. The output never gives a diagnosis or medicine advice, and every result carries a "call 112 if it worsens" line.

**Evidence (honest).**
- Routing, exact-text grouped cross-validation on the 301 labelled official rows: about 0.91 accuracy, 0.887 macro-F1. The safety net (rules + ML red-flag model + LLM screen + confirmation question) caught all 56 emergency rows. The weakest class is `paramedic_home_visit` (0.77 recall).
- Calibration of P(emergency): ECE 0.078, Brier 0.028.
- Fresh-wording red-flag test (53 AI-drafted rows): keyword rules alone caught 2 of 35, and the ML red-flag model alone is weak. With the LLM screen plus the confirmation question, 0.97 of emergencies were caught, with no false alarms on the negatives we ran. The classifier alone over-triaged 8 of 18 non-emergencies, which is why emergencies require evidence.
- Not done: a live false-alarm measurement of the one-shot emergency policy with DeepSeek, the live follow-up rate, and validation on human-written messages. The test sets were drafted by AI and not reviewed by a clinician.

**Data and declarations.** Official dataset (340 rows, only about 54 unique texts, so numbers are optimistic). Synthetic test sets and 607 LLM paraphrases used for training only; the paraphrase gain is preliminary because paraphrases were generated from the whole set. Extra hospital and home-doctor caregivers are synthetic demo data and never change the official labels. Services used: DeepSeek (LLM), Android SpeechRecognizer (voice), Supabase (history and bookings, synthetic data only, row-level security), Open-Meteo (optional context, with consent), scikit-learn, multilingual-e5-small. No real patient data is stored.

**Limitations.** Tiny training data; wording outside the training data depends on the LLM; the LLM adds latency and a dependency (when it is down the system falls back to ML plus rules and asks a combined screening question); not a medical device and not clinically validated.

**Next steps.** Human-written validation set, clinician review of the red-flag lexicon, more diverse training data, measured follow-up and false-alarm rates.
