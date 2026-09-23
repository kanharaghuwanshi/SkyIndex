from __future__ import annotations

import os

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

from backend.index.index_engine import (
    clean_quotes,
    calculate_route_representative,
    calculate_route_indices,
    calculate_overall_index,
)

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL is missing from .env")

if not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is missing from .env")


def main() -> None:

    supabase = create_client(
        SUPABASE_URL,
        SUPABASE_SERVICE_ROLE_KEY,
    )

    print("\n=== APIx DB TEST ===")

    # --------------------------------------------------
    # 1. LOAD REAL OBSERVATIONS
    # --------------------------------------------------

    response = (
        supabase
        .table("airfare_quotes")
        .select("*")
        .order("collection_date", desc=False)
        .execute()
    )

    rows = response.data or []

    print(f"Rows loaded from airfare_quotes: {len(rows)}")

    if not rows:
        raise RuntimeError(
            "No rows found in airfare_quotes. "
            "Run the SpiceJet collector first."
        )

    df = pd.DataFrame(rows)

    # --------------------------------------------------
    # 2. CLEAN USING CURRENT INDEX ENGINE
    # --------------------------------------------------

    cleaned = clean_quotes(
        df.to_dict(orient="records")
    )

    print(f"Rows after clean_quotes(): {len(cleaned)}")

    if cleaned.empty:
        raise RuntimeError(
            "No valid observations remain after cleaning."
        )

    # --------------------------------------------------
    # 3. CHECK COLLECTION DATES
    # --------------------------------------------------

    cleaned["collection_date"] = pd.to_datetime(
        cleaned["collection_date"],
        errors="coerce",
    ).dt.date

    cleaned = cleaned.dropna(
        subset=["collection_date"]
    )

    collection_dates = sorted(
        cleaned["collection_date"].unique()
    )

    print(
        "Collection dates:",
        ", ".join(str(d) for d in collection_dates)
    )

    # --------------------------------------------------
    # 4. CALCULATE DAILY ROUTE REPRESENTATIVES
    # --------------------------------------------------

    daily_representatives = []

    for collection_date in collection_dates:

        day_df = cleaned[
            cleaned["collection_date"] == collection_date
        ].copy()

        route_rep = calculate_route_representative(
            day_df
        )

        if route_rep.empty:
            continue

        route_rep["collection_date"] = collection_date

        daily_representatives.append(
            route_rep
        )

        print(
            f"\n{collection_date} "
            f"-> {len(route_rep)} routes with data"
        )

        print(
            route_rep[
                [
                    "origin",
                    "destination",
                    "total_fare",
                ]
            ].to_string(index=False)
        )

    if not daily_representatives:
        raise RuntimeError(
            "Could not calculate any daily route representatives."
        )

    daily_rep_df = pd.concat(
        daily_representatives,
        ignore_index=True,
    )

    # --------------------------------------------------
    # 5. REAL APIx NEEDS AT LEAST 2 COLLECTION DATES
    # --------------------------------------------------

    if len(collection_dates) < 2:

        print("\n=== APIx CHANGE TEST ===")
        print(
            "Only one collection date is currently available."
        )
        print(
            "A real baseline-vs-current APIx comparison "
            "cannot be calculated yet."
        )
        print(
            "Do NOT fabricate a baseline."
        )
        print(
            "\nDB-to-APIx representative-fare calculation: PASS"
        )

        return

    # --------------------------------------------------
    # 6. BASELINE = EARLIEST REAL DATE
    #    CURRENT  = LATEST REAL DATE
    # --------------------------------------------------

    baseline_date = collection_dates[0]
    current_date = collection_dates[-1]

    baseline = daily_rep_df[
        daily_rep_df["collection_date"]
        == baseline_date
    ].copy()

    current = daily_rep_df[
        daily_rep_df["collection_date"]
        == current_date
    ].copy()

    # Remove collection_date because current engine
    # expects route-level data.
    baseline = baseline.drop(
        columns=["collection_date"]
    )

    current = current.drop(
        columns=["collection_date"]
    )

    route_indices = calculate_route_indices(
        current,
        baseline,
    )

    if route_indices.empty:
        raise RuntimeError(
            "No common routes found between "
            "baseline and current dates."
        )

    # --------------------------------------------------
    # 7. OVERALL APIx
    # --------------------------------------------------

    apix = calculate_overall_index(
        route_indices
    )

    print("\n=== APIx RESULT ===")
    print(f"Baseline date : {baseline_date}")
    print(f"Current date  : {current_date}")
    print(f"APIx          : {apix:.2f}")

    print("\nRoute indices:")

    print(
        route_indices[
            [
                "origin",
                "destination",
                "total_fare_current",
                "total_fare_baseline",
                "route_index",
            ]
        ].to_string(index=False)
    )

    print(
        "\nDB-to-APIx calculation: PASS"
    )


if __name__ == "__main__":
    main()