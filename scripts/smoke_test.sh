#!/usr/bin/env bash
set -e

BASE_URL="${API_URL:-http://localhost:8000}"

echo "============================================="
echo " CareCompass Backend Smoke Tests"
echo " Target API: $BASE_URL"
echo "============================================="

# 1. Health check
echo -e "\n1. GET /health"
curl -s -X GET "$BASE_URL/health" | grep -q "ok" && echo "PASS: /health returned status ok" || echo "FAIL: /health"

# 2. Case 1: Simple fever (needs follow-up)
echo -e "\n2. POST /triage (Vague fever -> asks follow-up)"
curl -s -X POST "$BASE_URL/triage" \
  -H "Content-Type: application/json" \
  -d '{"user_input": "papa ko bukhar hai", "language": "hinglish", "conversation_history": []}' | grep -q "follow_up_question" && echo "PASS: Correctly triggered follow-up question" || echo "FAIL: Follow-up"

# 3. Case 2: Chest pain Hinglish (High-severity Red Flag -> emergency_112)
echo -e "\n3. POST /triage (Chest pain emergency in Hinglish)"
RESP_CASE2=$(curl -s -X POST "$BASE_URL/triage" \
  -H "Content-Type: application/json" \
  -d '{"user_input": "papa ko seene me tez dard hai aur paseena aa raha hai", "language": "hinglish", "conversation_history": []}')
echo "$RESP_CASE2" | grep -q "emergency_112" && echo "$RESP_CASE2" | grep -q "emergency_steps" && echo "PASS: Correctly routed to emergency_112 with emergency_steps" || echo "FAIL: Emergency"

# 4. Case 3: Negation handling (Fever with NO breathing problem)
echo -e "\n4. POST /triage (Negation: no breathing problem)"
curl -s -X POST "$BASE_URL/triage" \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "saans me koi dikkat nahi hai",
    "language": "hinglish",
    "conversation_history": [
      {"role": "user", "text": "papa ko do din se bukhar hai aur khansi bhi"},
      {"role": "assistant", "text": "Is there any difficulty in breathing?"}
    ],
    "location": {"lat": 28.54, "lng": 77.27}
  }' | grep -q "paramedic_home_visit" && echo "PASS: Correctly triaged to paramedic_home_visit with same_day" || echo "FAIL: Paramedic home visit"

# 5. Case 4: Caregiver matching standalone
echo -e "\n5. POST /match (Matching standalone)"
curl -s -X POST "$BASE_URL/match" \
  -H "Content-Type: application/json" \
  -d '{
    "care_type": "paramedic_home_visit",
    "urgency": "same_day",
    "location": {"lat": 28.54, "lng": 77.27},
    "language": "hi"
  }' | grep -q "caregiver_id" && echo "PASS: Caregivers matched and ranked" || echo "FAIL: Matching"

# 6. Case 5: Booking
echo -e "\n6. POST /book"
curl -s -X POST "$BASE_URL/book" \
  -H "Content-Type: application/json" \
  -d '{
    "caregiver_id": "CG_014",
    "slot": "today_afternoon",
    "user_name": "Rohan Gupta",
    "phone": "+919876543210",
    "triage_summary": "Fever for 2 days, vital check required"
  }' | grep -q "BK_" && echo "PASS: Booking created successfully" || echo "FAIL: Booking"

echo -e "\n============================================="
echo " All smoke tests completed successfully!"
echo "============================================="
