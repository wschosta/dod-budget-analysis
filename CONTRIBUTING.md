# Contributing to DoD Budget Analysis

Thank you for your interest in contributing. This guide covers prerequisites, development setup, code standards, testing, and the pull-request process.

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

# 4. Install Playwright for browser-based downloads
python -m playwright install chromium

# 5. (Optional) Build a local test database
python build_budget_db.py

# 6. (Optional) Install pre-commit hook
cp scripts/hooks/pre-commit-hook.py .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

# 7. Start the development API server
uvicorn api.app:app --reload --port 8000
# Open http://localhost:8000 in your browser
# OpenAPI docs: http://localhost:8000/docs
```

### Docker (alternative)

```bash
docker compose up --build        # starts the API with hot-reload
docker compose down              # stop
```

### Getting test data

```bash
# Download a small slice for development
python dod_budget_downloader.py --sources comptroller --years 2026

# Build the database
python build_budget_db.py

# Verify
python validate_budget_db.py --verbose
```

---

## Project Structure

```
dod-budget-analysis/
├── api/                    # FastAPI application
│   ├── app.py              # App factory, middleware, /health endpoints
│   ├── database.py         # DB path resolution, connection pool
│   ├── models.py           # Pydantic request/response models
│   └── routes/             # One file per router group
├── utils/                  # Shared utility library (16 modules)
├── tests/                  # pytest test suite (75 test files)
│   ├── conftest.py         # Shared fixtures
│   └── fixtures/           # Static test fixture data
├── templates/              # Jinja2 HTML templates
├── static/                 # CSS, JavaScript
├── scripts/                # Operational scripts
├── docs/                   # Documentation
│   ├── user-guide/         # End-user documentation
│   ├── developer/          # Developer documentation
│   ├── decisions/          # Architecture Decision Records
│   └── archive/            # Historical development docs
├── build_budget_db.py      # Main data ingestion pipeline
├── dod_budget_downloader.py # Multi-source document downloader
├── run_pipeline.py         # Full pipeline orchestrator
├── refresh_data.py         # Scheduled data refresh
├── docker-compose.yml      # Development Docker config
└── Dockerfile
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
ruff check . --select=E,W,F --ignore=E501 --exclude=DoD_Budget_Documents
ruff check . --fix          # auto-fix safe issues
```

### Type Hints

New functions and methods should have type annotations. We use **mypy** for static type checking:

```bash
mypy api/ utils/ --ignore-missing-imports
```

### General Guidelines

- Follow PEP 8 naming conventions
- Keep functions small and focused (single responsibility)
- Prefer `Path` objects over raw strings for file paths
- Use `sqlite3` directly — no ORM. Raw SQL is intentional
- Do not add external dependencies without discussing in an issue first
- Use `logging` module instead of `print()` in library code
- Use CSS variables for colors/theming (no hardcoded color values)

---

## Testing

### Run the full test suite

```bash
python -m pytest tests/ -v
```

### Run with coverage

```bash
python -m pytest tests/ --cov=api --cov=utils --cov-report=term-missing --cov-fail-under=80
```

### Run specific tests

```bash
python -m pytest tests/test_api.py -v
python -m pytest tests/test_rate_limiter.py::TestSearchRateLimit -v
```

### Skip GUI and optimization tests (as CI does)

```bash
python -m pytest tests/ --ignore=tests/test_gui_tracker.py --ignore=tests/optimization_validation
```

### Writing New Tests

1. Create `tests/test_<module>.py`
2. Use shared fixtures from `tests/conftest.py` where possible
3. For API tests: create an in-memory or `tmp_path`-backed SQLite DB, build the schema with `executescript()`, and wrap with `TestClient(create_app(db_path=...))`
4. Rate-limiter tests must clear `api.app._rate_counters` between cases (use `autouse=True` fixture)
5. Module-scoped `client` fixtures share global DB-path state — if a test changes the DB path, put it in a separate module
6. Use `test_db_excel_only` instead of `test_db` when tests only need Excel data (avoids pdfplumber PanicException)

See [docs/developer/testing.md](docs/developer/testing.md) for the full testing guide.

### Fixtures Overview

| Fixture | Scope | Description |
|---------|-------|-------------|
| `fixtures_dir` | session | Temp directory with Excel + PDF fixture files |
| `fixtures_dir_excel_only` | session | Temp directory with only Excel fixtures |
| `test_db` | session | Pre-built SQLite DB from all fixtures |
| `test_db_excel_only` | session | Pre-built SQLite DB from Excel-only fixtures |
| `bad_excel` | session | Intentionally malformed Excel file |
| `tmp_db` | function | Empty SQLite DB for unit tests |

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
<TYPE>: <short imperative summary (<=72 chars)>

<optional body explaining the "why", wrapped at 100 chars>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`.

Example:

```
feat: add --pdf-timeout flag to build_budget_db.py

PDF extraction can hang indefinitely on malformed files. Added a
configurable subprocess timeout (default 30 s) that kills stalled workers
and logs them as failures in failed_downloads.json.
```

### Pre-PR checklist

Before submitting a PR, ensure:

- [ ] `python -m pytest tests/ -v` passes locally
- [ ] `ruff check . --select=E,W,F --ignore=E501 --exclude=DoD_Budget_Documents` reports no errors
- [ ] `mypy api/ utils/ --ignore-missing-imports` passes
- [ ] New public functions have type annotations
- [ ] Any new endpoint has a corresponding test
- [ ] No hardcoded colors (use CSS variables)
- [ ] No secrets, credentials, or large binary files committed

---

## Pre-commit Hook

A pre-commit hook (`scripts/hooks/pre-commit-hook.py`) runs checks before each commit:
- Module import checks
- Syntax validation
- Code quality (no debug statements)
- Security (no hardcoded secrets)
- Database schema consistency
- Required files check

Install it:

```bash
cp scripts/hooks/pre-commit-hook.py .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

Or run manually:

```bash
python scripts/run_precommit_checks.py
```

---

## Reporting Issues

When reporting issues, include:

- **Bug reports:** Steps to reproduce, expected behavior, actual behavior, Python/OS version, and relevant log output
- **Data quality issues:** Source file path, exhibit type, specific field(s), expected vs actual values, and `python validate_budget_db.py --verbose` output
- **Feature requests:** Use case, proposed approach, alternatives considered

Open an issue at <https://github.com/wschosta/dod-budget-analysis/issues>.

---

## Further Reading

- [Developer Documentation](docs/developer/) — Architecture, API reference, testing, deployment
- [User Guide](docs/user-guide/) — Data sources, exhibit types, data dictionary, FAQ
- [Architecture Decisions](docs/decisions/) — ADRs for key technology choices
