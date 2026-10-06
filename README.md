# ✈️ SkyIndex

### Real-Time Airfare Price Index for India

**SkyIndex** is an end-to-end data engineering and statistical analytics platform that collects domestic airfare data from airline and Online Travel Aggregator (OTA) booking sources, standardizes and validates the observations, and converts them into a representative **Airfare Price Index (APIx)**.

The platform is designed to support **high-frequency airfare monitoring and augmentation of India's Consumer Price Index (CPI)** by transforming frequently changing airfare observations into structured, historical and statistically usable data.

---

## 📌 Problem

Airfares are highly dynamic and can change frequently based on:

- Demand and availability
- Booking lead time
- Route
- Airline
- Travel date
- Seasonality
- Fare type and applicable charges

Traditional periodic or manual collection therefore provides only a limited snapshot of a rapidly changing airfare market.

The challenge is not simply to find the cheapest flight, but to **systematically collect, normalize and analyze airfare observations so that market-level price movement can be measured over time.**

---

# 💡 Our Solution

**SkyIndex** provides a complete pipeline:

**Airline / OTA Sources → Automated Data Collection → Data Validation & Normalization → Historical Storage → Index Engine → Analytics Dashboard**

The platform combines web data acquisition, data processing, statistical index construction and visualization into a modular system.

Unlike a conventional flight-price comparison application, SkyIndex focuses on converting individual airfare observations into a **structured statistical indicator of airfare movement**.

---

# 🎯 Key Objectives

- Automate high-frequency domestic airfare data collection.
- Capture structured fare and flight metadata.
- Capture fare components wherever they are exposed by the source.
- Normalize observations from different airlines and OTAs into a common structure.
- Track airfare behaviour across routes and booking lead times.
- Generate a representative **Airfare Price Index (APIx)**.
- Provide historical and analytical views through dashboards and APIs.
- Build a scalable architecture for adding airlines, OTAs and routes independently.

---

# 🔍 Why Web Scraping?

Airfare APIs, GDSs and third-party datasets can be useful sources, but they may involve:

- Limited source or airline coverage
- Commercial/API access dependencies
- Restrictions on data fields or collection frequency
- Incomplete visibility into consumer-facing fare structures

SkyIndex therefore uses **direct source-level data acquisition through airline and OTA booking flows**, wherever appropriate and permitted.

This enables the system to capture market-facing airfare observations and, where exposed by the source, detailed fare components such as:

- Base Fare
- Taxes
- UDF / Airport Charges
- Convenience / Service Fees
- Other Charges
- Total Payable Fare

A **modular source-specific architecture** is used so that each airline or OTA can have its own extraction logic while sharing the common processing and indexing pipeline.

---

# ⚙️ System Architecture

```text
                 ┌───────────────────────────────┐
                 │       Airline / OTA Sources   │
                 │                               │
                 │   SpiceJet / Other Airlines  │
                 │          / OTAs               │
                 └───────────────┬───────────────┘
                                 │
                                 ▼
                 ┌───────────────────────────────┐
                 │     Data Acquisition Layer    │
                 │                               │
                 │  Source-specific Scrapers     │
                 │  Scrapy / Selenium            │
                 └───────────────┬───────────────┘
                                 │
                                 ▼
                 ┌───────────────────────────────┐
                 │       Fare Observations       │
                 │  Fare + Flight + Route Data   │
                 └───────────────┬───────────────┘
                                 │
                                 ▼
                 ┌───────────────────────────────┐
                 │     Data Processing Layer     │
                 │                               │
                 │  Python + Pandas              │
                 │  Validation / Normalization   │
                 │  Deduplication / Filtering    │
                 └───────────────┬───────────────┘
                                 │
                                 ▼
                 ┌───────────────────────────────┐
                 │      PostgreSQL / Supabase    │
                 │      Historical Data Store    │
                 └───────────────┬───────────────┘
                                 │
                                 ▼
                 ┌───────────────────────────────┐
                 │      SkyIndex Index Engine    │
                 │                               │
                 │             APIx              │
                 └───────────────┬───────────────┘
                                 │
                       ┌─────────┴─────────┐
                       ▼                   ▼
              ┌─────────────────┐  ┌─────────────────┐
              │   API Layer     │  │   Analytics /   │
              │    FastAPI      │  │    Dashboard    │
              └────────┬────────┘  └────────┬────────┘
                       └──────────┬─────────┘
                                  ▼
                         ┌───────────────────┐
                         │   SkyIndex UI     │
                         │ Trends & Analysis │
                         └───────────────────┘
```

