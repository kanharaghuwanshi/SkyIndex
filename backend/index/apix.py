from __future__ import annotations

import argparse
import math
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
    APIX_BASELINE_DATE,
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
    """Load all raw observations without changing the existing schema contract."""
    rows = []
    offset = 0
    page_size = 1000

    while True:
        response = (
            db
            .table("airfare_quotes")
            .select(QUOTE_COLUMNS)
            .order("collection_date")
            .range(offset, offset + page_size - 1)
            .execute()
        )

        page = response.data or []
        rows.extend(page)

        if len(page) < page_size:
            break

        offset += len(page)

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


def resolve_api_baseline_date(raw: pd.DataFrame) -> date:
    """Validate and return the configured fixed APIx baseline date."""
    configured = date.fromisoformat(APIX_BASELINE_DATE)

    available_dates = set(
        pd.to_datetime(
            raw["collection_date"],
            errors="coerce",
        ).dt.date.dropna().tolist()
    )

    if configured not in available_dates:
        raise RuntimeError(
            "Configured APIX_BASELINE_DATE "
            f"{configured.isoformat()} was not found in airfare_quotes. "
            "No APIx history was written."
        )

    return configured


def build_historical_derived_data(raw: pd.DataFrame, baseline_date: date):
    """Build daily lead-time/route summaries with per-date cleaning.

    clean_quotes() deliberately runs separately for each collection date so
    its quote-key de-duplication cannot collapse the same quote observed on
    different dates.
    """
    normalized_dates = sorted(
        pd.to_datetime(
            raw["collection_date"],
            errors="coerce",
        ).dt.date.dropna().unique()
    )

    dates = [
        value
        for value in normalized_dates
        if value >= baseline_date
    ]

    lead_by_date = {}
    route_by_date = {}
    daily_by_date = {}

    for collection_date in dates:
        daily = prepare_daily_quotes(raw, collection_date)

        if daily.empty:
            continue

        run_id = str(uuid.uuid4())

        lead_history = build_leadtime_history(
            daily,
            collection_date,
            run_id,
        )

        if lead_history.empty:
            continue

        route_history = build_route_history(
            lead_history
        )

        if route_history.empty:
            continue

        # Enrich route rows from the raw daily data without changing their
        # existing representative-fare methodology. Pre-create object columns
        # so assigning dict-valued JSON metadata through .at is safe in pandas.
        if "source_coverage" not in route_history.columns:
            route_history["source_coverage"] = pd.Series(
                [None] * len(route_history),
                index=route_history.index,
                dtype="object",
            )

        if "currency" not in route_history.columns:
            route_history["currency"] = pd.Series(
                ["INR"] * len(route_history),
                index=route_history.index,
                dtype="object",
            )

        for index, route_row in route_history.iterrows():
            mask = (
                daily["origin"].astype(str).eq(str(route_row["origin"]))
                & daily["destination"].astype(str).eq(str(route_row["destination"]))
            )
            route_quotes = daily.loc[mask]

            if "source" in route_quotes.columns:
                route_history.at[
                    index,
                    "source_coverage"
                ] = (
                    route_quotes["source"]
                    .fillna("unknown")
                    .astype(str)
                    .value_counts()
                    .to_dict()
                )

            if "currency" in route_quotes.columns:
                currency_values = (
                    route_quotes["currency"]
                    .dropna()
                    .astype(str)
                )
                route_history.at[
                    index,
                    "currency"
                ] = (
                    currency_values.iloc[0]
                    if not currency_values.empty
                    else "INR"
                )

            if "airline" in route_quotes.columns:
                route_history.at[
                    index,
                    "airline_count"
                ] = int(
                    route_quotes["airline"]
                    .dropna()
                    .astype(str)
                    .nunique()
                )

        daily_by_date[collection_date] = daily
        lead_by_date[collection_date] = lead_history
        route_by_date[collection_date] = route_history

    return dates, daily_by_date, lead_by_date, route_by_date


