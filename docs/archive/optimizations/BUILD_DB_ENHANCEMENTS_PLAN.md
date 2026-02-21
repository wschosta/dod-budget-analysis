# Build Budget Database - Enhancement Plan

## Requested Enhancements

### 1. Enhanced Progress Tracking
- **File Details:** Show current file name, page count in PDF, total pages processed
- **Files Remaining:** Display how many files are left to process
- **Total Progress:** Better visualization of overall progress

### 2. Better Time Estimates
- **Speed Calculation:** Track rows/pages per second
- **Dynamic ETA:** Calculate remaining time based on processed items
- **Throughput Metrics:** Show processing speed in real-time

### 3. Graceful Shutdown
- **Resume Capability:** Save progress state so process can resume later
- **Checkpoint System:** Save progress to database periodically
- **Keyboard Interrupt Handling:** Catch Ctrl+C and allow resume

### 4. Progress State Persistence
- **Checkpoint Table:** Track which files have been processed
- **Resume from Checkpoint:** Skip already-processed files
- **Recovery:** Handle crashes gracefully

---

## Implementation Areas

### A. Database Schema Enhancement

**New Table: `build_progress`**
```sql
CREATE TABLE build_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,           -- Unique session identifier
    checkpoint_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    files_processed INTEGER DEFAULT 0,  -- Total files processed this session
    total_files INTEGER,                -- Total files to process
    pages_processed INTEGER DEFAULT 0,  -- Total pages extracted
    rows_inserted INTEGER DEFAULT 0,    -- Total rows inserted
    bytes_processed INTEGER DEFAULT 0,  -- Total bytes processed
    status TEXT DEFAULT 'in_progress',  -- in_progress, paused, completed
    last_file TEXT,                     -- Last file being processed
    notes TEXT                          -- Any notes about state
);
```

### B. Progress Tracker Class Enhancement

**Current:**
- Tracks files processed/skipped/failed
- Shows download/file progress

**Enhanced:**
- Page count in PDFs
- Total pages processed
- Files remaining (not just completed)
- Processing speed (pages/rows per second)
- Better ETA calculation
- Session persistence

### C. Main Build Loop Enhancement

**Add:**
- Progress state checkpointing every N files
- Session tracking for resume capability
- Graceful shutdown handling (SIGINT)
- Better logging of processing metrics

### D. CLI Arguments

**New flags:**
```bash
python build_budget_db.py --checkpoint-interval 10  # Save every 10 files
python build_budget_db.py --resume                  # Resume from last checkpoint
python build_budget_db.py --show-metrics            # Show detailed metrics
python build_budget_db.py --graceful-shutdown       # Enable Ctrl+C to pause
```

---

## Detailed Enhancements

### 1. Progress Display Enhancement

**Before:**
```
Ingesting Excel files...
  [=====>          ] 25.0%  (5/20 files)
  Current: annual_report_2026.xlsx
```

**After:**
```
Ingesting Excel files...
  Overall:  [=====>          ] 25.0%  (5/20 files)
  Files:    5 processed, 15 remaining

  Current File: annual_report_2026.xlsx
  - Pages: 25 total, 18 extracted

  Progress:
  - Excel rows: 2,450 / 8,900
  - PDF pages: 485 / 1,200
  - Total size: 125 MB / 480 MB

  Speed:
  - Processing: 45.2 rows/sec, 3.2 pages/sec
  - ETA: 4 minutes 20 seconds remaining
```

### 2. Checkpointing System

**Checkpoint on:**
- Every N files (configurable, default 10)
- Every N minutes (configurable, default 5)
- On graceful shutdown (Ctrl+C)

**Checkpoint stores:**
- Which files completed successfully
- Current file being processed
- Rows/pages processed so far
- Processing speed baseline
- Session ID for resume

### 3. Resume Capability

**On resume:**
1. Load checkpoint from database
2. Skip already-processed files
3. Resume current file from last position (if supported)
4. Show what was already completed
5. Continue with remaining files

### 4. Graceful Shutdown

**On Ctrl+C:**
1. Catch keyboard interrupt
2. Finish current file if mid-stream
3. Save checkpoint to database
4. Print resume instructions
5. Exit cleanly (exit code 0)

**User sees:**
```
^C
Keyboard interrupt received. Saving checkpoint...
Checkpoint saved. Resume with:
  python build_budget_db.py --resume

Session: sess-20260217-142530
Processed:
  - 5 Excel files (2,450 rows)
  - 18 PDF files (485 pages)
Files remaining: 17
```

---

## Implementation Steps

