from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from backend.scraper.spicejet.parser import parse_availability_response


SPICEJET_SEARCH_URL = "https://www.spicejet.com/search"
AVAILABILITY_PATH = "/api/v3/search/availability"

# Deliberately conservative. This is request pacing, not an anti-bot bypass.
MIN_REQUEST_INTERVAL_SECONDS = 30.0
PAGE_LOAD_WAIT_SECONDS = 10.0
POST_RESPONSE_WAIT_SECONDS = 5.0
MAX_403_RETRIES = 1
RETRY_403_WAIT_SECONDS = 30.0


@dataclass(frozen=True)
class SpiceJetSearch:
    origin: str
    destination: str
    travel_date: str
    adults: int = 1
    children: int = 0
    senior_citizens: int = 0
    infants: int = 0
    currency: str = "INR"

    def validate(self) -> None:
        if len(self.origin) != 3 or not self.origin.isalpha():
            raise ValueError("origin must be a 3-letter IATA code")
        if len(self.destination) != 3 or not self.destination.isalpha():
            raise ValueError("destination must be a 3-letter IATA code")

        datetime.strptime(self.travel_date, "%Y-%m-%d")

        if self.adults < 1:
            raise ValueError("adults must be >= 1")
        if min(self.children, self.senior_citizens, self.infants) < 0:
            raise ValueError("passenger counts cannot be negative")

    def url(self) -> str:
        self.validate()
        params = {
            "from": self.origin.upper(),
            "to": self.destination.upper(),
            "tripType": 1,
            "departure": self.travel_date,
            "adult": self.adults,
            "child": self.children,
            "srCitizen": self.senior_citizens,
            "infant": self.infants,
            "currency": self.currency.upper(),
            "redirectTo": "/",
        }
        return f"{SPICEJET_SEARCH_URL}?{urlencode(params)}"


class SpiceJetHTTPError(RuntimeError):
    def __init__(self, status: int, url: str) -> None:
        self.status = int(status)
        self.url = url
        super().__init__(f"SpiceJet availability returned HTTP {self.status}: {self.url}")


