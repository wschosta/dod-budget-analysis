# Frontend Technology Decision — Step 3.A1-a

**Decision Date**: 2026-02-18  
**Status**: APPROVED  
**Review Date**: 2026-06-30

---

## Recommendation

**Selected Technology**: HTMX + Jinja2 (Python/Flask)

---

## Decision Summary

We evaluated three primary approaches for the DoD Budget Analysis frontend:

### Evaluated Options

| Criterion | HTMX+Jinja2 | React+Vite | Svelte | Vue 3 |
|-----------|:-----------:|:---------:|:------:|:-----:|
| **Setup Complexity** | Minimal | High | High | Medium |
| **Build/Serve Required** | None | Yes | Yes | Yes |
| **Python Integration** | Excellent | Good | Fair | Good |
| **Deployment** | Simple | Requires npm | Requires npm | Requires npm |
| **Learning Curve** | Low | Medium | Medium | Low |
| **Performance** | Good | Excellent | Excellent | Good |
| **Total Complexity** | Low | High | High | Medium |

### Final Recommendation Rationale

**HTMX + Jinja2 WINS** for this project because:

1. **Zero JavaScript Build Complexity**
   - No npm, webpack, or bundler configuration
   - Pure HTML templating with Jinja2 (already familiar to Python developers)
   - Server-side rendering avoids SPA complexity

2. **Direct Flask/Python Integration**
   - API endpoints (Flask views) directly serve HTML partials
   - Single code path: request → Flask handler → Jinja2 template → HTMX update
   - No separate build process or npm dependency management

3. **Simpler Deployment**
   - Entire app runs in Docker container with Python dependencies only
   - No separate frontend build/serve process
   - Reduces operational complexity

4. **Suitable Feature Set**
   - HTMX provides all needed interactivity for data exploration UI:
     - Live search with autocomplete (hx-trigger="keyup")
     - Dynamic filter updates (hx-get to refresh results)
     - Pagination without page reload (hx-push-url)
     - Form submissions with client-side validation
   - Not building a real-time collaborative tool, so SPA benefits don't apply

### When to Reconsider

If any of these situations arise, revisit this decision:

1. **Real-time Collaboration Features**
   - Multiple users editing the same budget simultaneously
   - WebSocket-based live updates
   - Undo/redo with conflict resolution

2. **Extreme Performance Requirements**
   - Sub-100ms interactions required
   - 10,000+ rows displayed on single page
   - Complex client-side data transformations

3. **Mobile Native App**
   - Standalone iOS/Android apps (not web)
   - React Native or Flutter more appropriate

4. **Widespread User Base**
   - Thousands of concurrent users
   - CDN caching becomes critical benefit
   - Consider decoupling frontend (React) from backend (Flask)

---

## Implementation Plan

### Phase 1: Core UI (Weeks 1-2)

1. **Create Flask app structure**
   ```
   app/
     __init__.py
     routes.py          # API endpoints + template routes
     templates/
       base.html        # Base layout
       search.html      # Search form + results
       filters.html     # Filter sidebar
       results.html     # Result table (partial)
     static/
       css/
         style.css
       js/
         htmx.min.js    # Single JS dependency
   ```

2. **Build search form** (Jinja2)
   - Input field with hx-trigger="keyup delay:500ms"
   - Organization multi-select dropdown
   - Fiscal year multi-select
   - Exhibit type checkboxes
   - Amount range slider

3. **Implement search results view**
   - Pagination with hx-push-url for bookmarkable links
   - Live result count update
   - Sortable columns (hx-get with sort param)

### Phase 2: Advanced Features (Weeks 3-4)

1. **Autocomplete suggestions** (hx-target with input)
2. **Saved searches** (localStorage + server persistence)
3. **Export to CSV/JSON** (Flask response handlers)
4. **Budget comparison view** (side-by-side tables)

### Phase 3: Deployment (Week 5)

1. **Docker containerization**
2. **Nginx reverse proxy**
3. **Production Flask server (gunicorn)**

---

## Technology Stack Details

### Backend (Python/Flask)
```python
from flask import Flask, render_template, request, jsonify
from utils import search_budget_lines, format_amount

app = Flask(__name__)

@app.route("/api/search")
def search():
    query = request.args.get("q", "")
    org = request.args.get("org", "")
    results = search_budget_lines(query, org=org, limit=25)
    return render_template("results.html", results=results)
```

### Frontend (HTML/HTMX)
```html
<input 
  type="text" 
  name="query" 
  hx-get="/api/search"
  hx-target="#results"
  hx-trigger="keyup delay:500ms"
  placeholder="Search budget items..."
/>
<div id="results"></div>
```

### Styling
- **CSS Framework**: Bootstrap 5 (optional, or custom CSS)
- **Icons**: Bootstrap Icons
- **Responsive**: Mobile-first design

---

## Development Dependencies

```
# Backend
Flask==2.3.0
Jinja2==3.1.0
SQLAlchemy==2.0.0  (optional, for ORM)

# Already in project
requests
beautifulsoup4
pdfplumber
openpyxl
sqlite3 (built-in)
```

**No npm, Node.js, or JavaScript build tools required.**

---

## Deployment Architecture

```
┌─────────────────┐
│   Client        │
│   Browser       │
│   (HTML/HTMX)   │
└────────┬────────┘
         │ HTTP
         ↓
┌─────────────────┐
│  Nginx          │
│  Reverse Proxy  │
└────────┬────────┘
         │
         ↓
┌─────────────────────────┐
│  Flask App (Gunicorn)   │
│  - Routes               │
│  - API handlers         │
│  - Jinja2 templates     │
└────────┬────────────────┘
         │
         ↓
┌─────────────────────────┐
│  SQLite Database        │
│  budget_lines           │
│  pdf_pages              │
│  ingested_files         │
└─────────────────────────┘
```

**Docker Image**: Single Python base + Flask dependencies (~300 MB)

---

## Success Criteria

- [ ] Page loads in <500ms
- [ ] Search results display in <1s
- [ ] Responsive on mobile (320px+)
- [ ] Works in all modern browsers (Chrome, Firefox, Safari, Edge)
- [ ] No console errors
- [ ] Accessibility: WCAG 2.1 AA compliant (use semantic HTML)

---

## Risks & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|:-----------:|:------:|-----------|
| HTMX limitations | Low | Medium | Fallback: Move to Vite+Vue if needed (separated later) |
| Jinja2 escaping bugs | Low | Low | Thorough HTML escaping in templates |
| Performance issues at scale | Low | Medium | Add caching, optimize SQL queries |
| Lack of HTMX ecosystem | Low | Low | Comprehensive docs available; fallback to vanilla JS |

---

## Future Extensibility

If requirements change later:

1. **Easy migration to SPA** (React/Vite)
   - Current Flask API endpoints are SPA-ready
   - Simply create separate React frontend consuming same API
   - Zero changes to backend

2. **Easy addition of real-time features**
   - Add WebSockets with Flask-SocketIO
   - Keep Jinja2 templates; add js event listeners

3. **Easy mobile app creation**
   - React Native or Flutter can consume same Flask API
   - Backend is already decoupled

---

## References

- **HTMX Documentation**: https://htmx.org
- **Jinja2 Documentation**: https://jinja.palletsprojects.com
- **Flask Documentation**: https://flask.palletsprojects.com
- **Bootstrap 5**: https://getbootstrap.com/docs/5.0/

---

**Decision Owner**: Project Lead  
**Approved By**: Architecture Review  
**Document Version**: 1.0
