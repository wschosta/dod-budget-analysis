# Optimization Analysis: dod_budget_downloader.py - File Discovery Section

## Overview
The file discovery section (lines 1363-1392) iterates through selected years and sources, making HTTP requests to discover downloadable files. Several optimizations can improve performance.

---

## Current Implementation Issues

### 1. **Sequential Discovery Requests (Lines 1368-1392)**
**Problem**: The nested loop processes each year-source combination sequentially:
```python
for year in selected_years:
    all_files[year] = {}
    for source in selected_sources:
        # ... discovery call ...
        time.sleep(args.delay)
```

**Impact**: With 5 years × 5 sources = 25 requests, plus delays, this can take 12+ seconds just for discovery.

**Recommendation**: Parallelize using `concurrent.futures.ThreadPoolExecutor`:
- Threads are ideal here (I/O-bound work: HTTP requests)
- Keep `args.delay` between requests to avoid overwhelming servers
- Use a thread pool with max_workers=4-5

**Expected speedup**: 3-4x faster (from ~12s to ~3s for 25 requests)

---

### 2. **Redundant `discover_comptroller_files()` Lookup (Line 1374)**
**Problem**: The code duplicates logic by checking `source == "comptroller"` inline instead of adding it to `SOURCE_DISCOVERERS` dict.

```python
# Current (lines 1372-1377):
if source == "comptroller":
    url = available_years[year]
    files = discover_comptroller_files(session, year, url)
else:
    discoverer = SOURCE_DISCOVERERS[source]
    files = discoverer(session, year)
```

**Issue**:
- Two code paths for discovery logic
- `discover_comptroller_files` not in the discoverer registry
- Harder to add new sources later

**Recommendation**:
Add comptroller to `SOURCE_DISCOVERERS` dict and pass `available_years` as context:
```python
# Register comptroller with a closure
def _make_comptroller_discoverer(available_years_dict):
    def discoverer(session, year):
        url = available_years_dict[year]
        return discover_comptroller_files(session, year, url)
    return discoverer

# In main(), before discovery loop:
comptroller_discoverer = _make_comptroller_discoverer(available_years)
SOURCE_DISCOVERERS["comptroller"] = comptroller_discoverer
```

**Impact**: Cleaner code, enables parallel discovery without special cases

---

### 3. **Fixed Time Delays Don't Account for Response Times (Line 1392)**
**Problem**: `time.sleep(args.delay)` is applied after every source, regardless of how long the request took.

```python
time.sleep(args.delay)  # Always sleeps, even if request took 5 seconds
```

**Issue**:
- If a request takes 3 seconds and delay=0.5s, you only add 0.5s between requests
- If a request is instant, you lose 0.5s of parallelization opportunity
- Server-friendly: respects delay BETWEEN requests, not delay per request

**Recommendation**: Track request time and adjust sleep:
```python
start_discovery = time.time()
files = discoverer(session, year)
elapsed = time.time() - start_discovery
remaining_delay = max(0, args.delay - elapsed)
if remaining_delay > 0:
    time.sleep(remaining_delay)
```

**Impact**: More realistic request pacing, 10-20% faster discovery

---

### 4. **Browser Initialization Happens Per-Source (Lines 1376-1377)**
**Problem**: For army, navy, airforce sources, the browser is lazily initialized (first call to `_get_browser_context()`).

**Current flow**:
1. First browser-required source → browser starts (1-2 seconds)
2. Remaining sources use same browser

**Recommendation**:
Pre-check if browser is needed (line 1355 already does this!) and initialize before discovery:
```python
# Line 1355 already checks:
needs_browser = any(s in BROWSER_REQUIRED_SOURCES for s in selected_sources)

# Add before discovery loop:
if needs_browser:
    print("Pre-starting browser for WAF-protected sources...")
    _get_browser_context()  # Initialize once
```

**Impact**: Browser startup time appears in discovery phase rather than blocking first file discovery. ~1-2 seconds saved in perceived responsiveness

---

## Optimization Priority Table

| Optimization | Speedup | Difficulty | Priority |
|---|---|---|---|
| Parallelize discovery (Thread pool) | 3-4x | Medium | **HIGH** |
| Unify discovery logic (remove comptroller special case) | 5-10% | Low | **MEDIUM** |
| Smart sleep delays | 10-20% | Low | **MEDIUM** |
| Pre-start browser | ~2s savings | Very Low | **LOW** |

---

## Recommended Implementation Order

1. **Phase 1 (Highest Impact)**: Parallelize discovery with ThreadPoolExecutor
2. **Phase 2 (Code Quality)**: Unify discovery logic
3. **Phase 3 (Polish)**: Smart sleep delays + pre-start browser

---

## Code Skeleton for Parallelization

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

# In main(), replace the discovery loop (1368-1392):
all_files = {}
browser_labels = set()

# Pre-register comptroller discoverer
comptroller_discoverer = _make_comptroller_discoverer(available_years)
SOURCE_DISCOVERERS["comptroller"] = comptroller_discoverer

# Build task list
tasks = []
for year in selected_years:
    all_files[year] = {}
    for source in selected_sources:
        tasks.append((year, source))

# Execute in parallel
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {
        executor.submit(
            SOURCE_DISCOVERERS[source], session, year
        ): (year, source)
        for year, source in tasks
    }

    for future in as_completed(futures):
        year, source = futures[future]
        try:
            files = future.result()
            if type_filter:
                files = [f for f in files if f["extension"] in type_filter]
            label = SERVICE_PAGE_TEMPLATES[source]["label"] if source != "comptroller" else "Comptroller"
            all_files[year][label] = files
            if _is_browser_source(source):
                browser_labels.add(label)
        except Exception as e:
            print(f"ERROR discovering {source} for FY{year}: {e}")
            all_files[year][label] = []
```

---

## Notes

- **Thread-safe session**: The `requests.Session` object in the current code is thread-safe for read operations (getting URLs). Confirm no mutations to session state.
- **IGNORED_HOSTS & DOWNLOADABLE_EXTENSIONS**: These are duplicated between Python and JavaScript. Already noted as TODO in code (line 740).
- **Browser initialization**: Already lazy-loaded, but pre-starting when needed improves perceived speed.
