from __future__ import annotations

from typing import Iterable

import pandas as pd

from backend.config import ROUTE_WEIGHTS


VALID_LEAD_TIMES = (1, 7, 15, 30, 45)

# Fields that every fare observation needs before it can participate in APIx.
REQUIRED_COLUMNS = (
    "origin",
    "destination",
    "travel_date",
    "airline",
    "flight_number",
    "total_fare",
)

# Numeric fare components exposed by direct airline adapters such as SpiceJet.
OPTIONAL_NUMERIC_COLUMNS = (
    "total_fare",
    "base_fare",
    "taxes",
    "udf",
    "fees",
    "convenience_fee",
    "service_fee",
    "other_charges",
    "duration_minutes",
    "stops",
    "availability",
)

TEXT_NORMALIZE_COLUMNS = (
    "origin",
    "destination",
    "airline",
    "flight_number",
    "fare_class",
    "fare_class_of_service",
    "fare_code",
    "product_class",
    "currency",
    "source",
)


def _empty_quote_frame() -> pd.DataFrame:
    """Return an empty frame with the most useful normalized columns."""
    return pd.DataFrame(
        columns=[
            *REQUIRED_COLUMNS,
            "collection_date",
            "collected_at",
            "lead_time",
            "duration_minutes",
            "stops",
            "fare_class",
            "fare_class_of_service",
            "fare_code",
            "product_class",
            "base_fare",
            "taxes",
            "udf",
            "fees",
            "convenience_fee",
            "service_fee",
            "other_charges",
            "currency",
            "availability",
            "source",
            "quote_key",
            "segments",
            "breakdown_match",
        ]
    )


def _normalize_text_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Trim text consistently without inventing missing values."""
    for column in TEXT_NORMALIZE_COLUMNS:
        if column not in df.columns:
            continue

        df[column] = df[column].where(df[column].notna(), None)
        df[column] = df[column].map(
            lambda value: value.strip() if isinstance(value, str) else value
        )

    # IATA/source codes are naturally case-insensitive in our normalized layer.
    for column in ("origin", "destination", "currency", "source"):
        if column in df.columns:
            df[column] = df[column].map(
                lambda value: value.upper() if isinstance(value, str) else value
            )

    return df


def _ensure_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Convert numeric fields; invalid values become NaN rather than strings."""
    for column in OPTIONAL_NUMERIC_COLUMNS:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def _validate_dates_and_lead_times(df: pd.DataFrame) -> pd.DataFrame:
    """Use collection_date as the source of truth for lead_time when available."""
    for column in ("travel_date", "collection_date"):
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce").dt.strftime("%Y-%m-%d")

    # Prefer the explicit collection_date → travel_date relationship over
    # collected_at timestamps. This keeps the index engine independent of the
    # scraper implementation and matches the project's advance-purchase model.
    if "collection_date" in df.columns and "travel_date" in df.columns:
        valid_dates = df["collection_date"].notna() & df["travel_date"].notna()
        if valid_dates.any():
            computed = (
                pd.to_datetime(df.loc[valid_dates, "travel_date"])
                - pd.to_datetime(df.loc[valid_dates, "collection_date"])
            ).dt.days
            df.loc[valid_dates, "lead_time"] = computed

    if "lead_time" not in df.columns:
        df["lead_time"] = pd.NA

    df["lead_time"] = pd.to_numeric(df["lead_time"], errors="coerce")
    df = df[df["lead_time"].isin(VALID_LEAD_TIMES)]
    return df


def _build_quote_key(df: pd.DataFrame) -> pd.DataFrame:
    """Create deterministic keys only when the source did not provide one."""
    if "quote_key" not in df.columns:
        df["quote_key"] = pd.NA

    missing_key = df["quote_key"].isna() | (df["quote_key"].astype(str).str.strip() == "")
    if not missing_key.any():
        return df

    key_columns = (
        "source",
        "origin",
        "destination",
        "travel_date",
        "flight_number",
        "departure_time",
        "arrival_time",
        "fare_code",
        "fare_class",
        "total_fare",
    )

    available = [column for column in key_columns if column in df.columns]
    if not available:
        return df

    def make_key(row: pd.Series) -> str:
        values = []
        for column in available:
            value = row.get(column)
            values.append("" if pd.isna(value) else str(value).strip())
        return "normalized:" + ":".join(values)

    df.loc[missing_key, "quote_key"] = df.loc[missing_key].apply(make_key, axis=1)
    return df


