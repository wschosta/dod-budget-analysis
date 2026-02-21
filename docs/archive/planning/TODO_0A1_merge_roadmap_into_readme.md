# Step 0.A1 — Merge ROADMAP into README

**Status:** Complete
**Type:** Documentation (AI-agent completable)
**Depends on:** None

## Task

Merge the content from `ROADMAP.md` into `README.md` so that the project's
direction is visible at the top-level file contributors see first.

## Acceptance Criteria

- `README.md` retains all existing content (data sources, usage, architecture)
- A new "Roadmap" or "Project Roadmap" section is appended after the existing
  content, containing the phase overview table and current status from `ROADMAP.md`
- Detailed per-step tables from `ROADMAP.md` are either inlined or linked
  (prefer linking to keep `README.md` scannable — e.g., "See [ROADMAP.md](ROADMAP.md)
  for the full task breakdown")
- `ROADMAP.md` remains as the canonical detailed reference; `README.md` gets a
  summary + link
- No functional code changes

## Agent Instructions

1. Read `README.md` and `ROADMAP.md`
2. Append a "## Project Roadmap" section to `README.md` containing:
   - The Phase Overview table from `ROADMAP.md`
   - The Current Project Status table from `ROADMAP.md`
   - A link to `ROADMAP.md` for the full breakdown
3. Verify no duplicate sections were created
4. Estimated tokens: ~500 output tokens
