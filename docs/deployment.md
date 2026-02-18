# Deployment Runbook — DoD Budget API

This runbook covers everything needed to deploy, operate, and maintain the DoD Budget API
in local development, Docker, and CI-assisted environments.

---

## 1. Prerequisites

| Tool | Minimum Version | Notes |
|------|----------------|-------|
| Python | 3.11 | 3.12 recommended; tested in CI on both |
| Docker | 24.x | Required for containerised deployments |
| Docker Compose | 2.x (`docker compose` or `docker-compose`) | Required for dev compose stack |
| git | 2.x | Required to clone the repository |

Clone the repository before proceeding:

```bash
git clone <repo-url> dod-budget-analysis
cd dod-budget-analysis
```

---

## 2. Quick Start — Local Development (No Docker)

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Build the SQLite database from downloaded source documents
python build_budget_db.py

# 4. Start the API server with auto-reload
uvicorn api.app:app --reload --host 127.0.0.1 --port 8000
```

The API is now available at `http://localhost:8000`.
Confirm it is healthy:

```bash
curl http://localhost:8000/health
```

---

## 3. Docker Deployment

### Build the image

```bash
docker build -t dod-budget .
```

### Run the container

The database file is mounted from the host at runtime. Build it first if it does not exist
(see Section 2, step 3).

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
  -e LOG_LEVEL=info \
  dod-budget
```

See Section 6 for the full environment variable reference.

---

## 4. docker-compose — Development with Hot-Reload

The included `docker-compose.yml` mounts the local source tree and enables Uvicorn's
`--reload` flag so that changes to `api/` and `utils/` take effect without restarting
the container.

```bash
# Start the stack (builds the image if not already built)
docker-compose up

# Rebuild the image before starting (e.g. after requirements.txt changes)
docker-compose up --build

# Run in detached mode
docker-compose up -d

# Stop and remove containers (data volume is on the host, not in Docker)
docker-compose down
```

The API is available at `http://localhost:8000`.

> **Note:** The compose file mounts `./dod_budget.sqlite` read-only into the container.
> Run `python build_budget_db.py` on the host whenever you need to refresh the database.

---

## 5. Data Updates

### Manual refresh on the host

```bash
# Optional: target a specific fiscal year
python refresh_data.py --years 2026 -v

# Dry run — preview what would be downloaded without writing files
python refresh_data.py --years 2026 --dry-run -v
```

`refresh_data.py` downloads new source documents and then calls `build_budget_db.py`
internally. The resulting `dod_budget.sqlite` is written to the working directory.

### Triggering the GitHub Actions workflow

The **Refresh Data** workflow runs automatically every Sunday at 06:00 UTC.
To trigger it manually:

1. Go to **Actions → Refresh Data** in the GitHub repository.
2. Click **Run workflow**.
3. Optionally set **Fiscal year** (default: `2026`) and **Dry run**.
4. After the run completes, download the `dod-budget-db-<year>-<run_id>` artifact
   which contains `dod_budget.sqlite`, `data_quality_report.json`, and
   `refresh_report.json`.
5. Replace the running database file with the artifact (see Section 7 for backup steps
   before replacing).

---

## 6. Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_DB_PATH` | `/app/dod_budget.sqlite` | Absolute path to the SQLite database file. Override when mounting the DB at a custom path. |
| `LOG_LEVEL` | `info` | Uvicorn / application log level. Accepted values: `debug`, `info`, `warning`, `error`, `critical`. |

Set these in a `.env` file for local development or pass them with `-e` flags to `docker run`.

---

## 7. Database Backup

The entire application state lives in a single SQLite file. Back it up by copying it:

```bash
# Simple timestamped backup
cp dod_budget.sqlite "dod_budget_$(date +%Y%m%d_%H%M%S).sqlite"

# Or copy to a dedicated backup directory
mkdir -p backups
cp dod_budget.sqlite backups/dod_budget_$(date +%Y%m%d).sqlite
```

SQLite files are safe to copy while the API is running in read-only mode (the compose
stack mounts it `:ro`). For a running read-write deployment, use SQLite's backup API or
stop the container first.

---

## 8. Rollback Procedure

1. **Stop the running container.**

   ```bash
   docker stop dod-budget       # standalone
   docker-compose down          # compose
   ```

2. **Restore the previous database.**

   ```bash
   cp backups/dod_budget_<previous_date>.sqlite dod_budget.sqlite
   ```

3. **Re-tag or pull the previous Docker image** (if a code change is also being rolled back).

   ```bash
   # Example: roll back to a specific image digest or tag
   docker tag dod-budget:previous dod-budget:latest
   ```

4. **Restart the service.**

   ```bash
   docker run -d --name dod-budget -p 8000:8000 \
     -v "$(pwd)/dod_budget.sqlite:/app/dod_budget.sqlite" dod-budget

   # Or with compose:
   docker-compose up -d
   ```

5. **Verify health** (see Section 9).

---

## 9. Health Check

The API exposes a `/health` endpoint. A `200 OK` response confirms the server is running
and the database is reachable. A `503` response indicates the database file is missing or
unreadable.

```bash
curl -sf http://localhost:8000/health && echo "OK" || echo "UNHEALTHY"
```

Docker monitors this automatically via the `HEALTHCHECK` instruction in the Dockerfile
(interval: 30 s, timeout: 5 s, retries: 3). Check container health status with:

```bash
docker inspect --format='{{.State.Health.Status}}' dod-budget
```

---

## 10. Secrets Management

No secrets are required to run the DoD Budget API in its current form. All source data
is downloaded from public DoD websites without authentication.

**If cloud deployment keys are added in the future**, follow these guidelines:

- Store secrets in the CI environment as **GitHub Actions encrypted secrets**
  (Settings → Secrets and variables → Actions), never in the repository.
- For server deployments, use a secrets manager (e.g. AWS Secrets Manager, HashiCorp
  Vault) and inject values as environment variables at runtime — do not bake them into
  the Docker image.
- Rotate keys immediately if they are ever committed to the repository by mistake, and
  invalidate the exposed credential before rewriting git history.
- Document any new secrets in this section, listing the variable name, purpose, and
  which team member owns rotation.
