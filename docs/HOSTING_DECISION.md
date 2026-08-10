# Hosting Decision (Roadmap 4.A1 / Group G1)

**Status:** Decided — Fly.io, single machine with a persistent volume.
**Date:** 2026-08-10

---

## 1. What the application actually needs

The hosting choice follows from four properties of this app. The third is the
one that rules most options out, and it is easy to miss.

**It carries its own database.** SQLite + FTS5, no external data service. There
is no Postgres to provision, no Redis, no object store, no queue. The runtime
dependency list is "a filesystem and a Python process."

**It is not read-only at runtime.** This is the constraint that shapes
everything else. The Keyword Explorer — which is the default landing page at
`/` — builds its cache by issuing `DROP TABLE` / `CREATE TABLE` / `INSERT`
against the live database (`api/routes/keyword_search.py`), driven by
`POST /api/v1/explorer/build`. `api/database.py` opens connections in WAL mode
with `synchronous=NORMAL`. So the database file must be writable in production,
and the deployment cannot be a read-only image with the DB baked in unless the
Explorer cache is pre-built and rebuilds are disabled.

**It must run as a single instance.** SQLite in WAL mode supports one writer and
does not coordinate across machines. Two app instances backed by separate
volumes would silently serve different Explorer caches; two instances sharing
one network volume would corrupt it. Horizontal scaling is therefore off the
table until the storage layer changes, and the platform must let us pin the app
to exactly one machine.

**Its data is large and refreshed rarely.** The corpus is thousands of PDFs and
spreadsheets ingested into one file, rebuilt when a new budget cycle publishes —
roughly annually, plus corrections. Reads dominate overwhelmingly. This is a
workload that wants one modest always-on machine with a disk, not elastic
compute.

There is also a smaller write path: `POST /api/v1/feedback` appends to
`feedback.json` in the working directory (`api/routes/feedback.py`). It needs
the same persistence, or feedback is lost on every redeploy.

## 2. Options considered

| Platform | Persistent disk | Single-instance pinning | Docker image deploy | Verdict |
|---|---|---|---|---|
| **Fly.io** | Volumes, per-machine | Yes — explicit machine count | Yes, `--image` from GHCR | **Chosen** |
| Render | Disks, paid instances only | Yes | Yes | Viable, costlier for the same disk |
| Railway | Volumes | Yes | Yes | Viable, usage-based billing is less predictable |
| Plain VPS | Native | Yes | Yes | Cheapest at scale, most operational burden |
| Serverless (Lambda/Cloud Run) | No durable local disk | N/A | N/A | Rejected — incompatible with a writable SQLite file |

Serverless is the notable exclusion. It is the reflexive answer for a small
read-mostly API, and it cannot work here: the Explorer's cache build needs a
durable, writable, single-writer filesystem, and function filesystems are
ephemeral and per-invocation.

## 3. Decision and rationale

**Fly.io, one machine, one volume.**

- **Volumes are first-class and cheap.** A volume attaches to a specific
  machine, which matches the single-writer model exactly rather than fighting it.
- **It deploys a prebuilt image.** `flyctl deploy --image ghcr.io/…` consumes the
  image `deploy.yml` already builds and pushes, so CI keeps one build path and
  the platform step stays a one-liner.
- **Scale-to-zero is available but optional.** For a public tool where the first
  request should not pay a cold-start plus SQLite page-cache warm-up, we keep one
  machine always running. The knob exists if cost becomes a concern.
- **TLS and custom domains are included**, with automatic certificate issuance —
  which closes roadmap task 4.A4 without extra infrastructure.

Render is the closest runner-up and would work; it costs more for an equivalent
always-on instance with a disk. A VPS is cheaper at steady state but reintroduces
OS patching, TLS renewal, and log shipping that the platform otherwise handles.

## 4. Deployment topology

```
GitHub Actions (deploy.yml)
   │  build image, push to GHCR
   ▼
ghcr.io/wschosta/dod-budget-analysis:<sha>
   │  flyctl deploy --image
   ▼
Fly machine  ×1   (min=1, max=1)
   ├── /app                 application code, from the image
   └── /data                Fly volume  ← APP_DB_PATH, feedback.json
```

The database lives on the volume, **not** in the image. That keeps image builds
fast and lets a data refresh land without rebuilding or redeploying the app,
which matters because the two change on completely different cadences: code
changes often, data changes about once a budget cycle.

## 5. Open question: how the database reaches the volume

The pipeline that produces `dod_budget.sqlite` needs network access to DoD sites
and substantial time. It should not run inside the deploy path. Two workable
patterns:

1. **Build locally or in the refresh workflow, upload once.** Run
   `python scripts/run_pipeline.py`, then `fly sftp shell` or a one-off machine
   to place the file on the volume. Simplest, manual, fine at an annual cadence.
2. **Publish the DB as a release artifact and fetch on boot.** Have
   `refresh-data.yml` attach the built `dod_budget.sqlite` to a GitHub release,
   and add a container entrypoint that downloads it to the volume when absent or
   stale. More moving parts, but makes refreshes hands-off.

Start with (1). Move to (2) only if the refresh cadence increases.

**Unmeasured:** the built database size is not known in this repository — it is
gitignored and has never been built in CI. Volume size and the viability of ever
baking the DB into the image both depend on it. Measure it on the first pipeline
run (`ls -lh dod_budget.sqlite`) and size the volume to roughly 3× that, leaving
room for the WAL file, the Explorer cache tables, and one refresh in flight.

## 6. What the operator still has to supply

These require account access and cannot be completed from the repository:

| Item | Where it goes | Needed for |
|---|---|---|
| `FLY_API_TOKEN` | GitHub repository secret | `deploy.yml` platform step |
| Fly app name | `fly.toml` (`app = …`) | Naming the deployment |
| Volume creation | `fly volumes create dod_budget_data` | Persistent storage |
| Custom domain + DNS | Fly certs + registrar | Roadmap 4.A4 |

Until `FLY_API_TOKEN` exists, `deploy.yml` builds and pushes the image and then
skips the deploy step rather than failing the run.
