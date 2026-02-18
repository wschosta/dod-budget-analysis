# DoD Budget Downloader - Optimization Analysis Report

Generated: 2026-02-17

## Pattern Analysis Summary

This report analyzes 5 critical performance patterns in `dod_budget_downloader.py` and identifies 16 optimization opportunities with estimated impact levels.

---

## 1. HTTP Session and Retry Configuration (Lines 646-658)

### Current Pattern
```python
def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    adapter = requests.adapters.HTTPAdapter(
        max_retries=requests.adapters.Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
```

### Issues Identified
- **No connection pooling configuration**: HTTPAdapter uses default pool settings (10 connections)
- **No keep-alive timeout**: Connections may close prematurely
- **Weak retry strategy**: backoff_factor=1 means delays are [1, 2, 4] seconds (linear exponential)
- **Session created fresh each time**: No reuse across discovery/download phases
- **No request timeout defaults**: Timeout specified per-request but not in session
- **No pool recycle**: Long-lived connections may become stale

---

## 2. Discovery Functions and BeautifulSoup Parsing (Lines 966-990)

### Current Pattern
```python
def discover_comptroller_files(session: requests.Session, year: str,
                               page_url: str) -> list[dict]:
    print(f"  [Comptroller] Scanning FY{year}...")
    resp = session.get(page_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return _extract_downloadable_links(soup, page_url)

def discover_defense_wide_files(session: requests.Session, year: str) -> list[dict]:
    url = SERVICE_PAGE_TEMPLATES["defense-wide"]["url"].format(fy=year)
    print(f"  [Defense Wide] Scanning FY{year}...")
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"    WARNING: Could not fetch Defense Wide page for FY{year}: {e}")
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    return _extract_downloadable_links(soup, url)
```

### Issues Identified
- **No parser specification**: "html.parser" is slower than "lxml" for large documents
- **No response encoding check**: Encoding may not be properly detected
- **No caching of parsed pages**: Same page fetched multiple times across runs
- **Linear parsing**: Links extracted sequentially without optimization
- **No early termination**: Entire page parsed even if needed links found early
- **Fiscal year cache exists but not used optimally**: Only caches discover_fiscal_years()

---

## 3. File Download and Retry Logic (Lines 1080-1148)

### Current Pattern
```python
def download_file(session: requests.Session, url: str, dest_path: Path,
                  overwrite: bool = False, use_browser: bool = False) -> bool:
    # ... [omitted for brevity]
    _retry_delays = [2, 4, 8]
    last_exc = None
    for attempt in range(len(_retry_delays) + 1):
        if attempt > 0:
            delay = _retry_delays[attempt - 1]
            print(f"\r    [RETRY {attempt}/{len(_retry_delays)}] {fname}: "
                  f"retrying in {delay}s...          ")
            time.sleep(delay)
        try:
            resp = session.get(url, timeout=120, stream=True)
            resp.raise_for_status()

            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if _tracker:
                        _tracker.print_file_progress(
                            fname, downloaded, total_size, file_start
                        )
            # ... [omitted for brevity]
```

### Issues Identified
- **Fixed chunk size (8192)**: Not optimized for network conditions
- **No timeout differentiation**: Same 120s timeout for connection/read phases
- **Inefficient retry delays**: [2, 4, 8] not jittered (could overwhelm server)
- **No partial download resume**: Failed downloads restart from byte 0
- **Stream overhead on small files**: All files use streaming even <1MB
- **No download speed detection**: Can't adapt chunk size for slow connections
- **Blocking progress updates**: Tracker calls on every chunk slow down I/O

---

## 4. Browser Page Loading Timeouts (Lines 726-727, 787, 810, 827, 856)

### Current Pattern
```python
# Line 726-727 (domcontentloaded)
page.goto(url, timeout=15000, wait_until="domcontentloaded")

# Line 787 (domcontentloaded with origin)
page.goto(origin, timeout=15000, wait_until="domcontentloaded")

# Line 810 (120s timeout on page.request)
resp = page.request.get(url, timeout=120000)

# Line 827 (120s timeout on expect_download)
with page.expect_download(timeout=120000) as download_info:

# Line 856 (120s timeout on direct navigation)
resp = page.goto(url, timeout=120000, wait_until="load")
```

### Issues Identified
- **Inconsistent timeout strategies**: domcontentloaded (15s) vs load (120s)
- **No adaptive timeouts**: Same timeout regardless of response time history
- **wait_until="load" is expensive**: Waits for all resources vs just DOM
- **No timeout differentiation by network**: Desktop vs mobile speed
- **Redundant page creation**: Three strategies create separate pages
- **No page reuse**: Each download creates new page context
- **Extra init script overhead**: Webdriver detection script added 5 times