def enrich_route_history_with_baseline(
    current_routes: pd.DataFrame,
    baseline_routes: pd.DataFrame,
    baseline_date: date,
) -> pd.DataFrame:
    """Attach fixed-baseline total and fare-component comparisons."""
    if current_routes.empty:
        return current_routes

    lookup = {
        f"{row.origin}-{row.destination}": row
        for row in baseline_routes.itertuples(index=False)
    }

    component_map = (
        ("base_fare", "representative_base_fare"),
        ("taxes", "representative_taxes"),
        ("udf", "representative_udf"),
        ("fees", "representative_fees"),
        ("convenience_fee", "representative_convenience_fee"),
        ("service_fee", "representative_service_fee"),
        ("other_charges", "representative_other_charges"),
    )

    result = current_routes.copy()

    def pct_change(current, baseline):
        try:
            if current is None or baseline is None:
                return None
            if pd.isna(current) or pd.isna(baseline):
                return None
            if float(baseline) == 0:
                return None
            return (float(current) / float(baseline) - 1.0) * 100.0
        except (TypeError, ValueError):
            return None

    for index, row in result.iterrows():
        route_key = f"{row['origin']}-{row['destination']}"
        baseline_row = lookup.get(route_key)

        result.at[
            index,
            "baseline_date"
        ] = baseline_date.isoformat()

        if baseline_row is None:
            # Keep the row, but clearly mark that it is not comparable to the
            # fixed baseline route.
            result.at[index, "baseline_total_fare"] = None
            result.at[index, "route_index"] = None
            result.at[index, "fare_change"] = None
            result.at[index, "fare_change_pct"] = None
            result.at[index, "weighted_contribution"] = None
            result.at[index, "baseline_quote_count"] = None
            result.at[index, "baseline_lead_times_observed"] = None
            result.at[index, "baseline_breakdown_quality_pct"] = None
            for component_name, _ in component_map:
                result.at[
                    index,
                    f"baseline_{component_name}"
                ] = None
                result.at[
                    index,
                    f"{component_name}_change"
                ] = None
                result.at[
                    index,
                    f"{component_name}_change_pct"
                ] = None
            continue

        current_total = pd.to_numeric(
            row["representative_total_fare"],
            errors="coerce",
        )
        baseline_total = pd.to_numeric(
            getattr(
                baseline_row,
                "representative_total_fare",
                None,
            ),
            errors="coerce",
        )

        if (
            pd.notna(current_total)
            and pd.notna(baseline_total)
            and float(baseline_total) > 0
        ):
            route_index = (
                float(current_total)
                / float(baseline_total)
                * 100.0
            )
            fare_change = (
                float(current_total)
                - float(baseline_total)
            )
            fare_change_pct = pct_change(
                current_total,
                baseline_total,
            )
        else:
            route_index = None
            fare_change = None
            fare_change_pct = None

        result.at[
            index,
            "baseline_total_fare"
        ] = (
            float(baseline_total)
            if pd.notna(baseline_total)
            else None
        )
        result.at[
            index,
            "route_index"
        ] = route_index
        result.at[
            index,
            "fare_change"
        ] = fare_change
        result.at[
            index,
            "fare_change_pct"
        ] = fare_change_pct
        result.at[
            index,
            "baseline_quote_count"
        ] = int(
            getattr(
                baseline_row,
                "current_quote_count",
                0,
            )
        )
        result.at[
            index,
            "baseline_lead_times_observed"
        ] = int(
            getattr(
                baseline_row,
                "current_lead_times_observed",
                0,
            )
        )
        result.at[
            index,
            "baseline_breakdown_quality_pct"
        ] = float(
            getattr(
                baseline_row,
                "current_breakdown_quality_pct",
                0,
            )
        )

        route_weight = float(
            ROUTE_WEIGHTS.get(
                route_key,
                0,
            ) or 0
        )

        result.at[
            index,
            "weighted_contribution"
        ] = (
            route_index * route_weight
            if route_index is not None
            else None
        )

        for component_name, current_column in component_map:
            current_value = pd.to_numeric(
                row.get(current_column),
                errors="coerce",
            )
            baseline_value = pd.to_numeric(
                getattr(
                    baseline_row,
                    current_column,
                    None,
                ),
                errors="coerce",
            )

            result.at[
                index,
                f"baseline_{component_name}"
            ] = (
                float(baseline_value)
                if pd.notna(baseline_value)
                else None
            )

            if (
                pd.notna(current_value)
                and pd.notna(baseline_value)
            ):
                result.at[
                    index,
                    f"{component_name}_change"
                ] = (
                    float(current_value)
                    - float(baseline_value)
                )
                result.at[
                    index,
                    f"{component_name}_change_pct"
                ] = pct_change(
                    current_value,
                    baseline_value,
                )
            else:
                result.at[
                    index,
                    f"{component_name}_change"
                ] = None
                result.at[
                    index,
                    f"{component_name}_change_pct"
                ] = None

    return result


