# Step 0.A2 — Create Wiki Skeleton

**Status:** Not started
**Type:** Documentation (AI-agent completable)
**Depends on:** None

## Task

Create skeleton markdown pages in `docs/wiki/` that will serve as the
project wiki. Each page should have a title, purpose description, and
placeholder sections to be filled in as subsequent phases complete.

## Pages to Create

| File | Purpose | Filled during |
|------|---------|---------------|
| `Home.md` | Wiki landing page with links to all other pages | Phase 0 |
| `Data-Sources.md` | Catalog of every URL/source/format (becomes DATA_SOURCES.md in 1.A5) | Phase 1.A |
| `Exhibit-Types.md` | Exhibit type catalog with column layouts | Phase 1.B |
| `Data-Dictionary.md` | Field definitions for the database and API | Phase 2 / 3.C2 |
| `Database-Schema.md` | Schema documentation and ER diagrams | Phase 2.A |
| `API-Reference.md` | REST endpoint docs | Phase 2.C |
| `Getting-Started.md` | End-user guide | Phase 3.C1 |
| `FAQ.md` | Common questions and answers | Phase 3.C3 |
| `Methodology.md` | Data collection methodology and limitations | Phase 3.C6 |
| `Contributing.md` | Dev setup, coding standards, PR process | Phase 4.C6 |

## Acceptance Criteria

- Each file exists in `docs/wiki/` with a `# Title`, a one-line purpose, and
  empty `## Section` headings matching the expected content
- `Home.md` links to all other pages
- No substantive content required — just structural placeholders

## Agent Instructions

1. Create each file listed above with heading structure only
2. In `Home.md`, create a table of contents linking to each page
3. Estimated tokens: ~1500 output tokens
