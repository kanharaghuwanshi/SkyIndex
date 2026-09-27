SKYINDEX — CURRENT-FILE-COMPATIBLE UPDATE

This package is based ONLY on the current files supplied in the latest turn.

CHANGED
-------
backend/config.py
- Adds APIX_BASELINE_DATE.
- Default: 2026-09-24.
- Existing configuration names remain unchanged.

backend/index/apix.py
- Keeps the current import path and existing index_engine helpers.
- Keeps per-collection-date cleaning.
- Uses the fixed APIx baseline date.
- Recalculates every real collection date on/after the baseline against the same baseline.
- previous_apix/change_value/change_pct are previous-available-real-date changes.
- --rebuild refreshes all derived history from the baseline onward.
- Normal run refreshes only the latest derived date.
- airfare_quotes is never modified.

frontend/data-access.js
- Keeps every existing exported function name and dashboard snapshot shape.
- Adds richer current-schema quote fields.
- Adds getCollectionDates() and getAllQuotes().
- Existing script.js remains compatible.

frontend/script.js
- Only adds display of fixed baseline metadata.
- Existing dashboard logic is preserved.

frontend/index.html
- Existing DOM/layout is preserved.
- Navigation now links to Overview / Analysis / Data Explorer.
- Status label changed from LIVE MONITORING to OBSERVATION DATA.
- Adds a fixed-baseline metadata label.

frontend/style.css
- Existing design is preserved.
- Adds styles for the new analysis/explorer pages.

NEW
---
frontend/analysis.html
frontend/analysis.js
  Historical behaviour analysis:
  - fare trend
  - APIx trend
  - lead-time behaviour
  - fare component behaviour
  - airline comparison
  - route vs fixed baseline
  - volatility / descriptive signals

frontend/explorer.html
frontend/explorer.js
  Raw normalized observations with filters.

UNCHANGED ON PURPOSE
--------------------
spicejet_collector.py
spicejet_scraper.py
backend/scraper/spicejet/client.py
backend/scraper/spicejet/parser.py
backend/scraper/spicejet/__init__.py
backend/index/index_engine.py

RUN
---
One-time baseline rebuild:
    python -m backend.index.apix --rebuild

Normal future APIx update:
    python -m backend.index.apix

Frontend:
    python -m http.server 5500 --directory frontend

The baseline refers to collection_date, not travel_date.
No synthetic historical observations are created.
