import csv
from pathlib import Path
from app.schemas import TriageRequest, Location, ChatMessage
from app.core.pipeline import run_triage_pipeline

DATA_DIR = Path(__file__).resolve().parent / "data"
URGENCY_LEVELS = {"scheduled": 0, "same_day": 1, "emergency": 2}


def evaluate():
    test_file = DATA_DIR / "val.csv"
    if not test_file.exists():
        test_file = DATA_DIR / "train.csv"

    rows = []
    with open(test_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total = len(rows)
    if total == 0:
        print("No evaluation cases found.")
        return

    correct_care = 0
    correct_urgency = 0
    under_triage_count = 0
    emergency_true_count = 0
    emergency_recalled = 0
    follow_up_count = 0

    per_language_stats = {}

    for row in rows:
        u_input = row["user_input"]
        true_care = row["care_type"]
        true_urgency = row["urgency"]
        lang = row.get("language", "auto")

        # Turn 1
        req1 = TriageRequest(
            user_input=u_input,
            language=lang,
            location=Location(lat=28.54, lng=77.27),
            conversation_history=[],
        )
        resp1 = run_triage_pipeline(req1)

        final_resp = resp1
        # If follow-up question requested, simulate natural user response
        if resp1.follow_up_question:
            follow_up_count += 1
            # Answer: no breathing difficulty / mild / 2 days depending on context
            reply = "No breathing difficulty, pain is moderate"
            hist = [
                ChatMessage(role="user", text=u_input),
                ChatMessage(role="assistant", text=resp1.follow_up_question),
            ]
            req2 = TriageRequest(
                user_input=reply,
                language=lang,
                location=Location(lat=28.54, lng=77.27),
                conversation_history=hist,
            )
            final_resp = run_triage_pipeline(req2)

        pred_care = final_resp.care_type
        pred_urgency = final_resp.urgency

        # Care accuracy
        if pred_care == true_care:
            correct_care += 1

        # Urgency accuracy
        if pred_urgency == true_urgency:
            correct_urgency += 1

        # Under-triage check: predicted urgency < true urgency
        t_level = URGENCY_LEVELS.get(true_urgency, 0)
        p_level = URGENCY_LEVELS.get(pred_urgency, 0)
        if p_level < t_level:
            under_triage_count += 1

        # Emergency recall check
        if true_urgency == "emergency":
            emergency_true_count += 1
            if pred_urgency == "emergency":
                emergency_recalled += 1

        # Language tracking
        if lang not in per_language_stats:
            per_language_stats[lang] = {"total": 0, "correct_urgency": 0}
        per_language_stats[lang]["total"] += 1
        if pred_urgency == true_urgency:
            per_language_stats[lang]["correct_urgency"] += 1

    care_acc = correct_care / total
    urgency_acc = correct_urgency / total
    under_triage_rate = under_triage_count / total
    emergency_recall = (emergency_recalled / emergency_true_count) if emergency_true_count > 0 else 1.0

    print("========================================")
    print("      CARECOMPASS MODEL EVALUATION      ")
    print("========================================")
    print(f"Total Test Cases:       {total}")
    print(f"Care Type Accuracy:     {care_acc:.2%}")
    print(f"Urgency Accuracy:       {urgency_acc:.2%}")
    print(f"Emergency Recall:       {emergency_recall:.2%} (Target >= 98%)")
    print(f"Under-Triage Rate:      {under_triage_rate:.2%} (Target < 5%)")
    print(f"Follow-ups Triggered:   {follow_up_count}")
    print("----------------------------------------")
    print("Per-Language Urgency Accuracy:")
    for l, st in per_language_stats.items():
        acc = st["correct_urgency"] / st["total"]
        print(f"  - {l:8s}: {acc:.2%} ({st['correct_urgency']}/{st['total']})")
    print("========================================")


if __name__ == "__main__":
    evaluate()
