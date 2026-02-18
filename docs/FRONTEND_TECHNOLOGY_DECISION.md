# Front-End Technology Decision Record — TODO 3.A1-a

**Decision:** Use **HTMX + Jinja2 templates + minimal vanilla JavaScript** for the DoD Budget Analysis UI.

**Date:** 2026-02-18
**Status:** Approved

---

## Context

The DoD Budget Analysis project requires a web UI for:
- Full-text search and filtering of budget data
- Interactive results table with sorting and pagination
- Line-item detail views
- Data export in multiple formats
- Mobile-responsive design

This is a **data-heavy CRUD/search application**, not a complex single-page application (SPA).

Four technologies were evaluated:
1. **React + Vite** — Most ecosystem support
2. **Svelte/SvelteKit** — Smaller bundle, simpler reactivity
3. **HTMX + Jinja2** — Server-rendered, no build step, simplest deployment
4. **Vue 3** — Middle ground between React and Svelte

---

## Evaluation Matrix

| Factor | React + Vite | Svelte/SvelteKit | HTMX + Jinja2 | Vue 3 |
|--------|--------------|------------------|---------------|-------|
| **Build Step** | Yes (Vite) | Yes (SvelteKit) | None | Yes |
| **Bundle Size** | ~40KB | ~15KB | ~14KB | ~30KB |
| **Learning Curve** | Moderate | Moderate | Shallow | Moderate |
| **Ecosystem** | Massive | Growing | Minimal (by design) | Good |
| **State Management** | Required (Redux, Zustand) | Built-in | Server state | Pinia/Vuex |
| **Deployment** | Separate frontend build/serve | Separate frontend build/serve | Single Python process | Separate frontend build/serve |
| **Best For** | Complex SPAs | Rich, interactive UIs | Form-heavy, server-centric apps | Balanced UIs |

---

## Recommendation: HTMX + Jinja2

### Why HTMX + Jinja2?

**1. Single-Process Deployment**
- No separate Node.js build pipeline
- No npm/yarn dependency management for frontend
- Entire application (API + UI) runs as: `python app.py` + `uvicorn api:app`
- Drastically simplifies deployment to production (one Docker image, one process)
- Perfect for government/institutional deployments where simplicity is valued

**2. Server-Driven Interactivity**
- HTMX enables dynamic UI updates **without** requiring a heavy JavaScript framework
- The server (FastAPI) remains the source of truth for data
- Reduces client-side state management complexity
- Perfect fit for a data-query application where the backend already has the logic

**3. Minimal Performance Impact**
- HTMX is ~14KB gzipped (vs React 40KB, Vue 30KB)
- No JavaScript build step means faster development iteration
- Direct browser-to-API communication, no transpilation
- Form submissions and table updates are simple HTTP requests

**4. HTML-First Development**
- Developers write HTML + Jinja2 templates (not JSX or SFC syntax)
- Lower barrier to entry for backend/full-stack developers
- Standards-based (HTML, CSS, JavaScript) rather than framework-specific abstractions
- Easier to maintain and debug for teams unfamiliar with modern SPA frameworks

**5. Rapid Prototyping**
- Wireframes ARE the implementation — write Jinja2 templates directly
- No hot-reload pipeline, but changes are instantly visible (just refresh)
- Suitable for rapid iteration on UI/UX before freezing design

---

## Architecture

### File Structure

```
frontend/
  templates/
    base.html              # Layout with nav, CSS, JS includes
    index.html             # Search/filter page
    results.html           # Results table (served by htmx)
    detail.html            # Line item detail panel
    partials/
      filters.html         # Filter sidebar (reusable partial)
      table_body.html      # Results table body (swapped by htmx on filter change)
      pagination.html      # Pagination controls
  static/
    css/
      style.css            # Main stylesheet (~500 lines)
      responsive.css       # Mobile media queries
    js/
      app.js               # Minimal JS (~100 lines)
                           # - Column visibility toggle
                           # - Form validation
                           # - Chart initialization
    images/
      logo.svg             # DoD seal or project logo
```

### Interaction Flow

1. **Page Load:**
   - Server renders `base.html` + `index.html` with initial filters
   - Displays empty results table or recent data

2. **User Changes Filter:**
   - Form input triggers `hx-get="/api/v1/results"` with current filter values
   - Server queries database and returns partial HTML (`table_body.html`)
   - HTMX swaps only the results section (no full page reload)
   - URL is updated with query parameters via `hx-push-url="true"`

3. **User Clicks Detail:**
   - Link triggers `hx-get="/detail/{id}"`
   - Server renders `detail.html` partial
   - HTMX opens modal or swaps panel below results table

