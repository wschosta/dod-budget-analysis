# Step 1.B3 — Normalize Monetary Values

**Status:** Complete
**Type:** Code modification (AI-agent completable)
**Depends on:** 1.B1 (to know what units each exhibit uses)

## User Decisions (RESOLVED)

- **Canonical storage unit:** Thousands of dollars
- **Display toggle:** Search/UI supports toggle to millions (divide by 1,000)

---

## Sub-tasks

### 1.B3-a — Detect source unit from exhibit headers
**Type:** AI-agent + DATA PROCESSING
**Estimated tokens:** ~600 output

1. In `ingest_excel_file()`, scan header area for unit indicators:
   - Patterns: "in thousands", "in millions", "($ thousands)", "Thousands of Dollars"
2. Add a `_detect_amount_unit(header_rows) -> str` function returning "thousands"|"millions"|"unknown"
3. If "millions": set a multiplier of 1000 (convert to thousands before storing)
4. If "unknown": default to thousands with a log warning

**File:** `build_budget_db.py`

---

### 1.B3-b — Add amount_unit column to schema
**Type:** AI-agent
**Estimated tokens:** ~300 output

1. Add `amount_unit TEXT DEFAULT 'thousands'` to `budget_lines` CREATE TABLE
2. Store detected source unit for provenance
3. Requires `--rebuild` to take effect

**File:** `build_budget_db.py` — modify `create_database()`

---

### 1.B3-c — Apply unit normalization during ingestion
**Type:** AI-agent
**Estimated tokens:** ~400 output
**Depends on:** 1.B3-a, 1.B3-b

1. In `ingest_excel_file()`, after detecting unit:
   - If source is millions: multiply all `_safe_float()` results by 1000
   - Store original unit in `amount_unit` column
2. Add test: mock Excel with "millions" header, verify stored values are ×1000

**File:** `build_budget_db.py`

---

### 1.B3-d — Add budget_type column for BA/Appropriation/Outlay distinction
**Type:** AI-agent
**Estimated tokens:** ~400 output

1. Add `budget_type TEXT` column to `budget_lines` (values: "BA", "Appn", "Outlay", NULL)
2. C-1 already has authorization vs. appropriation amounts — detect from column headers
3. Other exhibits may have TOA (Total Obligation Authority) vs. BA
4. Map during ingestion; NULL if not determinable

**File:** `build_budget_db.py` — modify schema and `ingest_excel_file()`

---

### 1.B3-e — Add --unit toggle to search_budget.py
**Type:** AI-agent
**Estimated tokens:** ~600 output

1. Add `--unit thousands|millions` CLI argument (default: thousands)
2. Update `_fmt_amount()`: if millions, divide by 1000, format as `$X.XXM`
3. In interactive mode: add `unit millions` / `unit thousands` command
4. Update `docs/wiki/Data-Dictionary.md` with unit convention note

**File:** `search_budget.py`

---

### 1.B3-f — Update validation suite for unit consistency
**Type:** AI-agent
**Estimated tokens:** ~300 output
**Depends on:** 1.B3-b

1. Add a `check_unit_consistency(conn)` to `validate_budget_db.py`
2. Flag rows where `amount_unit` is not "thousands" (suggests normalization missed)
3. Also update `validate_budget_data.py` if applicable

**File:** `validate_budget_db.py`

---

## Annotations

- Sub-tasks 1.B3-a through 1.B3-c form the core normalization pipeline
- 1.B3-d is a separate enhancement (BA/Appn/Outlay)
- 1.B3-e is display-only (no storage change)
- Schema changes require `--rebuild`
