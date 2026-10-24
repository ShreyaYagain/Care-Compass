# MMCQS Robustness Report

Robustness of the CareCompass pipeline on code-mixed Hinglish queries
(MMCQS / MedSumm, `ArkaAcharya/MMCQSD`, CC-BY-4.0).

## Groq OFF (n=500)

| Metric | Value |
|---|---|
| Decided | 33.4% |
| Follow-up | 66.6% |
| Defaulted to teleconsultation | 8.4% |
| Flagged emergency | 4.8% |
| Median latency (ms) | 12.3 |
| Crashes | 0 (must be 0) |

## Groq ON (n=0)

| Metric | Value |
|---|---|
| Decided | n/a |
| Follow-up | n/a |
| Defaulted to teleconsultation | n/a |
| Flagged emergency | n/a |
| Median latency (ms) | 0.0 |
| Crashes | 0 (must be 0) |


## Emergency-flagged queries (for manual check)

- emergency_112 / emergency flags=['breathlessness']
- emergency_112 / emergency flags=['seizure']
- emergency_112 / emergency flags=['seizure']
- emergency_112 / emergency flags=['seizure']
- emergency_112 / emergency flags=['seizure']
- emergency_112 / emergency flags=['seizure']
- emergency_112 / emergency flags=['seizure']
- emergency_112 / emergency flags=['seizure']
- emergency_112 / emergency flags=['seizure']
- emergency_112 / emergency flags=['seizure']
- emergency_112 / emergency flags=['seizure']
- emergency_112 / emergency flags=['seizure', 'unconsciousness']
- emergency_112 / emergency flags=['seizure']
- emergency_112 / emergency flags=['breathlessness']
- emergency_112 / emergency flags=['breathlessness']
- emergency_112 / emergency flags=['breathlessness']
- emergency_112 / emergency flags=['seizure']
- emergency_112 / emergency flags=['seizure']
- emergency_112 / emergency flags=['breathlessness']
- emergency_112 / emergency flags=[]
