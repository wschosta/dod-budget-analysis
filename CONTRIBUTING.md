# Contributing to DoD Budget Explorer

Thank you for your interest in contributing.  This guide covers everything you need to get started: prerequisites, development setup, code standards, testing, and the pull-request process.

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.10+ | 3.11 or 3.12 recommended |
| Git | 2.x | Any recent version |
| Docker | 24+ | Optional — only needed for container testing |
| SQLite | 3.35+ | Built into Python; FTS5 must be enabled |

Check your Python version:

```bash
python3 --version   # must be >= 3.10
python3 -c "import sqlite3; sqlite3.connect(':memory:').execute('CREATE VIRTUAL TABLE t USING fts5(x)')"
# no output = FTS5 is available
```

---

## Development Setup

```bash
# 1. Clone the repository
git clone https://github.com/wschosta/dod-budget-analysis.git
cd dod-budget-analysis

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install production + dev dependencies
pip install -r requirements-dev.txt

# 4. (Optional) Build a local test database
#    Downloads and processes ~50 MB of public DoD budget spreadsheets.
python build_budget_db.py --help
python build_budget_db.py        # writes dod_budget.sqlite in the project root

# 5. (Optional) Install pre-commit hook
cp scripts/hooks/pre-commit-hook.py .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

# 6. Start the development API server
uvicorn api.app:app --reload --port 8000
# Open http://localhost:8000 in your browser
# OpenAPI docs: http://localhost:8000/docs
```

### Docker (alternative)

```bash
docker compose up --build        # starts the API with hot-reload
docker compose down              # stop
```

---

## Project Structure

```
dod-budget-analysis/
├── api/                    # FastAPI application
│   ├── app.py              # App factory, middleware, /health endpoints
│   ├── database.py         # DB path resolution
│   └── routes/             # One file per router group
│       ├── aggregations.py # /api/v1/aggregations
│       ├── budget_lines.py # /api/v1/budget-lines
│       ├── download.py     # /api/v1/download
│       ├── frontend.py     # GET /, /charts, /partials/*
│       ├── reference.py    # /api/v1/reference/*
│       └── search.py       # /api/v1/search
├── build_budget_db.py      # Download + ingest pipeline (Excel + PDF)
├── refresh_data.py         # Scheduled data refresh with rollback
├── scripts/
│   └── backup_db.py        # SQLite online backup script
├── static/css/             # main.css
├── templates/              # Jinja2 HTML templates
│   ├── base.html
│   ├── index.html          # Search page
│   ├── charts.html         # Visualizations page
│   └── partials/           # HTMX partial responses
├── tests/                  # pytest test suite
├── utils/                  # Shared utilities
├── docs/wiki/              # Extended documentation
├── docker-compose.yml      # Development Docker config
├── docker-compose.staging.yml  # Staging Docker config
└── Dockerfile
```

### Data Flow

```
DoD Comptroller websites
        │
        ▼
build_budget_db.py  ──►  dod_budget.sqlite  ──►  api/app.py  ──►  Browser
  (ingest XLSX/PDF)       (SQLite + FTS5)         (FastAPI)        (HTMX + Chart.js)
        │
        ▼
refresh_data.py  (weekly scheduled refresh with automatic rollback)
```

---

## Code Standards

### Formatting

All Python code is formatted with **black** (line length 100):

```bash
black .
```

### Linting

**ruff** is used for fast linting:

```bash
ruff check . --select=E,W,F --ignore=E501
ruff check . --fix          # auto-fix safe issues
```

### Type Hints

New functions and methods should have type annotations.  We use **mypy** for static type checking:

```bash
mypy api/ utils/ --ignore-missing-imports
```

### General Guidelines

- Follow PEP 8 naming conventions.
- Keep functions small and focused (single responsibility).
- Prefer `Path` objects over raw strings for file paths.
- Use `sqlite3` directly — no ORM.  Raw SQL is fine and intentional here.
- Do not add external dependencies without discussing in the issue first.
- Avoid `print()` in library code; use `logging`.

---

## Testing

### Run the full test suite

```bash
pytest tests/ -v
```

### Run with coverage

```bash
pytest tests/ --cov=. --cov-report=term-missing
```

### Run a specific test file

```bash
pytest tests/test_charts_data.py -v
pytest tests/test_rate_limiter.py::TestSearchRateLimit -v
```

### Writing New Tests

1. Create `tests/test_<module>.py`.
2. Use the shared fixtures in `tests/conftest.py` where possible.
3. For API tests, create an in-memory or `tmp_path`-backed SQLite DB, build
   the schema with `executescript()`, and wrap it with `create_app(db_path=...)`.
4. Rate-limiter tests must clear `api.app._rate_counters` between cases
   (use an `autouse=True` fixture).
5. Module-scoped `client` fixtures are efficient but share global DB-path state —
   if a test changes the DB path, put it in a separate module.

```python
import sqlite3
import api.app as app_module
from fastapi.testclient import TestClient
from api.app import create_app

@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db = tmp_path_factory.mktemp("mytest") / "test.sqlite"
    conn = sqlite3.connect(str(db))
    conn.executescript("CREATE TABLE budget_lines (...); ...")
    conn.close()
    return TestClient(create_app(db_path=db))

@pytest.fixture(autouse=True)
def clear_rate_counters():
    app_module._rate_counters.clear()
    yield
    app_module._rate_counters.clear()
```

### Fixtures Overview

| Fixture | Scope | Description |
|---------|-------|-------------|
| `test_db_excel_only` | session | 200-row DB with Excel data only |
| `test_db` | session | 200-row DB with Excel + PDF data |
| `client` (conftest) | session | `TestClient` backed by `test_db` |
| *per-file fixtures* | module | Test-specific DBs created in `tmp_path` |

---

## Pull Request Process

### Branch naming

```
claude/<ticket-id>-<short-description>   # agent branches
feat/<short-description>                 # new features
fix/<short-description>                  # bug fixes
docs/<short-description>                 # documentation only
```

### Commit message format

```
<TYPE>: <short imperative summary (≤72 chars)>

<optional body explaining the "why", wrapped at 100 chars>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`.

Example:

```
feat: add --pdf-timeout flag to build_budget_db.py

PDF extraction can hang indefinitely on malformed files.  Added a
configurable subprocess timeout (default 30 s) that kills stalled workers
and logs them as failures in failed_downloads.json.
```

### Review checklist

Before submitting a PR, ensure:

- [ ] `pytest tests/ -v` passes locally
- [ ] `ruff check .` reports no errors
- [ ] `mypy api/ utils/ --ignore-missing-imports` passes
- [ ] New public functions have type annotations
- [ ] Any new endpoint has a corresponding test
- [ ] `REMAINING_TODOS.md` updated if a TODO was completed
- [ ] No secrets, credentials, or large binary files committed

---

## Getting Help

- Open an issue at <https://github.com/wschosta/dod-budget-analysis/issues>
- Check `docs/wiki/` for extended documentation on the API, data model,
  and architecture decisions
- Review `docs/design/deployment_design.py` and the `TODO` comments in each source file
  for planned-but-not-yet-implemented features
