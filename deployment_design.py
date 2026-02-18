"""
Deployment & Operations Design — Steps 4.A, 4.B, 4.C

**Status:** Phase 4 Planning (Phases 1-3 must be complete first)

Plans and TODOs for containerization, CI/CD, deployment, and monitoring.

──────────────────────────────────────────────────────────────────────────────
TODOs — Step 4.A (Containerization & Infrastructure)
──────────────────────────────────────────────────────────────────────────────

TODO 4.A1-a [Complexity: MEDIUM] [Tokens: ~2500] [User: NO]
    Write Dockerfile for the application.
    Steps:
      1. Use python:3.12-slim as base image
      2. COPY requirements.txt and pip install
      3. COPY source code (api/, templates/, static/, utils/, *.py)
      4. COPY pre-built database (dod_budget.sqlite) into image
      5. EXPOSE 8000; CMD uvicorn api.app:create_app --host 0.0.0.0
      6. Add .dockerignore for tests/, docs/, .git/, __pycache__/
    Success: `docker build -t dod-budget . && docker run -p 8000:8000 dod-budget`
    serves the app on localhost:8000.

TODO 4.A1-b [Complexity: LOW] [Tokens: ~1000] [User: NO]
    Write docker-compose.yml for local development.
    Steps:
      1. Define service: web (build: ., ports: 8000:8000, volumes for hot reload)
      2. Mount database file as volume for persistence
      3. Add healthcheck: curl localhost:8000/api/v1/reference/fiscal-years
    Success: `docker-compose up` starts the full application locally.

TODO 4.A2-a [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Create a data-build Docker stage (multi-stage build).
    Steps:
      1. Stage 1 (builder): install playwright + all deps, run download +
         build_budget_db.py to produce dod_budget.sqlite
      2. Stage 2 (runtime): copy only the sqlite file + app code
      3. This keeps the runtime image small (~100MB vs ~2GB)
    Note: Stage 1 requires network access and may take hours.
    Success: Multi-stage build produces lean runtime image with embedded data.

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

TODO 4.B1-a [Complexity: MEDIUM] [Tokens: ~2500] [User: NO]
    Create GitHub Actions CI workflow (.github/workflows/ci.yml).
    Steps:
      1. Trigger on: push to main, pull requests
      2. Matrix: Python 3.11, 3.12
      3. Steps: checkout, install deps, run pytest, run precommit checks
      4. Fail on: test failures or precommit violations
      5. Upload test results as artifact
    Success: PRs show pass/fail status; main branch always green.

TODO 4.B2-a [Complexity: MEDIUM] [Tokens: ~2000] [User: YES — needs secrets]
    Create GitHub Actions deploy workflow (.github/workflows/deploy.yml).
    Steps:
      1. Trigger on: push to main (after CI passes)
      2. Build Docker image and push to registry (GHCR or platform-native)
      3. Deploy to chosen platform (Fly.io/Railway CLI)
      4. Run smoke test against deployed URL
    Dependency: TODO 4.A3-a (platform choice) must be done first.
    Success: Merging to main auto-deploys within minutes.

TODO 4.B3-a [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Create data refresh workflow (.github/workflows/refresh-data.yml).
    Steps:
      1. Trigger: weekly schedule + manual workflow_dispatch
      2. Install playwright, run dod_budget_downloader.py, build DB
      3. Upload new database as release artifact or deploy update
      4. Notify on failure (GitHub Actions notification)
    Success: Database refreshed weekly without manual intervention.


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

TODO 4.C2-a [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Add health check endpoint and basic monitoring.
    Steps:
      1. Add GET /health endpoint returning {status: ok, db_rows: N, uptime: Ns}
      2. Configure hosting platform health check to hit /health
      3. Set up uptime monitoring (e.g., UptimeRobot free tier)
    Success: Downtime detected and alerted within 5 minutes.

TODO 4.C3-a [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Add request logging and error tracking.
    Steps:
      1. Add structured access logging (method, path, status, duration)
      2. Add Sentry free tier for error tracking (or simple error log)
      3. Log slow queries (>500ms) for performance monitoring
    Success: Errors and slow queries visible in dashboard/logs.

TODO 4.C4-a [Complexity: LOW] [Tokens: ~1000] [User: NO]
    Add rate limiting to prevent abuse.
    Steps:
      1. Add slowapi or custom middleware for rate limiting
      2. Limits: 60 req/min for search, 10 req/min for download
      3. Return 429 Too Many Requests with Retry-After header
    Success: Excessive requests get rate-limited gracefully.

TODO 4.C5-a [Complexity: LOW] [Tokens: ~2000] [User: NO]
    Write deployment runbook (docs/deployment.md).
    Steps:
      1. Document: how to deploy, how to update data, how to rollback
      2. Include: environment variables, secrets management, database backup
      3. ~100 lines of markdown
    Success: A new maintainer can deploy and manage the app.

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
