#!/usr/bin/env bash
# check_hypersonics.sh — pre-flight data quality check for the hypersonics view
#
# Usage:
#   ./scripts/check_hypersonics.sh [BASE_URL]
#
# Default BASE_URL: http://localhost:8000
# Example:
#   ./scripts/check_hypersonics.sh http://localhost:8000

set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
URL="$BASE_URL/api/v1/hypersonics/debug"

# ── colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[0;33m'; BLD='\033[1m'; RST='\033[0m'
ok()   { echo -e "  ${GRN}✓${RST}  $*"; }
warn() { echo -e "  ${YLW}⚠${RST}  $*"; }
fail() { echo -e "  ${RED}✗${RST}  $*"; }

echo -e "\n${BLD}Hypersonics pre-flight check${RST}  →  $URL\n"

# ── fetch ─────────────────────────────────────────────────────────────────────
if ! RAW=$(curl -sf "$URL"); then
  echo -e "${RED}ERROR: could not reach $URL${RST}"
  echo "  Is the server running? Try: uvicorn api.app:app --reload --port 8000"
  exit 1
fi

j() { echo "$RAW" | python3 -c "import sys,json; d=json.load(sys.stdin); print($1)"; }

# ── 1. Amount columns ─────────────────────────────────────────────────────────
echo -e "${BLD}1. Amount columns${RST}"
MISSING=$(j "','.join(d['amount_columns']['years_with_no_data'])")
if [ "$MISSING" = "" ]; then
  ok "All FY columns present"
else
  warn "Years with no amount column: $MISSING"
fi

echo "$RAW" | python3 - <<'PY'
import sys, json
d = json.load(sys.stdin)["amount_columns"]["per_year_priority_used"]
fallbacks = {k: v for k, v in d.items() if v not in ("request", "missing")}
if fallbacks:
    for fy, col in sorted(fallbacks.items()):
        print(f"  \033[0;33m⚠\033[0m  {fy}: falling back to '{col}' (no _request column)")
PY

# ── 2. pe_descriptions ────────────────────────────────────────────────────────
echo -e "\n${BLD}2. pe_descriptions table${RST}"
PD_EXISTS=$(j "d['pe_descriptions']['table_exists']")
PD_POP=$(j "d['pe_descriptions']['populated']")
if [ "$PD_EXISTS" = "False" ]; then
  fail "Table does not exist — run: python enrich_budget_db.py"
elif [ "$PD_POP" = "False" ]; then
  fail "Table exists but is empty — run: python enrich_budget_db.py"
else
  PD_ROWS=$(j "d['pe_descriptions']['row_count']")
  PD_PES=$(j "d['pe_descriptions']['distinct_pe_numbers']")
  PD_HITS=$(j "d['pe_descriptions']['pe_numbers_matching_keywords']")
  ok "Populated: $PD_ROWS rows, $PD_PES PE numbers, $PD_HITS match hypersonics keywords"
fi

# ── 3. source_file coverage ───────────────────────────────────────────────────
echo -e "\n${BLD}3. Source file (citation) coverage${RST}"
SF_OK=$(j "d['source_file']['ok']")
SF_NULL=$(j "d['source_file']['null_count']")
SF_TOTAL=$(j "d['source_file']['total_matching_rows']")
SF_PCT=$(j "d['source_file']['null_pct']")
if [ "$SF_OK" = "True" ]; then
  ok "All $SF_TOTAL matching rows have source_file set"
else
  warn "$SF_NULL / $SF_TOTAL rows missing source_file (${SF_PCT}%) — citation dots will be absent for those cells"
fi

# ── 4. color-of-money normalisation ──────────────────────────────────────────
echo -e "\n${BLD}4. Color-of-money normalisation${RST}"
COM_OK=$(j "d['color_of_money']['ok']")
if [ "$COM_OK" = "True" ]; then
  ok "All appropriation titles normalised cleanly"
else
  echo "$RAW" | python3 - <<'PY'
import sys, json
d = json.load(sys.stdin)["color_of_money"]
unk = d["breakdown"].get("Unknown", 0)
if unk:
    print(f"  \033[0;31m✗\033[0m  {unk} sub-element(s) mapped to 'Unknown' (NULL approp_title)")
for t in d["unrecognized_approp_titles"]:
    print(f"  \033[0;33m⚠\033[0m  Unrecognized approp_title (shown verbatim): \"{t}\"")
print("      → add matches in _color_of_money() in api/routes/hypersonics.py")
PY
fi

# ── 5. keyword coverage ───────────────────────────────────────────────────────
echo -e "\n${BLD}5. Keyword PE hit counts${RST}"
echo "$RAW" | python3 - <<'PY'
import sys, json
hits = json.load(sys.stdin)["keyword_pe_hits"]
for kw, n in hits.items():
    if n == 0:
        print(f"  \033[0;33m⚠\033[0m  '{kw}' matched 0 PE numbers — check spelling or consider removing")
    else:
        print(f"  \033[0;32m✓\033[0m  '{kw}' → {n} PE number(s)")
PY

ZERO=$(j "','.join(d['keywords_with_zero_hits'])")
if [ "$ZERO" != "" ]; then
  echo -e "      → see TODO(real-data) in _HYPERSONICS_KEYWORDS for candidate additions"
fi

# ── 6. Summary ────────────────────────────────────────────────────────────────
echo -e "\n${BLD}6. Summary${RST}"
SUB=$(j "d['summary']['total_sub_elements']")
PES=$(j "d['summary']['distinct_pe_numbers']")
YRS=$(j "str(d['summary']['active_fiscal_years'])")
OVERALL=$(j "d['summary']['overall_ok']")
echo -e "  Sub-elements: $SUB across $PES PE lines"
echo -e "  Active years: $YRS"
if [ "$OVERALL" = "True" ]; then
  echo -e "\n  ${GRN}${BLD}All checks passed.${RST}"
else
  echo -e "\n  ${YLW}${BLD}Some checks need attention (see above).${RST}"
fi
echo
