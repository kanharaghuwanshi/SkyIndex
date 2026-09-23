from __future__ import annotations

import json
from pathlib import Path

from .parser import parse_availability_response


HERE = Path(__file__).resolve().parent
DEFAULT_HAR = HERE / "www.spicejet.com after search.har"


def load_availability_from_har(har_path: str | Path) -> dict:
    har = json.loads(Path(har_path).read_text(encoding="utf-8"))

    for entry in har.get("log", {}).get("entries", []):
        request = entry.get("request", {})
        response = entry.get("response", {})
        url = request.get("url", "")
        text = (response.get("content") or {}).get("text") or ""

        if "/api/v3/search/availability" not in url or not text:
            continue

        return json.loads(text)

    raise RuntimeError("No populated /api/v3/search/availability response found in HAR")


def main() -> None:
    har_path = Path(__import__("sys").argv[1]) if len(__import__("sys").argv) > 1 else DEFAULT_HAR
    response = load_availability_from_har(har_path)
    quotes = parse_availability_response(response)

    print(f"Parsed quotes: {len(quotes)}")

    for quote in quotes:
        print(
            f"{quote['flight_number']:8} "
            f"{quote['fare_code']:6} "
            f"base={quote['base_fare']} "
            f"tax={quote['taxes']} "
            f"udf={quote['udf']} "
            f"fees={quote['fees']} "
            f"total={quote['total_fare']} "
            f"match={quote['breakdown_match']}"
        )


if __name__ == "__main__":
    main()
