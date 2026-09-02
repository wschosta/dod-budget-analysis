# GitHub Pages Assessment (companion to HOSTING_DECISION.md)

**Status:** Assessment only — no decision taken, no code written.
**Date:** 2026-09-02
**Question:** what would it take to publish this application on GitHub Pages?

[`HOSTING_DECISION.md`](HOSTING_DECISION.md) evaluated *servers* and chose Fly.io.
It did not evaluate *static hosting*, because static hosting was implicitly
excluded by the same constraint that eliminated serverless. This document makes
that exclusion explicit, then asks whether the constraint can be engineered away
— and at what cost.

Every number below is tagged **[measured]** (observed in this repository),
**[documented]** (taken from `HOSTING_DECISION.md` or `PRD.md`, measured
previously), **[external]** (vendor documentation, linked), or **[estimate]**
(reasoned, not verified — treat with suspicion). §7 lists what could not be
measured and why.

---

## 1. What GitHub Pages is, precisely

Pages is a static file server. It executes nothing. The relevant limits:

| Constraint | Value | Source |
|---|---|---|
| Server-side code | **None.** No PHP, Ruby, or Python executes | [external](https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site) |
| Published site size | **1 GB** | [external](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) |
| Bandwidth | **100 GB/month**, soft | [external](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) |
| Builds | 10/hour, soft — **does not apply** to a custom Actions workflow | [external](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) |
| Single file in git | **100 MB hard block** (50 MiB warning) | [external](https://docs.github.com/en/enterprise-server@3.14/repositories/working-with-files/managing-large-files/about-large-files-on-github) |
| Repository size | under 1 GB recommended | [external](https://docs.github.com/en/enterprise-server@3.14/repositories/working-with-files/managing-large-files/about-large-files-on-github) |

Two properties are more useful than they first appear, and both are load-bearing
for §4's option C:

- **Pages honours HTTP Range requests.** A browser can read arbitrary byte
  ranges of a hosted file without downloading it. This is what makes
  querying a large SQLite file from a static host possible at all.
- **Deploying via an Actions artifact bypasses git.** `actions/deploy-pages`
  publishes a build artifact directly. Large generated assets never enter the
  repository's history, so the 100 MB file limit and the repo-size
  recommendation apply to *sources*, not to build output. The 1 GB published
  site limit still binds.

One property is a genuine trap: **there are no server-side rewrites.** A URL
like `/programs/0604030N` must correspond to a real file, or be recovered
client-side through the `404.html` fallback convention. This matters because 8
of this application's 22 page routes are parameterised (§2.2).

---

## 2. What survives the trip

The application is 62 routes: **40 JSON API endpoints** across 13 routers, plus
**22 HTML page and partial routes** in `api/routes/frontend.py` **[measured]**,
enumerated by AST walk over `api/routes/*.py`.

Classification below assumes the most capable static option — a read-only
SQLite file queried in the browser over Range requests (§4, option C). Under any
weaker option, more moves to *Impossible*.

- **Feasible** — a pure read query; port the SQL to the client, behaviour
  preserved.
- **Degraded** — achievable, but loses a property (freshness, precision,
  arbitrary input, or file output) or needs a substitute library.
- **Impossible** — depends on writing to the database, on a filesystem the site
  cannot carry, or on work that must happen server-side per request.

### 2.1 API endpoints (40)

| Router | Endpoints | Verdict | Note |
|---|---|---|---|
| `reference.py` | 5 | **Feasible** | Small lookup tables; ship as flat JSON, no SQLite needed |
| `metadata.py` | 2 | **Feasible** | Static once the DB build is frozen |
| `aggregations.py` | 2 | **Feasible** | `GROUP BY` over `budget_lines`; also precomputable |
| `budget_lines.py` | 2 | **Feasible** | Filtered `SELECT` + row lookup |
| `facets.py` | 1 | **Feasible** | Cross-filtered counts; `GROUP BY` |
| `search.py` | 2 | **Feasible\*** | FTS5 — see the caveat in §5 |
| `pe.py` | 12 of 14 | **Feasible** | Reads over `pe_index`, `pe_descriptions`, `pe_tags`, `pe_lineage` |
| `bli.py` | 1 | **Feasible** | Read over `bli_index` |
| `dashboard.py` `/summary` | 1 | **Feasible** | Precompute to JSON; it is one payload |
| `download.py` | 1 | **Degraded** | CSV/NDJSON regenerate client-side as a Blob; the `xlsx` branch needs a JS writer to replace `openpyxl` |
| `pe.py` `/export/table` | 1 | **Degraded** | CSV, trivially client-side |
| `pe.py` `/export/pages` | 1 | **Impossible** | Streams a ZIP of extracted PDF page text; needs the full `pdf_pages` corpus resident |
| `explorer.py` `GET` ×3 | 3 | **Degraded** | Reads work — but only against a cache that must now be built ahead of time |
| `explorer.py` `/download/xlsx` | 1 | **Degraded** | Server-side `xlsxwriter` → JS writer |
| `explorer.py` `POST /build`, `GET /status` | 2 | **Impossible** | The core blocker — see §3 |
| `dashboard.py` `/cache-clear` | 1 | **Impossible** | No server cache exists to clear; the endpoint becomes meaningless |
| `feedback.py` | 1 | **Impossible** | Appends to `feedback.json`; needs a writable store or a third-party form endpoint |
| `files.py` | 1 | **Impossible** | Serves from a 3.4 GB document corpus **[documented]**; cannot be hosted. Substitute: link to the originating DoD URL |

**28 feasible, 6 degraded, 6 impossible** — but the six impossible ones are not
evenly weighted. `POST /explorer/build` is the product.

### 2.2 Page routes (22)

All 22 are Jinja2 server-rendered. Every one becomes an HTML shell plus a
client-side query. The split that matters is parameterised versus not:

| Kind | Routes | Static shape |
|---|---|---|
| Fixed path | `/`, `/home`, `/about`, `/dashboard`, `/charts`, `/programs`, `/compare`, `/consolidated`, `/explorer` (9) | One HTML file each. Straightforward |
| Parameterised | `/programs/{pe}`, `/bli/{bli_key:path}`, `/consolidated/{pe}`, `/partials/detail/{item_id}`, and 5 `/partials/program-*/{pe}` (8) | Either pre-generate one file per entity, or client-route through the `404.html` fallback |
| Query-driven partial | `/partials/results`, `/partials/spruill-table`, `/partials/program-list`, `/partials/top-changes` (4), plus `/partials/detail` above | HTMX swaps become client-side renders; the partial templates stop existing as routes |

The parameterised set is where the effort concentrates. Pre-generating one file
per PE is the robust answer and keeps deep links working without a fallback
hack — but its cost scales with the number of PEs and BLIs, which is the single
number I could not measure (§7).

`/consolidated` and `/consolidated/{pe}` carry a separate problem regardless of
hosting: they read `dod_budget_work.sqlite`, a **second database that
`run_pipeline.py` does not produce** and which returns 503 until built by hand
**[documented, PRD §4.1]**. Under static hosting it would have to be built,
slimmed, and shipped as a second payload. Recommend dropping these two routes
from any static build.

---

## 3. The blocker, stated precisely

The default landing page writes to the database at request time.

`POST /api/v1/explorer/build` runs `DROP TABLE` / `CREATE TABLE` / `INSERT`
against the live SQLite file (`api/routes/explorer.py:235`,
`api/routes/keyword_search.py:517,579,602`) **[measured]**, dispatched to a
background thread via FastAPI `BackgroundTasks`, with `GET /status` polled by the
browser for progress. `HOSTING_DECISION.md` §1 identifies this as the constraint
that "rules most options out," and §2 rejected serverless on exactly these
grounds. Pages is strictly more restrictive than serverless: it has no compute
at all.

**This is not, however, unfixable — and `HOSTING_DECISION.md` §5 already
contains the fix.** Profiling on 2026-08-13 found a single-term search costs
3.77 s to return one row, of which ~95% is `mine_pdf_subelements` parsing every
R-2/R-2A page in the corpus — 6,630 pages — through `parse_r2_cost_table`
**[documented]**. The doc's own conclusion:

> the expensive half is **keyword-independent**: the parse is identical for
> every search and only `find_matched_keywords` varies. Materialising the parsed
> R-2 rows once during enrichment would make each search proportional to its
> matches rather than to the corpus.

Materialising that parse is the prerequisite for static hosting *and* an
independently worthwhile performance fix for the Fly deployment. It is the
highest-leverage item in this document.

What it does **not** solve: arbitrary keyword entry. The Explorer accepts up to
20 free-text keywords with fuzzy matching **[documented, PRD §4.1]**. Even with
the R-2 parse materialised, the remaining match step must run somewhere. On a
static host that means running it in the browser over the shipped tables —
plausible once the expensive parse is precomputed, but unverified.

`HOSTING_DECISION.md` §5 also warns against the obvious shortcut here (scoping
the page scan by `pdf_pe_numbers`), because the loop's `else` branch is how the
Explorer discovers programs *not* in the requested set. Any static
reimplementation must preserve that discovery path or silently lose the feature.

---

## 4. Options

### A. Documentation site only

Publish `docs/` — PRD, ROADMAP, data-sources guide — via MkDocs or Jekyll.
Does not publish the tool.

**Effort: ~half a day.** Note this partly duplicates the existing
[GitHub Wiki](https://github.com/wschosta/dod-budget-analysis/wiki), which
`CLAUDE.md` already designates for the user and developer guides. Worth doing
only if the intent is a versioned, PR-reviewable docs site that the wiki cannot
provide.

### B. Static shell on Pages + API on Fly

Pages serves HTML/CSS/JS; all data comes cross-origin from the Fly API.
Requires porting 22 SSR routes to client rendering and locking down
`APP_CORS_ORIGINS` (currently `*` **[measured]**).

**Effort: ~1 week. [estimate]** **Recommend against.** It is the full frontend
rewrite of option C with none of the benefit — the Fly machine still runs, still
costs, and is now a hard dependency of a site that appears to be static. The
only case for it is CDN offload of static assets, which is not a problem this
application has.

### C. Fully static — SQLite in the browser

The real answer to the question as asked. A read-only database is published as a
Pages asset and queried in-browser over HTTP Range requests, so users download
only the pages their queries touch, not the whole file. The technique is
established — [`sql.js-httpvfs`](https://github.com/phiresky/sql.js-httpvfs) was
built specifically for hosting SQLite on GitHub Pages, and supports splitting a
database into chunks to stay under per-file limits.

Required work:

1. **Materialise the R-2 parse** (§3). Prerequisite for everything else.
2. **Build a slimmed read-only DB.** Drop the raw `pdf_pages` text and
   `pdf_pages_fts` once the parse is materialised; drop `data_changelog`,
   `explorer_cache_meta`, the `kw_cache_*` tables. Whether this gets under the
   1 GB site cap is **unverified** — see §7.
3. **Rewrite the frontend** — 22 routes, ~140 KB of existing JS **[measured]**
   that currently talks to the API.
4. **Substitute the impossible six** (§2.1): drop file serving in favour of
   links to DoD source URLs; move feedback to a third-party form or GitHub
   Issues; replace server XLSX with a JS writer.
5. **Deploy via Actions artifact**, not a committed branch, so annual data
   refreshes do not accumulate ~700 MB per revision in git history.

**Effort: several weeks. [estimate]** Risks in §5.

### D. Derived-data snapshot

Precompute JSON for the bounded, aggregate views — charts, dashboard, programs
list, per-PE funding — and ship a few MB. No WASM, no Range requests, no
chunking, no FTS5 build. Deep links work by pre-generating one JSON + one HTML
per PE.

What you lose: arbitrary full-text search and the Explorer's free-keyword
mining. What you keep: most of `/charts`, `/dashboard`, `/programs`,
`/programs/{pe}`, `/compare`.

**Effort: 2-3 days. [estimate]** The best value-per-day on this list, and it is
a strict subset of option C's work — nothing done for D is wasted if C follows.

---

## 5. Risks specific to option C

**FTS5 is not in the stock browser build.** This application's search is
entirely FTS5 — `budget_lines_fts`, `pdf_pages_fts`, `pe_descriptions_fts`,
`bli_descriptions_fts`, and `sanitize_fts5_query()` **[measured]**. Stock
`sql.js` ships FTS3, not FTS5; FTS5 requires a custom build with
`-DSQLITE_ENABLE_FTS5` or the
[`sql.js-fts5`](https://www.npmjs.com/package/sql.js-fts5) package
**[external]**. Since `sql.js-httpvfs` is a fork of `sql.js`, it needs the same
treatment — a custom build of a fork. **Verify this before committing to C.**

**`sql.js-httpvfs` appears unmaintained** — reported as roughly two years
without a commit **[external]**. Actively-maintained alternatives exist
([`sqlite-wasm-http`](https://github.com/mmomtchev/sqlite-wasm-http), built on
the official SQLite WASM distribution; `wa-sqlite`), but the FTS5 and chunking
story would need re-verifying on whichever is chosen.

**Bandwidth is a real cost, not a formality.** Range requests mean each query
pulls only the SQLite pages it needs — but a poorly-indexed query pulls many.
Against a 100 GB/month soft cap, a table scan served to a few hundred users is
enough to matter. Index coverage becomes a hosting concern, not just a latency
one.

**No cache eviction.** Pages fetched during a session are cached in worker
memory and that cache never shrinks **[external]** — a user running many
queries sees memory grow monotonically.

**The 1 GB cap does not grow with the corpus.** `HOSTING_DECISION.md` §5 is
emphatic that 730 MB is "a floor, not a ceiling" — Army and Air Force are not
yet ingested, and the database grew 6× in one night from a downloader fix. A
static build that fits today may not fit after the next refresh.

---

## 6. Recommendation

**Do not pursue option C as a replacement for Fly.** The application's defining
feature writes to its database, its corpus is already 730 MB against a 1 GB cap
with known growth ahead, and its search depends on an extension absent from the
stock browser build. Each is solvable; together, on a moving corpus, they are a
second application to maintain.

**Do the §3 work regardless.** Materialising the R-2 parse is recommended by the
existing hosting doc on performance grounds alone, fixes a 3.77 s query path on
the live Fly deployment, and is the prerequisite for every static option. It is
worth doing whether or not Pages ever happens.

**Then reconsider D.** With the parse materialised and a measured table-size
breakdown in hand, a derived-data snapshot on Pages becomes a cheap public
front door — charts, dashboards, program pages — sitting alongside the full
tool on Fly rather than replacing it.

**Separately: the Fly deployment is one secret away.** `deploy.yml` builds and
pushes to GHCR today and skips the deploy step because `FLY_API_TOKEN` is unset
**[measured]**; `HOSTING_DECISION.md` §6 lists it as the only blocking item. If
the underlying goal is "get this in front of people," that is a shorter path
than anything in this document.

---

## 7. What could not be measured

`dod_budget.sqlite` is gitignored and absent from this checkout **[measured]**,
so the following are unknown, and the effort estimates in §4 inherit that
uncertainty. Deliberately not guessed:

| Unknown | Why it decides things |
|---|---|
| Per-table byte breakdown | Whether dropping `pdf_pages` + `pdf_pages_fts` gets a static build under 1 GB — the hypothesis behind option C, currently unverified |
| Distinct PE count in `pe_index` | Number of files to pre-generate for `/programs/{pe}`; the dominant cost in §2.2 |
| Distinct BLI count in `bli_index` | Same, for `/bli/{bli_key}` |
| Row count in `budget_lines` | Whether client-side filtering is viable at all under option D |

Answerable from a built database with:

```sql
-- per-table size, largest first (SQLite compiled with SQLITE_ENABLE_DBSTAT_VTAB)
SELECT name, SUM(pgsize) AS bytes FROM dbstat GROUP BY name ORDER BY bytes DESC;

SELECT COUNT(DISTINCT pe_number) FROM pe_index;
SELECT COUNT(*) FROM bli_index;
SELECT COUNT(*) FROM budget_lines;
```
