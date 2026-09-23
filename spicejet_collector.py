from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from supabase import Client, create_client

from backend.config import (
    LEAD_TIMES,
    MAX_SEARCH_QUERIES_PER_RUN,
    MIN_REQUEST_INTERVAL_SECONDS,
    PAGE_LOAD_WAIT_SECONDS,
    POST_RESPONSE_WAIT_SECONDS,
    ROUTES,
    SUPABASE_SERVICE_ROLE_KEY,
    SUPABASE_URL,
)
from backend.index.index_engine import clean_quotes
from spicejet_scraper import SpiceJetScraper, SpiceJetSearch

TABLE_NAME = "airfare_quotes"
COLLECTION_TIMEZONE = ZoneInfo("Asia/Kolkata")

DB_COLUMNS = [
    "collected_at", "collection_date", "origin", "destination", "airline",
    "flight_number", "travel_date", "lead_time", "departure_time",
    "arrival_time", "duration_minutes", "stops", "fare_class",
    "fare_class_of_service", "fare_code", "product_class", "base_fare",
    "taxes", "udf", "fees", "convenience_fee", "service_fee",
    "other_charges", "total_fare", "currency", "availability", "source",
    "quote_key", "segments", "fee_breakdown", "breakdown_match",
]


class CollectionError(RuntimeError):
    pass


def current_collection_date() -> date:
    return datetime.now(COLLECTION_TIMEZONE).date()


def build_jobs(
    collection_date: date,
    routes: list[tuple[str, str]],
    lead_times: list[int],
    *,
    offset: int = 0,
    max_queries: int | None = None,
) -> list[tuple[str, str, int, str]]:
    if offset < 0:
        raise ValueError("offset cannot be negative")

    jobs: list[tuple[str, str, int, str]] = []
    for origin, destination in routes:
        for lead_time in lead_times:
            travel_date = collection_date + timedelta(days=int(lead_time))
            jobs.append((
                origin.upper(),
                destination.upper(),
                int(lead_time),
                travel_date.isoformat(),
            ))

    jobs = jobs[offset:]
    if max_queries is not None:
        if max_queries <= 0:
            raise ValueError("max_queries must be > 0")
        jobs = jobs[:max_queries]
    return jobs


def dataframe_to_quotes(cleaned_df) -> list[dict[str, Any]]:
    if cleaned_df.empty:
        return []
    # Converts pandas NaN/NaT to JSON null, preventing httpx JSON errors.
    return json.loads(cleaned_df.to_json(orient="records", date_format="iso"))


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except Exception:
            pass
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def to_db_row(quote: dict[str, Any]) -> dict[str, Any]:
    row = {column: _json_safe(quote.get(column)) for column in DB_COLUMNS}
    row["source"] = "SPICEJET"

    required = ["collection_date", "origin", "destination", "airline",
                "flight_number", "travel_date", "lead_time",
                "total_fare", "quote_key"]
    missing = [field for field in required if row.get(field) in (None, "")]
    if missing:
        raise CollectionError(f"Missing required DB fields: {missing}")

    if float(row["total_fare"]) <= 0:
        raise CollectionError(f"Invalid total_fare for {row['quote_key']}")

    return row


def validate_job_quotes(
    quotes: list[dict[str, Any]],
    *,
    origin: str,
    destination: str,
    lead_time: int,
    travel_date: str,
    collection_date: date,
) -> None:
    for quote in quotes:
        checks = {
            "origin": (quote.get("origin"), origin),
            "destination": (quote.get("destination"), destination),
            "travel_date": (quote.get("travel_date"), travel_date),
            "collection_date": (quote.get("collection_date"), collection_date.isoformat()),
            "lead_time": (quote.get("lead_time"), lead_time),
            "source": (quote.get("source"), "SPICEJET"),
        }
        for field, (actual, expected) in checks.items():
            if actual != expected:
                raise CollectionError(
                    f"{field} mismatch: expected {expected}, got {actual} "
                    f"for quote {quote.get('quote_key')}"
                )
        if quote.get("breakdown_match") is not True:
            raise CollectionError(
                f"Fare breakdown validation failed for {quote.get('quote_key')}"
            )


def get_supabase_client() -> Client:
    if not SUPABASE_URL:
        raise CollectionError("SUPABASE_URL is missing")
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise CollectionError("SUPABASE_SERVICE_ROLE_KEY is missing")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def fetch_existing_keys(client: Client, collection_date: str, quote_keys: list[str]) -> set[str]:
    existing: set[str] = set()
    keys = list(dict.fromkeys(k for k in quote_keys if k))
    for start in range(0, len(keys), 100):
        chunk = keys[start:start + 100]
        response = (
            client.table(TABLE_NAME)
            .select("quote_key")
            .eq("collection_date", collection_date)
            .in_("quote_key", chunk)
            .execute()
        )
        existing.update(str(item["quote_key"]) for item in (response.data or []) if item.get("quote_key"))
    return existing


