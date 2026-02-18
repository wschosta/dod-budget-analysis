"""
Deployment & Operations Design — Steps 4.A, 4.B, 4.C

**Status:** Phase 4 Planning (Phases 1-3 must be complete first)

Plans and TODOs for containerization, CI/CD, deployment, and monitoring.

──────────────────────────────────────────────────────────────────────────────
TODOs — Step 4.A (Containerization & Infrastructure)
──────────────────────────────────────────────────────────────────────────────

DONE 4.A1-a  Dockerfile: python:3.12-slim, non-root appuser, HEALTHCHECK,
    COPY requirements.txt + pip install, COPY api/ utils/ templates/ static/ *.py,
    ENV APP_DB_PATH, EXPOSE 8000, CMD uvicorn 2-worker.

DONE 4.A1-b  docker-compose.yml: web service ports 8000:8000, volume mounts for
    dod_budget.sqlite (ro) and api/ utils/ for hot-reload, healthcheck.

DONE 4.A2-a  Dockerfile.multistage: 2-stage build.
    Stage 1 (builder): python:3.12 full + Playwright Chromium + poppler-utils;
    runs build_budget_db.py to produce dod_budget.sqlite.
    Stage 2 (runtime): python:3.12-slim, copies only sqlite + app code from builder;
    runtime image ~150MB vs ~2GB for builder.

TODO 4.A3-a [Complexity: MEDIUM] [Tokens: ~2000] [User: YES — needs cloud account]
    Choose hosting platform and document decision.
    Steps:
      1. Evaluate: Railway, Fly.io, Render, AWS ECS, DigitalOcean App Platform
      2. Criteria: cost (free tier?), SQLite support (persistent disk),
         auto-deploy from GitHub, custom domain, HTTPS
      3. Recommendation: Fly.io or Railway (both support persistent volumes
         for SQLite; free tier available; auto-deploy from GitHub)
      4. Write decision record
    Success: Platform chosen; account created; test deploy done.


──────────────────────────────────────────────────────────────────────────────
TODOs — Step 4.B (CI/CD Pipeline)
──────────────────────────────────────────────────────────────────────────────

DONE 4.B1-a  .github/workflows/ci.yml: matrix Python 3.11/3.12, checkout + pip install
    + ruff lint + pytest (ignoring test_gui_tracker.py) + upload artifact.
DONE 4.B3-a  .github/workflows/refresh-data.yml: weekly cron + manual dispatch,
    playwright install, refresh_data.py, upload db artifact, step summary.

TODO 4.B2-a [Complexity: MEDIUM] [Tokens: ~2000] [User: YES — needs secrets]
    Create GitHub Actions deploy workflow (.github/workflows/deploy.yml).
    Steps:
      1. Trigger on: push to main (after CI passes)
      2. Build Docker image and push to registry (GHCR or platform-native)
      3. Deploy to chosen platform (Fly.io/Railway CLI)
      4. Run smoke test against deployed URL
    Dependency: TODO 4.A3-a (platform choice) must be done first.
    Success: Merging to main auto-deploys within minutes.


──────────────────────────────────────────────────────────────────────────────
TODOs — Step 4.C (Monitoring, Domain & Launch)
──────────────────────────────────────────────────────────────────────────────

TODO 4.C1-a [Complexity: LOW] [Tokens: ~1000] [User: YES — needs domain]
    Configure custom domain + HTTPS.
    Steps:
      1. Register domain (e.g., dodbudget.org or similar)
      2. Configure DNS to point to hosting platform
      3. Enable HTTPS (most platforms provide free TLS via Let's Encrypt)
    Success: App accessible at https://custom-domain.com.

DONE 4.C2-a  GET /health endpoint in api/app.py: returns {status, database, budget_lines}
    or 503 if DB absent/degraded.
DONE 4.C3-a  HTTP middleware in api/app.py: structured access logging (method/path/
    status/duration_ms/ip) + slow-query warnings (>500ms).
DONE 4.C4-a  Rate limiting middleware in api/app.py: fixed-window per-IP counter,
    search=60/min, download=10/min, others=120/min; returns 429 + Retry-After.

DONE 4.C5-a  docs/deployment.md (~147 lines): prerequisites, quick start,
    Docker deploy, docker-compose, data updates, env vars (APP_DB_PATH),
    database backup, rollback, health check, secrets management.

TODO 4.C6-a [Complexity: LOW] [Tokens: ~1500] [User: YES — needs community review]
    Prepare for public launch.
    Steps:
      1. Review README for public-facing accuracy
      2. Add CONTRIBUTING.md with guidelines
      3. Add LICENSE file (recommend MIT or public domain for gov data)
      4. Create GitHub release with changelog
      5. Submit to relevant data/policy communities for feedback
    Success: Repository is public, documented, and discoverable.
"""

# No implementation code — this is a planning document.
# Deployment artifacts will be created as individual files:
#   Dockerfile
#   docker-compose.yml
#   .dockerignore
#   .github/workflows/ci.yml
#   .github/workflows/deploy.yml
#   .github/workflows/refresh-data.yml
