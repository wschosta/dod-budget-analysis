# Mobile App Roadmap: DoD Budget Analysis

## Executive Summary

This document evaluates building native mobile apps (Android + iOS) from the
existing DoD Budget Analysis web platform. The web app is a FastAPI backend
with a Jinja2/HTMX frontend, Chart.js visualizations, FTS5 full-text search,
and a well-structured REST API (47 endpoints). The existing API layer is the
single biggest advantage here — a mobile client can consume it with minimal
backend changes.

---

## 1. Approach Options

### Option A: Progressive Web App (PWA)

Wrap the existing site with service workers, a manifest, and responsive
tweaks. Users install it from the browser — no app store needed.

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Reuse of existing code | ~90% (same HTML/CSS/JS) |
| App store presence | No (home-screen install only) |
| Offline support | Partial (service worker cache) |
| Push notifications | Limited on iOS |
| Native device access | Minimal |
| Maintenance burden | Very low (single codebase) |

### Option B: Cross-Platform Native (React Native or Flutter)

Build a shared codebase that compiles to both Android and iOS, consuming the
existing REST API.

| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium-High |
| Reuse of existing code | API only (~30% of total effort) |
| App store presence | Yes (Google Play + App Store) |
| Offline support | Full (local SQLite on device) |
| Push notifications | Full |
| Native device access | Full |
| Maintenance burden | Medium (second codebase + API) |

### Option C: Fully Native (Kotlin + Swift)

Two separate native apps, one per platform.

| Dimension | Assessment |
|-----------|------------|
| Complexity | High |
| Reuse of existing code | API only |
| App store presence | Yes |
| Offline support | Full |
| Push notifications | Full |
| Native device access | Full |
| Maintenance burden | High (three codebases) |

### Recommendation

**Option B (cross-platform) is the sweet spot** if app store distribution
matters. If it doesn't, **Option A (PWA) delivers 80% of the value at 20% of
the cost** and should be attempted first. The rest of this roadmap assumes
Option B with a PWA fallback, since Option C doubles the native work for
marginal benefit.

---

## 2. Feature Mapping: Web to Mobile

| Web Feature | Mobile Equivalent | Complexity | Notes |
|-------------|-------------------|------------|-------|
| Full-text search with filters | Search screen with filter drawer | Medium | Existing `/api/v1/search` powers this directly |
| Search results table | Scrollable card list | Medium | Tables don't work well on small screens; redesign as cards |
| Column visibility toggle | Not needed | — | Card layout eliminates columns |
| Row detail expansion | Detail screen (tap-to-navigate) | Low | Natural mobile pattern |
| Saved searches (localStorage) | Saved searches (device storage) | Low | AsyncStorage or equivalent |
| Charts dashboard (6 charts) | Charts screen with swipeable cards | High | Chart.js won't work natively; need a native charting lib |
| Dashboard summary stats | Summary screen with stat cards | Low | Simple API call + layout |
| Program Element detail view | PE detail screen | Medium | Nested data display, funding table |
| CSV/NDJSON export | Share sheet (export to Files/email) | Medium | Platform share APIs differ |
| Dark/light theme | System theme integration | Low | Most frameworks support this natively |
| HTMX partial updates | Not applicable | — | Native apps manage state differently |
| Pagination | Infinite scroll or load-more | Low | Standard mobile pattern |
| About/FAQ page | Static screen | Low | |

---

## 3. Phased Delivery Plan

### Phase 1: API Hardening

Prepare the backend to support mobile clients reliably.