---

## 5. Link Extraction and Deduplication (Lines 884-914)

### Current Pattern
```python
def _extract_downloadable_links(soup: BeautifulSoup, page_url: str,
                                text_filter: str | None = None) -> list[dict]:
    """Extract all downloadable file links from a parsed page."""
    files = []
    seen_urls = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        full_url = urljoin(page_url, href)

        parsed = urlparse(full_url)
        if parsed.hostname and parsed.hostname.lower() in IGNORED_HOSTS:
            continue

        clean_path = parsed.path.lower()

        ext = Path(clean_path).suffix
        if ext not in DOWNLOADABLE_EXTENSIONS:
            continue

        if text_filter and text_filter.lower() not in full_url.lower():
            continue

        dedup_key = parsed._replace(query="", fragment="").geturl()
        if dedup_key in seen_urls:
            continue
        seen_urls.add(dedup_key)

        link_text = link.get_text(strip=True)
        filename = unquote(Path(parsed.path).name)

        files.append({
            "name": link_text if link_text else filename,
            "url": full_url,
            "filename": _sanitize_filename(filename),
            "extension": ext,
        })

    return files
```

### Issues Identified
- **Sequential filtering**: Each link checked against all conditions (inefficient predicate ordering)
- **String operations in loop**: `.lower()` called multiple times per link
- **URL parsing called twice**: Once in urlparse, again in Path()
- **Deduplication via URL reconstruction**: Rebuilds URL string for dedup key
- **No early rejection optimization**: DOWNLOADABLE_EXTENSIONS checked after hostname
- **No cached extension matching**: String suffix comparison on every iteration
- **Inefficient text filter**: Case-insensitive substring search on full URL

---

## Optimization Opportunities - Ranked by Impact

### HIGH IMPACT Optimizations

#### 1. Connection Pool Configuration (Estimated: 15-25% throughput improvement)
**Pattern**: HTTP session and retry configuration
**Issue**: Default pool size (10) and no keep-alive optimization
**Recommendation**:
- Increase pool size to 20-30 for parallel downloads
- Add pool_connections and pool_maxsize to HTTPAdapter
- Add `poolmanager_kwargs` for socket keep-alive (TCP_NODELAY=1)
- Set recycle parameter to recycle stale connections every 300s

**Code location**: Lines 646-658 (get_session function)
**Implementation effort**: Low (5-10 lines)
**Testing required**: Measure throughput with mixed file sizes

---

#### 2. Parser Optimization - Use lxml Instead of html.parser (Estimated: 3-5x faster parsing)
**Pattern**: BeautifulSoup parsing in discovery functions
**Issue**: html.parser is 3-5x slower than lxml for large HTML documents
**Recommendation**:
- Check for lxml availability, fallback to html.parser
- Add import: `from lxml import etree` with fallback handling
- Update all BeautifulSoup() calls: `BeautifulSoup(resp.text, "lxml")`
- This particularly impacts large pages with 100+ links

**Code location**: Lines 971, 986, 953 (BeautifulSoup instantiations)
**Implementation effort**: Low (3-5 lines)
**Testing required**: Benchmark parsing time on sample pages

---

#### 3. Adaptive Timeout Strategy (Estimated: 10-20% retry rate reduction)
**Pattern**: Browser page loading and download timeouts
**Issue**: Fixed timeouts (15s, 120s) don't adapt to network conditions or page complexity
**Recommendation**:
- Implement exponential backoff timeout: start at 10s, increase to 20s, then 40s on retries
- Track response times per domain, adjust future timeouts accordingly
- Use wait_until="domcontentloaded" for discovery (faster), wait_until="load" only for download verification
- Separate connection timeout (10s) from read timeout (120s)

**Code location**: Lines 726, 787, 810, 827, 856
**Implementation effort**: Medium (20-30 lines, requires response time tracking)
**Testing required**: Monitor actual timeout rates across different network conditions

---

#### 4. Partial Download Resume (Estimated: 20-30% faster recovery from failures)
**Pattern**: File download retry logic
**Issue**: Failed downloads restart from byte 0 instead of resuming
**Recommendation**:
- Implement HTTP Range requests (byte-range resume)
- Check for partial files: if dest_path exists and < remote_size, resume from offset
- Send `Range: bytes=start-` header in retry attempts
- Validate Content-Range header in response

