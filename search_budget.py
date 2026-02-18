"""
DoD Budget Database Search Tool

Search the SQLite budget database built by build_budget_db.py.
Supports full-text search across budget line items and PDF documents,
structured queries by organization/account/exhibit type, and aggregations.

Usage:
    python search_budget.py "missile defense"
    python search_budget.py "Army basic research" --type excel
    python search_budget.py "cyber" --org Army --top 20
    python search_budget.py "missile" --category Navy --type pdf
    python search_budget.py --summary
    python search_budget.py --sources
    python search_budget.py --interactive
"""

import argparse
import csv
import json
import re
import sqlite3
import sys
import textwrap
from pathlib import Path

DEFAULT_DB_PATH = Path("dod_budget.sqlite")


# FTS5 operator keywords that should be treated as literal text in user queries
_FTS5_KEYWORDS = {"AND", "OR", "NOT", "NEAR"}

# Characters that have special meaning in FTS5 query syntax
_FTS5_SPECIAL_CHARS = re.compile(r'[\"()*:^+]')


def _sanitize_fts5_query(query: str) -> str:
    """Sanitize user input for safe use in an FTS5 MATCH expression.

    Strips FTS5 special characters, removes standalone operator keywords,
    and wraps each term in double quotes so FTS5 treats them as literals.
    Returns terms joined with OR for broad matching.
    """
    # Strip characters that act as FTS5 operators
    cleaned = _FTS5_SPECIAL_CHARS.sub(" ", query)
    # Split into individual terms
    terms = cleaned.split()
    # Drop FTS5 boolean keywords (case-insensitive) and empty/dash-only terms
    terms = [t for t in terms if t.upper() not in _FTS5_KEYWORDS
             and t.strip("-")]
    if not terms:
        return ""
    # Wrap each term in double quotes to force literal matching
    return " OR ".join(f'"{t}"' for t in terms)