| Task | Complexity | Description |
|------|------------|-------------|
| API versioning enforcement | Low | Lock `/api/v1/` contract; add version header |
| Authentication layer | Medium | Add API key or OAuth2 (currently unauthenticated) |
| Response envelope standardization | Low | Ensure all endpoints return consistent `{data, meta, errors}` |
| Pagination cursor support | Medium | Offset pagination is fragile on mobile; add cursor-based option |
| Push notification infrastructure | Medium | FCM (Android) + APNs (iOS) integration for data-refresh alerts |
| Rate limit adjustments for mobile | Low | Mobile clients may burst differently than browsers |
| API response compression | Low | Ensure gzip/brotli is active for all JSON responses |
| OpenAPI spec update | Low | Regenerate from FastAPI; used for client SDK generation |

**Total Phase 1 complexity: Medium**

### Phase 2: Core Mobile App (MVP)

The minimum viable mobile app.

| Task | Complexity | Description |
|------|------------|-------------|
| Project scaffolding | Low | React Native (Expo) or Flutter project init |
| Navigation structure | Low | Tab bar: Search, Dashboard, Charts, Settings |
| API client layer | Medium | Auto-generated from OpenAPI spec, with retry + offline queue |
| Search screen | Medium | Text input + filter drawer + results list |
| Search result cards | Medium | Redesign tabular data as mobile-friendly cards |
| Result detail screen | Low | Single budget line item with all fields |
| Dashboard summary screen | Low | Stat cards + service breakdown chart |
| Saved searches | Low | Persist to device storage |
| Dark mode / theming | Low | Follow system setting |
| Error handling + empty states | Low | Offline banner, no-results state, error retry |
| Loading states + skeletons | Low | Skeleton screens during API calls |

**Total Phase 2 complexity: Medium**

### Phase 3: Charts and Visualization

| Task | Complexity | Description |
|------|------------|-------------|
| Charting library integration | High | Evaluate: Victory Native, react-native-chart-kit, or fl_chart (Flutter) |
| Service comparison bar chart | Medium | Port from Chart.js to native charting lib |
| Year-over-year trend chart | Medium | Line/bar chart with FY axis |
| Top 10 budget items chart | Medium | Horizontal bar chart |
| Budget comparison chart | Medium | Side-by-side bar chart |
| Treemap visualization | High | Few native mobile treemap libs exist; may need custom view or WebView fallback |
| Appropriation doughnut chart | Medium | Standard pie/doughnut |
| Chart interaction (tap, zoom, pan) | Medium | Touch gestures for exploration |
| Chart export (share as image) | Low | Screenshot capture + share sheet |

**Total Phase 3 complexity: High**

### Phase 4: Offline Support and Data Sync

| Task | Complexity | Description |
|------|------------|-------------|
| On-device SQLite database | Medium | Store subset of budget data locally |
| Sync strategy design | High | Decide: full mirror vs. query cache vs. starred-items-only |
| Background data sync | Medium | Periodic sync when on WiFi |
| Offline search | High | Port FTS5 logic to mobile SQLite (Android has FTS5; iOS needs configuration) |
| Conflict resolution | Low | Server is source of truth; client is read-only |
| Storage management UI | Low | Show cache size, clear cache option |
| Sync status indicator | Low | Last-synced timestamp in settings |

**Total Phase 4 complexity: High**

### Phase 5: Program Element Deep Dive

| Task | Complexity | Description |
|------|------------|-------------|
| PE detail screen | Medium | Funding table, sub-elements, related PEs |
| PE search by topic/tag | Low | Existing API endpoint |
| PDF page viewer | High | Render original PDF pages for budget exhibits |
| Export: Spruill table | Medium | Formatted table export via share sheet |
| Export: PDF ZIP download | Medium | Download + save to device files |
| Bookmarked PEs | Low | Save favorite program elements |
| PE comparison view | Medium | Side-by-side funding comparison |

**Total Phase 5 complexity: Medium-High**

### Phase 6: Polish and App Store Release