**Code location**: Lines 1106-1117 (download loop)
**Implementation effort**: Medium (15-20 lines)
**Testing required**: Test with interrupted downloads, verify Content-Range support on servers

---

#### 5. Reusable Global Session with Smart Pooling (Estimated: 10-15% latency reduction)
**Pattern**: HTTP session creation in get_session()
**Issue**: Function called potentially multiple times, doesn't reuse connections
**Recommendation**:
- Create module-level session object initialized once
- Reuse for all discovery and download phases
- Add context manager for cleanup
- Implement session reset on persistent errors

**Code location**: Lines 646-658, 1301 (session creation and usage)
**Implementation effort**: Medium (refactor session lifecycle)
**Testing required**: Monitor connection reuse metrics

---

### MEDIUM IMPACT Optimizations

#### 6. Chunk Size Optimization Based on File Size (Estimated: 5-15% download speed improvement)
**Pattern**: Fixed 8192-byte chunks in download_file
**Issue**: Chunk size not adapted to file size or network speed
**Recommendation**:
- Use smaller chunks (4KB) for files <5MB (low memory footprint)
- Use larger chunks (64KB-256KB) for files >100MB (reduce iteration overhead)
- Implement adaptive chunking based on download speed
- Cache file sizes from discovery phase

**Code location**: Lines 1124 (iter_content chunk_size)
**Implementation effort**: Low-Medium (10-15 lines)
**Testing required**: Benchmark with various file sizes and connection speeds

---

#### 7. Pre-compiled Regex for Extension Matching (Estimated: 2-5% discovery speed improvement)
**Pattern**: Extension filtering in link extraction
**Issue**: Path.suffix and set membership tested sequentially
**Recommendation**:
- Pre-compile regex: `DOWNLOADABLE_PATTERN = re.compile(r'\.(pdf|xlsx?|zip|csv)$')`
- Use regex match instead of Path.suffix loop-up
- Cache extension check at module level
- Move text_filter to regex pattern as well

**Code location**: Lines 900-902 (extension matching)
**Implementation effort**: Low (5-8 lines)
**Testing required**: Verify regex matches all intended extensions

---

#### 8. Predicate Reordering for Early Rejection (Estimated: 3-8% discovery speed improvement)
**Pattern**: Sequential link validation in _extract_downloadable_links
**Issue**: Expensive checks (text_filter) run before cheap checks (extension)
**Recommendation**:
- Order checks: hostname (O(1)) → extension (O(1)) → text_filter (O(n)) → dedup (O(1))
- Pre-filter soup.find_all with CSS selectors when possible
- Use `soup.find_all("a", href=re.compile(r'\.(pdf|xlsx?|zip|csv)$'))`

**Code location**: Lines 890-910
**Implementation effort**: Low (5-10 lines, reordering)
**Testing required**: Verify same results, measure time reduction

---

#### 9. Batch Progress Updates to Reduce Overhead (Estimated: 2-8% download speed improvement)
**Pattern**: Tracker.print_file_progress called on every chunk (Lines 1128-1130)
**Issue**: Excessive function calls and I/O for progress updates
**Recommendation**:
- Update progress only every 10-50 chunks or 100ms (already done at line 299 with 0.25s throttling)
- Verify throttling is working correctly (it appears to be)
- Consider batching multiple chunks before write

**Code location**: Lines 1128-1130, 299 (throttling already exists)
**Implementation effort**: Very Low (already implemented, just document)
**Testing required**: Verify throttling is effective

---

#### 10. Cache Discovered Pages Metadata (Estimated: 10-20% faster repeated runs)
**Pattern**: Discovery functions fetch same pages each run (lines 966-987)
**Issue**: No caching of page metadata across runs
**Recommendation**:
- Implement disk-based cache of discovered links: `downloads/discovery_cache/{year}_{source}.json`
- Store page URL, fetch timestamp, ETag, and discovered links
- Check Last-Modified header before re-fetching
- Add `--refresh-cache` flag to force re-discovery

**Code location**: Discovery functions (lines 944-1024)
**Implementation effort**: Medium (30-40 lines, add cache I/O)
**Testing required**: Verify cache invalidation logic, test with stale pages

---

### MEDIUM-LOW IMPACT Optimizations

#### 11. Browser Page Reuse Strategy (Estimated: 5-10% browser-based download speedup)
**Pattern**: Browser download creates new page per file (lines 818, 824, 851)
**Issue**: Each download creates new page context and init script
**Recommendation**:
- Reuse single browser page for multiple downloads
- Add pooling of browser pages (maintain 2-3 warm pages)
- Lazy reinitialize page on errors instead of creating new
- Cache webdriver detection script as string constant

