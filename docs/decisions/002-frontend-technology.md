# ADR-002: HTMX + Jinja2 for Frontend

**Date:** 2026-02-18
**Status:** Accepted
**Deciders:** Project team

## Context

The DoD Budget Analysis project requires a web UI for:
- Full-text search and filtering of budget data
- Interactive results table with sorting and pagination
- Line-item detail views and data export
- Data visualization (charts, dashboards)
- Mobile-responsive design

This is a **data-heavy search/query application**, not a complex single-page application (SPA).

Four technologies were evaluated:
1. **React + Vite** — largest ecosystem
2. **Svelte/SvelteKit** — smaller bundle, simpler reactivity
3. **HTMX + Jinja2** — server-rendered, no build step
4. **Vue 3** — middle ground

## Decision

Use **HTMX + Jinja2 templates + minimal vanilla JavaScript** for the web UI.

## Evaluation

| Factor | React + Vite | Svelte | HTMX + Jinja2 | Vue 3 |
|--------|-------------|--------|---------------|-------|
| **Build Step** | Yes | Yes | None | Yes |
| **Bundle Size** | ~40 KB | ~15 KB | ~14 KB | ~30 KB |
| **Learning Curve** | Moderate | Moderate | Shallow | Moderate |
| **State Management** | Required (Redux/Zustand) | Built-in | Server state | Pinia/Vuex |
| **Deployment** | Separate build | Separate build | Single Python process | Separate build |
| **Python Integration** | Good | Fair | Excellent | Good |
| **Best For** | Complex SPAs | Rich interactive UIs | Server-centric apps | Balanced UIs |

## Rationale

1. **Single-Process Deployment** — No separate Node.js build pipeline. The entire application (API + UI) runs as one Python process. Simplifies deployment, especially for government/institutional environments.

2. **Server-Driven Interactivity** — HTMX enables dynamic UI updates without a heavy JavaScript framework. The FastAPI backend remains the source of truth, reducing client-side state management complexity.

3. **Minimal Performance Impact** — HTMX is ~14 KB gzipped. No JavaScript build step means faster development iteration. Form submissions and table updates are simple HTTP requests.

4. **HTML-First Development** — Templates use standard HTML + Jinja2 syntax, not JSX or framework-specific abstractions. Lower barrier to entry for full-stack Python developers.

5. **Rapid Prototyping** — Write Jinja2 templates directly. No hot-reload pipeline required; just refresh.

## Implementation

### File Structure

```
templates/
├── base.html                 # Base layout template
├── index.html                # Search page
├── charts.html               # Visualizations page
├── dashboard.html            # Dashboard page
├── about.html                # About page
├── programs.html             # Programs listing
├── program-detail.html       # Program detail page
├── errors/                   # Custom error pages (404, 500)
└── partials/                 # HTMX partial responses
    ├── results.html          # Search results
    ├── detail.html           # Detail view
    ├── advanced-search.html  # Advanced search form
    └── ...

static/
├── css/main.css              # Styles with CSS variables for dark mode
└── js/
    ├── app.js                # Main JS (search, HTMX integration)
    ├── charts.js             # Chart.js visualizations
    ├── dark-mode.js          # Dark mode toggle
    └── ...
```

### HTMX Interaction Pattern

1. User changes a filter → `hx-get="/partials/results"` fires with filter values
2. FastAPI renders the `partials/results.html` template with query results
3. HTMX swaps only the results section (no full page reload)
4. URL updates via `hx-push-url="true"` for shareable filtered views

### JavaScript Usage

Vanilla JavaScript only, for:
- Chart.js initialization and interactivity
- Dark mode toggle and persistence
- Keyboard shortcuts (/ or Ctrl+K for search)
- Download modal and progress
- Custom checkbox-select dropdown component

### Styling

- **Vanilla CSS** with CSS custom properties for theming
- **Dark mode** via CSS variables (no hardcoded colors)
- **Mobile-first** responsive design with breakpoints at 640px, 768px, 1024px
- **Accessibility**: skip-to-content links, ARIA live regions, focus-visible styles, print styles

## Consequences

- **Positive:** Zero JavaScript build tooling. No npm, webpack, or bundler configuration.
- **Positive:** Single Docker image serves everything. Simple CI/CD pipeline.
- **Positive:** Server-side rendering means fast initial page loads and good SEO.
- **Positive:** Chart.js provides sufficient data visualization without a heavy framework.
- **Negative:** Complex client-side interactions require more manual JavaScript than a framework would.
- **Negative:** No component reusability model (unlike React/Vue components).
- **Negative:** HTMX debugging tools are less mature than React DevTools.

### When to Reconsider

Migrate to a SPA framework if requirements expand to include:
- Real-time collaborative features
- Complex client-side state with undo/redo
- Offline-first capability
- Highly interactive data manipulation (drag-and-drop, inline editing)

## References

- [HTMX Documentation](https://htmx.org/)
- [Jinja2 Template Engine](https://jinja.palletsprojects.com/)
- [Chart.js](https://www.chartjs.org/)
- [FastAPI Templating](https://fastapi.tiangolo.com/advanced/templates/)
