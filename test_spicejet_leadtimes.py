from __future__ import annotations

from datetime import date

from spicejet_scraper import SpiceJetScraper, SpiceJetSearch

COLLECTION_DATE = date(2026, 9, 22)
ROUTES = [("DEL", "BOM")]
LEAD_TIMES = [1, 7, 15, 30, 45]


def main() -> None:
    print("SpiceJet lead-time validation test")
    print(f"Collection date: {COLLECTION_DATE.isoformat()}")
    print(f"Lead times: {LEAD_TIMES}")
    print("Minimum interval between searches: 30 seconds\n")

    with SpiceJetScraper(min_request_interval=30) as scraper:
        for origin, destination in ROUTES:
            for index, lead_time in enumerate(LEAD_TIMES, start=1):
                travel_date = (
                    COLLECTION_DATE
                    + __import__("datetime").timedelta(days=lead_time)
                ).isoformat()

                print(f"========== T+{lead_time} ({index}/{len(LEAD_TIMES)}) ==========")
                print(f"Route: {origin} -> {destination}")
                print(f"Travel date: {travel_date}")

                search = SpiceJetSearch(
                    origin=origin,
                    destination=destination,
                    travel_date=travel_date,
                    adults=1,
                )

                quotes = scraper.search(search)

                # Do not overwrite a common quotes.json during validation.
                filename = f"{origin}_{destination}_T{lead_time}.json"
                scraper.save_quotes(quotes, filename)
                print(
                    f"T+{lead_time} completed: {len(quotes)} quotes -> {filename}\n"
                )


if __name__ == "__main__":
    main()