def clean_quotes(quotes: Iterable[dict]) -> pd.DataFrame:
    """Normalize and validate fare observations from any source adapter.

    The function is intentionally source-agnostic. It accepts SpiceJet,
    SerpApi/Google Flights, or future airline adapters as long as they emit the
    common normalized quote schema.
    """
    if quotes is None:
        return _empty_quote_frame()

    df = pd.DataFrame(list(quotes))
    if df.empty:
        return _empty_quote_frame()

    # Add missing optional columns so downstream code can safely reference them.
    for column in (
        "collection_date",
        "collected_at",
        "lead_time",
        "duration_minutes",
        "stops",
        "fare_class",
        "fare_class_of_service",
        "fare_code",
        "product_class",
        "base_fare",
        "taxes",
        "udf",
        "fees",
        "convenience_fee",
        "service_fee",
        "other_charges",
        "currency",
        "availability",
        "source",
        "quote_key",
        "segments",
        "breakdown_match",
    ):
        if column not in df.columns:
            df[column] = pd.NA

    # Required schema validation: missing columns are more actionable than a
    # later KeyError deep inside a groupby/merge operation.
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing_columns:
        raise ValueError(
            "Normalized quote data is missing required columns: "
            + ", ".join(missing_columns)
        )

    df = _normalize_text_columns(df)
    df = _ensure_numeric_columns(df)

    # Keep only observations with a real, positive total fare.
    df = df.dropna(subset=["total_fare"])
    df = df[df["total_fare"] > 0]

    # Core identity is required for a meaningful market observation.
    df = df.dropna(subset=list(REQUIRED_COLUMNS[:-1]))
    df = df[
        df["origin"].astype(str).str.len().eq(3)
        & df["destination"].astype(str).str.len().eq(3)
    ]

    df = _validate_dates_and_lead_times(df)
    df = _build_quote_key(df)

    # A provided quote_key is the strongest identity signal. For fallback keys,
    # include the fare code/class so different fare products remain distinct.
    df["quote_key"] = df["quote_key"].astype(str).str.strip()
    df = df[df["quote_key"].ne("")]

    # Do not silently collapse different sources into one observation.
    df = df.drop_duplicates(subset=["quote_key"], keep="last")

    # Ensure fare-quality arithmetic is available for auditing, but never invent
    # a missing component. A mismatch is a flag, not a reason to fabricate data.
    component_columns = [
        column
        for column in ("base_fare", "fees", "udf", "taxes")
        if column in df.columns
    ]
    if component_columns:
        complete_breakup = df[component_columns].notna().all(axis=1)
        component_sum = df[component_columns].sum(axis=1, min_count=len(component_columns))
        df["breakdown_match"] = complete_breakup & component_sum.round(2).eq(
            df["total_fare"].round(2)
        )

    # Stable column ordering makes DB inserts, debugging, and CSV exports easier.
    preferred_order = [
        "collection_date",
        "collected_at",
        "origin",
        "destination",
        "travel_date",
        "lead_time",
        "airline",
        "flight_number",
        "departure_time",
        "arrival_time",
        "duration_minutes",
        "stops",
        "segments",
        "fare_class",
        "fare_class_of_service",
        "fare_code",
        "product_class",
        "base_fare",
        "taxes",
        "udf",
        "fees",
        "convenience_fee",
        "service_fee",
        "other_charges",
        "total_fare",
        "currency",
        "availability",
        "source",
        "quote_key",
        "breakdown_match",
    ]
    existing_order = [column for column in preferred_order if column in df.columns]
    remaining = [column for column in df.columns if column not in existing_order]

    return df[existing_order + remaining].reset_index(drop=True)


