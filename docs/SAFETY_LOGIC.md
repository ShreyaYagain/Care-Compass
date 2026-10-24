# Safety Logic & Red-Flag Escalation Protocol

## 1. Overview
In CareCompass, the emergency bypass layer guards patient safety. If a high-severity red flag is detected, or the user confirms a critical symptom, the system routes directly to emergency services (`emergency_112` / `emergency`), bypassing home visits and caregiver matching.

## 2. Official 9 Red-Flag Categories (IIIT-Delhi Hackathon Standard)
The platform evaluates inputs against the 9 official red-flag IDs:

| # | Official Red-Flag ID | Core Clinical Symptoms | Associated Mappings from Extended Triggers |
|---|---|---|---|
| 1 | `chest_pain` | Chest pain, pressure, tightness, suspected myocardial infarction | Angina, heart attack |
| 2 | `breathlessness` | Shortness of breath, suffocating, gasping, inability to breathe | Anaphylaxis, throat swelling, cyanosis (blue lips) |
| 3 | `unconsciousness` | Unresponsive, fainted, blacked out, collapse | Severe head trauma, acute poisoning / overdose |
| 4 | `severe_bleeding` | Uncontrolled active hemorrhage, spurting blood | Vomiting blood (hematemesis), pregnancy bleeding / acute pain, severe acid/fire burns, venomous snake bites |
| 5 | `stroke_symptoms` | Face drooping, unilateral weakness, slurred speech, acute paralysis | Lakwa, falij, hemiplegia |
| 6 | `seizure` | Convulsions, epilepsy fit, continuous violent shaking | Daura, mirgi, active status epilepticus |
| 7 | `high_fever_infant` | High fever in neonates/infants (< 3 months, or temp > 104°F) | Navjat shishu bukhar |
| 8 | `suicidal_ideation` | Self-harm statements, suicide crisis, desire to end life | Aatmahatya crisis |
| 9 | `severe_dehydration` | Extreme volume depletion, sunken eyes, anuria (>24 hrs), collapse | Ulti/dast severe dehydration |

## 3. Emergency Evaluation Rules
An emergency response (`care_type="emergency_112"`, `urgency="emergency"`, `matched_caregivers=[]`) is triggered **only** under three conditions:
1. **Red-Flag Match**: A non-negated high-severity red flag from the 9 official IDs is detected.
2. **Follow-Up Affirmation**: The user answers "Yes" to a safety follow-up inquiry concerning an emergency symptom.
3. **Calibrated ML Confidence**: The triage classifier predicts $P(\text{emergency\_112}) \ge 0.50$.

*Under no circumstances do low confidence, vague symptoms, empty input, or "Not sure" answers trigger an emergency referral.*