> The current repository contains the **SpiceJet source adapter** as the active direct-airline implementation. The architecture is designed to extend the same pattern to additional airlines and OTAs.

---

# 🧩 Core Components

## 1. Data Acquisition Layer

SkyIndex follows a **source-specific scraper architecture**.

### Current Implementation

The current repository contains a dedicated **SpiceJet scraper** consisting of:

- `client.py` — source interaction / request and collection logic
- `parser.py` — parsing and normalization of extracted fare data

Additional airline and OTA adapters can be added using the same modular approach.

### Planned Expansion

The architecture can be extended independently for:

- Major Indian airlines
- Online Travel Aggregators (OTAs)
- Additional domestic and regional routes

The core processing and index engine do not need to be redesigned for every new source.

---

# 2. Fare Data Extraction

For each valid airfare observation, SkyIndex is designed to capture information such as:

### Flight & Route Metadata

- Origin
- Destination
- Airline
- Departure date
- Collection date / time
- Booking lead time
- Fare / fare-class information, where available

### Fare Information

- Base Fare
- Taxes
- UDF / Airport Charges
- Convenience / Service Fees
- Other Charges
- Total Fare

> Individual fare components depend on what the source exposes during the booking flow.

---

# 3. Data Processing

Collected observations are processed before being used for statistical analysis.

### Processing includes

- Schema normalization
- Data type conversion
- Missing-value handling
- Deduplication
- Input validation
- Invalid observation filtering
- Outlier checks
- Cross-source consistency checks

The objective is to convert heterogeneous source data into a **common analytical structure** suitable for comparison and index computation.

---

# 📊 Airfare Price Index — APIx

The core analytical component of SkyIndex is the **Airfare Price Index (APIx)**.

The index converts individual airfare observations into a representative measure of airfare movement over time.

### Route Basket

A representative basket of domestic Indian routes is maintained for index construction.

Routes can be assigned different weights based on their relevance within the target airfare market.

### Booking Lead Time

SkyIndex tracks multiple advance-purchase windows, including:

```text
T+1
T+7
T+15
T+30
T+45
```

This allows the platform to study how airfare behaviour changes as the travel date approaches.

### Index Outputs

The index engine can generate:

- Overall Airfare Price Index
- Route-level price relatives
- Lead-time level price movement
- Percentage change
- Historical index trends

---

# 🗄️ Data Storage

SkyIndex uses **PostgreSQL / Supabase** as the structured data layer.

Historical observations provide the foundation for:

- Index calculation
- Historical trend analysis
- Route-level comparison
- Airline-level analysis
- Fare-component analysis
- Data validation
- Dashboard and API queries

---

# ⏱️ Automated & Scalable Collection

The architecture is designed to support recurring and scalable collection jobs.

For a larger deployment, background processing can be handled using:

- **Celery** — task scheduling and background execution
- **Redis** — task/message broker

This allows data collection, processing and user-facing services to operate independently.

---

# 🚀 API Layer

**FastAPI** provides the API architecture for exposing processed data and analytical outputs.

The API layer can serve:

- Fare observations
- Historical data
- Index values
- Route-level analytics
- Airline-level analytics
- Dashboard data

This also provides a foundation for future integration with institutional statistical systems.

---

# 📈 Dashboard

The SkyIndex dashboard converts processed airfare data into analytical views.

### Main Capabilities

- Overall APIx movement
- Daily / weekly / monthly trends
- Route-wise comparison
- Airline-wise comparison
- Booking lead-time analysis
- Fare-component analysis
- Historical price movement
- Index change indicators

### Analytical Questions

The dashboard is designed to answer questions such as:

> **Are domestic airfares increasing or decreasing?**

> **Which routes are contributing most to the movement?**

> **How does airfare change with booking lead time?**

> **Which airlines or fare components are contributing to the change?**

---

# 🛠️ Technology Stack

| Layer | Technology |
|---|---|
| Data Collection | Scrapy, Selenium |
| Programming | Python |
| Data Processing | Pandas |
| Background Jobs | Celery |
| Message Broker | Redis |
| Database | PostgreSQL |
| Managed Database | Supabase |
| Backend API | FastAPI |
| Visualization | Chart.js |
| Frontend | HTML, CSS, JavaScript |
| Version Control | Git / GitHub |

---