| Task | Complexity | Description |
|------|------------|-------------|
| App icon and splash screen | Low | Design assets |
| Onboarding flow | Low | 3-screen walkthrough for first launch |
| Accessibility audit (a11y) | Medium | Screen reader, dynamic type, contrast |
| Performance profiling | Medium | Startup time, scroll performance, memory |
| App Store listing (iOS) | Medium | Screenshots, description, review process |
| Google Play listing (Android) | Low | Less restrictive review |
| Analytics integration | Low | Usage tracking (screen views, search terms) |
| Crash reporting | Low | Sentry or Crashlytics |
| Deep linking | Medium | URL scheme for `dod-budget://pe/0602115E` |

**Total Phase 6 complexity: Medium**

---

## 4. Complexity Summary

| Phase | Complexity | Estimated Relative Effort |
|-------|------------|--------------------------|
| Phase 1: API Hardening | Medium | 1x (baseline) |
| Phase 2: Core Mobile MVP | Medium | 2x |
| Phase 3: Charts | High | 2.5x |
| Phase 4: Offline Support | High | 2x |
| Phase 5: PE Deep Dive | Medium-High | 1.5x |
| Phase 6: Polish + Release | Medium | 1.5x |
| **Total** | | **~10.5x baseline** |

If Phase 1 (API hardening) takes N units of effort, expect the full mobile
app to take roughly 10-11x that.

---

## 5. Tests Required

### 5.1 Unit Tests (per-screen, per-component)

| Area | Tests | Count Estimate |
|------|-------|----------------|
| API client methods | Response parsing, error handling, retry logic, auth header injection | ~40 |
| Search filter logic | Filter combination, validation, default values | ~20 |
| Data formatting | Currency display, percentage formatting, date formatting, large numbers | ~15 |
| Saved searches | CRUD operations in device storage | ~10 |
| Offline cache | Read/write/eviction, storage size tracking | ~15 |
| Sync logic | Incremental update detection, conflict handling | ~15 |
| Navigation | Deep link parsing, tab state preservation | ~10 |
| Theme logic | System theme detection, manual override | ~5 |
| **Subtotal** | | **~130** |

### 5.2 Integration Tests

| Area | Tests | Count Estimate |
|------|-------|----------------|
| API contract tests | Verify mobile client against actual API responses (snapshot testing) | ~25 |
| Search end-to-end | Type query → filter → see results → tap detail | ~10 |
| Chart data pipeline | API response → chart data transformation → render | ~12 |
| Export flow | Trigger export → file created → share sheet opens | ~5 |
| Offline fallback | Disconnect network → verify cached data serves → reconnect → sync | ~8 |
| Authentication flow | Token acquisition, refresh, expiry handling | ~8 |
| **Subtotal** | | **~68** |

### 5.3 UI / Snapshot Tests

| Area | Tests | Count Estimate |
|------|-------|----------------|
| Screen snapshots (light + dark) | Each screen rendered in both themes | ~24 (12 screens x 2) |
| Empty states | No results, no network, first launch | ~6 |
| Loading states | Skeleton screens for each data-loading screen | ~6 |
| Error states | API error, timeout, malformed data | ~6 |
| Responsive layouts | Phone portrait, phone landscape, tablet | ~18 (6 key screens x 3) |
| **Subtotal** | | **~60** |

### 5.4 End-to-End Tests (Detox / Appium / Maestro)

| Area | Tests | Count Estimate |
|------|-------|----------------|
| Search and browse flow | Full user journey from launch to detail view | ~5 |
| Chart interaction | Tap chart segment, verify filter applied | ~4 |
| Export and share | Trigger CSV export, verify share sheet | ~2 |
| Offline mode | Toggle airplane mode, verify graceful degradation | ~3 |
| Deep linking | Open app via URL, verify correct screen | ~3 |
| **Subtotal** | | **~17** |

### 5.5 Non-Functional Tests

