# 📁 SkyIndex — Project Structure

> Compact technical overview of the current SkyIndex codebase.

## 🔹 Architecture

```text
Data Sources
    ↓
SpiceJet Scraper
    ↓
Parsing & Structuring
    ↓
Data Processing
    ↓
PostgreSQL / Supabase
    ↓
APIx Index Engine
    ↓
Frontend Dashboard
```

---

# 📂 Project Structure

```text
SkyIndex/
│
├── backend/
│   ├── scraper/
│   │   └── spicejet/
│   │       ├── client.py
│   │       └── parser.py
│   │
│   ├── index/
│   │   ├── apix.py
│   │   └── index_engine.py
│   │
│   └── config.py
│
├── frontend/
│   ├── index.html
│   ├── script.js
│   ├── analysis.html
│   ├── analysis.js
│   ├── explorer.html
│   ├── explorer.js
│   ├── style.css
│   └── data-access.js
│
├── spicejet_collector.py
├── spicejet_scraper.py
│
├── database/
│   └── schema.sql (run it in Supabase SQL editor to get tables it will create four tables)
├── .env.example
├── requirements.txt
├── README.md
└── PROJECT_STRUCTURE.md
```

---

# 🐍 Backend

## `backend/config.py`
Central configuration for the project.

Contains configurable values such as:
- Routes
- Booking lead times
- API limits
- Airline/source settings
- Route weights
- Environment-based configuration

---

## `backend/scraper/spicejet/client.py`
Handles interaction with the SpiceJet booking/source flow.

Responsible for:
- Sending requests / initiating source interaction
- Handling the source-side collection flow
- Returning raw source responses/data to the parser

---

## `backend/scraper/spicejet/parser.py`
Converts raw SpiceJet responses/pages into structured airfare observations.

Responsible for extracting fields such as:
- Origin / destination
- Flight information
- Travel date
- Fare
- Fare components where available
- Other relevant metadata

---

## `backend/index/index_engine.py`
Core statistical processing and index-generation logic.

Responsible for:
- Preparing validated observations for indexing
- Route-level aggregation
- Price-relative calculation
- Applying route weights
- Generating the overall **Airfare Price Index (APIx)**

---

## `backend/index/apix.py`
Execution layer for the APIx calculation.

Responsible for:
- Loading relevant historical/current data
- Running the index engine
- Producing APIx-related outputs
- Supporting index analysis/execution

---

# 🌐 Frontend

## `frontend/index.html`
Main SkyIndex dashboard/home interface.

Provides the primary overview of:
- Airfare Index
- Key metrics
- Major trends
- Overall system output

---

## `frontend/script.js`
Controls the main dashboard behaviour.

Handles:
- UI interactions
- Dashboard logic
- Dynamic data rendering
- Main-page visual updates

---

## `frontend/analysis.html`
Dedicated analysis dashboard.

Provides deeper views of airfare movements and trends.

---

## `frontend/analysis.js`
Controls the analysis dashboard.

Handles:
- Analytical calculations/display logic
- Filtering
- Trend rendering
- Dynamic analysis components

---

## `frontend/explorer.html`
Interactive data exploration interface.

Used to explore airfare observations at a more detailed level.

---

## `frontend/explorer.js`
Controls the explorer interface.

Handles:
- Search/filter functionality
- Data exploration
- Sorting
- Dynamic table/visual updates

---

## `frontend/style.css`
Global frontend styling.

Controls:
- Layout
- Typography
- Responsive design
- Dashboard components
- Tables
- Charts
- Overall visual appearance

---

## `frontend/data-access.js`
Frontend data-access layer.

Responsible for:
- Fetching data from backend/API/database-access endpoints
- Providing data to dashboard and analysis modules
- Keeping data retrieval logic separate from UI logic

---

# 🔄 Root-Level Scripts

## `spicejet_scraper.py`
Main SpiceJet scraping workflow.

Coordinates the scraping process and acts as a top-level entry point for collecting SpiceJet airfare data.

---

## `spicejet_collector.py`
Collection/orchestration layer for SpiceJet data.

Responsible for:
- Running collection jobs
- Managing the collection workflow
- Passing collected data into the processing/storage pipeline

---

# ⚙️ Project Configuration

## `.env.example`
Template for required environment variables.

Typically contains configuration placeholders for:
- API keys
- Database credentials
- Backend settings
- Other environment-specific values

**Actual secrets must not be committed to GitHub.**

---

## `requirements.txt`
Contains the Python dependencies required to run the SkyIndex backend, scraper and data-processing components.

---

# 📄 Documentation

## `README.md`
Main project documentation.

Contains:
- Problem statement
- SkyIndex solution
- Architecture
- Technology stack
- APIx methodology
- Dashboard capabilities
- Current scope
- Future scope
- SIH context

---

## `PROJECT_STRUCTURE.md`
Compact developer-oriented documentation of the codebase.

Contains:
- Current folder structure
- Individual file responsibilities
- Component relationships
- Quick understanding of the implementation

---

# 🔗 Component Relationship

```text
spicejet_scraper.py
        ↓
backend/scraper/spicejet/
        ├── client.py
        └── parser.py
        ↓
Structured Fare Data
        ↓
Storage / Processing
        ↓
backend/index/
        ├── index_engine.py
        └── apix.py
        ↓
APIx
        ↓
frontend/
        ├── index.html
        ├── analysis.html
        └── explorer.html
        ↓
Visualization & Analysis
```

---

# 🚧 Current vs Future

### Current
- SpiceJet source adapter
- Domestic route analysis
- Multiple booking lead times
- Fare data processing
- APIx calculation
- Interactive dashboard

### Future
The same modular architecture will be extended to:

```text
SpiceJet
IndiGo
Air India
Air India Express
Akasa Air
Other Airlines
OTAs
      ↓
Common Data Schema
      ↓
Common Processing Pipeline
      ↓
Common APIx Engine
      ↓
Common Dashboard
```

This keeps source-specific scraping logic isolated while allowing the **core indexing and analytics system to remain reusable**.