def insert_new_rows(client: Client, rows: list[dict[str, Any]]) -> tuple[int, int]:
    if not rows:
        return 0, 0

    collection_dates = {str(row["collection_date"]) for row in rows}
    if len(collection_dates) != 1:
        raise CollectionError("All rows in one run must have the same collection_date")

    collection_date = next(iter(collection_dates))
    existing = fetch_existing_keys(client, collection_date, [str(row["quote_key"]) for row in rows])
    new_rows = [row for row in rows if str(row["quote_key"]) not in existing]

    inserted = 0
    for start in range(0, len(new_rows), 50):
        batch = new_rows[start:start + 50]
        response = client.table(TABLE_NAME).insert(batch).execute()
        returned = len(response.data or [])
        if returned != len(batch):
            raise CollectionError(f"Supabase insert mismatch: sent {len(batch)}, received {returned}")
        inserted += returned

    return inserted, len(rows) - inserted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SkyIndex SpiceJet collector")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--max-queries", type=int, default=MAX_SEARCH_QUERIES_PER_RUN)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    collection_date = current_collection_date()

    jobs = build_jobs(
        collection_date,
        list(ROUTES),
        [int(value) for value in LEAD_TIMES],
        offset=args.offset,
        max_queries=args.max_queries,
    )

    if not jobs:
        print("No collection jobs selected.")
        return

    print("========== SKYINDEX SPICEJET COLLECTION ==========")
    print(f"Collection date : {collection_date.isoformat()}")
    print(f"Jobs selected   : {len(jobs)}")
    print(f"Minimum gap     : {MIN_REQUEST_INTERVAL_SECONDS}s")
    print(f"Page wait       : {PAGE_LOAD_WAIT_SECONDS}s")
    print(f"Post-response   : {POST_RESPONSE_WAIT_SECONDS}s")

    all_rows: list[dict[str, Any]] = []
    failed_jobs: list[str] = []

    with SpiceJetScraper(
        min_request_interval=MIN_REQUEST_INTERVAL_SECONDS,
        page_load_wait=PAGE_LOAD_WAIT_SECONDS,
        post_response_wait=POST_RESPONSE_WAIT_SECONDS,
        output_dir="spicejet_data",
    ) as scraper:
        for index, (origin, destination, lead_time, travel_date) in enumerate(jobs, start=1):
            label = f"{origin}->{destination} T+{lead_time} ({travel_date})"
            print(f"\n========== JOB {index}/{len(jobs)}: {label} ==========")
            try:
                quotes = scraper.search(SpiceJetSearch(
                    origin=origin,
                    destination=destination,
                    travel_date=travel_date,
                    adults=1,
                ))

                if not quotes:
                    print("No fare observations returned.")
                    continue

                cleaned_df = clean_quotes(quotes)
                cleaned_quotes = dataframe_to_quotes(cleaned_df)
                validate_job_quotes(
                    cleaned_quotes,
                    origin=origin,
                    destination=destination,
                    lead_time=lead_time,
                    travel_date=travel_date,
                    collection_date=collection_date,
                )
                rows = [to_db_row(quote) for quote in cleaned_quotes]
                all_rows.extend(rows)
                print(f"Validated observations: {len(rows)}")

            except Exception as exc:
                failed_jobs.append(f"{label}: {exc}")
                print(f"JOB FAILED: {exc}")
                print("Stopping remaining searches after collection error.")
                break

    unique_rows = {}
    for row in all_rows:
        unique_rows[(str(row["collection_date"]), str(row["quote_key"]))] = row
    all_rows = list(unique_rows.values())

    if args.dry_run:
        print(f"\nDRY RUN — rows ready for DB: {len(all_rows)}")
    elif all_rows:
        client = get_supabase_client()
        inserted, skipped = insert_new_rows(client, all_rows)
        print("\n========== DATABASE RESULT ==========")
        print(f"Prepared rows       : {len(all_rows)}")
        print(f"Inserted            : {inserted}")
        print(f"Already stored      : {skipped}")
    else:
        print("\nNo valid observations collected; nothing written.")

    print("\n========== RUN SUMMARY ==========")
    print(f"Jobs selected       : {len(jobs)}")
    print(f"Rows collected      : {len(all_rows)}")
    print(f"Failed jobs         : {len(failed_jobs)}")
    if failed_jobs:
        for failure in failed_jobs:
            print(f"- {failure}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