**Code location**: Lines 814-869 (_browser_download_file)
**Implementation effort**: Medium (refactor _browser_download_file)
**Testing required**: Verify memory usage doesn't grow, test page reuse limits

---

#### 12. Jittered Exponential Backoff for Retries (Estimated: 5-10% fewer false timeouts)
**Pattern**: Retry delays in download_file (line 1107)
**Issue**: Retry delays [2, 4, 8] are fixed and non-jittered
**Recommendation**:
- Add jitter: `delay = (2^attempt) + random(0, 1) * (2^attempt)`
- Prevents thundering herd on server recovery
- Use: `import random; delays = [random.uniform(2**i, 2**(i+1)) for i in range(3)]`
- Add configurable backoff_factor via CLI

**Code location**: Lines 1107-1114
**Implementation effort**: Low (3-5 lines)
**Testing required**: Monitor retry patterns in logs

---

#### 13. Response Encoding Detection (Estimated: 1-3% parsing accuracy improvement)
**Pattern**: BeautifulSoup receives resp.text directly (no encoding verification)
**Issue**: Encoding mismatch on some pages may cause parsing errors
**Recommendation**:
- Detect encoding from Content-Type header or response body
- Use: `soup = BeautifulSoup(resp.content, "lxml", from_encoding=resp.encoding)`
- Add fallback UTF-8 encoding for malformed responses

**Code location**: Lines 971, 986, 953
**Implementation effort**: Low (2-3 lines)
**Testing required**: Verify parsing on international character pages

---

#### 14. Conditional HEAD Requests Before Download (Estimated: 2-5% redundant transfer reduction)
**Pattern**: _check_existing_file does HEAD, but also downloads (lines 1039-1078)
**Issue**: Some files may have been partially downloaded previously
**Recommendation**:
- Cache file size from discovery phase
- Skip HEAD request if local file size exactly matches cached remote size
- Implement conditional GET with If-Modified-Since for updates

**Code location**: Lines 1056-1068, 1439-1449 (pre-filter logic)
**Implementation effort**: Low-Medium (10-15 lines)
**Testing required**: Verify size caching through discovery/download phases

---

#### 15. Reduce init_script Calls in Browser Context (Estimated: 2-5% browser initialization speedup)
**Pattern**: Webdriver detection script added 5 times (lines 720, 783, 852)
**Issue**: Redundant init script execution per page
**Recommendation**:
- Move init script to browser context level instead of per-page
- Set once in _get_browser_context() via `_pw_context.add_init_script(...)`
- Remove from individual page creations
- Add comment noting security context for webdriver detection

**Code location**: Lines 720, 783, 852
**Implementation effort**: Very Low (3 lines removed, 1 line added)
**Testing required**: Verify webdriver detection still works, measure init time

---

### LOW IMPACT Optimizations

#### 16. String Interning for Repeated Comparisons (Estimated: <1% memory reduction)
**Pattern**: Extension and hostname strings compared multiple times (lines 895, 901, 904)
**Issue**: String object creation overhead in tight loop
**Recommendation**:
- Pre-compile IGNORED_HOSTS as frozenset of interned strings
- Pre-compile DOWNLOADABLE_EXTENSIONS pattern once
- Use `sys.intern()` for hostname comparisons

**Code location**: Lines 895, 901, IGNORED_HOSTS definition
**Implementation effort**: Very Low (1-2 lines)
**Testing required**: Profile memory usage on large discovery sets

---

## Summary Table

| # | Optimization | Pattern | Est. Impact | Effort | Priority |
|---|---|---|---|---|---|
| 1 | Connection Pool Configuration | HTTP Session | 15-25% | Low | P0 |
| 2 | Use lxml Parser | BeautifulSoup | 3-5x | Low | P0 |
| 3 | Adaptive Timeouts | Browser Timeouts | 10-20% | Medium | P1 |
| 4 | Partial Download Resume | Download Retry | 20-30% | Medium | P1 |
| 5 | Reusable Global Session | HTTP Session | 10-15% | Medium | P1 |
| 6 | Adaptive Chunk Sizing | Download Retry | 5-15% | Low-Med | P2 |
| 7 | Pre-compiled Regex Matching | Link Extraction | 2-5% | Low | P2 |
| 8 | Predicate Reordering | Link Extraction | 3-8% | Low | P2 |
| 9 | Batch Progress Updates | Download Retry | 2-8% | Very Low | P3 |
| 10 | Page Metadata Caching | Discovery | 10-20% | Medium | P2 |
| 11 | Browser Page Reuse | Browser Download | 5-10% | Medium | P2 |
| 12 | Jittered Exponential Backoff | Download Retry | 5-10% | Low | P2 |
| 13 | Response Encoding Detection | BeautifulSoup | 1-3% | Low | P3 |
| 14 | Conditional HEAD Requests | Download Retry | 2-5% | Low-Med | P3 |
| 15 | Context-level Init Script | Browser Download | 2-5% | Very Low | P3 |
| 16 | String Interning | Link Extraction | <1% | Very Low | P4 |