class SpiceJetScraper:
    """Reusable Selenium-based SpiceJet availability scraper.

    One browser session can execute multiple searches, but every search is
    intentionally paced by MIN_REQUEST_INTERVAL_SECONDS by default.

    The scraper does not attempt to bypass CAPTCHA, fingerprinting, rate
    limits, IP restrictions, or other anti-abuse controls. If the site blocks
    or challenges the session, the caller should stop the collection run.
    """

    def __init__(
        self,
        *,
        min_request_interval: float = MIN_REQUEST_INTERVAL_SECONDS,
        page_load_wait: float = PAGE_LOAD_WAIT_SECONDS,
        post_response_wait: float = POST_RESPONSE_WAIT_SECONDS,
        output_dir: str | Path = "spicejet_data",
    ) -> None:
        if min_request_interval < 0:
            raise ValueError("min_request_interval cannot be negative")
        if page_load_wait < 0 or post_response_wait < 0:
            raise ValueError("wait values cannot be negative")

        self.min_request_interval = float(min_request_interval)
        self.page_load_wait = float(page_load_wait)
        self.post_response_wait = float(post_response_wait)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.driver = self._build_driver()
        self._last_search_started_at: float | None = None

    @staticmethod
    def _build_driver() -> webdriver.Chrome:
        options = Options()
        options.add_argument("--start-maximized")
        options.set_capability(
            "goog:loggingPrefs",
            {"performance": "ALL", "browser": "ALL"},
        )

        driver = webdriver.Chrome(options=options)
        driver.execute_cdp_cmd("Network.enable", {})
        return driver

    def _wait_for_request_slot(self) -> None:
        if self._last_search_started_at is None:
            return

        elapsed = time.monotonic() - self._last_search_started_at
        remaining = self.min_request_interval - elapsed
        if remaining > 0:
            print(f"Waiting {remaining:.1f}s before next SpiceJet search...")
            time.sleep(remaining)

    def _clear_performance_logs(self) -> None:
        # Drain old performance events before a new navigation so a response
        # from a previous search can never be mistaken for the current search.
        try:
            self.driver.get_log("performance")
        except Exception:
            pass

    def _read_availability_response(self) -> dict[str, Any]:
        logs = self.driver.get_log("performance")

        # Read from newest matching response first. Logs were drained before
        # navigation, so matching events belong to the current search attempt.
        for entry in reversed(logs):
            try:
                outer = json.loads(entry["message"])
                message = outer["message"]
            except (KeyError, TypeError, json.JSONDecodeError):
                continue

            if message.get("method") != "Network.responseReceived":
                continue

            params = message.get("params", {})
            response = params.get("response", {})
            url = str(response.get("url", ""))

            if AVAILABILITY_PATH not in url:
                continue

            status = int(response.get("status", 0))
            print(f"Availability response: HTTP {status}")

            if status != 200:
                raise SpiceJetHTTPError(status, url)

            request_id = params.get("requestId")
            if not request_id:
                continue

            try:
                body_result = self.driver.execute_cdp_cmd(
                    "Network.getResponseBody",
                    {"requestId": request_id},
                )
                body = body_result.get("body", "")
            except Exception as exc:
                raise RuntimeError(
                    f"Could not retrieve availability response body: {exc}"
                ) from exc

            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                raise RuntimeError("Availability response body was not valid JSON") from exc

            if not isinstance(payload, dict):
                raise RuntimeError("Availability response JSON is not an object")

            return payload

        raise RuntimeError(
            "No /api/v3/search/availability response was captured. "
            "The page may still be loading or the search did not complete."
        )

    @staticmethod
    def _print_summary(quotes: list[dict[str, Any]]) -> None:
        print(f"Parsed quotes: {len(quotes)}")
        for quote in quotes:
            print(
                f"{quote.get('flight_number', '-'):8} "
                f"{quote.get('fare_code', '-'):6} "
                f"base={quote.get('base_fare')} "
                f"tax={quote.get('taxes')} "
                f"udf={quote.get('udf')} "
                f"fees={quote.get('fees')} "
                f"total={quote.get('total_fare')} "
                f"match={quote.get('breakdown_match')}"
            )

    def search(self, request: SpiceJetSearch) -> list[dict[str, Any]]:
        request.validate()
        self._wait_for_request_slot()

        url = request.url()
        last_error: Exception | None = None

        for attempt in range(MAX_403_RETRIES + 1):
            if attempt > 0:
                print(
                    f"HTTP 403 retry {attempt}/{MAX_403_RETRIES}; "
                    f"waiting {RETRY_403_WAIT_SECONDS:.0f}s..."
                )
                time.sleep(RETRY_403_WAIT_SECONDS)

            self._clear_performance_logs()
            self._last_search_started_at = time.monotonic()
            print(f"Opening: {url}" if attempt == 0 else f"Retrying: {url}")

            # One browser navigation triggers the normal site request flow.
            # No direct API call is made here.
            self.driver.get(url)
            time.sleep(self.page_load_wait)
            time.sleep(self.post_response_wait)

            try:
                raw = self._read_availability_response()
                last_error = None
                break
            except SpiceJetHTTPError as exc:
                last_error = exc
                if exc.status != 403 or attempt >= MAX_403_RETRIES:
                    raise
                print("Availability returned HTTP 403; one controlled retry will be attempted.")

        if last_error is not None:
            raise last_error

        collected_at_dt = datetime.now().astimezone()
        collected_at = collected_at_dt.isoformat()
        collection_date = collected_at_dt.date().isoformat()
        lead_time = (
            datetime.strptime(request.travel_date, "%Y-%m-%d").date()
            - collected_at_dt.date()
        ).days

        quotes = parse_availability_response(
            raw,
            collection_date=collection_date,
            collected_at=collected_at,
            lead_time=lead_time,
        )

        self._print_summary(quotes)
        return quotes

    def save_raw_response(self, response: dict[str, Any], filename: str = "availability.json") -> Path:
        path = self.output_dir / filename
        path.write_text(json.dumps(response, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved raw response: {path.resolve()}")
        return path

    def save_quotes(self, quotes: list[dict[str, Any]], filename: str = "quotes.json") -> Path:
        path = self.output_dir / filename
        path.write_text(json.dumps(quotes, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved parsed quotes: {path.resolve()}")
        return path

    def close(self) -> None:
        if getattr(self, "driver", None) is not None:
            self.driver.quit()
            self.driver = None

    def __enter__(self) -> "SpiceJetScraper":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def main() -> None:
    search = SpiceJetSearch(
        origin="DEL",
        destination="BOM",
        travel_date="2026-09-30",
        adults=1,
    )

    with SpiceJetScraper() as scraper:
        quotes = scraper.search(search)
        scraper.save_quotes(quotes)


if __name__ == "__main__":
    main()