def calculate_route_representative(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate one representative fare per route.

    Method preserved from the prototype:
        1. median fare for each route + lead_time
        2. arithmetic mean across available lead-time medians

    Additional coverage columns are returned for auditing and historical UI.
    """
    if df is None or df.empty:
        return pd.DataFrame(
            columns=[
                "origin",
                "destination",
                "total_fare",
                "lead_times_observed",
                "quote_count",
            ]
        )

    required = {"origin", "destination", "lead_time", "total_fare"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(
            "Cannot calculate route representative; missing columns: "
            + ", ".join(sorted(missing))
        )

    work = df.copy()
    work["total_fare"] = pd.to_numeric(work["total_fare"], errors="coerce")
    work["lead_time"] = pd.to_numeric(work["lead_time"], errors="coerce")
    work = work.dropna(subset=["origin", "destination", "lead_time", "total_fare"])
    work = work[work["total_fare"] > 0]
    work = work[work["lead_time"].isin(VALID_LEAD_TIMES)]

    if work.empty:
        return pd.DataFrame(
            columns=[
                "origin",
                "destination",
                "total_fare",
                "lead_times_observed",
                "quote_count",
            ]
        )

    lead_time_summary = (
        work.groupby(
            ["origin", "destination", "lead_time"],
            as_index=False,
        )
        .agg(
            lead_time_median_fare=("total_fare", "median"),
            quote_count=("total_fare", "size"),
        )
    )

    route_rep = (
        lead_time_summary.groupby(
            ["origin", "destination"],
            as_index=False,
        )
        .agg(
            total_fare=("lead_time_median_fare", "mean"),
            lead_times_observed=("lead_time", "nunique"),
            quote_count=("quote_count", "sum"),
        )
    )

    return route_rep


def calculate_route_indices(
    current: pd.DataFrame,
    baseline: pd.DataFrame,
) -> pd.DataFrame:
    """Compare current vs baseline route representatives."""
    if current is None or baseline is None or current.empty or baseline.empty:
        return pd.DataFrame()

    required = {"origin", "destination", "total_fare"}
    for frame_name, frame in (("current", current), ("baseline", baseline)):
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(
                f"{frame_name} route data is missing columns: "
                + ", ".join(sorted(missing))
            )

    current_work = current.copy()
    baseline_work = baseline.copy()

    # One row per route is required before merging, otherwise a duplicated route
    # can create a many-to-many merge and distort the index.
    current_work = (
        current_work.groupby(["origin", "destination"], as_index=False)["total_fare"]
        .mean()
    )
    baseline_work = (
        baseline_work.groupby(["origin", "destination"], as_index=False)["total_fare"]
        .mean()
    )

    current_work["total_fare"] = pd.to_numeric(current_work["total_fare"], errors="coerce")
    baseline_work["total_fare"] = pd.to_numeric(baseline_work["total_fare"], errors="coerce")

    current_work = current_work[current_work["total_fare"] > 0]
    baseline_work = baseline_work[baseline_work["total_fare"] > 0]

    merged = current_work.merge(
        baseline_work,
        on=["origin", "destination"],
        suffixes=("_current", "_baseline"),
        how="inner",
        validate="one_to_one",
    )

    if merged.empty:
        return merged

    merged["route_index"] = (
        merged["total_fare_current"]
        / merged["total_fare_baseline"]
        * 100.0
    )
    merged["fare_change"] = (
        merged["total_fare_current"] - merged["total_fare_baseline"]
    )
    merged["fare_change_pct"] = (
        merged["total_fare_current"]
        / merged["total_fare_baseline"]
        - 1.0
    ) * 100.0

    return merged


def calculate_overall_index(route_indices: pd.DataFrame) -> float:
    """Calculate the weighted overall APIx using configured route weights."""
    if route_indices is None or route_indices.empty:
        return 0.0

    required = {"origin", "destination", "route_index"}
    missing = required.difference(route_indices.columns)
    if missing:
        raise ValueError(
            "Route index data is missing columns: "
            + ", ".join(sorted(missing))
        )

    weighted_sum = 0.0
    total_weight = 0.0

    for _, row in route_indices.iterrows():
        route = f"{row['origin']}-{row['destination']}"
        weight = float(ROUTE_WEIGHTS.get(route, 0) or 0)
        index_value = pd.to_numeric(row["route_index"], errors="coerce")

        if weight <= 0 or pd.isna(index_value):
            continue

        weighted_sum += float(index_value) * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0

    return weighted_sum / total_weight


def calculate_index_summary(route_indices: pd.DataFrame) -> dict:
    """Return APIx plus route/weight coverage metrics for dashboards and logs."""
    if route_indices is None or route_indices.empty:
        return {
            "apix": 0.0,
            "routes_used": 0,
            "weighted_routes": 0,
            "weight_coverage_pct": 0.0,
        }

    routes_used = 0
    weighted_routes = 0
    used_weight = 0.0
    configured_weight = sum(float(weight or 0) for weight in ROUTE_WEIGHTS.values())

    for _, row in route_indices.iterrows():
        routes_used += 1
        route = f"{row['origin']}-{row['destination']}"
        weight = float(ROUTE_WEIGHTS.get(route, 0) or 0)
        if weight > 0 and pd.notna(row.get("route_index")):
            weighted_routes += 1
            used_weight += weight

    coverage = 0.0
    if configured_weight > 0:
        coverage = used_weight / configured_weight * 100.0

    return {
        "apix": round(calculate_overall_index(route_indices), 4),
        "routes_used": routes_used,
        "weighted_routes": weighted_routes,
        "weight_coverage_pct": round(coverage, 2),
    }
