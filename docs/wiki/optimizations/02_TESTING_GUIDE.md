# Optimization Testing Guide

## Quick Start

```bash
# First run - creates cache, tests lxml/connection pool
python dod_budget_downloader.py --years 2026 --sources all --list --no-gui

# Second run - uses cache, should be 10-20x faster
python dod_budget_downloader.py --years 2026 --sources all --list --no-gui

# Force refresh cache
python dod_budget_downloader.py --years 2026 --sources all --list --refresh-cache --no-gui
```

---

## Verification Tests

### Test 1: lxml Parser Verification
**Objective:** Confirm lxml is being used for parsing

```bash
# Add temporary debug: search for "PARSER =" in output
# Expected: Should see "lxml" if available, "html.parser" otherwise
```

### Test 2: Connection Pool Verification
**Objective:** Confirm connection reuse

- Run multiple discovery commands in quick succession
- Should see connection reuse in network traces
- Compare with original version (baseline)

### Test 3: Cache Functionality
**Objective:** Verify discovery caching works

1. **First run:**
   ```bash
   time python dod_budget_downloader.py --years 2026 --sources army navy --list --no-gui
   # Note the discovery time
   ```

2. **Second run (should be faster):**
   ```bash
   time python dod_budget_downloader.py --years 2026 --sources army navy --list --no-gui
   # Should see "Using cached results"
   ```

3. **Verify cache files created:**
   ```bash
   ls -la discovery_cache/
   # Should see: army_2026.json, navy_2026.json
   ```

4. **Refresh cache:**
   ```bash
   python dod_budget_downloader.py --years 2026 --sources army navy --list --refresh-cache --no-gui
   # Should skip cache, re-discover from source
   ```

### Test 4: Download Resume Verification
**Objective:** Confirm partial resume works

1. **Start a download:**
   ```bash
   python dod_budget_downloader.py --years 2026 --sources comptroller --no-gui
   # Let it download a few files...
   ```

2. **Interrupt with Ctrl+C** mid-download

3. **Restart the same command:**
   ```bash
   python dod_budget_downloader.py --years 2026 --sources comptroller --no-gui
   # Should see partial files being resumed instead of re-downloaded
   # Check output for "[RETRY]" messages
   ```

### Test 5: Timeout Adaptation Verification
**Objective:** Confirm timeout manager is learning

- Run discovery on slow domain (e.g., Navy)
- First attempt: uses default 15s timeout
- Subsequent attempts: should show adapted timeouts
- Check for any timeout-related messages

### Test 6: Chunk Sizing Verification
**Objective:** Confirm adaptive chunk sizes

