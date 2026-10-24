# CareCompass Clinical Taxonomy & Classification Standards (v2 Official)

## Official Care Types
1. **paramedic_home_visit**: Acute or subacute symptoms (moderate fever, chills, respiratory distress, general malaise) where vital signs, oxygen saturation, blood sugar, and rapid clinical examination need in-person measurement at home.
2. **home_nursing**: Patients requiring procedural nursing care (wound dressings, suture removal, IV/IM injections, catheter care, palliative care, bedsore management).
3. **lab_test_home**: Diagnostic blood tests and sample collection at home (full body checkup, thyroid, lipid profile, CBC, routine screening).
4. **teleconsultation**: Virtual doctor consultations for medical advice, non-urgent symptoms, medication reviews, and second opinions.
5. **emergency_112**: Acute life-threatening conditions (chest pain, stroke symptoms, unconsciousness, severe respiratory failure, heavy hemorrhage). Immediate transport to the nearest emergency facility.

## Official Urgency Levels
- **emergency**: Immediate emergency medical intervention required; call 112/102 immediately.
- **same_day**: Requires medical evaluation or visit today (within 12-24 hours).
- **scheduled**: Routine or elective care that can be scheduled conveniently.

## Deterministic Mapping
Urgency is derived deterministically from care type via `CARE_TO_URGENCY`:
- `emergency_112` $\rightarrow$ `emergency`
- `home_nursing` $\rightarrow$ `same_day`
- `paramedic_home_visit` $\rightarrow$ `same_day`
- `teleconsultation` $\rightarrow$ `same_day`
- `lab_test_home` $\rightarrow$ `scheduled`
