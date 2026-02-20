# DoD Budget Analysis — Wiki

Welcome to the project wiki for the **DoD Budget Analysis** tool — a public,
web-facing, queryable database of Department of Defense budget data.

> For the project roadmap and current status, see the
> [README](../../README.md) and [ROADMAP](../ROADMAP.md).

---

## Pages

| Page | Description | Status |
|------|-------------|--------|
| **[Performance Optimizations](Performance-Optimizations.md)** | **3-6x speedup achieved** — Overview of all 13 optimizations | Complete |
| [Getting Started](Getting-Started.md) | End-user guide for searching, downloading, and querying data | Complete |
| [Data Sources](Data-Sources.md) | Catalog of all DoD budget data sources, URLs, and file formats | Complete |
| [Exhibit Types](Exhibit-Types.md) | Budget exhibit type catalog with column layouts and semantics | Complete |
| [Data Dictionary](Data-Dictionary.md) | Field definitions for the database | Complete |
| [Database Schema](Database-Schema.md) | Schema documentation and entity relationships | Complete |
| [Methodology](Methodology.md) | Data collection, parsing methodology, and known limitations | Complete |
| [FAQ](FAQ.md) | Frequently asked questions | Complete |
| [Utilities Reference](Utilities-Reference.md) | Shared utility modules — http, formatting, database, strings | Complete |
| [Contributing](Contributing.md) | Development setup, coding standards, and PR process | Complete |
| [API Reference](API-Reference.md) | REST API endpoint documentation | Planned (Phase 2.C) |

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Download budget documents (FY2026, all sources)
python dod_budget_downloader.py --years 2026 --sources all

# 3. Build the database
python build_budget_db.py

# 4. Search
python search_budget.py "F-35"

# 5. Validate data quality
python validate_budget_db.py --verbose
```

---

## Quick Links

- **Task Index:** [docs/TASK_INDEX.md](../TASK_INDEX.md) — master list of all Phase 0-1 tasks
- **Validation Suite:** `python validate_budget_db.py --verbose` — run data quality checks
- **Downloader:** `python dod_budget_downloader.py` — download DoD budget documents
- **Database Builder:** `python build_budget_db.py` — parse documents into SQLite
- **GUI Builder:** `python build_budget_gui.py` — graphical builder with progress tracking
- **Search:** `python search_budget.py <query>` — full-text search the database
- **Refresh Pipeline:** `python refresh_data.py --years 2026` — download + build + validate