- Download multiple files of different sizes
- Small files (<5MB): should complete quickly
- Large files (>100MB): should show higher throughput
- Monitor memory usage (shouldn't spike with large files)

---

## Performance Benchmarking

### Baseline Measurement (Before Optimizations)
```bash
# Time the original version (without optimizations)
time python dod_budget_downloader_original.py --years 2026 --sources all --list

# Result: Baseline time (T0)
```

### After Optimizations
```bash
# Run 1: Fresh discovery (tests lxml, connection pool, timeout mgr)
time python dod_budget_downloader.py --years 2026 --sources all --list --no-gui
# Result: Time T1 (should be faster due to lxml)

# Run 2: From cache (tests caching optimization)
time python dod_budget_downloader.py --years 2026 --sources all --list --no-gui
# Result: Time T2 (should be 10-20x faster than T1)
```

### Expected Results

| Operation | Baseline | Optimized | Speedup |
|-----------|----------|-----------|---------|
| Fresh discovery | T0 | T1 = 0.8*T0 | 1.25x (from lxml) |
| Cached discovery | N/A | T2 = 0.05*T0 | 20x (cached) |
| Single file download | D0 | D1 = 0.95*D0 | 1.05x (chunking) |
| Failed+resume | R0 | R1 = 0.7*R0 | 1.43x (resume) |
| 10 parallel files | P0 | P1 = 0.6*P0 | 1.67x (pooling) |

---

## Visual Inspection Checklist

### Console Output Verification

```
Expected messages:

✓ "Using cached results for FY2026" - Cache working
✓ "[RETRY X/3]" messages - Resume/retry working
✓ No "[Timeout]" errors - Timeout adaptation working
✓ Connection reuse in logs - Session pooling working
✓ "discovery_cache/" directory exists - Cache system working
```

### File System Verification

```bash
# Check cache directory created
ls -la discovery_cache/

# Expected files:
# - comptroller_2026.json
# - defense-wide_2026.json
# - army_2026.json
# - navy_2026.json
# - navy-archive_2026.json
# - airforce_2026.json

# Check file timestamps (should be recent)
stat discovery_cache/army_2026.json

# Check cache content
head discovery_cache/army_2026.json
# Should show JSON with "timestamp" and "files" keys
```

---

## Performance Profiling

### Method 1: Simple Time Measurement
```bash
# Measure discovery time with timer
python -m timeit -s 'import subprocess' \
  'subprocess.run(["python", "dod_budget_downloader.py", "--years", "2026", "--sources", "all", "--list", "--no-gui"])'
```

### Method 2: Manual Timing
```bash
# First run
time python dod_budget_downloader.py --years 2026 --sources all --list --no-gui

# Second run (should be faster)
time python dod_budget_downloader.py --years 2026 --sources all --list --no-gui

# Calculate speedup: T1 / T2
```

### Method 3: Monitor Resource Usage
```bash
# On Windows (PowerShell)
Measure-Command { python dod_budget_downloader.py --years 2026 --sources all --list --no-gui }

# On Unix/Mac
time python dod_budget_downloader.py --years 2026 --sources all --list --no-gui
```

---

## Troubleshooting

### Issue: Cache not being used
**Solution:** Check if lxml works:
```python
python -c "import lxml; print('lxml available')"
```

### Issue: Slow discovery (lxml not helping)
**Check:**
1. Is lxml installed? (`pip list | grep lxml`)
2. Is it being used? (Add debug print in code)
3. Install if missing: `pip install lxml`

### Issue: Download resume not working
**Check:**
1. Does server support Accept-Ranges? (Check response headers)
2. Is file permissions correct? (Can write to destination)
3. Check HEAD request response in code

### Issue: Timeout errors
**Solution:**
1. First run learns timeouts for your network
2. Subsequent runs should have better timeouts
3. Check `_timeout_mgr.response_times` dict

---

## Success Criteria

- [x] Syntax validation passed
- [ ] lxml parser confirmed in use
- [ ] Cache directory created with JSON files
- [ ] Second run 10-20x faster (or indicates cache use)
- [ ] Download resume works on interrupted transfers
- [ ] No new errors or warnings
- [ ] All file downloads complete successfully
- [ ] Memory usage reasonable (no spikes)
- [ ] Timeout adaptation reduces retry rate

---

## Regression Testing

### Ensure Original Functionality Preserved

1. **File discovery still works:**
   ```bash
   python dod_budget_downloader.py --years 2026 --sources comptroller --list
   # Should still find all comptroller files
   ```

2. **Download still works:**
   ```bash
   python dod_budget_downloader.py --years 2026 --sources comptroller
   # Should download files successfully
   ```

3. **File extraction still works:**
   ```bash
   python dod_budget_downloader.py --years 2026 --sources comptroller --extract-zips
   # Should extract ZIP files after download
   ```

4. **Type filtering still works:**
   ```bash
   python dod_budget_downloader.py --years 2026 --sources all --types pdf
   # Should only list/download PDFs
   ```

5. **GUI mode still works:**
   ```bash
   python dod_budget_downloader.py --years 2026
   # Should show GUI progress window
   ```

---

## Performance Expectations by Use Case

### Scenario 1: One-time Fresh Discovery
- **Expected:** 20-30% faster (lxml parsing + connection pooling)
- **Time:** ~2-3 minutes instead of ~3-4 minutes

### Scenario 2: Repeated Runs (Cached)
- **Expected:** 10-20x faster (bypasses discovery entirely)
- **Time:** ~5-10 seconds instead of ~2-3 minutes

### Scenario 3: Download-Heavy
- **Expected:** 5-15% faster (chunking + resume + pooling)
- **Time:** Depends on file sizes and network

### Scenario 4: Resume After Failure
- **Expected:** 2-3x faster (resume instead of re-download)
- **Time:** Only download remaining bytes

---

## Notes

- Cache files are safe to delete (will be regenerated)
- Cache respects 24-hour TTL (can be tuned)
- --refresh-cache forces cache regeneration
- All optimizations are non-breaking and gracefully degrade
- First run is discovery-heavy; subsequent runs use cache
