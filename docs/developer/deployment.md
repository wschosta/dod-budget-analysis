# Deployment Runbook

This runbook covers everything needed to deploy, operate, and maintain the DoD
Budget API in local development, Docker, and CI-assisted environments.

---

## 1. Prerequisites

| Tool | Minimum Version | Notes |
|------|----------------|-------|
| Python | 3.11 | 3.12 recommended; tested in CI on both |
| Docker | 24.x | Required for containerized deployments |
| Docker Compose | 2.x (`docker compose` or `docker-compose`) | Required for dev compose stack |
| git | 2.x | Required to clone the repository |

Clone the repository before proceeding:

```bash
git clone <repo-url> dod-budget-analysis
cd dod-budget-analysis
```

---

## 2. Quick Start -- Local Development (No Docker)

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install dev dependencies (for testing, linting, type checking)
pip install -r requirements-dev.txt

# 4. Build the SQLite database from downloaded source documents
python build_budget_db.py

# 5. Start the API server with auto-reload
uvicorn api.app:app --reload --host 127.0.0.1 --port 8000
```

The API is now available at `http://localhost:8000`.
Confirm it is healthy:

```bash
curl http://localhost:8000/health
```

---

## 3. Docker Deployment

### Dockerfile

The project provides multiple Docker configurations:

| File | Purpose |
|------|---------|
| `Dockerfile` | Standard development/production image |
| `docker/Dockerfile.multistage` | Multi-stage production build (smaller image) |
| `docker-compose.yml` | Development with hot-reload |
| `docker/docker-compose.staging.yml` | Staging environment |

### Build the image

```bash
docker build -t dod-budget .
```

### Run the container

The database file is mounted from the host at runtime. Build it first if it
does not exist (see Section 2, step 4).

```bash
docker run -d \
  --name dod-budget \
  -p 8000:8000 \
  -v "$(pwd)/dod_budget.sqlite:/app/dod_budget.sqlite" \
  dod-budget
```

### Environment variables at runtime

```bash
docker run -d \
  --name dod-budget \
  -p 8000:8000 \
  -v "$(pwd)/dod_budget.sqlite:/app/dod_budget.sqlite" \
  -e APP_DB_PATH=/app/dod_budget.sqlite \
  -e APP_LOG_FORMAT=json \
  -e RATE_LIMIT_SEARCH=30 \
  dod-budget
```

See Section 6 for the full environment variable reference.

### Docker security

- The container runs as a non-root user (`appuser`) for security
- The database is mounted as a volume, not baked into the image
- The health check endpoint (`/health`) is configured in the Dockerfile

---

## 4. docker-compose -- Development with Hot-Reload

The included `docker-compose.yml` mounts the local source tree and enables
Uvicorn's `--reload` flag so that changes to `api/` and `utils/` take effect
without restarting the container.

```bash
# Start the stack (builds the image if not already built)
docker compose up

# Rebuild the image before starting (e.g., after requirements.txt changes)
docker compose up --build

# Run in detached mode
docker compose up -d

# Stop and remove containers (data volume is on the host, not in Docker)
docker compose down
```

The API is available at `http://localhost:8000`.

> **Note:** The compose file mounts `./dod_budget.sqlite` read-only into the
> container. Run `python build_budget_db.py` on the host whenever you need to
> refresh the database.

---

## 5. Data Updates

### Manual refresh on the host

```bash
# Full pipeline: download, build, validate, enrich
python run_pipeline.py

# Or step by step:
python dod_budget_downloader.py --years 2026 --sources all
python build_budget_db.py
python validate_budget_data.py
python enrich_budget_db.py

# Refresh with automatic rollback on failure
python refresh_data.py --years 2026 -v

# Dry run -- preview what would be downloaded without writing files
python refresh_data.py --years 2026 --dry-run -v
```

`refresh_data.py` downloads new source documents and then calls
`build_budget_db.py` internally. The resulting `dod_budget.sqlite` is written
to the working directory.

