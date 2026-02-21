# Documentation

Comprehensive documentation for the DoD Budget Analysis project. This index organizes all documentation by audience and purpose.

## User Guide

Documentation for end-users — analysts, researchers, journalists, and anyone exploring DoD budget data.

| Document | Description |
|----------|-------------|
| [Getting Started](user-guide/getting-started.md) | Setup, downloading, building, searching, and using the web UI |
| [Data Sources](user-guide/data-sources.md) | Catalog of all DoD budget data sources and coverage |
| [Exhibit Types](user-guide/exhibit-types.md) | Budget exhibit type reference (P-1, R-1, O-1, etc.) with column layouts |
| [Data Dictionary](user-guide/data-dictionary.md) | Field definitions for all database tables |
| [Methodology](user-guide/methodology.md) | How data is collected, parsed, and loaded |
| [FAQ](user-guide/faq.md) | Frequently asked questions about data, units, and limitations |

## Developer Guide

Documentation for developers contributing to or extending the project.

| Document | Description |
|----------|-------------|
| [Architecture](developer/architecture.md) | System overview, data flow, component design |
| [API Reference](developer/api-reference.md) | REST API endpoints, parameters, response schemas, examples |
| [Database Schema](developer/database-schema.md) | Table definitions, indexes, FTS5, migrations |
| [Utilities Reference](developer/utilities.md) | Shared `utils/` package — modules, functions, usage examples |
| [Testing Guide](developer/testing.md) | Test framework, fixtures, running tests, writing new tests |
| [Deployment](developer/deployment.md) | Local dev, Docker, CI/CD, backups, rollback procedures |
| [Performance](developer/performance.md) | Optimization summary for downloader and build pipeline |

## Architecture Decisions

Architecture Decision Records (ADRs) documenting key technology choices.

| ADR | Decision |
|-----|----------|
| [ADR-001](decisions/001-api-framework.md) | FastAPI as API framework |
| [ADR-002](decisions/002-frontend-technology.md) | HTMX + Jinja2 for frontend |
| [ADR-003](decisions/003-fts5-search.md) | SQLite FTS5 for full-text search |

## Project Management

| Document | Description |
|----------|-------------|
| [Roadmap](ROADMAP.md) | Project phases, task breakdown, and current status |

## Root-Level Files

| File | Description |
|------|-------------|
| [README.md](../README.md) | Project overview, features, installation, and quick start |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Development setup, code standards, PR process |
| [CLAUDE.md](../CLAUDE.md) | Guide for AI assistants working on this codebase |

## Archived Documentation

Historical development documents preserved for reference in [archive/](archive/):
- Agent instruction files (LION, TIGER, BEAR, OH MY)
- Implementation logs and fix documentation
- TODO breakdowns and planning documents
- Detailed optimization analysis (27 files)
