# CLAUDE.md

Instructions for AI agents working on this codebase.

## Canonical References

- **[docs/PRD.md](docs/PRD.md)** — Program Requirements Document. The canonical description of all features. **Read this before implementing anything** to avoid duplicating or overwriting existing functionality. **Update this file whenever features are added, changed, or removed.**
- **[docs/ROADMAP.md](docs/ROADMAP.md)** — All project tasks (completed and remaining), plus the **"Remaining Work"** section with Groups A–G task assignments and DB verification queries. This is the single source of truth for what's done and what's left.
- **[docs/NOTICED_ISSUES.md](docs/NOTICED_ISSUES.md)** — Data quality and UI issues observed against the live database, with root cause analysis and resolution status (63 issues across 5 rounds).
- **[GitHub Wiki](https://github.com/wschosta/dod-budget-analysis/wiki)** — Detailed user guide, developer guide, architecture decisions, and API reference.

## Update Rules

When making changes to the codebase:

1. **Before implementing:** Read `docs/PRD.md` to understand what already exists.
2. **After implementing a feature change:** Update `docs/PRD.md` to reflect the new state.
3. **After completing a roadmap task:** Update `docs/ROADMAP.md` status.
4. **After changing user-facing docs content:** Update the corresponding [wiki page](https://github.com/wschosta/dod-budget-analysis/wiki). The wiki repo is at `https://github.com/wschosta/dod-budget-analysis.wiki.git`. Clone it, edit the relevant `.md` file, commit, and push.
5. **Wiki page naming:** Hyphens in filenames (`Getting-Started.md`), `[[Page Name]]` for internal links.

## Quick Reference

```bash
# Install
pip install -r requirements-dev.txt
python -m playwright install chromium

# Tests (114 files, coverage tracked on api/ and utils/)
python -m pytest tests/ -v
python -m pytest tests/ --cov=api --cov=utils --cov-report=term-missing
python -m pytest tests/ --ignore=tests/test_gui_tracker.py --ignore=tests/optimization_validation

# Lint, type check, format
ruff check . --select=E,W,F --ignore=E501 --exclude=DoD_Budget_Documents
mypy api/ utils/ --ignore-missing-imports
black .

# Dev server
uvicorn api.app:app --reload --port 8000

# Full pipeline
python run_pipeline.py --skip-download --rebuild

# Docker
docker compose up --build
```

## Repository Structure

```
dod-budget-analysis/
├── api/                     # FastAPI application
│   ├── app.py               # App factory, middleware, rate limiting, health
│   ├── database.py          # get_db() dependency, per-request connections
│   ├── models.py            # Pydantic request/response models
│   └── routes/              # One file per router group
│       ├── aggregations.py  # GET /api/v1/aggregations
│       ├── budget_lines.py  # GET /api/v1/budget-lines, /budget-lines/{id}
│       ├── dashboard.py     # Dashboard data endpoints
│       ├── download.py      # GET /api/v1/download (streaming CSV/NDJSON)
│       ├── explorer.py      # Keyword Explorer endpoints
│       ├── facets.py        # GET /api/v1/facets (cross-filtered counts)
│       ├── feedback.py      # POST /api/v1/feedback
│       ├── files.py         # GET /api/v1/files/{file_path}
│       ├── frontend.py      # HTML routes (/, /about, /charts, /compare, /consolidated, /dashboard, /explorer, /hypersonics, /programs)
│       ├── hypersonics.py   # Hypersonics PE lines pivot view
│       ├── keyword_search.py # Shared keyword-search cache-building logic
│       ├── metadata.py      # GET /api/v1/metadata
│       ├── pe.py            # PE-centric views, funding, sub-elements
│       ├── reference.py     # GET /api/v1/reference/{type}
│       └── search.py        # GET /api/v1/search (FTS5)
├── utils/                   # Shared utility library (19 modules)
├── pipeline/                # Data pipeline modules (15 modules)
│   ├── builder.py           # Database builder (Excel/PDF parsing)
│   ├── schema.py            # DB schema, migrations, reference table seeding
│   ├── enricher.py          # PE enrichment (tags, descriptions, lineage)
│   ├── db_validator.py      # Data quality validation
│   ├── validator.py         # Validation rules
│   ├── exhibit_catalog.py   # Exhibit type column layouts
│   ├── search.py            # CLI full-text search
│   ├── gui.py               # tkinter build interface
│   ├── refresh.py           # Data refresh workflow
│   └── ...                  # backfill, staging, logging, run_ledger
├── downloader/              # Document downloader modules (6 modules)
├── templates/               # Jinja2 HTML templates (12 pages + errors/ + partials/)
├── static/                  # CSS (main.css) + JS assets (10 modules)
├── tests/                   # pytest test suite (114 files)
├── scripts/                 # Operational scripts (21 modules: backups, audits, migrations, profiling)
├── docs/                    # PRD, ROADMAP, NOTICED_ISSUES, TOOL_ASSESSMENT, user-guide/, archive/
├── run_pipeline.py          # 5-step pipeline orchestrator
├── run_precommit_checks.py  # Pre-commit validation (ruff, mypy, pytest)
├── repair_database.py       # Data quality repair (7-step process)
└── stage_budget_data.py     # Data staging utility
```

## Architecture Decisions

- **Database:** SQLite + FTS5, WAL mode, raw SQL (no ORM)
- **API:** FastAPI + Pydantic v2
- **Frontend:** Jinja2 + HTMX + Chart.js (no build step)
- **Browser automation:** Playwright (Chromium) for WAF-protected sites
- **File paths:** `Path` objects, not raw strings
- **Dark mode:** CSS variables only (no hardcoded colors)

## Testing

- **Framework:** pytest + pytest-cov, config in `pyproject.toml`
- **Fixtures:** `test_db`, `test_db_excel_only`, `tmp_db`, `fixtures_dir` — defined in `tests/conftest.py`
- Use `test_db_excel_only` when tests only need Excel data (avoids pdfplumber panics)
- Rate-limiter tests must clear `api.app._rate_counters` (use `autouse=True` fixture)
- API tests: `TestClient(create_app(db_path=...))` with tmp_path-backed SQLite

## Code Standards

- **Formatter:** black (line length 100)
- **Linter:** ruff (`--select=E,W,F --ignore=E501`)
- **Type checker:** mypy on `api/` and `utils/`
- PEP 8 naming, type annotations on new functions
- `sqlite3` directly — no ORM
- `logging` not `print()` in library code
- CSS variables for theming — no hardcoded colors
- No new external dependencies without discussion

## Commit Messages

```
<TYPE>: <short imperative summary (<=72 chars)>

<optional body explaining "why", wrapped at 100 chars>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`

## Branch Naming

```
claude/<ticket-id>-<short-description>
feat/<short-description>
fix/<short-description>
docs/<short-description>
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_DB_PATH` | `dod_budget.sqlite` | Database path |
| `APP_PORT` | `8000` | Server port |
| `APP_HOST` | `127.0.0.1` | Server bind address |
| `APP_LOG_FORMAT` | `text` | Logging format (`text` or `json`) |
| `APP_CORS_ORIGINS` | `*` | CORS origins |
| `APP_DB_POOL_SIZE` | `10` | Max DB connections in pool |
| `RATE_LIMIT_SEARCH` | `60` | Search req/min/IP |
| `RATE_LIMIT_DOWNLOAD` | `10` | Download req/min/IP |
| `RATE_LIMIT_DEFAULT` | `120` | Default req/min/IP |
| `TRUSTED_PROXIES` | *(empty)* | Comma-separated proxy IPs for forwarded headers |

## Common Tasks

### Adding a New API Endpoint

1. Create/edit route file in `api/routes/`
2. Define Pydantic models in `api/models.py` if needed
3. Register router in `api/app.py`
4. Use `Depends(get_db)` for database access
5. Add tests in `tests/test_<endpoint>.py`
6. **Update `docs/PRD.md` section 3 (REST API)**

### Adding a New Frontend Page

1. Create template in `templates/` (extend `base.html`)
2. Add route in `api/routes/frontend.py`
3. Add JS in `static/js/` if needed
4. Use CSS variables for theming
5. Add tests in `tests/test_frontend_routes.py`
6. **Update `docs/PRD.md` section 4 (Web Frontend)**

### Modifying the Database Schema

1. Update DDL in `pipeline/schema.py`
2. Add migration to `migrate()` with incremented version
3. Test with `tests/test_pipeline_group/test_bear_migration.py`
4. **Update `docs/PRD.md` section 5 (Database Schema)**

### Adding a New Utility Module

1. Create `utils/<module>.py`
2. Export from `utils/__init__.py`
3. Add tests in `tests/test_<module>.py`
4. Ensure 80% coverage maintained

### Pre-PR Checklist

- [ ] `python -m pytest tests/ -v` passes
- [ ] `ruff check . --select=E,W,F --ignore=E501 --exclude=DoD_Budget_Documents` clean
- [ ] `mypy api/ utils/ --ignore-missing-imports` passes
- [ ] New functions have type annotations
- [ ] New endpoints have tests
- [ ] No hardcoded colors
- [ ] No secrets committed
- [ ] `docs/PRD.md` updated if features changed
- [ ] Wiki updated if user/developer docs affected
