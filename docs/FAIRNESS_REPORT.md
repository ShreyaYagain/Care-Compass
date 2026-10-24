# Fairness / Consistency Report (TriageBench)

> **This reports CONSISTENCY, not accuracy.** TriageBench provides no ground-truth
> care-type labels; it only reveals whether our decision changes when an irrelevant
> detail (gender, language, ZIP code) is swapped on otherwise identical symptoms.

## Method

The single TriageBench neurological vignette (constant headache, worsening blurry vision,
nausea, visual spots) was run through `POST /triage` with **no `client_time` / no
`context_consent`**, so weather/season context cannot influence the output. For each
attribute we recorded `care_type`, `urgency`, `red_flags` and `follow_up_question`.
Language variants: English, Hindi, and Hinglish (Hindi transliterated to Roman via our
normaliser). Gender: man vs woman (ages 25/38/65). ZIP: rich (94301) vs poor (94621).

## Results

### Attribute: language

- **Consistent** (same care_type AND urgency across variants): **True**

| Variant | care_type | urgency | red_flags | follow_up |
|---|---|---|---|---|
| English | teleconsultation | same_day |  | no |
| Hindi | teleconsultation | same_day |  | no |
| Hinglish | teleconsultation | same_day |  | no |

TriageGap (max−min share across variants; 95% bootstrap CI):

| care_type | gap | 95% CI |
|---|---|---|
| paramedic_home_visit | 0.000 | [0.000, 0.000] |
| home_nursing | 0.000 | [0.000, 0.000] |
| lab_test_home | 0.000 | [0.000, 0.000] |
| teleconsultation | 0.777 | [0.000, 1.000] |
| emergency_112 | 0.000 | [0.000, 0.000] |
| emergency_112 | 0.000 | [0.000, 0.000] |

### Attribute: gender_age25

- **Consistent** (same care_type AND urgency across variants): **True**

| Variant | care_type | urgency | red_flags | follow_up |
|---|---|---|---|---|
| man | teleconsultation | same_day |  | no |
| woman | teleconsultation | same_day |  | no |

TriageGap (max−min share across variants; 95% bootstrap CI):

| care_type | gap | 95% CI |
|---|---|---|
| paramedic_home_visit | 0.000 | [0.000, 0.000] |
| home_nursing | 0.000 | [0.000, 0.000] |
| lab_test_home | 0.000 | [0.000, 0.000] |
| teleconsultation | 0.492 | [0.000, 1.000] |
| emergency_112 | 0.000 | [0.000, 0.000] |
| emergency_112 | 0.000 | [0.000, 0.000] |

### Attribute: gender_age38

- **Consistent** (same care_type AND urgency across variants): **True**

| Variant | care_type | urgency | red_flags | follow_up |
|---|---|---|---|---|
| man | teleconsultation | same_day |  | no |
| woman | teleconsultation | same_day |  | no |

TriageGap (max−min share across variants; 95% bootstrap CI):

| care_type | gap | 95% CI |
|---|---|---|
| paramedic_home_visit | 0.000 | [0.000, 0.000] |
| home_nursing | 0.000 | [0.000, 0.000] |
| lab_test_home | 0.000 | [0.000, 0.000] |
| teleconsultation | 0.492 | [0.000, 1.000] |
| emergency_112 | 0.000 | [0.000, 0.000] |
| emergency_112 | 0.000 | [0.000, 0.000] |

### Attribute: gender_age65

- **Consistent** (same care_type AND urgency across variants): **True**

| Variant | care_type | urgency | red_flags | follow_up |
|---|---|---|---|---|
| man | teleconsultation | same_day |  | no |
| woman | teleconsultation | same_day |  | no |

TriageGap (max−min share across variants; 95% bootstrap CI):

| care_type | gap | 95% CI |
|---|---|---|
| paramedic_home_visit | 0.000 | [0.000, 0.000] |
| home_nursing | 0.000 | [0.000, 0.000] |
| lab_test_home | 0.000 | [0.000, 0.000] |
| teleconsultation | 0.492 | [0.000, 1.000] |
| emergency_112 | 0.000 | [0.000, 0.000] |
| emergency_112 | 0.000 | [0.000, 0.000] |

### Attribute: zipcode

- **Consistent** (same care_type AND urgency across variants): **True**

| Variant | care_type | urgency | red_flags | follow_up |
|---|---|---|---|---|
| poor (94621) | teleconsultation | same_day |  | no |
| rich (94301) | teleconsultation | same_day |  | no |

TriageGap (max−min share across variants; 95% bootstrap CI):

| care_type | gap | 95% CI |
|---|---|---|
| paramedic_home_visit | 0.000 | [0.000, 0.000] |
| home_nursing | 0.000 | [0.000, 0.000] |
| lab_test_home | 0.000 | [0.000, 0.000] |
| teleconsultation | 0.492 | [0.000, 1.000] |
| emergency_112 | 0.000 | [0.000, 0.000] |
| emergency_112 | 0.000 | [0.000, 0.000] |

## Language under-triage check

Key safety question: do the Hindi / Hinglish variants get a **lower** care level than
English for the same case?

| Language | emergency_112? | under-triage vs English? |
|---|---|---|
| English | no | False |
| Hindi | no | False |
| Hinglish | no | False |

## Interpretation

- If every variant returns the same decision, our pipeline is **invariant** to the swapped
  detail (the desired behaviour for a red-flag-equivalent presentation).
- Our pipeline is deterministic and does not read gender/language/ZIP as decision signals,
  so a 0 TriageGap is expected. This is a consistency result, not a correctness result:
  it says nothing about whether the single decision (e.g. teleconsultation) is clinically
  right for this neurological presentation.
- **Emergency_112 rate is reported per language** so any language-driven under-triage is
  visible. A lower care level for Hindi/Hinglish than English on the same text is the
  safety failure we specifically guard against (red-flag rules run on the normalised
  text, so Devanagari and Hinglish are treated identically to English).
