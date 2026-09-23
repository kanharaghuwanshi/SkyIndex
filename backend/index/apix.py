from __future__ import annotations

import uuid
from datetime import date

import pandas as pd
from supabase import create_client

from pathlib import Path
import sys

# Project root:
# skyindex/
# ├── backend/
# │   └── index/
# │       └── apix.py
PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import (
    LEAD_TIMES,
    ROUTE_WEIGHTS,
    SUPABASE_SERVICE_ROLE_KEY,
    SUPABASE_URL,
)
from backend.index.index_engine import (
    calculate_overall_index,
    calculate_route_indices,
    clean_quotes,
)


QUOTE_COLUMNS = "*"


def get_db():
    if not SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL is missing")

    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is missing")

    return create_client(
        SUPABASE_URL,
        SUPABASE_SERVICE_ROLE_KEY,
    )


def load_all_quotes(db) -> pd.DataFrame:
    response = (
        db
        .table("airfare_quotes")
        .select(QUOTE_COLUMNS)
        .order("collection_date")
        .execute()
    )

    rows = response.data or []

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


def get_latest_collection_date(df: pd.DataFrame) -> date:
    dates = pd.to_datetime(
        df["collection_date"],
        errors="coerce",
    ).dt.date.dropna()

    if dates.empty:
        raise RuntimeError(
            "No valid collection_date found in airfare_quotes"
        )

    return max(dates)


def prepare_daily_quotes(
    df: pd.DataFrame,
    collection_date: date,
) -> pd.DataFrame:

    work = df.copy()

    work["collection_date"] = pd.to_datetime(
        work["collection_date"],
        errors="coerce",
    ).dt.date

    work = work[
        work["collection_date"] == collection_date
    ].copy()

    if work.empty:
        return work

    return clean_quotes(
        work.to_dict(orient="records")
    )


def component_median(group: pd.DataFrame, column: str):
    if column not in group.columns:
        return None

    values = pd.to_numeric(
        group[column],
        errors="coerce",
    ).dropna()

    if values.empty:
        return None

    return float(values.median())


def build_leadtime_history(
    daily: pd.DataFrame,
    collection_date: date,
    run_id: str,
) -> pd.DataFrame:

    rows = []

    for (
        origin,
        destination,
        lead_time,
    ), group in daily.groupby(
        [
            "origin",
            "destination",
            "lead_time",
        ]
    ):

        total_values = pd.to_numeric(
            group["total_fare"],
            errors="coerce",
        ).dropna()

        if total_values.empty:
            continue

        travel_dates = pd.to_datetime(
            group["travel_date"],
            errors="coerce",
        ).dt.date.dropna()

        if travel_dates.empty:
            continue

        flight_count = (
            group["flight_number"]
            .dropna()
            .astype(str)
            .nunique()
        )

        if "journey_key" in group.columns:
            journey_count = (
                group["journey_key"]
                .dropna()
                .astype(str)
                .nunique()
            )
        else:
            journey_count = flight_count

        airline_count = (
            group["airline"]
            .dropna()
            .astype(str)
            .nunique()
        )

        breakdown_valid_count = int(
            (
                group["breakdown_match"]
                == True
            ).sum()
        )

        quote_count = len(group)

        quality_pct = (
            breakdown_valid_count
            / quote_count
            * 100
            if quote_count
            else 0
        )

        source_coverage = (
            group["source"]
            .fillna("unknown")
            .astype(str)
            .value_counts()
            .to_dict()
        )

        rows.append(
            {
                "run_id": run_id,
                "index_date": collection_date.isoformat(),
                "origin": origin,
                "destination": destination,
                "lead_time": int(lead_time),
                "travel_date": min(travel_dates).isoformat(),

                "representative_total_fare": float(
                    total_values.median()
                ),

                "representative_base_fare":
                    component_median(
                        group,
                        "base_fare",
                    ),

                "representative_taxes":
                    component_median(
                        group,
                        "taxes",
                    ),

                "representative_udf":
                    component_median(
                        group,
                        "udf",
                    ),

                "representative_fees":
                    component_median(
                        group,
                        "fees",
                    ),

                "representative_convenience_fee":
                    component_median(
                        group,
                        "convenience_fee",
                    ),

                "representative_service_fee":
                    component_median(
                        group,
                        "service_fee",
                    ),

                "representative_other_charges":
                    component_median(
                        group,
                        "other_charges",
                    ),

                "quote_count": quote_count,
                "flight_count": flight_count,
                "journey_count": journey_count,
                "airline_count": airline_count,

                "breakdown_valid_count":
                    breakdown_valid_count,

                "breakdown_quality_pct":
                    round(quality_pct, 3),

                "source_coverage": source_coverage,

                "currency": (
                    str(group["currency"].dropna().iloc[0])
                    if "currency" in group.columns
                    and not group["currency"].dropna().empty
                    else "INR"
                ),
            }
        )

    return pd.DataFrame(rows)


