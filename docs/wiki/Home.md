# DoD Budget Analysis — Wiki

Welcome to the project wiki for the **DoD Budget Analysis** tool — a public,
web-facing, queryable database of Department of Defense budget data.

> For the project roadmap and current status, see the
> [README](../../README.md) and [ROADMAP](../../ROADMAP.md).

---

## Pages

| Page | Description | Status |
|------|-------------|--------|
| **[Performance Optimizations](Performance-Optimizations.md)** ⚡ | **3-6x speedup achieved** — Overview of all 13 optimizations | ✅ Complete |
| [Data Sources](Data-Sources.md) | Catalog of all DoD budget data sources, URLs, and file formats | 🔄 In Progress (Phase 1.A, Step 1.A5) |
| [Exhibit Types](Exhibit-Types.md) | Budget exhibit type catalog with column layouts and semantics | 🔄 In Progress (Phase 1.B, Step 1.B1) |
| [Data Dictionary](Data-Dictionary.md) | Field definitions for the database and API | 📋 Planned (Phase 2–3, Steps 2.A1, 3.C2) |
| [Database Schema](Database-Schema.md) | Schema documentation and entity relationships | 📋 Planned (Phase 2.A, Steps 2.A1–2.A5) |
| [API Reference](API-Reference.md) | REST API endpoint documentation | 📋 Planned (Phase 2.C, Steps 2.C2–2.C6) |
| [Getting Started](Getting-Started.md) | End-user guide for searching and downloading data | 🔄 Partial (Phase 3.C, Step 3.C1) |
| [FAQ](FAQ.md) | Frequently asked questions | 🔄 Partial (Phase 3.C, Step 3.C3) |
| [Methodology](Methodology.md) | Data collection methodology and known limitations | 🔄 Partial (Phase 3.C, Step 3.C6) |
| [Contributing](Contributing.md) | Development setup, coding standards, and PR process | 📋 Planned (Phase 4.C, Step 4.C6) |

---

## Quick Links

- **Task Index:** [docs/TASK_INDEX.md](../TASK_INDEX.md) — master list of all Phase 0–1 tasks
- **Validation Suite:** `python validate_budget_db.py --verbose` — run data quality checks
- **Downloader:** `python dod_budget_downloader.py` — download DoD budget documents
- **Database Builder:** `python build_budget_db.py` — parse documents into SQLite
- **Search:** `python search_budget.py <query>` — full-text search the database
