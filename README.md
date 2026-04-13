# DoD Budget Explorer

A searchable database of Department of Defense budget justification documents. Downloads thousands of Excel spreadsheets and PDF documents from official DoD websites, parses them into structured data, and serves them through a REST API and web interface. Built for defense analysts, congressional staffers, journalists, and researchers who need to search, filter, compare, and export DoD budget data without manually navigating dozens of government websites.

**Key capabilities:**
- **6 data sources** — Comptroller, Defense-Wide, Army, Navy, Air Force (including WAF-protected sites via Playwright)
- **15+ exhibit types** — P-1, P-5, R-1, R-2, R-3, R-4, O-1, M-1, C-1, RF-1, plus OCO/supplemental/amendment variants
- **Full-text search** — SQLite FTS5 with BM25 relevance ranking across budget lines and PDF page text
- **Keyword Explorer** — Fuzzy keyword search with prefix/acronym/edit-distance matching, async cache build, and XLSX export with dynamic array formulas
- **30+ API endpoints** — Filtered queries, aggregations, PE drill-downs, faceted counts, streaming exports
- **Interactive web UI** — HTMX + Chart.js with dark mode, sparklines, and responsive design

## Quick Start

```bash
# Clone and install
git clone https://github.com/wschosta/dod-budget-analysis.git
cd dod-budget-analysis
pip install -r requirements.txt
python -m playwright install chromium

# Run the full pipeline (download + build + repair + validate + enrich)
python scripts/run_pipeline.py --years 2026 --sources all

# Start the web UI and API
uvicorn api.app:app --reload --port 8000
# Open http://localhost:8000
```

Or use Docker:

```bash
docker compose up --build
```

## Data Pipeline

The system operates as a 5-step pipeline orchestrated by `scripts/run_pipeline.py`:

```
DoD websites (Comptroller, Army, Navy, Air Force, Defense-Wide)
        |
        v
    Download       ->  DoD_Budget_Documents/  (PDFs, XLSX, CSV, ZIP)
        |
        v
    Build          ->  dod_budget.sqlite  (SQLite + FTS5)
        |
        v
    Repair         ->  Normalized org names, reference tables, indexes
        |
        v
    Validate       ->  data_quality_report.json
        |
        v
    Enrich         ->  PE index, descriptions, tags, lineage, BLI data
        |
        v
    api/app.py     ->  Browser (HTMX + Chart.js)
```

- **Download** — Parallel discovery and download with smart file skipping, retry with exponential backoff, and `--retry-failures` for failed files
- **Build** — Excel/PDF parsing with data-driven column mapping, incremental and full-rebuild modes, parallel PDF processing
- **Repair** — Organization name normalization, reference table population, index creation, FTS5 rebuild
- **Validate** — 10+ automated quality checks including duplicate detection, null analysis, cross-service reconciliation
- **Enrich** — 9-phase enrichment: PE index, descriptions, tags, lineage, project decomposition, BLI index/tags/descriptions

## Data Sources

| Source | Website | Method |
|--------|---------|--------|
| **Comptroller** | comptroller.defense.gov | Direct HTTP |
| **Defense-Wide** | comptroller.defense.gov | Direct HTTP |
| **US Army** | asafm.army.mil | Playwright (WAF) |
| **US Navy** | secnav.navy.mil | Playwright (SharePoint) |
| **Navy Archive** | secnav.navy.mil | Playwright (SharePoint) |
| **US Air Force** | saffm.hq.af.mil | Playwright (WAF) |

## Web UI

The web interface at `http://localhost:8000` provides:

| Page | Description |
|------|-------------|
| **Explorer** (`/`) | Default landing page. Keyword search with fuzzy matching, async cache build, PE-level preview, drag-and-drop column picker, XLSX export. Includes a Hypersonics Preset. |
| **About** (`/about`) | Project description, data coverage, and methodology overview |
| **Programs** (`/programs`) | Program element browsing with tag filters, search, and funding history |
| **Dashboard** (`/dashboard`) | Summary cards, budget-by-service chart, Top-10 programs, appropriation breakdown |
| **Charts** (`/charts`) | Year-over-year trends, service comparisons, top-N programs, treemap, budget type breakdown |
| **Consolidated** (`/consolidated`) | Consolidated PE-level budget view with drill-down detail |
| **Spruill** (`/spruill`) | Spruill-chart view for individual PE funding analysis |

Additional UI features: dark mode with system detection, funding trend sparklines, keyboard shortcuts, responsive design, download modal (CSV/JSON/XLSX), contextual tooltips, and accessibility support (skip-to-content, ARIA live regions, focus-visible styles).

## REST API

All data endpoints are under `/api/v1`. Interactive docs at `/docs` (Swagger) and `/redoc`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/search` | GET | Full-text search (FTS5 + BM25 ranking) with snippet highlighting |
| `/api/v1/budget-lines` | GET | Filtered, paginated budget line items with sorting |
| `/api/v1/budget-lines/{id}` | GET | Single budget line item detail |
| `/api/v1/aggregations` | GET | GROUP BY summaries for charts/dashboards |
| `/api/v1/facets` | GET | Faceted filter counts with cross-filtering |
| `/api/v1/download` | GET | Streaming CSV/NDJSON export |
| `/api/v1/reference/{type}` | GET | Reference data (services, exhibit types, fiscal years, appropriations) |
| `/api/v1/metadata` | GET | Database and dataset metadata |
| `/api/v1/pe/{pe_number}` | GET | Program element detail with funding history |
| `/api/v1/pe/{pe_number}/years` | GET | PE funding data across fiscal years |
| `/api/v1/pe/{pe_number}/changes` | GET | PE year-over-year funding changes |
| `/api/v1/pe/{pe_number}/subelements` | GET | PE sub-element breakdown |
| `/api/v1/pe/{pe_number}/descriptions` | GET | PE narrative descriptions |
| `/api/v1/pe/{pe_number}/related` | GET | Related PEs by similarity |
| `/api/v1/pe/top-changes` | GET | PEs with largest year-over-year funding changes |
| `/api/v1/pe/compare` | GET | Side-by-side funding comparison of multiple PEs |
| `/api/v1/dashboard/summary` | GET | Dashboard summary statistics |
| `/api/v1/explorer/build` | POST | Start async keyword cache build |
| `/api/v1/explorer` | GET | PE-level keyword search results |
| `/api/v1/explorer/download/xlsx` | POST | XLSX export with dynamic array formulas |
| `/api/v1/feedback` | POST | User feedback submission |
| `/health` | GET | Health check with DB connectivity |
| `/health/detailed` | GET | Uptime, request/error counts, query stats |

Per-IP rate limiting (configurable), ETag caching, CORS, CSP headers, and structured access logging.

Amounts are in **thousands of dollars ($K)** unless `amount_unit` says otherwise.

## Project Status

| Phase | Status | Details |
|-------|--------|---------|
| **0 — Documentation** | ✅ Complete | README, wiki, roadmap |
| **1 — Data Extraction** | ✅ ~97% Complete | 6 sources, 15+ exhibit types, 5-step pipeline |
| **2 — Database & API** | ✅ Complete | Schema, migrations, 30+ API endpoints, 15 route modules |
| **3 — Frontend & Docs** | ✅ Complete | 10 pages, Chart.js visualizations, 6 user guide docs |
| **4 — Publish & Iterate** | 🔄 ~56% Complete | CI/CD, Docker, monitoring done; hosting/domain/launch pending |

**Test suite:** 107 test files with comprehensive coverage across all modules. Automated CI via GitHub Actions (matrix testing, ruff, mypy, pytest+coverage, Docker build).

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full task breakdown (65 tasks across 4 phases).

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
