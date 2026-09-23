from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


# Project root .env
# backend/config.py -> project root is one level above backend/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


# ==========================================================
# ENV / SECRETS
# ==========================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")

# Backend ingestion should use the service-role key when database writes
# require bypassing Row Level Security. Keep the anon key available only
# for compatibility with older code; do not use it for trusted ingestion.
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")


# ==========================================================
# COLLECTION SETTINGS
# ==========================================================

# SkyIndex collection model.
LEAD_TIMES = [1, 7, 15, 30, 45]
VALID_LEAD_TIMES = tuple(LEAD_TIMES)

# Number of route/date search queries allowed in one collection run.
# This is intentionally a search-query limit, not a raw HTTP-request count,
# because one browser search can generate several site-side requests.
MAX_SEARCH_QUERIES_PER_RUN = int(
    os.getenv("MAX_SEARCH_QUERIES_PER_RUN", "5")
)


# ==========================================================
# BROWSER / SCRAPER PACING
# ==========================================================

# Conservative pacing for direct airline collection.
# These values control collection speed; they are not anti-bot bypass settings.
MIN_REQUEST_INTERVAL_SECONDS = float(
    os.getenv("MIN_REQUEST_INTERVAL_SECONDS", "30.0")
)

PAGE_LOAD_WAIT_SECONDS = float(
    os.getenv("PAGE_LOAD_WAIT_SECONDS", "10.0")
)

POST_RESPONSE_WAIT_SECONDS = float(
    os.getenv("POST_RESPONSE_WAIT_SECONDS", "5.0")
)

# Browser remains visible by default during development/testing.
HEADLESS_BROWSER = os.getenv("HEADLESS_BROWSER", "false").strip().lower() == "true"


# Backward-compatible alias for older collection code.
REQUEST_DELAY_SECONDS = MIN_REQUEST_INTERVAL_SECONDS


# ==========================================================
# ROUTES
# ==========================================================

# Initial representative domestic routes.
# More routes can be added later after the collection pipeline is stable.
ROUTES = [
    ("DEL", "BOM"),
    ("DEL", "BLR"),
    ("BOM", "BLR"),
    ("DEL", "CCU"),
    ("BLR", "HYD"),
    ("MAA", "DEL"),
]


# ==========================================================
# AIRLINES
# ==========================================================

TARGET_AIRLINES = {
    "IndiGo",
    "Air India",
    "Air India Express",
    "Akasa Air",
    "SpiceJet",
}


# ==========================================================
# ROUTE WEIGHTS
# ==========================================================

ROUTE_WEIGHTS = {
    "DEL-BOM": 0.25,
    "DEL-BLR": 0.20,
    "BOM-BLR": 0.15,
    "DEL-CCU": 0.15,
    "BLR-HYD": 0.10,
    "MAA-DEL": 0.15,
}


def _validate_config() -> None:
    if not ROUTES:
        raise ValueError("ROUTES cannot be empty")

    if not LEAD_TIMES:
        raise ValueError("LEAD_TIMES cannot be empty")

    if any(not isinstance(value, int) or value <= 0 for value in LEAD_TIMES):
        raise ValueError("LEAD_TIMES must contain positive integers")

    if MAX_SEARCH_QUERIES_PER_RUN <= 0:
        raise ValueError("MAX_SEARCH_QUERIES_PER_RUN must be > 0")

    if MIN_REQUEST_INTERVAL_SECONDS < 0:
        raise ValueError("MIN_REQUEST_INTERVAL_SECONDS cannot be negative")

    if PAGE_LOAD_WAIT_SECONDS < 0:
        raise ValueError("PAGE_LOAD_WAIT_SECONDS cannot be negative")

    if POST_RESPONSE_WAIT_SECONDS < 0:
        raise ValueError("POST_RESPONSE_WAIT_SECONDS cannot be negative")

    # Every configured route should have a weight. The weights are expected
    # to sum to 1.0 for the default APIx basket.
    route_keys = {f"{origin}-{destination}" for origin, destination in ROUTES}
    missing_weights = route_keys - ROUTE_WEIGHTS.keys()
    if missing_weights:
        raise ValueError(
            "Missing ROUTE_WEIGHTS for routes: "
            + ", ".join(sorted(missing_weights))
        )

    total_weight = sum(float(weight) for weight in ROUTE_WEIGHTS.values())
    if abs(total_weight - 1.0) > 1e-9:
        raise ValueError(
            f"ROUTE_WEIGHTS must sum to 1.0; currently {total_weight:.6f}"
        )


_validate_config()