### Triggering the GitHub Actions workflow

The **Refresh Data** workflow runs automatically every Sunday at 06:00 UTC.
To trigger it manually:

1. Go to **Actions -> Refresh Data** in the GitHub repository.
2. Click **Run workflow**.
3. Optionally set **Fiscal year** (default: `2026`) and **Dry run**.
4. After the run completes, download the `dod-budget-db-<year>-<run_id>`
   artifact which contains `dod_budget.sqlite`, `data_quality_report.json`,
   and `refresh_report.json`.
5. Replace the running database file with the artifact (see Section 7 for
   backup steps before replacing).

---

## 6. Environment Variables Reference

All environment variables have sensible defaults and are optional.

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_DB_PATH` | `dod_budget.sqlite` | Path to the SQLite database file. In Docker, override to `/app/dod_budget.sqlite`. |
| `APP_PORT` | `8000` | API server port. |
| `APP_LOG_FORMAT` | `text` | Logging format: `text` (human-readable) or `json` (structured). |
| `APP_CORS_ORIGINS` | `*` | Comma-separated list of allowed CORS origins. Set to specific domains in production. |
| `APP_DB_POOL_SIZE` | `10` | Maximum number of database connections in the connection pool. |
| `RATE_LIMIT_SEARCH` | `60` | Maximum search requests per minute per IP address. |
| `RATE_LIMIT_DOWNLOAD` | `10` | Maximum download/export requests per minute per IP address. |
| `RATE_LIMIT_DEFAULT` | `120` | Maximum requests per minute per IP address for all other endpoints. |
| `TRUSTED_PROXIES` | (empty) | Comma-separated list of trusted proxy IP addresses for `X-Forwarded-For` handling. |
| `SUPPORTED_FISCAL_YEARS` | `2024,2025,2026` | Comma-separated list of supported fiscal years for validation and filtering. |

Set these in a `.env` file for local development or pass them with `-e` flags
to `docker run`.

### Production recommendations

| Variable | Recommendation |
|----------|---------------|
| `APP_CORS_ORIGINS` | Set to your specific frontend domain(s) instead of `*` |
| `APP_LOG_FORMAT` | Use `json` for structured log aggregation |
| `APP_DB_POOL_SIZE` | Increase to `20` or higher for high-traffic deployments |
| `TRUSTED_PROXIES` | Set to your load balancer/reverse proxy IP(s) |
| `RATE_LIMIT_SEARCH` | Adjust based on expected traffic patterns |

---

## 7. Database Backup

The entire application state lives in a single SQLite file. Back it up by
copying it:

```bash
# Simple timestamped backup
cp dod_budget.sqlite "dod_budget_$(date +%Y%m%d_%H%M%S).sqlite"

# Or copy to a dedicated backup directory
mkdir -p backups
cp dod_budget.sqlite backups/dod_budget_$(date +%Y%m%d).sqlite