def save_leadtime_history(
    db,
    history: pd.DataFrame,
):
    if history.empty:
        return

    rows = history.where(
        pd.notna(history),
        None,
    ).to_dict(
        orient="records"
    )

    db.table(
        "apix_leadtime_history"
    ).upsert(
        rows,
        on_conflict=(
            "index_date,"
            "origin,"
            "destination,"
            "lead_time"
        ),
    ).execute()


def build_route_history(
    leadtime_history: pd.DataFrame,
) -> pd.DataFrame:

    rows = []

    for (
        index_date,
        origin,
        destination,
    ), group in leadtime_history.groupby(
        [
            "index_date",
            "origin",
            "destination",
        ]
    ):

        total = pd.to_numeric(
            group["representative_total_fare"],
            errors="coerce",
        ).dropna()

        if total.empty:
            continue

        expected_lead_times = len(
            LEAD_TIMES
        )

        observed_lead_times = (
            group["lead_time"]
            .nunique()
        )

        lead_coverage = (
            observed_lead_times
            / expected_lead_times
            * 100
        )

        route_key = (
            f"{origin}-{destination}"
        )

        route_weight = float(
            ROUTE_WEIGHTS.get(
                route_key,
                0,
            )
        )

        def mean_component(column):
            if column not in group.columns:
                return None

            values = pd.to_numeric(
                group[column],
                errors="coerce",
            ).dropna()

            if values.empty:
                return None

            return float(values.mean())

        quote_count = int(
            pd.to_numeric(
                group["quote_count"],
                errors="coerce",
            ).fillna(0).sum()
        )

        rows.append(
            {
                "run_id": group["run_id"].iloc[0],
                "index_date": index_date,
                "baseline_date": None,

                "origin": origin,
                "destination": destination,

                "route_weight": route_weight,

                "representative_total_fare":
                    float(total.mean()),

                "representative_base_fare":
                    mean_component(
                        "representative_base_fare"
                    ),

                "representative_taxes":
                    mean_component(
                        "representative_taxes"
                    ),

                "representative_udf":
                    mean_component(
                        "representative_udf"
                    ),

                "representative_fees":
                    mean_component(
                        "representative_fees"
                    ),

                "representative_convenience_fee":
                    mean_component(
                        "representative_convenience_fee"
                    ),

                "representative_service_fee":
                    mean_component(
                        "representative_service_fee"
                    ),

                "representative_other_charges":
                    mean_component(
                        "representative_other_charges"
                    ),

                "current_quote_count":
                    quote_count,

                "current_lead_times_observed":
                    observed_lead_times,

                "lead_time_coverage_pct":
                    round(
                        lead_coverage,
                        3,
                    ),

                "current_breakdown_quality_pct":
                    float(
                        pd.to_numeric(
                            group[
                                "breakdown_quality_pct"
                            ],
                            errors="coerce",
                        ).mean()
                    ),

                "airline_count":
                    int(
                        pd.to_numeric(
                            group["airline_count"],
                            errors="coerce",
                        ).max()
                    ),
            }
        )

    return pd.DataFrame(rows)