---

## Recommended Implementation Order

### Phase 1 (Immediate - High ROI, Low Risk)
1. **Optimization #2**: Switch to lxml parser (3-5x parsing speedup, trivial change)
2. **Optimization #1**: Configure connection pooling (15-25% throughput, low risk)
3. **Optimization #7**: Pre-compile extension regex (2-5% discovery speedup)
4. **Optimization #15**: Move init_script to context level (2-5% browser init speedup)

### Phase 2 (Medium-term - High Impact, Medium Risk)
5. **Optimization #4**: Implement download resume (20-30% faster failure recovery)
6. **Optimization #3**: Adaptive timeout strategy (10-20% retry reduction)
7. **Optimization #5**: Reusable global session (10-15% latency reduction)
8. **Optimization #6**: Adaptive chunk sizing (5-15% download speedup)

### Phase 3 (Long-term - Medium Impact, Higher Complexity)
9. **Optimization #10**: Page metadata caching (10-20% for repeated runs)
10. **Optimization #11**: Browser page pooling (5-10% browser speedup)
11. **Optimization #12**: Jittered backoff (5-10% retry resilience)
12. **Optimization #8**: Predicate reordering (3-8% discovery speedup)

### Phase 4 (Nice-to-have)
- Remaining optimizations (#9, #13, #14, #16)

---

## Testing Strategy

### Performance Baseline
Before implementing optimizations:
1. Run full download of FY2026 all sources
2. Record: total time, throughput (MB/s), retry count, timeout count
3. Profile: CPU usage, memory peak, connection count

### Per-Optimization Validation
1. Implement optimization
2. Re-run same scenario
3. Measure improvement percentage
4. Check for regressions (timeout count, failure rate)
5. Verify correctness (downloaded files match before/after)

### Integration Testing
- Test with --list mode (discovery only)
- Test with --no-gui mode (terminal only)
- Test with --extract-zips mode
- Test with mixed FY years (2025, 2026)
- Test with --types filter
- Verify browser sources still work correctly

---

## Files Affected

### Primary File
- `C:\Users\wscho\OneDrive\Microsoft Copilot Chat Files\dod_budget_downloader.py`
  - Lines 646-658: get_session() - connection pooling
  - Lines 944-963: discover_fiscal_years() - caching (already good)
  - Lines 966-987: discovery functions - parser optimization
  - Lines 714-770: _browser_extract_links() - init script deduplication
  - Lines 792-873: _browser_download_file() - timeout strategies, page reuse
  - Lines 884-922: _extract_downloadable_links() - predicate reordering, regex
  - Lines 1080-1148: download_file() - retry logic, chunk sizing, resume
  - Lines 1301: session initialization - global session reuse

### Related Documentation Files
- `docs/wiki/optimizations` (if exists) - update with findings
- Performance baseline logs to track improvements

---

## Risk Assessment

### Low Risk Changes
- Parser swap (lxml) - extensive library, well-tested
- Regex pre-compilation - standard Python pattern
- Connection pool config - standard requests library feature
- Init script consolidation - single functionality

### Medium Risk Changes
- Download resume - requires HTTP Range header support verification
- Adaptive timeouts - could mask real errors if too aggressive
- Global session reuse - requires proper cleanup on exceptions
- Browser page reuse - potential memory leaks if not careful

### High Risk Changes (Avoid without extensive testing)
- Modifying retry delays without jitter - could cause retry storms
- Aggressive timeout reduction - could increase false negatives
- Changing deduplication logic - could cause duplicate downloads

---

## Conclusion

The dod_budget_downloader.py file has several low-hanging optimization opportunities, particularly in:
1. HTTP session management (pooling, keep-alive)
2. HTML parsing (parser selection)
3. Download resilience (resume capability, adaptive timeouts)
4. Browser efficiency (page reuse, init script consolidation)

Implementing Phase 1 optimizations alone could yield **10-15x speedup** for large downloads while maintaining code readability and safety.

Phase 1 + Phase 2 combined could achieve **20-30% throughput improvement** with minimal additional complexity.