# Using the backup script (uses SQLite online backup API)
python scripts/backup_db.py
```

SQLite files are safe to copy while the API is running in read-only mode (the
compose stack mounts it `:ro`). For a running read-write deployment, use the
`scripts/backup_db.py` script which uses SQLite's online backup API, or stop
the container first.

---

## 8. Rollback Procedure

1. **Stop the running container.**

   ```bash
   docker stop dod-budget       # standalone
   docker compose down          # compose
   ```

2. **Restore the previous database.**

   ```bash
   cp backups/dod_budget_<previous_date>.sqlite dod_budget.sqlite
   ```

3. **Re-tag or pull the previous Docker image** (if a code change is also
   being rolled back).

   ```bash
   # Example: roll back to a specific image digest or tag
   docker tag dod-budget:previous dod-budget:latest
   ```

4. **Restart the service.**

   ```bash
   docker run -d --name dod-budget -p 8000:8000 \
     -v "$(pwd)/dod_budget.sqlite:/app/dod_budget.sqlite" dod-budget

   # Or with compose:
   docker compose up -d
   ```

5. **Verify health** (see Section 9).

The `refresh_data.py` script includes automatic rollback: if the build or
validation step fails, the previous database is restored automatically.

---

## 9. Health Check

The API exposes two health endpoints:

### Basic health

```bash
curl -sf http://localhost:8000/health && echo "OK" || echo "UNHEALTHY"
```

A `200 OK` response confirms the server is running and the database is
reachable. A `503` response indicates the database file is missing or
unreadable.

### Detailed health

```bash
curl -s http://localhost:8000/health/detailed | python3 -m json.tool
```

Returns operational metrics including uptime, request counts, error counts,
database size, and rate limiter statistics. See
[API Reference](api-reference.md) for full response schema.

### Docker health monitoring

Docker monitors health automatically via the `HEALTHCHECK` instruction in the
Dockerfile (interval: 30s, timeout: 5s, retries: 3). Check container health
status with:

```bash
docker inspect --format='{{.State.Health.Status}}' dod-budget
```

---

## 10. Secrets Management

No secrets are required to run the DoD Budget API in its current form. All
source data is downloaded from public DoD websites without authentication.

**If cloud deployment keys are added in the future**, follow these guidelines:

- Store secrets in the CI environment as **GitHub Actions encrypted secrets**
  (Settings -> Secrets and variables -> Actions), never in the repository.
- For server deployments, use a secrets manager (e.g., AWS Secrets Manager,
  HashiCorp Vault) and inject values as environment variables at runtime --
  do not bake them into the Docker image.
- Rotate keys immediately if they are ever committed to the repository by
  mistake, and invalidate the exposed credential before rewriting git history.
- Document any new secrets in this section, listing the variable name, purpose,
  and which team member owns rotation.

---

## 11. CI/CD

### Workflows

| Workflow | File | Trigger | Description |
|----------|------|---------|-------------|
| CI | `.github/workflows/ci.yml` | Push/PR to main | Lint, type check, test groups, coverage, Docker build |
| Deploy | `.github/workflows/deploy.yml` | Manual/tag | Docker build/push to GHCR + deploy |
| Download | `.github/workflows/download.yml` | Manual | Automated document download |
| Refresh Data | `.github/workflows/refresh-data.yml` | Weekly (Sunday 06:00 UTC) / Manual | Download, build, validate, produce artifact |

### CI pipeline steps

1. **Lint** -- `ruff check` for style violations
2. **Type check** -- `mypy` on `api/` and `utils/`
3. **Test groups** -- Parallel test execution (see [Testing](testing.md))
4. **Coverage** -- Enforce 80% minimum on `api/` and `utils/`
5. **Docker build** -- Verify the image builds and imports work

---

## 12. Monitoring

### Log output

The API logs all requests with timing information. Use `APP_LOG_FORMAT=json`
for structured logging compatible with log aggregation tools (ELK, Datadog,
CloudWatch, etc.).

### Key metrics to monitor

| Metric | Source | Alert Threshold |
|--------|--------|----------------|
| Health status | `GET /health` | Any non-200 response |
| Error rate | `GET /health/detailed` → `error_count` | Sustained increase |
| Response time | `GET /health/detailed` → `avg_response_time_ms` | >500ms sustained |
| Rate limit blocks | `GET /health/detailed` → `rate_limiter_stats.blocked_requests` | Unusual spikes |
| Database size | `GET /health/detailed` → `db_size_bytes` | Unexpected growth |
| Container health | `docker inspect` | `unhealthy` status |

---

## Related Documentation

- [Architecture Overview](architecture.md) -- System design and component interactions
- [API Reference](api-reference.md) -- Endpoint specifications and security headers
- [Database Schema](database-schema.md) -- Database structure and pragmas
- [Performance](performance.md) -- Performance tuning and optimization
- [Testing](testing.md) -- How to run the test suite
