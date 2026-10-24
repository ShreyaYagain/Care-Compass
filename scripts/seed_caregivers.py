"""Seed the Supabase `caregivers` table from ml/data/official/caregivers.csv.

Run after applying supabase/schema.sql:

    python scripts/seed_caregivers.py

Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the environment (or .env).
"""
import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.db.supabase_client import get_supabase, supabase_available

CSV_PATH = Path(__file__).resolve().parent.parent / "ml" / "data" / "official" / "caregivers.csv"


def _split(value: str) -> list:
    if not value:
        return []
    return [s.strip() for s in value.split(";") if s.strip()]


def main() -> None:
    if not CSV_PATH.exists():
        print(f"caregivers.csv not found at {CSV_PATH}")
        sys.exit(1)
    if not supabase_available():
        print("Supabase not configured (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY). Nothing to seed.")
        sys.exit(1)

    client = get_supabase()
    if client is None:
        print("Could not initialise Supabase client.")
        sys.exit(1)

    rows = []
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "id": row["caregiver_id"],
                "name": row["name"],
                "role": row["role"],
                "qualification": row.get("qualification") or "",
                "languages": _split(row.get("languages", "")),
                "rating": float(row.get("rating") or 4.0),
                "phone": None,
                "lat": float(row["base_lat"]),
                "lng": float(row["base_lng"]),
                "services": _split(row.get("skills", "")),
                "free_from": row.get("free_from") or "09:00",
                "free_to": row.get("free_until") or "18:00",
            })

    # Upsert on id.
    try:
        resp = client.table("caregivers").upsert(rows, on_conflict="id").execute()
        print(f"Seeded {len(rows)} caregivers into Supabase `caregivers`.")
    except Exception as e:
        print(f"Seed failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
