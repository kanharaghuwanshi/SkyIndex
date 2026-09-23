from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BASE_URL = "https://www.spicejet.com"
AVAILABILITY_URL = f"{BASE_URL}/api/v3/search/availability"
SEARCH_URL = f"{BASE_URL}/search"


class SpiceJetAPIError(RuntimeError):
    """Raised when SpiceJet returns an unusable response."""


@dataclass(frozen=True)
class SearchRequest:
    origin: str
    destination: str
    travel_date: str
    adults: int = 1
    children: int = 0
    infants: int = 0
    sr_citizens: int = 0
    currency: str = "INR"
    journey_class: str = "ff"

    def validate(self) -> None:
        if len(self.origin) != 3 or not self.origin.isalpha():
            raise ValueError("origin must be a 3-letter IATA station code")
        if len(self.destination) != 3 or not self.destination.isalpha():
            raise ValueError("destination must be a 3-letter IATA station code")
        try:
            date.fromisoformat(self.travel_date)
        except ValueError as exc:
            raise ValueError("travel_date must be YYYY-MM-DD") from exc
        for name, value in (
            ("adults", self.adults),
            ("children", self.children),
            ("infants", self.infants),
            ("sr_citizens", self.sr_citizens),
        ):
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.adults < 1:
            raise ValueError("at least one adult is required")

    def payload(self) -> dict[str, Any]:
        self.validate()
        return {
            "destinationStationCode": self.destination.upper(),
            "originStationCode": self.origin.upper(),
            "onWardDate": self.travel_date,
            "currency": self.currency.upper(),
            "pax": {
                "journeyClass": self.journey_class,
                "adult": self.adults,
                "child": self.children,
                "infant": self.infants,
                "srCitizen": self.sr_citizens,
            },
        }

    def referer(self) -> str:
        query = urlencode(
            {
                "from": self.origin.upper(),
                "to": self.destination.upper(),
                "tripType": 1,
                "departure": self.travel_date,
                "adult": self.adults,
                "child": self.children,
                "srCitizen": self.sr_citizens,
                "infant": self.infants,
                "currency": self.currency.upper(),
                "redirectTo": "/",
            }
        )
        return f"{SEARCH_URL}?{query}"


class SpiceJetClient:
    """Small HTTP client for SpiceJet's observed availability endpoint.

    This client deliberately returns raw JSON. SpiceJet-specific extraction
    belongs in parser.py so the source layer and normalization layer stay
    separate.
    """

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout
        self.session = requests.Session()

        retry = Retry(
            total=2,
            connect=2,
            read=2,
            status=2,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"POST"}),
            raise_on_status=False,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers.update(
            {
                "Accept": "*/*",
                "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8,hi;q=0.7",
                "Content-Type": "application/json",
                "Origin": BASE_URL,
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/153.0.0.0 Safari/537.36"
                ),
                "os": "web",
            }
        )

    def search_availability(self, request: SearchRequest) -> dict[str, Any]:
        request.validate()
        headers = {"Referer": request.referer()}

        try:
            response = self.session.post(
                AVAILABILITY_URL,
                json=request.payload(),
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise SpiceJetAPIError(f"SpiceJet availability request failed: {exc}") from exc

        if response.status_code != 200:
            body_preview = response.text[:500].replace("\n", " ")
            raise SpiceJetAPIError(
                f"SpiceJet availability returned HTTP {response.status_code}: {body_preview}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise SpiceJetAPIError("SpiceJet returned a non-JSON availability response") from exc

        if not isinstance(data, dict):
            raise SpiceJetAPIError("Unexpected SpiceJet response type")

        return data

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "SpiceJetClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
