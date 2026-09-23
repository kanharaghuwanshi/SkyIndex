from __future__ import annotations

import json
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities



PAGE_LOAD_WAIT = 8
BEFORE_SEARCH_WAIT = 5
AFTER_SEARCH_WAIT = 10

URL = (
    "https://www.spicejet.com/search?"
    "from=DEL&to=BOM&tripType=1&departure=2026-09-30&"
    "adult=1&child=0&srCitizen=0&infant=0&currency=INR&redirectTo=/"
)

OUTPUT = Path("spicejet_live_availability.json")


def build_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--start-maximized")

    # Capture Chrome performance/network logs. Selenium 4 + Chrome supports this
    # through the performance log interface used below.
    options.set_capability("goog:loggingPrefs", {"performance": "ALL", "browser": "ALL"})
    return webdriver.Chrome(options=options)


def main() -> None:
    driver = build_driver()
    try:
        # Enable CDP Network domain before navigation so response bodies can be
        # retrieved when the availability request completes.
        driver.execute_cdp_cmd("Network.enable", {})

        print("Opening SpiceJet search page...")
        time.sleep(PAGE_LOAD_WAIT)
        driver.get(URL)
        time.sleep(15)

        print("Reading captured network events...")
        logs = driver.get_log("performance")

        found = []

        for entry in logs:
            try:
                message = json.loads(entry["message"])["message"]
            except (KeyError, json.JSONDecodeError):
                continue

            if message.get("method") != "Network.responseReceived":
                continue

            params = message.get("params", {})
            response = params.get("response", {})
            url = response.get("url", "")

            if "/api/v3/search/availability" not in url:
                continue

            request_id = params.get("requestId")
            print(f"Found availability response: HTTP {response.get('status')} {url}")

            try:
                body = driver.execute_cdp_cmd(
                    "Network.getResponseBody",
                    {"requestId": request_id},
                )
                text = body.get("body", "")
                data = json.loads(text)
            except Exception as exc:
                print(f"Could not read response body: {exc}")
                continue

            found.append(data)

        if not found:
            print("No /api/v3/search/availability response was captured.")
            print("Open DevTools manually and verify that the search page actually performed the search.")
            return

        OUTPUT.write_text(json.dumps(found[0], indent=2), encoding="utf-8")
        print(f"Saved live availability JSON to: {OUTPUT.resolve()}")

        # Optional: immediately feed the live response into your existing parser.
        try:
            from backend.scraper.spicejet.parser import parse_availability_response

            quotes = parse_availability_response(found[0])
            print(f"Parsed quotes: {len(quotes)}")
            for q in quotes:
                print(
                    q["flight_number"],
                    q["fare_code"],
                    f"base={q['base_fare']}",
                    f"tax={q['taxes']}",
                    f"udf={q['udf']}",
                    f"fees={q['fees']}",
                    f"total={q['total_fare']}",
                    f"match={q['breakdown_match']}",
                )
        except ImportError:
            print("Parser import skipped: run this script from your SkyIndex project root.")

    finally:
        print("Closing browser...")
        driver.quit()


if __name__ == "__main__":
    main()
