from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

from spicejet_scraper import SpiceJetScraper, SpiceJetSearch

try:
    from backend.index.index_engine import clean_quotes
except ImportError:
    from backend.index.index_engine import clean_quotes


load_dotenv(Path(__file__).resolve().parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL is missing from .env")
if not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is missing from .env")

TABLE = "airfare_quotes"

# One controlled live test only.
SEARCH = SpiceJetSearch(
    origin="DEL",
    destination="BOM",
    travel_date="2026-09-30",
    adults=1,
)


def db_row(q: dict) -> dict:
    return {
        "collected_at": q.get("collected_at"),
        "collection_date": q.get("collection_date"),
        "origin": q.get("origin"),
        "destination": q.get("destination"),
        "airline": q.get("airline"),
        "flight_number": q.get("flight_number"),
        "travel_date": q.get("travel_date"),
        "lead_time": q.get("lead_time"),
        "departure_time": q.get("departure_time"),
        "arrival_time": q.get("arrival_time"),
        "duration_minutes": q.get("duration_minutes"),
        "stops": q.get("stops"),
        "fare_class": q.get("fare_class"),
        "fare_class_of_service": q.get("fare_class_of_service"),
        "fare_code": q.get("fare_code"),
        "product_class": q.get("product_class"),
        "base_fare": q.get("base_fare"),
        "taxes": q.get("taxes"),
        "udf": q.get("udf"),
        "fees": q.get("fees"),
        "convenience_fee": q.get("convenience_fee"),
        "service_fee": q.get("service_fee"),
        "other_charges": q.get("other_charges"),
        "total_fare": q.get("total_fare"),
        "currency": q.get("currency", "INR"),
        "availability": q.get("availability"),
        "source": "spicejet",
        "quote_key": q.get("quote_key"),
        "segments": q.get("segments"),
        "fee_breakdown": q.get("fee_breakdown"),
        "breakdown_match": q.get("breakdown_match"),
    }


def main() -> None:
    with SpiceJetScraper(
        min_request_interval=30,
        page_load_wait=10,
        post_response_wait=5,
        output_dir="spicejet_data",
    ) as scraper:
        quotes = scraper.search(SEARCH)

    print(f"Scraper returned: {len(quotes)} quotes")

    cleaned = clean_quotes(quotes)
    import json
    
    cleaned_quotes = json.loads(
        cleaned.to_json(
            orient="records",
            date_format="iso",
        )
    )
    print(f"After index_engine cleaning: {len(cleaned_quotes)} quotes")

    if not cleaned_quotes:
        print("No valid quotes to insert.")
        return

    # This test is specifically checking schema compatibility and batch
    # insertion. We do not yet modify the production collector.
    rows = [db_row(q) for q in cleaned_quotes]

    # Safety checks before writing.
    bad = [
        row["quote_key"]
        for row in rows
        if not row.get("quote_key")
        or row.get("lead_time") not in (1, 7, 15, 30, 45)
        or not row.get("breakdown_match")
    ]
    if bad:
        raise RuntimeError(f"Refusing insert; invalid rows: {bad[:10]}")

    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    # Query existing keys for this exact collection_date so rerunning the test
    # does not create duplicate observations.
    collection_date = rows[0]["collection_date"]
    keys = [row["quote_key"] for row in rows]

    existing_response = (
        client.table(TABLE)
        .select("quote_key")
        .eq("collection_date", collection_date)
        .in_("quote_key", keys)
        .execute()
    )
    existing = {item["quote_key"] for item in (existing_response.data or [])}

    new_rows = [row for row in rows if row["quote_key"] not in existing]

    print(f"Already in DB: {len(existing)}")
    print(f"New rows to insert: {len(new_rows)}")

    if new_rows:
        response = client.table(TABLE).insert(new_rows).execute()
        if not response.data:
            raise RuntimeError("Supabase returned no inserted rows")
        print(f"INSERT SUCCESS: {len(response.data)} rows")
    else:
        print("Nothing new to insert.")

    # Read-back for this exact batch.
    verify = (
        client.table(TABLE)
        .select(
            "id,collection_date,origin,destination,airline,flight_number," 
            "travel_date,lead_time,fare_code,base_fare,taxes,udf,fees,total_fare," 
            "breakdown_match,quote_key"
        )
        .eq("collection_date", collection_date)
        .in_("quote_key", keys)
        .execute()
    )

    rows_read = verify.data or []
    print(f"READ-BACK ROWS: {len(rows_read)}")

    if len(rows_read) != len(rows):
        raise RuntimeError(
            f"Read-back mismatch: expected {len(rows)}, got {len(rows_read)}"
        )

    if not all(row.get("breakdown_match") is True for row in rows_read):
        raise RuntimeError("At least one stored row has breakdown_match != true")

    print("BATCH READ-BACK VERIFIED")


if __name__ == "__main__":
    main()