| Area | Tests | Count Estimate |
|------|-------|----------------|
| Performance: cold start time | < 2 seconds on mid-range device | 1 |
| Performance: search latency | < 500ms perceived (with skeleton) | 1 |
| Performance: scroll FPS | 60fps in results list (no jank) | 1 |
| Performance: memory ceiling | < 200MB RSS under normal use | 1 |
| Accessibility: screen reader | VoiceOver (iOS) + TalkBack (Android) pass | 2 |
| Accessibility: dynamic type | Layouts don't break at 200% font scale | 1 |
| Security: certificate pinning | Verify TLS pinning prevents MITM | 1 |
| Security: local storage encryption | Sensitive data encrypted at rest | 1 |
| Battery: background sync | < 1% drain per sync cycle | 1 |
| **Subtotal** | | **~10** |

### 5.6 Backend Tests (new, for mobile support)

| Area | Tests | Count Estimate |
|------|-------|----------------|
| Auth middleware | Token validation, expiry, revocation | ~10 |
| Cursor pagination | Forward/backward paging, edge cases | ~8 |
| Push notification dispatch | FCM/APNs payload format, delivery | ~6 |
| Rate limiting (mobile profile) | Burst patterns, throttle response | ~5 |
| **Subtotal** | | **~29** |

### Total Test Estimate: ~314 new tests

This is in addition to the existing 1,382 web/API tests.

---

## 6. Technical Considerations

### 6.1 What Works in Your Favor

- **Existing REST API is comprehensive.** 47 endpoints with consistent
  patterns, Pydantic models, and an OpenAPI spec. A mobile client SDK can be
  auto-generated.
- **Read-only data model.** No user-generated content means no sync
  conflicts, no optimistic concurrency, no merge logic. The server is always
  the source of truth.
- **Infrequent data changes.** DoD budget data updates annually (with
  amendments). Aggressive caching and offline support are straightforward
  because staleness is measured in months, not minutes.
- **Existing test infrastructure.** 1,382 tests and 80% coverage means API
  contract changes will be caught early.

### 6.2 Key Challenges

- **Chart.js doesn't work natively.** All 6 chart types must be re-implemented
  with a native charting library, or rendered in a WebView (which looks and
  feels non-native). This is the single most labor-intensive task.
- **Table-heavy data on small screens.** The web UI relies on wide tables with
  toggleable columns. Mobile needs a fundamentally different information
  architecture (cards, drill-down, progressive disclosure).
- **FTS5 on mobile.** Android's SQLite includes FTS5. iOS ships SQLite
  without FTS5 by default — you'd need to compile a custom SQLite build or
  use a wrapper like GRDB (Swift) or a server-side search fallback.
- **PDF rendering.** The PE detail view references original PDF pages. Mobile
  PDF rendering is possible but adds significant bundle size and complexity.
- **No authentication currently exists.** The API is open. Adding auth is
  necessary before exposing it to mobile clients on public networks. This is
  new infrastructure, not just a mobile concern.

### 6.3 Data and Privacy

- **No PII.** Budget data is publicly available government information. No
  GDPR/CCPA concerns for the data itself.
- **Analytics consent.** App store policies require disclosure of analytics
  collection. Plan for a consent dialog.
- **Government data disclaimer.** App store listings should note this is an
  independent analysis tool, not an official DoD product. Trademarks and
  service names need careful handling in store listings.

### 6.4 Platform-Specific Concerns

| Concern | Android | iOS |
|---------|---------|-----|
| Minimum OS version | API 26 (Android 8.0, ~95% coverage) | iOS 15+ (~95% coverage) |
| App Store review | ~1-2 days, lenient | ~1-7 days, stricter review |
| SQLite FTS5 | Built-in | Requires custom build |
| Push notifications | FCM, straightforward | APNs, requires Apple Developer account ($99/yr) |
| Background sync | WorkManager | BGTaskScheduler (limited) |
| File export | Share to any app | Share sheet, Files app |
| Deep links | App Links (verified) | Universal Links (verified) |

### 6.5 Infrastructure Additions

The backend currently runs as a single Docker container with SQLite. Mobile
clients add load and new requirements:

