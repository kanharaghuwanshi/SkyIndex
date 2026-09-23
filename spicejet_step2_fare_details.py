from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


ORIGIN = "DEL"
DESTINATION = "BOM"
TRAVEL_DATE = "2026-09-30"

PAGE_WAIT = 10
MANUAL_SELECTION_WAIT = 30
POST_SELECTION_WAIT = 8
OUTPUT_DIR = Path("spicejet_debug")
OUTPUT_DIR.mkdir(exist_ok=True)


def build_search_url() -> str:
    params = {
        "from": ORIGIN,
        "to": DESTINATION,
        "tripType": 1,
        "departure": TRAVEL_DATE,
        "adult": 1,
        "child": 0,
        "srCitizen": 0,
        "infant": 0,
        "currency": "INR",
        "redirectTo": "/",
    }
    return "https://www.spicejet.com/search?" + urlencode(params)


def make_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--start-maximized")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL", "browser": "ALL"})

    driver = webdriver.Chrome(options=options)
    # Network.enable allows Chrome DevTools Protocol response-body retrieval.
    driver.execute_cdp_cmd("Network.enable", {})
    return driver


def safe_json_loads(text: str) -> Any | None:
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def collect_network(driver: webdriver.Chrome) -> list[dict[str, Any]]:
    """Collect API response metadata and, where Chrome still exposes it, bodies."""
    captured: list[dict[str, Any]] = []

    for item in driver.get_log("performance"):
        raw = safe_json_loads(item.get("message", ""))
        if not raw:
            continue

        message = raw.get("message", {})
        if message.get("method") != "Network.responseReceived":
            continue

        params = message.get("params", {})
        response = params.get("response", {})
        request_id = params.get("requestId")
        url = response.get("url", "")

        # We only care about SpiceJet API/XHR responses for this step.
        if "spicejet.com/api/" not in url.lower():
            continue

        record: dict[str, Any] = {
            "request_id": request_id,
            "url": url,
            "status": response.get("status"),
            "mime_type": response.get("mimeType"),
            "resource_type": params.get("type"),
        }

        try:
            body_result = driver.execute_cdp_cmd(
                "Network.getResponseBody", {"requestId": request_id}
            )
            body = body_result.get("body")
            if body:
                record["body"] = body
                record["json"] = safe_json_loads(body)
        except Exception as exc:  # body may already be discarded by Chrome
            record["body_error"] = str(exc)

        captured.append(record)

    return captured


def save_captured(captured: list[dict[str, Any]]) -> None:
    # Keep only API responses; exact response bodies are saved unchanged where available.
    out = OUTPUT_DIR / "fare_detail_network.json"
    out.write_text(json.dumps(captured, indent=2, ensure_ascii=False), encoding="utf-8")

    # Also write individual populated JSON responses so they can be inspected easily.
    api_json_dir = OUTPUT_DIR / "api_json"
    api_json_dir.mkdir(exist_ok=True)

    count = 0
    for index, item in enumerate(captured, start=1):
        payload = item.get("json")
        if payload is None:
            continue
        (api_json_dir / f"response_{index:03d}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        count += 1

    print(f"Captured API responses: {len(captured)}")
    print(f"Responses with JSON body saved: {count}")
    print(f"Metadata file: {out.resolve()}")

    for item in captured:
        print(
            f"HTTP {item.get('status')} | {item.get('resource_type')} | "
            f"{item.get('url')}"
        )


def print_browser_console(driver: webdriver.Chrome) -> None:
    try:
        entries = driver.get_log("browser")
    except Exception:
        return

    if not entries:
        return

    print("\nBrowser console messages:")
    for entry in entries[-30:]:
        print(entry.get("level"), entry.get("message"))


def main() -> None:
    driver = make_driver()

    try:
        url = build_search_url()
        print(f"Opening: {url}")
        driver.get(url)
        time.sleep(PAGE_WAIT)

        print("\nResults page should now be loaded.")
        print(
            "Manually select ONE fare/flight in the browser. "
            "Do not continue to payment and do not submit a purchase."
        )
        print(f"Waiting {MANUAL_SELECTION_WAIT} seconds for that selection...")
        time.sleep(MANUAL_SELECTION_WAIT)

        print(f"Waiting {POST_SELECTION_WAIT} seconds for follow-up API responses...")
        time.sleep(POST_SELECTION_WAIT)

        captured = collect_network(driver)
        save_captured(captured)
        print_browser_console(driver)

    finally:
        print("Closing browser...")
        driver.quit()


if __name__ == "__main__":
    main()
