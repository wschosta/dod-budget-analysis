"""
Integration / pipeline tests — Step 1.C3

End-to-end tests that exercise the full ingest pipeline: file discovery →
Excel/PDF parsing → SQLite insertion → FTS indexing.  Also tests for
search_budget.py query functionality against a known database.

──────────────────────────────────────────────────────────────────────────────
TODOs — each is an independent test or small group of tests
──────────────────────────────────────────────────────────────────────────────

TODO 1.C3-a: Test full Excel ingestion pipeline.
    Use the session-scoped test_db fixture (from conftest.py).  Assert:
    - ingested_files table has one row per fixture file
    - budget_lines table has the expected total row count
    - Each row in budget_lines has a non-null source_file and exhibit_type
    Dependency: conftest.py fixtures (TODO 1.C1-a, 1.C1-c) must exist.

TODO 1.C3-b: Test full PDF ingestion pipeline.
    Same pattern as 1.C3-a but for PDFs:
    - pdf_pages table has rows for each page of each fixture PDF
    - content column is non-empty for extractable PDFs
    - FTS index (pdf_pages_fts) returns results for known text

TODO 1.C3-c: Test incremental update behavior.
    1. Build database from fixture files.
    2. Record ingested_files state.
    3. Run build again without changes — assert no new rows added.
    4. Touch one fixture file (update mtime) — assert only that file re-ingested.
    Token-efficient tip: use tmp_path, shutil.copy fixtures in, build, then
    copy one file again with a modified timestamp.

TODO 1.C3-d: Test --rebuild flag.
    Build database, then rebuild with --rebuild.  Assert all rows are fresh
    (ingested_files.file_hash values may stay the same, but the table should
    have been recreated — check by verifying ingested_at timestamps are all
    from the second run).

TODO 1.C3-e: Test search_budget.py query functions against test_db.
    Import search functions and run them against the test database:
    - Text search: search for a term known to be in fixtures, assert results
    - Filter by exhibit_type: assert only matching rows returned
    - Filter by organization: assert only matching rows returned
    - Empty search: assert no crash, returns empty list
    Dependency: test_db fixture from conftest.py.

TODO 1.C3-f: Test error handling for corrupt/unreadable files.
    Place a zero-byte .xlsx, a truncated .xlsx, and a non-Excel file renamed
    to .xlsx in the fixtures directory.  Assert that build_database() logs
    warnings but does not crash, and that the bad files are NOT in ingested_files.

TODO 1.C3-g: Test that FTS5 index is populated and queryable.
    After building the test database, run a raw SQL query against budget_lines_fts
    and pdf_pages_fts.  Assert that MATCH queries return the expected rows.
    Standalone — just needs the test_db fixture.

TODO 1.C3-h: Test database schema integrity.
    After building, query sqlite_master and assert all expected tables, indexes,
    and FTS virtual tables exist.  Also verify column names match expectations.
    Standalone — ~15 lines.
"""

# TODO: implement tests per TODOs above