def build_apix_rows(
    dates,
    daily_by_date,
    route_by_date,
    baseline_date,
):
    """Calculate every available real collection date against one fixed baseline."""
    if baseline_date not in route_by_date:
        raise RuntimeError(
            "The configured baseline date has no valid route history: "
            f"{baseline_date.isoformat()}"
        )

    baseline_routes = route_by_date[baseline_date]

    apix_rows = []
    enriched_route_by_date = {}

    previous_apix = None

    for collection_date in dates:
        current_routes = route_by_date.get(collection_date)
        daily = daily_by_date.get(collection_date)

        if current_routes is None or current_routes.empty:
            continue

        enriched_routes = enrich_route_history_with_baseline(
            current_routes,
            baseline_routes,
            baseline_date,
        )

        enriched_route_by_date[
            collection_date
        ] = enriched_routes

        current_for_index = (
            enriched_routes[
                [
                    "origin",
                    "destination",
                    "representative_total_fare",
                ]
            ]
            .rename(
                columns={
                    "representative_total_fare": "total_fare"
                }
            )
        )

        baseline_for_index = (
            baseline_routes[
                [
                    "origin",
                    "destination",
                    "representative_total_fare",
                ]
            ]
            .rename(
                columns={
                    "representative_total_fare": "total_fare"
                }
            )
        )

        route_indices = calculate_route_indices(
            current_for_index,
            baseline_for_index,
        )

        if route_indices.empty:
            continue

        apix_value = calculate_overall_index(
            route_indices
        )

        change_value = None
        change_pct = None

        if previous_apix is not None:
            change_value = (
                apix_value - previous_apix
            )
            if previous_apix != 0:
                change_pct = (
                    change_value / previous_apix
                ) * 100.0

        configured_weight = sum(
            float(value or 0)
            for value in ROUTE_WEIGHTS.values()
        )

        used_route_keys = {
            f"{row['origin']}-{row['destination']}"
            for _, row in route_indices.iterrows()
            if float(
                ROUTE_WEIGHTS.get(
                    f"{row['origin']}-{row['destination']}",
                    0,
                )
                or 0
            ) > 0
        }

        used_weight = sum(
            float(
                ROUTE_WEIGHTS.get(route_key, 0)
                or 0
            )
            for route_key in used_route_keys
        )

        weight_coverage = (
            used_weight / configured_weight * 100.0
            if configured_weight
            else 0.0
        )

        valid_breakdowns = int(
            (
                daily["breakdown_match"] == True
            ).sum()
        ) if "breakdown_match" in daily.columns else 0

        observation_count = int(
            len(daily)
        )

        breakdown_quality = (
            valid_breakdowns / observation_count * 100.0
            if observation_count
            else 0.0
        )

        source_coverage = (
            daily["source"]
            .fillna("unknown")
            .astype(str)
            .value_counts()
            .to_dict()
            if "source" in daily.columns
            else {}
        )

        all_configured_routes = set(
            ROUTE_WEIGHTS.keys()
        )

        missing_routes = sorted(
            all_configured_routes
            - used_route_keys
        )

        apix_rows.append(
            {
                "index_date": collection_date.isoformat(),
                "apix": float(apix_value),
                "previous_apix": previous_apix,
                "change_value": change_value,
                "change_pct": change_pct,
                "baseline_date": baseline_date.isoformat(),
                "calculation_version": "v2-fixed-baseline",
                "calculation_status": (
                    "calculated"
                    if not missing_routes
                    else "calculated_partial_coverage"
                ),
                "error_message": None,
                "route_count_expected": len(ROUTE_WEIGHTS),
                "route_count_used": len(used_route_keys),
                "weighted_route_count": len(used_route_keys),
                "observation_count": observation_count,
                "valid_breakdown_count": valid_breakdowns,
                "breakdown_quality_pct": round(
                    breakdown_quality,
                    3,
                ),
                "weight_coverage_pct": round(
                    weight_coverage,
                    3,
                ),
                "lead_times_expected": list(LEAD_TIMES),
                "routes_missing": missing_routes,
                "route_weights_snapshot": ROUTE_WEIGHTS,
                "source_coverage": source_coverage,
                "notes": (
                    "Fixed baseline is the configured first real "
                    "collection date. previous_apix/change fields "
                    "compare consecutive available real collection dates."
                ),
            }
        )

        previous_apix = float(
            apix_value
        )

    return (
        baseline_routes,
        enriched_route_by_date,
        apix_rows,
    )