4. **User Clicks Download:**
   - Form submission to `GET /api/v1/download?format=csv&filters=...`
   - Server streams CSV file directly (no need for frontend polling)

---

## Key HTMX Attributes Used

- `hx-get="/api/..."` — Fetch and insert HTML
- `hx-post="/api/..."` — POST form data
- `hx-trigger="change"` — Trigger on form input change
- `hx-target="#results"` — Swap target element
- `hx-swap="innerHTML"` — How to insert (innerHTML, outerHTML, etc.)
- `hx-push-url="true"` — Update URL without reload
- `hx-select="tbody"` — Select only the tbody from response, discard headers

---

## Styling & Responsive Design

**CSS Framework:** None (vanilla CSS)
- Clean, simple stylesheet (~500 lines)
- Mobile-first approach
- CSS Grid for layout
- Flexbox for components
- Media queries for responsive breakpoints

**Breakpoints:**
- Mobile: < 640px
- Tablet: 640px - 1024px
- Desktop: > 1024px

**Accessibility:**
- Semantic HTML (`<label>`, `<button>`, `<form>`)
- ARIA attributes where needed (`aria-label`, `aria-live` for live regions)
- Keyboard navigation support (Tab, Enter, Escape)
- Color contrast compliance (WCAG AA minimum)

---

## JavaScript Usage (Minimal)

Only vanilla JavaScript for:
1. **Column Visibility Toggle:**
   ```javascript
   // Show/hide columns based on localStorage preference
   document.querySelectorAll('[data-column]').forEach(col => {
     const visible = localStorage.getItem(`col_${col.id}`) !== 'hidden';
     col.style.display = visible ? '' : 'none';
   });
   ```

2. **Form Validation (optional, for UX polish):**
   ```javascript
   // Client-side validation before submission
   document.querySelector('form').addEventListener('submit', (e) => {
     if (!validateFilters()) e.preventDefault();
   });
   ```

3. **Chart Initialization (if visualization added):**
   ```javascript
   // Load Chart.js from CDN, initialize charts on page load
   new Chart(ctx, { type: 'bar', data: {...} });
   ```

**No frameworks, no build tools, no state management library.**

---

## Integration with FastAPI

### Template Rendering
```python
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="frontend/templates")

@app.get("/")
async def search_page(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "services": await get_services()}
    )
```

### Partial HTML Endpoints
```python
@app.get("/api/v1/results")
async def get_results(
    fiscal_year: str = None,
    service: str = None,
    limit: int = 20,
    offset: int = 0,
):
    results = await query_budget_db(fiscal_year, service, limit, offset)
    return templates.TemplateResponse(
        "partials/table_body.html",
        {"results": results}
    )
```

---

## Why NOT React/Svelte/Vue?

- **Unnecessary Complexity:** This is a data-query app, not a rich interactive UI
- **Build Pipeline Overhead:** Vite/SvelteKit/etc. add complexity to deployment
- **Larger Bundle:** 30-40KB vs 14KB, matters for slow networks (government networks often are)
- **State Management Friction:** React/Vue require Redux/Pinia; HTMX keeps state on server
- **Hiring/Maintenance:** Easier to find full-stack Python developers than React specialists

### When to Reconsider

If requirements change to include:
- Real-time collaborative features (multiple users editing simultaneously)
- Complex client-side state (e.g., advanced filtering with undo/redo)
- Offline-first capability
- Rich data visualization dashboard

Then re-evaluate and possibly migrate to React/Vue.

---

## Acceptance Criteria

- [ ] HTMX loaded from CDN (or bundled) in `base.html`
- [ ] Jinja2 template structure created (`templates/base.html`, `index.html`, `partials/`)
- [ ] `frontend/static/css/style.css` created (~500 lines)
- [ ] `frontend/static/js/app.js` created (minimal, ~100 lines)
- [ ] FastAPI endpoints return Jinja2TemplateResponse for HTML pages
- [ ] One HTMX endpoint working (e.g., `GET /api/v1/results` returns table body partial)
- [ ] URL query parameters persist via `hx-push-url="true"`
- [ ] Mobile-responsive design tested on phone/tablet/desktop

---

## References

- [HTMX Documentation](https://htmx.org/)
- [Jinja2 Template Engine](https://jinja.palletsprojects.com/)
- [FastAPI Templating](https://fastapi.tiangolo.com/advanced/templates/)
- [HTMX + FastAPI Example](https://github.com/burhanahmeed/fastapi-htmx)
- [MDN Web Docs — Responsive Design](https://developer.mozilla.org/en-US/docs/Learn/CSS/CSS_layout/Responsive_Design)
