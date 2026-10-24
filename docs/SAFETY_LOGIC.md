# CareCompass Safety Architecture & Emergency Guardrails

## Core Safety Philosophy
**Under-triage is a catastrophic error; over-triage is a minor inconvenience.**
In acute clinical navigation, missing an acute coronary syndrome, stroke, or severe respiratory distress leads to patient harm or mortality. CareCompass enforces a multi-tier safety architecture ensuring zero missed emergencies.

```
Incoming Request (Text or Voice)
       │
       ▼
[Tier 1: Transliteration & Normalization]
  • Converts Devanagari to Roman
  • Maps spelling variants & handles negations
       │
       ▼
[Tier 2: Deterministic Red-Flag Safety Net (Bypasses ML)]
  • High-recall rule-based pattern matching
  • Runs on BOTH original & transliterated text
  • ANY HIGH red-flag immediately halts pipeline -> EMERGENCY RESPONSE
       │
       ▼
[Tier 3: Asymmetric Cost Urgency Decision]
  • Model outputs calibrated class probabilities
  • Minimizes expected loss:
      Cost(True=Immediate, Pred=Routine) = 10.0
      Cost(True=SameDay, Pred=Routine) = 4.0
       │
       ▼
[Tier 4: Clinical Risk Modifiers (Escalation Only)]
  • Infants (<1y) & Elderly (>75y) with fever/breathing -> +1 level
  • Pregnancy + bleeding/pain -> Immediate
  • Chronic comorbidities (diabetes, COPD) -> +1 level
  • >5 days symptoms -> at least same_day
       │
       ▼
[Tier 5: Confidence Threshold Fallback]
  • If confidence < 0.55 -> Escalate one urgency level
```

## Hard Constraints
1. **Never Diagnose or Prescribe**: The system routes only. Explanations state recommended care settings (e.g., "Paramedic home visit recommended"), never a diagnostic condition (e.g., "Likely pneumonia") or drug recommendation.
2. **Deterministic Emergency Response**: If an emergency is triggered, matching is skipped. The app returns emergency contact numbers (`112`, `102`), immediate first-aid / safety steps in the user's language, and prompts immediate transfer.
3. **Audit Logging**: Every incoming request, matched flags, class probabilities, and decision trails are committed to SQLite `AuditLog`.