# 📁 Current Project Structure

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
├── .env.example
├── requirements.txt
└── README.md
```

### Structure Overview

| Component | Purpose |
|---|---|
| `backend/scraper/` | Source-specific airfare collection |
| `backend/scraper/spicejet/` | Current SpiceJet adapter |
| `client.py` | Source interaction and collection logic |
| `parser.py` | Parsing and structuring extracted data |
| `backend/index/` | Index calculation and analytical engine |
| `apix.py` | APIx-related index execution |
| `index_engine.py` | Core index-processing logic |
| `config.py` | Project configuration |
| `frontend/` | Dashboard and analytical interfaces |
| `spicejet_collector.py` | SpiceJet collection workflow |
| `spicejet_scraper.py` | SpiceJet scraping workflow |
| `.env.example` | Environment variable template |
| `requirements.txt` | Python dependencies |

> As additional airlines and OTAs are integrated, new source-specific adapters will be added under `backend/scraper/` without changing the core indexing architecture.

---

# 🔄 Data Pipeline

```text
1. Source Selection
        ↓
2. Fare Collection
        ↓
3. Raw Fare Observation
        ↓
4. Parsing
        ↓
5. Cleaning & Validation
        ↓
6. Normalization
        ↓
7. Deduplication / Filtering
        ↓
8. Historical Storage
        ↓
9. APIx Calculation
        ↓
10. Analytics / API
        ↓
11. Dashboard Visualization
```

---

# 📐 Index Calculation Concept

At a high level, SkyIndex follows a weighted index approach:

```text
Individual Fare Observations
            ↓
      Price Relatives
            ↓
   Route-level Aggregation
            ↓
       Route Weights
            ↓
      Overall APIx
```

The methodology is designed to remain **transparent and reproducible**, allowing the route basket, weights and statistical methodology to be refined as the dataset expands.

---

# ✅ Data Quality

Airfare data collected from online booking systems can contain:

- Duplicate observations
- Missing values
- Sold-out flights
- Invalid or incomplete fares
- Different fare structures across sources
- Source-specific formatting differences

SkyIndex applies validation, normalization and filtering before observations are used for analysis and index construction.

---

# 📌 Current Scope

The current implementation focuses on:

- Indian domestic airfare analysis
- Selected domestic routes
- Multiple booking lead-time windows
- **SpiceJet direct-airline data acquisition**
- Fare decomposition where exposed by the source
- Data cleaning and normalization
- Historical data storage
- Airfare Price Index (APIx)
- Interactive analytical dashboards

The underlying architecture is designed to expand to **additional airlines, OTAs and routes** without changing the core processing and indexing pipeline.

---

# 🚀 Scalability

SkyIndex is designed around a modular architecture in which:

```text
New Airline / OTA
        ↓
New Source Adapter
        ↓
Common Data Schema
        ↓
Same Processing Pipeline
        ↓
Same Database
        ↓
Same Index Engine
        ↓
Same Dashboard / API
```

This avoids creating a separate system for every airline and allows the platform to scale as the number of data sources and routes increases.

---

# 🔮 Future Scope

- Integration of major Indian airlines through independent source adapters
- Integration of major Online Travel Aggregators (OTAs)
- Expansion to a larger national route basket
- Higher-frequency automated collection
- Larger historical dataset
- Automated data-quality monitoring
- Advanced statistical index methodologies
- Distributed and scalable collection infrastructure
- Institutional API integrations
- Integration with government statistical data pipelines

---

# 🎯 Expected Impact

SkyIndex aims to transform frequently changing online airfare observations into a **structured, transparent and reproducible statistical signal** that can support:

- High-frequency airfare monitoring
- Route-level market analysis
- Airline-level analysis
- Booking lead-time analysis
- Fare-component analysis
- Historical airfare trend detection
- Data-driven inflation analysis
- Augmentation of Consumer Price Index (CPI) measurement

The long-term objective is to build a **scalable airfare data and statistical indexing infrastructure**, rather than a consumer flight-booking or fare-comparison application.

---

# 🏆 Smart India Hackathon

SkyIndex was developed in response to the Smart India Hackathon problem statement:

**Development of a Real-time Airfare Price Index for India through Automated Scraping of Airline and Online Travel Aggregator Portals for Augmentation of the Consumer Price Index**

### Problem Statement

**SIH26056**

### Organization

**Ministry of Statistics and Programme Implementation (MoSPI)**

### Category

**Software**

### Theme

**Travel & Tourism**

---

# 📜 License

This project is intended for research, academic and prototype development purposes.

Source-specific collectors should be used in accordance with applicable permissions, website requirements and relevant API/source terms.

---

## 👥 Project Status

**Current Phase:** Direct-airline airfare collection and index pipeline development

**Current Source Adapter:** SpiceJet

**Expansion Target:** Major Indian airlines + Online Travel Aggregators

**Core Objective:** Automated, high-frequency and statistically structured airfare data for Airfare Price Index generation.