| Need | Current State | Required Change |
|------|---------------|-----------------|
| Authentication | None | Add OAuth2 or API key middleware |
| HTTPS enforcement | Not enforced | Mandatory for mobile (ATS on iOS) |
| Push notification service | None | Add FCM/APNs integration (or use a service like OneSignal) |
| CDN for static assets | None | Charts/images should go through a CDN for mobile perf |
| API monitoring | Basic `/health` | Add latency percentiles, error rate dashboards |
| Horizontal scaling | Single process, 2 workers | May need to move from SQLite to PostgreSQL if concurrent mobile load grows |

### 6.6 SQLite Scaling Concern

The current backend uses SQLite in WAL mode. This works well for the web app
(low concurrency, read-heavy). If mobile clients drive concurrent read load
above ~50 requests/second, SQLite's single-writer model and file-level locking
may become a bottleneck. Migration to PostgreSQL would be a significant effort
(FTS5 queries → `tsvector`, connection pooling changes, deployment changes).

**Mitigation:** Start with a read-replica or CDN-cached API responses. Monitor
before migrating databases.

---

## 7. PWA Alternative (Low-Cost Path)

Before committing to a native app, consider that a PWA could deliver most of
the value:

| PWA Task | Complexity |
|----------|------------|
| Add `manifest.json` with app name, icons, theme color | Low |
| Add service worker for offline caching of static assets | Low |
| Cache API responses for offline search (limited) | Medium |
| Improve responsive CSS for phone-sized screens | Medium |
| Add "Add to Home Screen" prompt | Low |
| Test on Safari (iOS) and Chrome (Android) | Low |

**Total PWA effort: roughly equal to Phase 1 of the native roadmap alone.**

PWA limitations: no app store presence, limited iOS push notifications,
no background sync on iOS, WebView-quality chart rendering (which is fine
since Chart.js already works).

---

## 8. Decision Criteria

Choose the **PWA path** if:
- App store distribution is not required
- Budget/staffing is limited
- The primary mobile use case is "quick lookup on the go"
- iOS push notifications are not needed

Choose the **native app path** if:
- App store presence is important (discoverability, credibility)
- Offline-first with full-text search is required
- You want push notifications for budget data updates
- You expect significant mobile-only usage (not just occasional)
- You have dedicated mobile development capacity

Choose **neither** if:
- Mobile traffic analysis shows < 10% of users on mobile devices
- The responsive web layout (which already exists) is sufficient
- The maintenance cost of a second client is not justified by the audience size

---

## 9. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Chart library doesn't support all 6 chart types (especially treemap) | Medium | High | Evaluate charting libs in a spike before committing; accept WebView fallback for treemap |
| iOS App Store rejects app (government data concerns, trademark) | Low | High | Pre-clear with Apple review guidelines; add disclaimers |
| SQLite backend can't handle mobile-driven load | Low | High | Add caching layer; monitor before migrating to PostgreSQL |
| FTS5 unavailable on iOS SQLite | Certain | Medium | Use server-side search when online; compile custom SQLite for offline |
| Scope creep into features the web app doesn't have | High | Medium | Strict feature parity goal for v1; no net-new features |
| Auth implementation introduces breaking changes for web | Medium | Medium | Add auth as an optional layer; web can remain unauthenticated initially |
| Mobile app maintenance burden exceeds team capacity | Medium | High | Start with PWA; only go native if usage justifies it |

---

## 10. Suggested First Step

Run a **2-week spike** that:

1. Scaffolds a React Native (Expo) or Flutter project
2. Auto-generates an API client from the existing OpenAPI spec
3. Builds the search screen with filter drawer and card-based results
4. Evaluates one charting library with the service comparison chart
5. Tests on one Android and one iOS device

This spike will surface the real pain points (charting, screen design, API
gaps) before committing to the full roadmap. If the spike feels painful, pivot
to the PWA approach.
