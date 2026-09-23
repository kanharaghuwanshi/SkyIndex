from __future__ import annotations

"""
SkyIndex: SpiceJet -> index_engine -> Supabase ingestion runner.

Purpose:
    1. Run the existing Selenium-based SpiceJet scraper.
    2. Pass normalized quotes through the generic cleaning engine.
    3. Insert only the currently confirmed `airfare_quotes` columns into Supabase.
    4. Skip rows whose quote_key is already present.

This module intentionally does NOT alter the database schema.
Optional SpiceJet-only fields such as `udf`, `convenience_fee`,
`service_fee`, `other_charges`, `segments`, and detailed breakdown arrays
remain available in the parser output until the live DB schema is confirmed.
"""

import argparse
import math
import os
from typing import Any

from supabase import Client, create_client

from spicejet_scraper import SpiceJetScraper, SpiceJetSearch
from backend.index.index_engine import clean_quotes


TABLE = "airfare_quotes"

# These columns are confirmed by the current project schema/context.
DB_COLUMNS = [
    "collected_at",
    "collection_date",
    "origin",
    "destination",
    "airline",
    "flight_number",
    "travel_date",
    "lead_time",
    "fare_class",
    "base_fare",
    "taxes",
    "fees",
    "total_fare",
    "currency",
    "availability",
    "source",
    "quote_key",
    "departure_time",
    "arrival_time",
    "duration_minutes",
    "stops",
]


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_supabase_client() -> Client:
    url = get_required_env("SUPABASE_URL")

    # Backend-only credential. Never place this in frontend JavaScript.
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        raise RuntimeError(
            "Missing SUPABASE_SERVICE_ROLE_KEY. "
            "Use the backend service-role key for server-side ingestion."
        )

    return create_client(url, key)


def normalize_db_value(value: Any) -> Any:
    """Convert pandas/object values into Supabase-safe JSON values."""
    if value is None:
        return None

    # pandas/numpy NaN-like values without importing pandas here.
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
    except TypeError:
        pass

    # numpy scalar support without making numpy a hard dependency.
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return normalize_db_value(item())
        except Exception:
            pass

    return value


def to_db_rows(quotes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map normalized scraper quotes to the confirmed DB schema."""
    rows: list[dict[str, Any]] = []

    for quote in quotes:
        row = {
            column: normalize_db_value(quote.get(column))
            for column in DB_COLUMNS
        }

        # Source is fixed by this adapter; do not let a malformed parser
        # accidentally write a different source label.
        row["source"] = "spicejet"

        rows.append(row)

    return rows


def fetch_existing_quote_keys(
    client: Client,
    quote_keys: list[str],
) -> set[str]:
    """Fetch already-stored keys in chunks to avoid duplicate inserts."""
    existing: set[str] = set()

    unique_keys = [key for key in dict.fromkeys(quote_keys) if key]
    if not unique_keys:
        return existing

    # Keep request size modest.
    chunk_size = 100

    for start in range(0, len(unique_keys), chunk_size):
        chunk = unique_keys[start : start + chunk_size]

        response = (
            client.from_(TABLE)
            .select("quote_key")
            .in_("quote_key", chunk)
            .execute()
        )

        data = response.data or []
        for item in data:
            key = item.get("quote_key")
            if key:
                existing.add(key)

    return existing


def insert_new_rows(
    client: Client,
    rows: list[dict[str, Any]],
) -> tuple[int, int]:
    """Insert only rows that are not already present by quote_key."""
    if not rows:
        return 0, 0

    existing = fetch_existing_quote_keys(
        client,
        [row.get("quote_key") for row in rows if row.get("quote_key")],
    )

    new_rows = [
        row
        for row in rows
        if row.get("quote_key") and row["quote_key"] not in existing
    ]

    if not new_rows:
        return 0, len(rows)

    # Insert in moderate batches.
    inserted = 0
    batch_size = 50

    for start in range(0, len(new_rows), batch_size):
        batch = new_rows[start : start + batch_size]

        response = client.from_(TABLE).insert(batch).execute()

        if getattr(response, "error", None):
            raise RuntimeError(
                f"Supabase insert failed: {response.error}"
            )

        inserted += len(batch)

    return inserted, len(rows) - inserted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one SpiceJet search, clean quotes, and save new rows to Supabase."
    )

    parser.add_argument("--origin", required=True, help="Origin IATA code, e.g. DEL")
    parser.add_argument("--destination", required=True, help="Destination IATA code, e.g. BOM")
    parser.add_argument("--travel-date", required=True, help="Travel date YYYY-MM-DD")

    parser.add_argument(
        "--min-request-interval",
        type=float,
        default=30.0,
        help="Minimum seconds between browser searches (default: 30)",
    )
    parser.add_argument(
        "--page-load-wait",
        type=float,
        default=10.0,
        help="Seconds to wait after navigation (default: 10)",
    )
    parser.add_argument(
        "--post-response-wait",
        type=float,
        default=5.0,
        help="Additional seconds before reading network response (default: 5)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run scraper + cleaning but do not write to Supabase.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    search = SpiceJetSearch(
        origin=args.origin.upper(),
        destination=args.destination.upper(),
        travel_date=args.travel_date,
        adults=1,
    )

    print("\n========== SPICEJET INGESTION ==========")
    print(
        f"Route: {search.origin} -> {search.destination} | "
        f"Travel date: {search.travel_date}"
    )

    with SpiceJetScraper(
        min_request_interval=args.min_request_interval,
        page_load_wait=args.page_load_wait,
        post_response_wait=args.post_response_wait,
        output_dir="spicejet_data",
    ) as scraper:
        quotes = scraper.search(search)

        print(f"\nRaw normalized quotes: {len(quotes)}")

        cleaned_df = clean_quotes(quotes)
        cleaned_quotes = cleaned_df.to_dict(orient="records")

        print(f"Quotes after index_engine cleaning: {len(cleaned_quotes)}")

        if not cleaned_quotes:
            print("No valid quotes to store.")
            return

        rows = to_db_rows(cleaned_quotes)

        if args.dry_run:
            print("\nDRY RUN — no Supabase write.")
            for row in rows[:5]:
                print(
                    f"{row['flight_number']:20} "
                    f"T+{row['lead_time']} "
                    f"fare={row['total_fare']} "
                    f"class={row['fare_class']} "
                    f"key={row['quote_key']}"
                )
            print(f"Rows prepared: {len(rows)}")
            return

        client = get_supabase_client()
        inserted, skipped = insert_new_rows(client, rows)

        print("\n========== SUPABASE RESULT ==========")
        print(f"Prepared rows : {len(rows)}")
        print(f"Inserted      : {inserted}")
        print(f"Skipped existing: {skipped}")
        print("Status        : SUCCESS")


if __name__ == "__main__":
    main()
