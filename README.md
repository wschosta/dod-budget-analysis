# DoD Budget Explorer

A Python toolkit for downloading, parsing, normalizing, and querying Department of Defense budget justification documents. Features a bulk document downloader, Excel/PDF parser, SQLite database with full-text search, a FastAPI REST API, and a web frontend with interactive charts.

## Quick Start

```bash
# Clone and install
git clone https://github.com/wschosta/dod-budget-analysis.git
cd dod-budget-analysis
pip install -r requirements.txt
python -m playwright install chromium

# Run the full pipeline (download + build + validate + enrich)
python run_pipeline.py --years 2026 --sources all

# Start the web UI and API
uvicorn api.app:app --reload --port 8000
# Open http://localhost:8000
```

Or use Docker:

```bash
docker compose up --build
```

## Data Pipeline

```
DoD websites (Comptroller, Army, Navy, Air Force, Defense-Wide)
        |
        v
dod_budget_downloader.py  ->  DoD_Budget_Documents/  (PDFs, XLSX, CSV, ZIP)
        |
        v
build_budget_db.py        ->  dod_budget.sqlite  (SQLite + FTS5)
        |
        v
validate_budget_data.py   ->  data_quality_report.json
        |
        v
enrich_budget_db.py       ->  pe_index, pe_descriptions, pe_tags, pe_lineage
        |
        v
api/app.py (FastAPI)      ->  Browser (HTMX + Chart.js)
```

The full pipeline can be run with `python run_pipeline.py`.

## Data Sources

| Source | Website | Method |
|--------|---------|--------|
| **Comptroller** | comptroller.defense.gov | Direct HTTP |
| **Defense Wide** | comptroller.defense.gov | Direct HTTP |
| **US Army** | asafm.army.mil | Playwright (WAF) |
| **US Navy** | secnav.navy.mil | Playwright (SharePoint) |
| **US Air Force** | saffm.hq.af.mil | Playwright (WAF) |

## Web UI

The web interface at `http://localhost:8000` provides:

- **Search** — Full-text keyword search with filters for fiscal year, service, exhibit type, appropriation, and amount range
- **Charts** — Year-over-year trends, service comparisons, and top-N budget items
- **Dashboard** — Budget overview with interactive visualizations
- **Programs** — Browse and search by program element with funding history
- **Export** — Download filtered results as CSV, JSON, or Excel
- **Dark mode** — Toggle between light and dark themes

## REST API

All data endpoints are under `/api/v1`. Interactive docs at `/docs` (Swagger) and `/redoc`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/search` | GET | Full-text search (FTS5 + BM25 ranking) |
| `/api/v1/budget-lines` | GET | Filtered, paginated budget line items |
| `/api/v1/budget-lines/{id}` | GET | Single budget line item detail |
| `/api/v1/aggregations` | GET | GROUP BY summaries for charts/dashboards |
| `/api/v1/download` | GET | Streaming CSV/NDJSON export |
| `/api/v1/reference/{type}` | GET | Reference data (services, exhibit types, fiscal years) |
| `/api/v1/metadata` | GET | Database and dataset metadata |
| `/health` | GET | Health check |

Amounts are in **thousands of dollars ($K)** unless `amount_unit` says otherwise.

## Testing

```bash
python -m pytest tests/ -v
python -m pytest tests/ --cov=api --cov=utils --cov-report=term-missing --cov-fail-under=80
ruff check . --select=E,W,F --ignore=E501 --exclude=DoD_Budget_Documents
mypy api/ utils/ --ignore-missing-imports
```

## Documentation

| Resource | Description |
|----------|-------------|
| **[Wiki](https://github.com/wschosta/dod-budget-analysis/wiki)** | Full documentation: user guide, developer guide, architecture decisions |
| **[PRD](docs/PRD.md)** | Program Requirements Document — canonical feature list |
| **[Roadmap](docs/ROADMAP.md)** | Project roadmap with task tracking |
| **[Contributing](CONTRIBUTING.md)** | Development setup, code standards, PR process |

## License

This tool downloads publicly available U.S. government budget documents. All downloaded content is public domain.