### Phase 1: Database Schema (30 min)
- [ ] Add `build_progress` table to schema
- [ ] Add helper functions to manage checkpoints
- [ ] Test checkpoint creation/update

### Phase 2: Progress Tracker Enhancement (45 min)
- [ ] Extend progress tracker with file/page counts
- [ ] Add speed calculations
- [ ] Implement better ETA logic
- [ ] Update progress display format

### Phase 3: Checkpointing System (60 min)
- [ ] Implement checkpoint save/load
- [ ] Track processed files list
- [ ] Add session ID generation
- [ ] Test checkpoint creation and loading

### Phase 4: Resume Capability (30 min)
- [ ] Skip already-processed files
- [ ] Detect partial completion
- [ ] Resume from checkpoint
- [ ] Update CLI with --resume flag

### Phase 5: Graceful Shutdown (30 min)
- [ ] Implement SIGINT handler
- [ ] Save checkpoint on interrupt
- [ ] Clean exit procedures
- [ ] User-friendly messaging

### Phase 6: Testing & Documentation (30 min)
- [ ] Unit tests for checkpoint system
- [ ] Integration tests for resume
- [ ] User documentation
- [ ] Example usage

---

## Estimated Impact

### User Benefits
- **Clear visibility:** Know exactly how long remaining
- **Interruptible:** Can pause and resume without losing progress
- **Recovery:** Crashes don't require starting over
- **Better planning:** ETA helps with scheduling

### Performance
- Minimal overhead from checkpointing
- Faster rebuilds when resuming
- Reduced wasted processing

### Complexity Trade-off
- ~300-400 lines of new code
- Additional database table
- More command-line options
- Better overall experience

---

## Technical Considerations

### Database Locking
- Use separate connection for progress updates
- Non-blocking checkpoint writes
- No impact on main ingestion

### Resume Logic
- Track file checksums to detect changes
- Handle renamed files gracefully
- Detect partial file completion

### Error Handling
- Graceful degradation if checkpoint fails
- Continue even if checkpoint lost
- Log recovery attempts

### Testing
- Test checkpoint creation
- Test resume from various points
- Test graceful shutdown
- Test with interrupt during file processing

---

## Files to Modify

1. **build_budget_db.py** (main file)
   - Add progress tracker enhancements
   - Add checkpoint save/load logic
   - Add graceful shutdown handler
   - Modify main() for resume support

2. **build_budget_gui.py** (if GUI version exists)
   - Update progress display
   - Add checkpoint indicators
   - Show file details

3. **tests/test_pipeline.py**
   - Add checkpoint tests
   - Add resume tests
   - Add metrics tests

---

## Configuration

**New config options:**
```python
# Checkpoint settings
CHECKPOINT_INTERVAL = 10  # Save every N files
CHECKPOINT_TIME_INTERVAL = 5 * 60  # Save every N seconds
SHOW_DETAILED_METRICS = True  # Show page/speed info

# Resume settings
AUTO_RESUME = False  # Automatically resume last session
KEEP_CHECKPOINTS = 5  # Keep last N checkpoints
TIMEOUT_THRESHOLD = 24 * 3600  # Resume if <24h old
```

---

## Success Criteria

- [x] Plan created
- [ ] Progress display shows files remaining
- [ ] Progress display shows page counts
- [ ] Better time remaining estimate
- [ ] Checkpoint system working
- [ ] Resume capability functional
- [ ] Graceful shutdown working
- [ ] Tests passing
- [ ] Documentation complete
- [ ] User can pause and resume without data loss

---

## Next Steps

1. **Approval:** Confirm scope and priorities
2. **Begin Phase 1:** Database schema changes
3. **Iterate:** Complete phases 2-6
4. **Test:** Comprehensive testing
5. **Deploy:** Release with documentation

---

## Questions for User

1. **Priority:** Which enhancement is most important?
   - [ ] Better progress display
   - [ ] Time estimates
   - [ ] Graceful shutdown / resume

2. **Checkpoint frequency:** How often to save?
   - [ ] Every N files (e.g., 10)
   - [ ] Every N minutes (e.g., 5)
   - [ ] Both

3. **Resume auto-detection:** Should it auto-resume?
   - [ ] Manual: require --resume flag
   - [ ] Automatic: detect and ask user
   - [ ] Automatic: always resume

4. **User interaction level:**
   - [ ] Minimal info (just progress bar)
   - [ ] Standard (current file + ETA)
   - [ ] Detailed (all metrics shown)

---

**Status:** Ready for implementation
**Estimated Total Time:** 3-4 hours (all phases)
**Estimated Lines of Code:** 300-400
