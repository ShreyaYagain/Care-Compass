"""Groq paraphrase augmentation (TRAINING ONLY, never validation).

For each (care_type, language) combination, generates 40+ distinct paraphrases of
the official examples via Groq. Outputs:
  - ml/data/augment_paraphrases.csv   (source=synthetic_llm, training only)
  - ml/data/augment_review.csv        (10% random sample for human spot-check,
                                       reviewed_by_human=false, blank human_label)

Emergencies are paraphrased from the official emergency seeds so the classifier
can learn emergency phrasing, but the RULE layer remains the only thing that
triggers emergency_112 at serving time.
"""
import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel, Field

from app.config import settings
from app.core.llm import groq_json, is_groq_available

DATA_DIR = Path(__file__).resolve().parent / "data"
OFFICIAL = DATA_DIR / "official" / "triage_dataset.jsonl"
OUT = DATA_DIR / "augment_paraphrases.csv"
REVIEW = DATA_DIR / "augment_review.csv"

PER_COMBO = 40
REVIEW_FRACTION = 0.10

URGENCY_BY_CARE = settings.CARE_TO_URGENCY


class ParaphraseOut(BaseModel):
    paraphrases: list[str] = Field(default_factory=list)


def load_official() -> dict[tuple[str, str], list[dict]]:
    by_key: dict[tuple[str, str], list[dict]] = {}
    with open(OFFICIAL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            req = item.get("request", {})
            resp = item.get("response", {})
            ct = resp.get("care_type")
            if ct is None:
                continue
            lang = (item.get("detected_language") or "English").strip()
            if lang not in ("English", "Hindi", "Hinglish"):
                lang = "Hinglish"
            by_key.setdefault((ct, lang), []).append({
                "text": req.get("user_input", ""),
                "red_flags": resp.get("red_flags", []),
            })
    return by_key


def generate_paraphrases(care_type: str, lang: str, seeds: list[dict]) -> list[dict]:
    if not is_groq_available():
        return []

    seed_texts = [s["text"] for s in seeds[:8]]
    red_flags_note = ""
    if care_type == "emergency_112":
        flags = sorted({f for s in seeds for f in s.get("red_flags", [])})
        red_flags_note = (
            f"\nThese are EMERGENCY messages with red flags: {flags}. "
            "Keep the emergency severity and at least one of those red flags in every paraphrase."
        )

    system = (
        "You are a medical triage dataset augmenter for an Indian home-care routing app. "
        f"Generate {PER_COMBO} DISTINCT natural paraphrases of the example patient messages "
        f"(care_type={care_type}, language={lang}). "
        f"{red_flags_note}\n"
        "Rules:\n"
        "- Same care need, same language, different wording (use a mix of family-relationship "
        "phrasing like 'papa', 'dadi', 'mummy' for Hindi/Hinglish).\n"
        "- Keep each paraphrase under 22 words.\n"
        "- Occasional realistic misspellings are allowed but the message must stay understandable.\n"
        "- Do not add symptoms that change the care type.\n"
        "- Return valid JSON with a single key 'paraphrases' (array of strings)."
    )

    user = "Example messages:\n" + "\n".join(f"- {t}" for t in seed_texts)

    # Try models in order (separate rate-limit pools on Groq).
    model_chain = [
        settings.GROQ_FAST_MODEL,
        settings.GROQ_MODEL,
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
    ]
    res = None
    for model in model_chain:
        if not model:
            continue
        res = groq_json(system=system, user=user, schema=ParaphraseOut, model=model)
        if res is not None:
            break
    if not res:
        return []

    out = []
    seen = {s["text"].lower() for s in seeds}
    for p in res.paraphrases or []:
        p = (p or "").strip()
        if not p or p.lower() in seen:
            continue
        seen.add(p.lower())
        out.append({
            "user_input": p,
            "language": lang,
            "care_type": care_type,
            "urgency": URGENCY_BY_CARE.get(care_type, "same_day"),
            "red_flags": ";".join(seeds[0].get("red_flags", [])) if seeds else "",
            "source": "synthetic_llm",
        })
    return out


def main():
    by_key = load_official()
    print(f"Official data: {sum(len(v) for v in by_key.values())} labeled rows across "
          f"{len(by_key)} (care_type, language) combos.")

    all_rows = []
    for (ct, lang), seeds in sorted(by_key.items()):
        rows = generate_paraphrases(ct, lang, seeds)
        print(f"  {ct:>22} / {lang:<9}: generated {len(rows)} paraphrases (seeds={len(seeds)})")
        all_rows.extend(rows)

    if not all_rows:
        print("No paraphrases generated (Groq unavailable?). Nothing written.")
        return

    for i, r in enumerate(all_rows, 1):
        r["id"] = f"AUG_{i:04d}"

    fields = ["id", "user_input", "language", "care_type", "urgency", "red_flags", "source"]
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(all_rows)
    print(f"Wrote {len(all_rows)} paraphrases -> {OUT}")

    rng = random.Random(42)
    sample = rng.sample(all_rows, max(1, int(len(all_rows) * REVIEW_FRACTION)))
    with open(REVIEW, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields + ["reviewed_by_human", "human_label"])
        w.writeheader()
        for r in sample:
            w.writerow({**r, "reviewed_by_human": "false", "human_label": ""})
    print(f"Wrote {len(sample)} rows ({REVIEW_FRACTION:.0%} spot-check) -> {REVIEW}")


if __name__ == "__main__":
    main()