def get_connection(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        print("Run 'python build_budget_db.py' first to build the database.")
        sys.exit(1)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# ── Summary / Stats ───────────────────────────────────────────────────────────

def show_summary(conn: sqlite3.Connection) -> None:
    """Show database summary statistics."""
    print("=" * 65)
    print("  DoD BUDGET DATABASE SUMMARY")
    print("=" * 65)

    row = conn.execute("SELECT COUNT(*) as c FROM budget_lines").fetchone()
    print(f"\n  Budget line items:  {row['c']:,}")

    row = conn.execute("SELECT COUNT(*) as c FROM pdf_pages").fetchone()
    print(f"  PDF pages indexed:  {row['c']:,}")

    row = conn.execute("SELECT COUNT(*) as c FROM ingested_files").fetchone()
    print(f"  Files ingested:     {row['c']:,}")

    # By exhibit type
    print(f"\n  {'Exhibit Type':<35} {'Lines':>10}")
    print(f"  {'-'*35} {'-'*10}")
    for r in conn.execute("""
        SELECT exhibit_type, COUNT(*) as c
        FROM budget_lines GROUP BY exhibit_type ORDER BY c DESC
    """):
        print(f"  {r['exhibit_type'] or 'unknown':<35} {r['c']:>10,}")

    # By organization
    print(f"\n  {'Organization':<25} {'Lines':>10}")
    print(f"  {'-'*25} {'-'*10}")
    for r in conn.execute("""
        SELECT organization_name, COUNT(*) as c
        FROM budget_lines GROUP BY organization_name ORDER BY c DESC
    """):
        print(f"  {r['organization_name'] or 'unknown':<25} {r['c']:>10,}")

    # PDF categories
    print(f"\n  {'PDF Category':<25} {'Pages':>10}")
    print(f"  {'-'*25} {'-'*10}")
    for r in conn.execute("""
        SELECT source_category, COUNT(*) as c
        FROM pdf_pages GROUP BY source_category ORDER BY c DESC
    """):
        print(f"  {r['source_category'] or 'unknown':<25} {r['c']:>10,}")

    # FY2026 totals by major account
    print(f"\n  {'Top FY2026 Request by Account':<45} {'$ Thousands':>15}")
    print(f"  {'-'*45} {'-'*15}")
    for r in conn.execute("""
        SELECT account_title,
               SUM(amount_fy2026_request) as total
        FROM budget_lines
        WHERE amount_fy2026_request IS NOT NULL
          AND (sheet_name LIKE '%Exhibit%' OR sheet_name LIKE '%Title%' OR sheet_name LIKE '%FY 2026%')
        GROUP BY account_title
        HAVING total > 0
        ORDER BY total DESC
        LIMIT 15
    """):
        print(f"  {(r['account_title'] or '')[:45]:<45} {r['total']:>15,.0f}")


def show_sources(conn: sqlite3.Connection) -> None:
    """Show data source tracking information."""
    print("=" * 80)
    print("  DATA SOURCES")
    print("=" * 80)

    print(f"\n  {'File':<55} {'Type':>5} {'Rows':>8} {'Ingested':>20}")
    print(f"  {'-'*55} {'-'*5} {'-'*8} {'-'*20}")
    for r in conn.execute("""
        SELECT file_path, file_type, row_count, ingested_at, status
        FROM ingested_files
        ORDER BY file_type, file_path
    """):
        status = "" if r["status"] == "ok" else f" [{r['status']}]"
        name = r["file_path"]
        if len(name) > 55:
            name = "..." + name[-52:]
        print(f"  {name:<55} {r['file_type']:>5} {r['row_count']:>8,} {r['ingested_at']:>20}{status}")

    # Show last update time
    row = conn.execute("SELECT MAX(ingested_at) as last FROM ingested_files").fetchone()
    print(f"\n  Last database update: {row['last']}")


# ── Search Functions ──────────────────────────────────────────────────────────

def search_budget_lines(conn: sqlite3.Connection, query: str,
                        org: str = None, exhibit: str = None,
                        limit: int = 25) -> list:
    """Search structured budget line items."""
    conditions = []
    params = []

    if query:
        conditions.append("""
            id IN (
                SELECT rowid FROM budget_lines_fts
                WHERE budget_lines_fts MATCH ?
            )
        """)
        # Convert natural language to FTS5 query (sanitized)
        fts_query = _sanitize_fts5_query(query)
        if not fts_query:
            return []
        params.append(fts_query)

    if org:
        conditions.append("organization_name LIKE ?")
        params.append(f"%{org}%")

    if exhibit:
        conditions.append("exhibit_type LIKE ?")
        params.append(f"%{exhibit}%")

    where = " AND ".join(conditions) if conditions else "1=1"

    sql = f"""
        SELECT id, source_file, exhibit_type, sheet_name, fiscal_year,
               account, account_title, organization_name,
               budget_activity_title, sub_activity_title,
               line_item, line_item_title,
               amount_fy2024_actual, amount_fy2025_enacted,
               amount_fy2026_request, amount_fy2026_total
        FROM budget_lines
        WHERE {where}
        ORDER BY COALESCE(amount_fy2026_request, amount_fy2026_total,
                          amount_fy2025_enacted, 0) DESC
        LIMIT ?
    """
    params.append(limit)
    return conn.execute(sql, params).fetchall()


def search_pdf_pages(conn: sqlite3.Connection, query: str,
                     category: str = None, limit: int = 15) -> list:
    """Search PDF document content."""
    conditions = []
    params = []

    if query:
        conditions.append("""
            id IN (
                SELECT rowid FROM pdf_pages_fts
                WHERE pdf_pages_fts MATCH ?
            )
        """)
        fts_query = _sanitize_fts5_query(query)
        if not fts_query:
            return []
        params.append(fts_query)

    if category:
        conditions.append("source_category LIKE ?")
        params.append(f"%{category}%")

    where = " AND ".join(conditions) if conditions else "1=1"

    sql = f"""
        SELECT id, source_file, source_category, page_number,
               page_text, has_tables, table_data
        FROM pdf_pages
        WHERE {where}
        LIMIT ?
    """
    params.append(limit)
    return conn.execute(sql, params).fetchall()


# ── Display ───────────────────────────────────────────────────────────────────

def _fmt_amount(val: float | None) -> str:
    """Format a dollar amount in thousands."""
    if val is None:
        return "-"
    return f"${val:,.0f}"


def display_budget_results(results: list, query: str) -> None:
    """Display budget line item search results."""
    if not results:
        print(f"\n  No budget line items found for: '{query}'")
        return

    print(f"\n{'='*90}")
    print(f"  BUDGET LINE ITEMS ({len(results)} results)")
    print(f"{'='*90}")

    for r in results:
        title_parts = [r["account_title"] or ""]
        if r["budget_activity_title"]:
            title_parts.append(r["budget_activity_title"])
        if r["line_item_title"]:
            title_parts.append(r["line_item_title"])
        elif r["sub_activity_title"]:
            title_parts.append(r["sub_activity_title"])

        title = " > ".join(t for t in title_parts if t)
        org = r["organization_name"] or ""

        print(f"\n  [{org}] {title}")
        print(f"    Account: {r['account']}  |  Exhibit: {r['exhibit_type']}  |  Sheet: {r['sheet_name']}")
        print(f"    FY2024 Actual: {_fmt_amount(r['amount_fy2024_actual']):>15}"
              f"    FY2025 Enacted: {_fmt_amount(r['amount_fy2025_enacted']):>15}"
              f"    FY2026 Request: {_fmt_amount(r['amount_fy2026_request']):>15}")
        if r["amount_fy2026_total"] and r["amount_fy2026_total"] != r["amount_fy2026_request"]:
            print(f"    FY2026 Total:   {_fmt_amount(r['amount_fy2026_total']):>15}")
        print(f"    Source: {r['source_file']}")


def display_pdf_results(results: list, query: str) -> None:
    """Display PDF search results with context snippets."""
    if not results:
        print(f"\n  No PDF content found for: '{query}'")
        return

    print(f"\n{'='*90}")
    print(f"  PDF DOCUMENT MATCHES ({len(results)} results)")
    print(f"{'='*90}")

    for r in results:
        print(f"\n  [{r['source_category']}] {r['source_file']} (page {r['page_number']})")

        text = r["page_text"] or ""
        # Show a snippet around the query terms
        snippet = _extract_snippet(text, query, max_len=300)
        if snippet:
            wrapped = textwrap.fill(snippet, width=85, initial_indent="    ",
                                    subsequent_indent="    ")
            print(wrapped)

        if r["has_tables"] and r["table_data"]:
            table_snippet = _extract_snippet(r["table_data"], query, max_len=200)
            if table_snippet:
                print(f"    [TABLE] {table_snippet[:200]}")


def _highlight_terms(text: str, query: str) -> str:
    """Highlight query terms in text using ANSI bold."""
    if not text or not query:
        return text or ""
    terms = query.split()
    # Build a pattern that matches any of the search terms (case-insensitive)
    escaped = [re.escape(t) for t in terms if t]
    if not escaped:
        return text
    pattern = re.compile("(" + "|".join(escaped) + ")", re.IGNORECASE)
    return pattern.sub(r"\033[1m\1\033[0m", text)


def _extract_snippet(text: str, query: str, max_len: int = 300) -> str:
    """Extract a text snippet around query terms with highlighted matches."""
    if not text or not query:
        return text[:max_len] if text else ""

    text_lower = text.lower()
    terms = query.lower().split()

    # Find the first matching term
    best_pos = len(text)
    for term in terms:
        pos = text_lower.find(term)
        if pos != -1 and pos < best_pos:
            best_pos = pos

    if best_pos == len(text):
        return _highlight_terms(text[:max_len], query)

    # Extract context around the match
    start = max(0, best_pos - 80)
    end = min(len(text), best_pos + max_len - 80)

    snippet = text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."

    return _highlight_terms(snippet, query)


# ── Interactive Mode ──────────────────────────────────────────────────────────

def interactive_mode(conn: sqlite3.Connection) -> None:
    """Interactive search REPL."""
    print("=" * 65)
    print("  DoD BUDGET DATABASE - Interactive Search")
    print("=" * 65)
    print()
    print("  Commands:")
    print("    <query>                Search both Excel data and PDFs")
    print("    excel:<query>          Search only budget line items")
    print("    pdf:<query>            Search only PDF documents")
    print("    org:<name> <query>     Filter by organization")
    print("    exhibit:<type> <query>  Filter by exhibit type (p1, r1, etc.)")
    print("    category:<name> <query> Filter PDFs by category (Army, Navy, etc.)")
    print("    summary                Show database summary")
    print("    sources                Show data source tracking")
    print("    top <org>              Top budget items by organization")
    print("    quit / exit            Exit")
    print()

    while True:
        try:
            raw = input("search> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not raw:
            continue
        if raw.lower() in ("quit", "exit", "q"):
            print("Goodbye.")
            break
        if raw.lower() == "summary":
            show_summary(conn)
            continue
        if raw.lower() == "sources":
            show_sources(conn)
            continue

        # Parse command prefixes
        search_type = "both"
        org_filter = None
        exhibit_filter = None
        category_filter = None
        query = raw

        if raw.lower().startswith("excel:"):
            search_type = "excel"
            query = raw[6:].strip()
        elif raw.lower().startswith("pdf:"):
            search_type = "pdf"
            query = raw[4:].strip()
        elif raw.lower().startswith("org:"):
            parts = raw[4:].strip().split(None, 1)
            org_filter = parts[0]
            query = parts[1] if len(parts) > 1 else ""
        elif raw.lower().startswith("exhibit:"):
            parts = raw[8:].strip().split(None, 1)
            exhibit_filter = parts[0]
            query = parts[1] if len(parts) > 1 else ""
        elif raw.lower().startswith("category:"):
            parts = raw[9:].strip().split(None, 1)
            category_filter = parts[0]
            query = parts[1] if len(parts) > 1 else ""
            search_type = "pdf"
        elif raw.lower().startswith("top "):
            org = raw[4:].strip()
            results = search_budget_lines(conn, "", org=org, limit=20)
            display_budget_results(results, f"top items for {org}")
            continue

        if not query:
            print("  Please enter a search query.")
            continue

        if search_type in ("both", "excel"):
            results = search_budget_lines(conn, query, org=org_filter,
                                          exhibit=exhibit_filter)
            display_budget_results(results, query)

        if search_type in ("both", "pdf"):
            results = search_pdf_pages(conn, query, category=category_filter)
            display_pdf_results(results, query)


# ── Export ────────────────────────────────────────────────────────────────────

def export_results(budget_results: list, pdf_results: list, query: str, fmt: str) -> None:
    """Export search results to CSV or JSON files."""
    slug = re.sub(r'[^\w\-]', '_', query)[:30]

    if fmt == "json":
        out = Path(f"results_{slug}.json")
        data = {
            "query": query,
            "budget_lines": [dict(r) for r in budget_results],
            "pdf_pages": [dict(r) for r in pdf_results],
        }
        out.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"\n  Exported {len(budget_results)} budget line(s) and "
              f"{len(pdf_results)} PDF page(s) to {out}")

    elif fmt == "csv":
        if budget_results:
            out = Path(f"results_{slug}_budget_lines.csv")
            rows = [dict(r) for r in budget_results]
            with open(out, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            print(f"\n  Exported {len(rows)} budget line(s) to {out}")

        if pdf_results:
            out = Path(f"results_{slug}_pdf_pages.csv")
            rows = [dict(r) for r in pdf_results]
            with open(out, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            print(f"  Exported {len(rows)} PDF page(s) to {out}")

        if not budget_results and not pdf_results:
            print("\n  No results to export.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search the DoD budget database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            Examples:
              python search_budget.py "missile defense"
              python search_budget.py "cyber" --org Army
              python search_budget.py "DARPA" --type pdf --top 30
              python search_budget.py "cyber" --export csv
              python search_budget.py "missile" --export json --type excel
              python search_budget.py --summary
              python search_budget.py --sources
              python search_budget.py --interactive
        """),
    )
    parser.add_argument("query", nargs="?", default=None,
                        help="Search query (use quotes for multi-word)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH,
                        help="Database path")
    parser.add_argument("--type", choices=["excel", "pdf", "both"], default="both",
                        help="Search type (default: both)")
    parser.add_argument("--org", default=None,
                        help="Filter by organization (Army, Navy, Air Force, etc.)")
    parser.add_argument("--exhibit", default=None,
                        help="Filter by exhibit type (m1, o1, p1, r1, etc.)")
    parser.add_argument("--category", default=None,
                        help="Filter PDF results by source category (Army, Navy, Comptroller, etc.)")
    parser.add_argument("--top", type=int, default=25,
                        help="Number of results (default: 25)")
    parser.add_argument("--summary", action="store_true",
                        help="Show database summary")
    parser.add_argument("--sources", action="store_true",
                        help="Show data source tracking")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Interactive search mode")
    parser.add_argument("--export", choices=["csv", "json"], default=None,
                        help="Export results to file (csv or json). "
                             "CSV writes separate files per result type; "
                             "JSON writes one file with both sections.")
    args = parser.parse_args()

    conn = get_connection(args.db)

    if args.summary:
        show_summary(conn)
    elif args.sources:
        show_sources(conn)
    elif args.interactive:
        interactive_mode(conn)
    elif args.query:
        excel_results = []
        pdf_results = []

        if args.type in ("both", "excel"):
            excel_results = search_budget_lines(conn, args.query, org=args.org,
                                                exhibit=args.exhibit, limit=args.top)
            display_budget_results(excel_results, args.query)

        if args.type in ("both", "pdf"):
            pdf_results = search_pdf_pages(conn, args.query,
                                           category=args.category, limit=args.top)
            display_pdf_results(pdf_results, args.query)

        if args.export:
            export_results(excel_results, pdf_results, args.query, args.export)
    else:
        parser.print_help()

    conn.close()


if __name__ == "__main__":
    main()
