from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client


# ---------------------------------------------------------
# Config
# ---------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "spicejet_data" / "DEL_BOM_T45.json"

load_dotenv(ROOT.parent / ".env")
load_dotenv(ROOT / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
)

TABLE_NAME = "airfare_quotes"


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def normalize_json_value(value):
    """Convert Python NaN/Infinity to JSON-safe null."""
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
    return value


def json_safe(value):
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return normalize_json_value(value)


def load_quotes():
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Source file not found: {DATA_FILE}")

    with DATA_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        # Support common wrapper shapes without making assumptions
        # about the scraper itself.
        for key in ("quotes", "data", "results"):
            if isinstance(data.get(key), list):
                return data[key]

    raise ValueError(
        "Could not find a quote list in the JSON file. "
        "Expected a list or one of: quotes/data/results."
    )


def make_key(row: dict):
    collection_date = row.get("collection_date")
    quote_key = row.get("quote_key")

    if not collection_date or not quote_key:
        raise ValueError(
            "Every quote must contain both collection_date and quote_key "
            "for this idempotency test."
        )

    return str(collection_date), str(quote_key)


# ---------------------------------------------------------
# Main test
# ---------------------------------------------------------
def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and a Supabase key were not found in .env"
        )

    quotes = load_quotes()
    print(f"Loaded source quotes: {len(quotes)}")
    print(f"Source file: {DATA_FILE}")

    keys = [make_key(q) for q in quotes]

    # Check for duplicate keys inside the source itself first.
    duplicate_keys = []
    seen = set()

    for key in keys:
        if key in seen:
            duplicate_keys.append(key)
        seen.add(key)

    if duplicate_keys:
        print("\nFAIL: Source JSON itself contains duplicate keys.")
        for key in duplicate_keys[:10]:
            print("  ", key)
        raise SystemExit(1)

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Query all rows matching the collection date(s) present in the file.
    collection_dates = sorted({collection_date for collection_date, _ in keys})

    existing_keys = set()

    for collection_date in collection_dates:
        response = (
            supabase.table(TABLE_NAME)
            .select("collection_date,quote_key")
            .eq("collection_date", collection_date)
            .execute()
        )

        for row in response.data or []:
            qk = row.get("quote_key")
            if qk is not None:
                existing_keys.add(
                    (str(row["collection_date"]), str(qk))
                )

    missing = [key for key in keys if key not in existing_keys]
    already_present = [key for key in keys if key in existing_keys]

    print(f"Already present in DB: {len(already_present)}")
    print(f"Missing from DB: {len(missing)}")

    if missing:
        print("\nFAIL: The database does not contain all source records.")
        print("Missing keys (up to 10):")
        for key in missing[:10]:
            print("  ", key)

        print(
            "\nNo INSERT/UPSERT was performed. "
            "This script is intentionally DB-read-only."
        )
        raise SystemExit(1)

    # Important: we do NOT insert anything here.
    # Presence of every source key proves a rerun would be a duplicate
    # under the project's unique (collection_date, quote_key) constraint.
    print("\nIDEMPOTENCY TEST PASSED")
    print(
        "All source records already exist for the same "
        "(collection_date, quote_key)."
    )
    print("No SpiceJet request was sent.")
    print("No database row was inserted or modified.")


if __name__ == "__main__":
    main()