def delete_derived_from_date(db, index_date: date):
    """Remove only derived rows at/after the rebuild boundary."""
    date_value = index_date.isoformat()

    for table_name in (
        "apix_leadtime_history",
        "apix_route_history",
        "apix_history",
    ):
        (
            db
            .table(table_name)
            .delete()
            .gte("index_date", date_value)
            .execute()
        )


INTEGER_COLUMNS_BY_TABLE = {
    "apix_history": {
        "route_count_expected",
        "route_count_used",
        "weighted_route_count",
        "observation_count",
        "valid_breakdown_count",
    },
    "apix_route_history": {
        "current_quote_count",
        "baseline_quote_count",
        "current_lead_times_observed",
        "baseline_lead_times_observed",
        "airline_count",
    },
    "apix_leadtime_history": {
        "lead_time",
        "quote_count",
        "flight_count",
        "journey_count",
        "airline_count",
        "breakdown_valid_count",
    },
}


def _json_safe(value):
    """Convert pandas/numpy values into strict JSON-compatible values."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            _json_safe(item)
            for item in value
        ]

    if isinstance(value, date):
        return value.isoformat()

    # numpy scalar -> native Python scalar.
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass

    if isinstance(value, float):
        return (
            float(value)
            if math.isfinite(value)
            else None
        )

    try:
        missing = pd.isna(value)
        if isinstance(missing, bool) and missing:
            return None
    except (TypeError, ValueError):
        pass

    return value


def upsert_dataframe(
    db,
    table_name: str,
    frame: pd.DataFrame,
    on_conflict: str,
):
    if frame is None or frame.empty:
        return

    clean_frame = frame.copy()

    integer_columns = INTEGER_COLUMNS_BY_TABLE.get(
        table_name,
        set(),
    )

    # PostgreSQL integer columns must receive JSON integers, not pandas/numpy
    # float values such as 2.0 created by nullable DataFrame columns.
    for column in integer_columns:
        if column not in clean_frame.columns:
            continue

        numeric_values = pd.to_numeric(
            clean_frame[column],
            errors="coerce",
        )

        non_null = numeric_values.dropna()
        invalid_fractional = non_null[
            (non_null % 1) != 0
        ]

        if not invalid_fractional.empty:
            raise ValueError(
                f"Non-integer value found in "
                f"{table_name}.{column}: "
                f"{invalid_fractional.tolist()[:10]}"
            )

        clean_frame[column] = numeric_values.astype(
            "Int64"
        )

    # Convert records first, then recursively sanitize values. Using
    # DataFrame.where(..., None) alone is insufficient because float columns
    # can retain NaN, which is invalid JSON and is rejected by httpx.
    rows = clean_frame.to_dict(
        orient="records"
    )

    safe_rows = [
        {
            column: _json_safe(value)
            for column, value in row.items()
        }
        for row in rows
    ]

    chunk_size = 500

    for start in range(
        0,
        len(safe_rows),
        chunk_size,
    ):
        db.table(
            table_name
        ).upsert(
            safe_rows[
                start:start + chunk_size
            ],
            on_conflict=on_conflict,
        ).execute()


def save_apix_history(
    db,
    result,
    current_date: date,
    current_route_history: pd.DataFrame,
):
    """Keep the legacy saver callable while the main flow uses rebuild-aware writes."""
    if result is None:
        return

    if isinstance(result, dict):
        rows = [result]
    else:
        rows = result

    db.table(
        "apix_history"
    ).upsert(
        rows,
        on_conflict="index_date",
    ).execute()


def main():
    parser = argparse.ArgumentParser(
        description="SkyIndex fixed-baseline APIx engine"
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help=(
            "Recalculate every real collection date on/after the "
            "configured fixed baseline and refresh all derived history."
        ),
    )
    args = parser.parse_args()

    print(
        "========== SKYINDEX APIx ENGINE =========="
    )

    db = get_db()

    raw = load_all_quotes(db)

    if raw.empty:
        raise RuntimeError(
            "airfare_quotes is empty"
        )

    baseline_date = resolve_api_baseline_date(
        raw
    )

    print(
        f"Fixed APIx baseline: {baseline_date}"
    )

    (
        dates,
        daily_by_date,
        lead_by_date,
        route_by_date,
    ) = build_historical_derived_data(
        raw,
        baseline_date,
    )

    if not dates:
        raise RuntimeError(
            "No valid collection dates exist on/after the configured APIx baseline."
        )

    (
        baseline_routes,
        enriched_route_by_date,
        apix_rows,
    ) = build_apix_rows(
        dates,
        daily_by_date,
        route_by_date,
        baseline_date,
    )

    if not apix_rows:
        raise RuntimeError(
            "No valid APIx rows could be calculated."
        )

    all_lead_frames = [
        frame
        for frame in lead_by_date.values()
        if frame is not None and not frame.empty
    ]

    all_route_frames = [
        frame
        for frame in enriched_route_by_date.values()
        if frame is not None and not frame.empty
    ]

    lead_history_all = (
        pd.concat(
            all_lead_frames,
            ignore_index=True,
        )
        if all_lead_frames
        else pd.DataFrame()
    )

    route_history_all = (
        pd.concat(
            all_route_frames,
            ignore_index=True,
        )
        if all_route_frames
        else pd.DataFrame()
    )

    if args.rebuild:
        print(
            "\nFULL REBUILD: replacing derived history from baseline onward."
        )

        delete_derived_from_date(
            db,
            baseline_date,
        )

        upsert_dataframe(
            db,
            "apix_leadtime_history",
            lead_history_all,
            "index_date,origin,destination,lead_time",
        )

        upsert_dataframe(
            db,
            "apix_route_history",
            route_history_all,
            "index_date,origin,destination",
        )

        upsert_dataframe(
            db,
            "apix_history",
            pd.DataFrame(apix_rows),
            "index_date",
        )

        print(
            f"Rebuilt APIx dates: {len(apix_rows)}"
        )

    else:
        latest_date = dates[-1]

        print(
            f"\nLatest collection date: {latest_date}"
        )

        delete_derived_from_date(
            db,
            latest_date,
        )

        latest_lead = (
            lead_history_all[
                lead_history_all["index_date"].astype(str)
                == latest_date.isoformat()
            ]
            if not lead_history_all.empty
            else pd.DataFrame()
        )

        latest_route = (
            route_history_all[
                route_history_all["index_date"].astype(str)
                == latest_date.isoformat()
            ]
            if not route_history_all.empty
            else pd.DataFrame()
        )

        latest_apix = [
            row
            for row in apix_rows
            if row["index_date"]
            == latest_date.isoformat()
        ]

        upsert_dataframe(
            db,
            "apix_leadtime_history",
            latest_lead,
            "index_date,origin,destination,lead_time",
        )

        upsert_dataframe(
            db,
            "apix_route_history",
            latest_route,
            "index_date,origin,destination",
        )

        upsert_dataframe(
            db,
            "apix_history",
            pd.DataFrame(latest_apix),
            "index_date",
        )

    latest = apix_rows[-1]

    print(
        "\n========== APIx RESULT =========="
    )
    print(
        f"Baseline date : {latest['baseline_date']}"
    )
    print(
        f"Latest date   : {latest['index_date']}"
    )
    print(
        f"APIx          : {latest['apix']:.4f}"
    )
    print(
        f"Previous APIx : {latest['previous_apix']}"
    )
    print(
        f"Change %      : {latest['change_pct']}"
    )
    print(
        f"Status        : {latest['calculation_status']}"
    )
    print(
        "Raw airfare_quotes: UNCHANGED"
    )

if __name__ == "__main__":
    main()