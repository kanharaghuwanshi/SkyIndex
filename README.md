# SpiceJet Step 1 — Direct Availability Adapter

This step intentionally does **not** scrape rendered HTML. It uses the observed
SpiceJet `POST /api/v3/search/availability` response and keeps parsing separate
from the HTTP client.

## Files

```text
backend/scraper/spicejet/
├── __init__.py
├── client.py
├── parser.py
├── test_har_parser.py
└── www.spicejet.com after search.har   # captured fixture for parser testing
```

## Install

```bash
pip install -r requirements.txt
```

## Test the parser against the captured HAR

From the directory containing `backend`:

```bash
python -m backend.scraper.spicejet.test_har_parser
```

Or supply another HAR file:

```bash
python -m backend.scraper.spicejet.test_har_parser path/to/file.har
```

## Live request example

```python
from backend.scraper.spicejet import SpiceJetClient, parse_availability_response
from backend.scraper.spicejet.client import SearchRequest

request = SearchRequest(
    origin="DEL",
    destination="BOM",
    travel_date="2026-09-30",
    adults=1,
    children=0,
    infants=0,
    sr_citizens=0,
    currency="INR",
)

with SpiceJetClient(timeout=30) as client:
    raw = client.search_availability(request)
    quotes = parse_availability_response(raw, lead_time=8)

for quote in quotes:
    print(quote)
```

## Important behavior

- Returns **all journey/fare combinations** exposed in the availability response.
- Does not select only the cheapest flight.
- Uses source-provided values for base fare, taxes, UDF, and named charges.
- `convenience_fee` and `service_fee` stay `None` when the observed search response does not expose an amount for them.
- Keeps the raw fee/tax component list so later code can map source codes without losing information.
- Performs a component-vs-total validation flag (`breakdown_match`).
- Does not write to Supabase or modify APIx yet.









SPICEJET IMPORTANT : SpiceJet ki own historical pricing announcement ne 2014 me fuel surcharge ko separate component ke roop me remove karke base fare me consolidate karne ki baat kahi thi.