def save_route_history(
    db,
    route_history: pd.DataFrame,
):
    if route_history.empty:
        return

    rows = route_history.where(
        pd.notna(route_history),
        None,
    ).to_dict(
        orient="records"
    )

    db.table(
        "apix_route_history"
    ).upsert(
        rows,
        on_conflict=(
            "index_date,"
            "origin,"
            "destination"
        ),
    ).execute()


def calculate_real_apix_if_possible(
    db,
    current_route_history: pd.DataFrame,
    current_date: date,
):

    if current_route_history.empty:
        return None

    previous_response = (
        db
        .table("apix_route_history")
        .select("*")
        .lt(
            "index_date",
            current_date.isoformat(),
        )
        .order(
            "index_date",
            desc=True,
        )
        .execute()
    )

    previous_rows = (
        previous_response.data
        or []
    )

    if not previous_rows:
        print(
            "\nNo earlier real collection date."
        )
        print(
            "APIx history will NOT be written yet."
        )
        return None

    previous_df = pd.DataFrame(
        previous_rows
    )

    previous_date = (
        pd.to_datetime(
            previous_df["index_date"]
        ).dt.date.max()
    )

    current_for_index = (
        current_route_history[
            [
                "origin",
                "destination",
                "representative_total_fare",
            ]
        ]
        .rename(
            columns={
                "representative_total_fare":
                    "total_fare"
            }
        )
        .copy()
    )

    baseline_for_index = (
        previous_df[
            previous_df["index_date"]
            == previous_date.isoformat()
        ][
            [
                "origin",
                "destination",
                "representative_total_fare",
            ]
        ]
        .rename(
            columns={
                "representative_total_fare":
                    "total_fare"
            }
        )
        .copy()
    )

    route_indices = calculate_route_indices(
        current_for_index,
        baseline_for_index,
    )

    if route_indices.empty:
        print(
            "\nNo common routes between "
            "current and previous real dates."
        )
        return None

    apix = calculate_overall_index(
        route_indices
    )

    return {
        "apix": float(apix),
        "baseline_date": previous_date,
        "route_indices": route_indices,
    }


def save_apix_history(
    db,
    result,
    current_date: date,
    current_route_history: pd.DataFrame,
):

    if result is None:
        return

    route_indices = result[
        "route_indices"
    ]

    run_id = str(
        uuid.uuid4()
    )

    apix_value = result["apix"]

    previous_response = (
        db
        .table("apix_history")
        .select(
            "apix,index_date"
        )
        .order(
            "index_date",
            desc=True,
        )
        .limit(1)
        .execute()
    )

    previous = (
        previous_response.data[0]
        if previous_response.data
        else None
    )

    previous_apix = (
        float(previous["apix"])
        if previous and previous.get("apix")
        is not None
        else None
    )

    change_value = None
    change_pct = None

    if previous_apix is not None:
        change_value = (
            apix_value
            - previous_apix
        )

        if previous_apix != 0:
            change_pct = (
                change_value
                / previous_apix
                * 100
            )

    expected_routes = len(
        ROUTE_WEIGHTS
    )

    used_routes = len(
        route_indices
    )

    weighted_routes = sum(
        1
        for _, row
        in route_indices.iterrows()
        if ROUTE_WEIGHTS.get(
            f"{row['origin']}-{row['destination']}",
            0,
        ) > 0
    )

    observation_count = int(
        pd.to_numeric(
            current_route_history[
                "current_quote_count"
            ],
            errors="coerce",
        ).fillna(0).sum()
    )

    valid_breakdowns = int(
        round(
            observation_count
            * (
                float(
                    current_route_history[
                        "current_breakdown_quality_pct"
                    ].mean()
                )
                / 100
            )
        )
    )

    breakdown_quality = (
        valid_breakdowns
        / observation_count
        * 100
        if observation_count
        else 0
    )

    configured_weight = sum(
        float(value)
        for value
        in ROUTE_WEIGHTS.values()
    )

    used_weight = sum(
        float(
            ROUTE_WEIGHTS.get(
                f"{row['origin']}-{row['destination']}",
                0,
            )
        )
        for _, row
        in route_indices.iterrows()
    )

    weight_coverage = (
        used_weight
        / configured_weight
        * 100
        if configured_weight
        else 0
    )

    source_counts = {}

    response = (
        db
        .table("airfare_quotes")
        .select(
            "source"
        )
        .eq(
            "collection_date",
            current_date.isoformat(),
        )
        .execute()
    )

    for row in (
        response.data or []
    ):
        source = row.get(
            "source"
        ) or "unknown"

        source_counts[source] = (
            source_counts.get(
                source,
                0,
            )
            + 1
        )

    row = {
        "index_date":
            current_date.isoformat(),

        "apix":
            apix_value,

        "previous_apix":
            previous_apix,

        "change_value":
            change_value,

        "change_pct":
            change_pct,

        "baseline_date":
            result[
                "baseline_date"
            ].isoformat(),

        "calculation_version":
            "v1",

        "calculation_status":
            "calculated",

        "route_count_expected":
            expected_routes,

        "route_count_used":
            used_routes,

        "weighted_route_count":
            weighted_routes,

        "observation_count":
            observation_count,

        "valid_breakdown_count":
            valid_breakdowns,

        "breakdown_quality_pct":
            round(
                breakdown_quality,
                3,
            ),

        "weight_coverage_pct":
            round(
                weight_coverage,
                3,
            ),

        "lead_times_expected":
            list(LEAD_TIMES),

        "routes_missing":
            [
                route
                for route
                in ROUTE_WEIGHTS
                if route
                not in {
                    f"{r['origin']}-{r['destination']}"
                    for _, r
                    in route_indices.iterrows()
                }
            ],

        "route_weights_snapshot":
            ROUTE_WEIGHTS,

        "source_coverage":
            source_counts,

        "notes":
            "Calculated only from real collected observations.",
    }

    db.table(
        "apix_history"
    ).upsert(
        [row],
        on_conflict="index_date",
    ).execute()

    print(
        f"\nAPIx history saved: "
        f"{apix_value:.4f}"
    )
    print(
        f"Baseline: "
        f"{result['baseline_date']}"
    )
    print(
        f"Current: "
        f"{current_date}"
    )
    print(
        f"Run ID: {run_id}"
    )


def main():

    print(
        "========== SKYINDEX APIx ENGINE =========="
    )

    db = get_db()

    raw = load_all_quotes(db)

    if raw.empty:
        raise RuntimeError(
            "airfare_quotes is empty"
        )

    latest_date = (
        get_latest_collection_date(
            raw
        )
    )

    print(
        f"Latest collection date: "
        f"{latest_date}"
    )

    daily = prepare_daily_quotes(
        raw,
        latest_date,
    )

    print(
        f"Valid observations: "
        f"{len(daily)}"
    )

    if daily.empty:
        raise RuntimeError(
            "No valid observations for latest collection date."
        )

    run_id = str(
        uuid.uuid4()
    )

    leadtime_history = (
        build_leadtime_history(
            daily,
            latest_date,
            run_id,
        )
    )

    save_leadtime_history(
        db,
        leadtime_history,
    )

    print(
        f"Lead-time history rows: "
        f"{len(leadtime_history)}"
    )

    route_history = (
        build_route_history(
            leadtime_history
        )
    )

    save_route_history(
        db,
        route_history,
    )

    print(
        f"Route history rows: "
        f"{len(route_history)}"
    )

    result = (
        calculate_real_apix_if_possible(
            db,
            route_history,
            latest_date,
        )
    )

    if result is None:
        print(
            "\nAPIx calculation deferred "
            "until a second real collection date exists."
        )
        return

    save_apix_history(
        db,
        result,
        latest_date,
        route_history,
    )


if __name__ == "__main__":
    main()