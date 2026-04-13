"""XLSX workbook generation for keyword-search exports.

Pure presentation layer — takes pre-built data structures and returns bytes.
No database queries or cache-building logic.
"""

from __future__ import annotations

import time
from typing import Any

from api.routes.keyword_helpers import (
    HIDDEN_LOOKUP_COL,
    SPILL_MAX_ROW,
    safe_json_list,
)

# ── Shared XLSX styles ───────────────────────────────────────────────────────


def xlsx_base_styles() -> dict[str, Any]:
    """Return xlsxwriter format property dicts for shared XLSX styling.

    Returns raw dicts — consumers call ``wb.add_format(props)`` to create
    workbook-bound Format objects (xlsxwriter formats are per-workbook).
    """
    return {
        "header": {
            "bold": True,
            "font_size": 11,
            "font_color": "#FFFFFF",
            "bg_color": "#2C3E50",
            "text_wrap": True,
            "align": "center",
        },
        "base": {"font_size": 10},
        "italic": {"italic": True, "font_color": "#888888", "font_size": 10},
        "total": {"bold": True, "font_size": 11},
        "source": {"font_size": 9, "font_color": "#666666", "valign": "top"},
        "desc": {"font_size": 9, "font_color": "#444444", "valign": "top"},
        "money_fmt": "$#,##0",
    }


# ── Shared XLSX workbook builder ─────────────────────────────────────────────

# Default column widths keyed by header name.
_COL_WIDTH_DEFAULTS: dict[str, int] = {
    "PE Number": 14,
    "Service/Org": 14,
    "Exhibit": 8,
    "Exhibit Type": 8,
    "Line Item / Sub-Program": 50,
    "Line Item Title": 50,
    "Budget Activity": 20,
    "Budget Activity (Normalized)": 20,
    "Appropriation": 30,
    "Color of Money": 12,
    "Alternate Titles": 40,
    "Keywords (Row)": 20,
    "Keywords (Desc)": 20,
    "Description": 60,
    "In Totals": 10,
}


def _col_letter(one_based: int) -> str:
    """Convert a 1-based column index to an Excel letter (1 → 'A')."""
    from xlsxwriter.utility import xl_col_to_name

    return xl_col_to_name(one_based - 1)


def _write_merged_fy_headers(
    ws: Any,
    fixed_columns: list[tuple[str, str]],
    active_years: list[int],
    fixed_count: int,
    sub_col_names: list[str],
    fmt_merge: Any,
    fmt_sub: Any,
) -> list[str]:
    """Write two-row merged FY headers and return the flat header list."""
    for ci, (h, _) in enumerate(fixed_columns):
        ws.merge_range(0, ci, 1, ci, h, fmt_merge)
    col = fixed_count
    for yr in active_years:
        if len(sub_col_names) > 1:
            ws.merge_range(
                0, col, 0, col + len(sub_col_names) - 1, f"FY{yr} ($K)", fmt_merge
            )
        else:
            ws.write(0, col, f"FY{yr} ($K)", fmt_merge)
        for si, sub in enumerate(sub_col_names):
            ws.write(1, col + si, sub, fmt_sub)
        col += len(sub_col_names)
    headers: list[str] = [h for h, _ in fixed_columns]
    for yr in active_years:
        for sub in sub_col_names:
            headers.append(f"FY{yr} {sub}" if sub != "($K)" else f"FY{yr} ($K)")
    return headers


def _set_fy_column_widths(
    ws: Any,
    fixed_columns: list[tuple[str, str]],
    fy_cols: list[Any],
    base_money_fmt: Any | None = None,
) -> None:
    """Set column widths for fixed columns and FY column groups."""
    for ci, (header, _field) in enumerate(fixed_columns):
        ws.set_column(ci, ci, _COL_WIDTH_DEFAULTS.get(header, 14))
    for fc in fy_cols:
        ws.set_column(fc.val - 1, fc.val - 1, 14, base_money_fmt)
        if fc.intotal:
            ws.set_column(fc.intotal - 1, fc.intotal - 1, 10)
        if fc.src:
            ws.set_column(fc.src - 1, fc.src - 1, 30)
        if fc.desc:
            ws.set_column(fc.desc - 1, fc.desc - 1, 40)
        if fc.desc_kw:
            ws.set_column(fc.desc_kw - 1, fc.desc_kw - 1, 25)


def _apply_fy_conditional_formatting(
    ws: Any,
    fy_cols: list[Any],
    intotal_letters: list[str],
    fixed_count: int,
    first_row: int,
    last_row: int,
    fmt: dict[str, Any],
) -> None:
    """Apply Y/N/P conditional formatting to FY columns and fixed columns."""
    for fc in fy_cols:
        data_cols = [fc.val - 1]
        if fc.src:
            data_cols.append(fc.src - 1)
        if fc.desc:
            data_cols.append(fc.desc - 1)
        for c0 in data_cols:
            ws.conditional_format(
                first_row,
                c0,
                last_row,
                c0,
                {
                    "type": "formula",
                    "criteria": f'=${fc.intotal_l}{first_row + 1}="Y"',
                    "format": fmt["cf_bold"],
                },
            )
            ws.conditional_format(
                first_row,
                c0,
                last_row,
                c0,
                {
                    "type": "formula",
                    "criteria": f'=${fc.intotal_l}{first_row + 1}="N"',
                    "format": fmt["cf_italic_gray"],
                },
            )
        if fc.intotal:
            ic0 = fc.intotal - 1
            for val, key in [("Y", "cf_green"), ("P", "cf_yellow"), ("N", "cf_red")]:
                ws.conditional_format(
                    first_row,
                    ic0,
                    last_row,
                    ic0,
                    {
                        "type": "formula",
                        "criteria": f'=${fc.intotal_l}{first_row + 1}="{val}"',
                        "format": fmt[key],
                    },
                )
    or_parts = ",".join(f'${lt}{first_row + 1}="Y"' for lt in intotal_letters)
    and_parts = ",".join(f'${lt}{first_row + 1}="N"' for lt in intotal_letters)
    ws.conditional_format(
        first_row,
        0,
        last_row,
        fixed_count - 1,
        {
            "type": "formula",
            "criteria": f"=OR({or_parts})",
            "format": fmt["cf_bold"],
        },
    )
    ws.conditional_format(
        first_row,
        0,
        last_row,
        fixed_count - 1,
        {
            "type": "formula",
            "criteria": f"=AND({and_parts})",
            "format": fmt["cf_italic_gray"],
        },
    )


def build_keyword_xlsx(
    items: list[dict],
    active_years: list[int],
    desc_by_pe_fy: dict[tuple[str, str], str],
    fixed_columns: list[tuple[str, str]],
    include_source: bool = True,
    include_description: bool = True,
    include_intotal: bool = True,
    include_desc_keywords: bool = True,
    sheet_title: str = "Results",
    build_summary: bool = True,
    keywords: list[str] | None = None,
    fy_desc_kws: dict[tuple[str, str], list[str]] | None = None,
    pe_has_r2_match: set[str] | None = None,
) -> bytes:
    """Build a keyword-search XLSX workbook and return it as bytes.

    Uses xlsxwriter for proper Excel 365 dynamic array formula support.
    Y/N/P is computed per-FY based on description keyword matches.
    """
    import io

    import xlsxwriter

    sty = xlsx_base_styles()
    money_fmt_str = sty["money_fmt"]
    fixed_count = len(fixed_columns)

    if fy_desc_kws is None:
        fy_desc_kws = {}
    if pe_has_r2_match is None:
        pe_has_r2_match = set()

    # Compute FY column stride and per-year column positions (1-based)
    fy_stride = (
        1
        + int(include_intotal)
        + int(include_source)
        + int(include_description)
        + int(include_desc_keywords)
    )

    class _FyCols:
        __slots__ = (
            "val",
            "intotal",
            "src",
            "desc",
            "desc_kw",
            "val_l",
            "intotal_l",
            "src_l",
            "desc_l",
            "desc_kw_l",
        )

        def __init__(self, fy_idx: int) -> None:
            base = fixed_count + (fy_idx * fy_stride) + 1
            col = base
            self.val = col
            col += 1
            self.intotal = col if include_intotal else 0
            if include_intotal:
                col += 1
            self.src = col if include_source else 0
            if include_source:
                col += 1
            self.desc = col if include_description else 0
            if include_description:
                col += 1
            self.desc_kw = col if include_desc_keywords else 0
            self.val_l = _col_letter(self.val)
            self.intotal_l = _col_letter(self.intotal) if self.intotal else ""
            self.src_l = _col_letter(self.src) if self.src else ""
            self.desc_l = _col_letter(self.desc) if self.desc else ""
            self.desc_kw_l = _col_letter(self.desc_kw) if self.desc_kw else ""

    fy_cols = [_FyCols(i) for i in range(len(active_years))]
    intotal_letters = [fc.intotal_l for fc in fy_cols if fc.intotal_l]

    # ── Build workbook ──
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    ws = wb.add_worksheet(sheet_title)

    # Create all Format objects once (xlsxwriter formats are workbook-bound)
    fmt = {
        "header": wb.add_format(sty["header"]),
        "base": wb.add_format(sty["base"]),
        "base_money": wb.add_format({**sty["base"], "num_format": money_fmt_str}),
        "total": wb.add_format(sty["total"]),
        "total_money": wb.add_format({**sty["total"], "num_format": money_fmt_str}),
        "source": wb.add_format(sty["source"]),
        "desc": wb.add_format(sty["desc"]),
        "cf_bold": wb.add_format({"bold": True}),
        "cf_italic_gray": wb.add_format({"italic": True, "font_color": "#888888"}),
        "cf_green": wb.add_format({"bg_color": "#C6EFCE"}),
        "cf_yellow": wb.add_format({"bg_color": "#FFEB9C"}),
        "cf_red": wb.add_format({"bg_color": "#FFC7CE"}),
    }

    # ── Headers: two-row layout with merged FY cells ──
    fmt_merge = wb.add_format(
        {
            "bold": True,
            "font_size": 11,
            "font_color": "#FFFFFF",
            "bg_color": "#2C3E50",
            "align": "center",
            "valign": "vcenter",
            "border": 1,
        }
    )
    fmt_sub = wb.add_format(
        {
            "bold": True,
            "font_size": 10,
            "font_color": "#FFFFFF",
            "bg_color": "#34495E",
            "align": "center",
            "border": 1,
        }
    )

    sub_col_names = ["($K)"]
    if include_intotal:
        sub_col_names.append("In Total")
    if include_source:
        sub_col_names.append("Source")
    if include_description:
        sub_col_names.append("Description")
    if include_desc_keywords:
        sub_col_names.append("Keywords")

    headers = _write_merged_fy_headers(
        ws,
        fixed_columns,
        active_years,
        fixed_count,
        sub_col_names,
        fmt_merge,
        fmt_sub,
    )

    # ── Data rows (row_num is 1-based for formula references, data starts row 3) ──
    first_data_row = 3
    row_num = first_data_row
    for row in items:
        r0 = row_num - 1  # 0-indexed for ws.write
        pe = row.get("pe_number", "")
        et = row.get("exhibit_type", "")

        for ci, (_header, field) in enumerate(fixed_columns):
            val = row.get(field, "")
            if isinstance(val, list):
                val = ", ".join(val)
            ws.write(r0, ci, val if val is not None else "", fmt["base"])

        refs_map = row.get("refs", {}) or {}

        # Pass 1: compute Y/N/P per FY
        fy_codes: list[str] = []
        if include_intotal:
            # Only row-level title/field matches count as direct hits.
            # matched_keywords_desc is PE-level (set on all rows in a PE)
            # and is too broad for Y/N/P — it feeds the Desc Keywords column instead.
            has_row_kw = bool(row.get("matched_keywords_row"))
            for fi, yr in enumerate(active_years):
                amount = row.get(f"fy{yr}")
                has_src = bool(refs_map.get(f"fy{yr}"))
                if amount is None or (amount == 0 and not has_src):
                    fy_codes.append("")
                    continue
                has_fy_kw = (pe, str(yr)) in fy_desc_kws
                has_match = has_row_kw or has_fy_kw
                if not has_match:
                    fy_codes.append("N")
                elif et == "r1" and pe in pe_has_r2_match:
                    # R1 is summary — cap at P when R2 subs have matches
                    # to avoid double-counting (R1 total includes R2 dollars)
                    fy_codes.append("P")
                else:
                    fy_codes.append("Y")
            # If any FY is Y, promote remaining N's to P (but leave blanks alone)
            if "Y" in fy_codes:
                fy_codes = ["P" if c == "N" else c for c in fy_codes]

        # Pass 2: write all FY columns
        for fi, yr in enumerate(active_years):
            fc = fy_cols[fi]

            amount = row.get(f"fy{yr}")
            has_source = bool(refs_map.get(f"fy{yr}"))
            # Skip $0 with no source — likely an artifact, not real data
            if amount is not None and (amount != 0 or has_source):
                ws.write_number(r0, fc.val - 1, amount, fmt["base_money"])

            if fc.intotal and fy_codes[fi]:
                ws.write(r0, fc.intotal - 1, fy_codes[fi], fmt["base"])

            if fc.src:
                source_ref = refs_map.get(f"fy{yr}", "")
                if source_ref:
                    ws.write(r0, fc.src - 1, source_ref, fmt["source"])

            if fc.desc:
                desc_text = desc_by_pe_fy.get((pe, str(yr)), "")
                if desc_text:
                    ws.write(r0, fc.desc - 1, desc_text, fmt["desc"])

            if fc.desc_kw:
                kws = fy_desc_kws.get((pe, str(yr)), [])
                ws.write(r0, fc.desc_kw - 1, ", ".join(kws) if kws else "", fmt["base"])

        row_num += 1

    last_data_row = row_num - 1

    # ── Data validation (Y/N/P dropdown) ──
    if include_intotal and last_data_row >= first_data_row:
        for fc in fy_cols:
            ws.data_validation(
                first_data_row - 1,
                fc.intotal - 1,
                last_data_row - 1,
                fc.intotal - 1,
                {
                    "validate": "list",
                    "source": ["Y", "N", "P"],
                    "error_message": "Please enter Y, N, or P",
                    "error_title": "Invalid value",
                },
            )

    # ── Conditional formatting ──
    if include_intotal and last_data_row >= first_data_row and active_years:
        _apply_fy_conditional_formatting(
            ws,
            fy_cols,
            intotal_letters,
            fixed_count,
            first_data_row - 1,
            last_data_row - 1,
            fmt,
        )

    # ── Totals rows ──
    if include_intotal and last_data_row >= first_data_row and active_years:
        y_row, p_row, grand_row = row_num, row_num + 1, row_num + 2
        ws.write(y_row - 1, 0, "Y TOTALS", fmt["total"])
        ws.write(p_row - 1, 0, "P TOTALS", fmt["total"])
        ws.write(grand_row - 1, 0, "GRAND TOTAL", fmt["total"])
        for fc in fy_cols:
            val_rng = f"${fc.val_l}${first_data_row}:${fc.val_l}${last_data_row}"
            it_rng = f"${fc.intotal_l}${first_data_row}:${fc.intotal_l}${last_data_row}"
            for tr, label, criteria in [(y_row, "Y Sum", "Y"), (p_row, "P Sum", "P")]:
                ws.write(tr - 1, fc.intotal - 1, label, fmt["total"])
                ws.write_formula(
                    tr - 1,
                    fc.val - 1,
                    f'=SUMIF({it_rng},"{criteria}",{val_rng})',
                    fmt["total_money"],
                )
            ws.write(grand_row - 1, fc.intotal - 1, "Grand Sum", fmt["total"])
            ws.write_formula(
                grand_row - 1,
                fc.val - 1,
                f"={fc.val_l}{y_row}+{fc.val_l}{p_row}",
                fmt["total_money"],
            )
    elif last_data_row >= first_data_row and active_years:
        totals_row = row_num
        ws.write(totals_row - 1, 0, "TOTALS", fmt["total"])
        for fc in fy_cols:
            vr = f"${fc.val_l}${first_data_row}:${fc.val_l}${last_data_row}"
            ws.write_formula(
                totals_row - 1, fc.val - 1, f"=SUM({vr})", fmt["total_money"]
            )

    # ── Column widths ──
    _set_fy_column_widths(ws, fixed_columns, fy_cols)

    freeze_col = min(5, fixed_count + 1)
    ws.freeze_panes(2, freeze_col - 1)
    ws.autofilter(1, 0, max(last_data_row, row_num) - 1, len(headers) - 1)

    # ── Selected sheet (dynamic FILTER of data sheet, Y or P rows only) ──
    if include_intotal and last_data_row >= first_data_row and active_years:
        ws_sel = wb.add_worksheet("Selected")

        _write_merged_fy_headers(
            ws_sel,
            fixed_columns,
            active_years,
            fixed_count,
            sub_col_names,
            fmt_merge,
            fmt_sub,
        )

        # FILTER formula: show rows where ANY In Total column = "Y" or "P"
        data_range = f"'{sheet_title}'!$A${first_data_row}:${_col_letter(len(headers))}${last_data_row}"
        it_checks = []
        for fc in fy_cols:
            if fc.intotal:
                it_col = f"'{sheet_title}'!${fc.intotal_l}${first_data_row}:${fc.intotal_l}${last_data_row}"
                it_checks.append(f'({it_col}="Y")+({it_col}="P")')
        filter_crit = "+".join(it_checks)
        filter_formula = f'=FILTER({data_range},{filter_crit},"No matching rows")'
        ws_sel.write_dynamic_array_formula(2, 0, 2, 0, filter_formula, fmt["base"])

        _set_fy_column_widths(
            ws_sel, fixed_columns, fy_cols, base_money_fmt=fmt["base_money"]
        )
        if intotal_letters and last_data_row >= first_data_row:
            _apply_fy_conditional_formatting(
                ws_sel,
                fy_cols,
                intotal_letters,
                fixed_count,
                2,
                SPILL_MAX_ROW,
                fmt,
            )

        ws_sel.freeze_panes(2, freeze_col - 1)

    # ── Summary sheets ──
    if build_summary and include_intotal:
        field_to_col = {
            field: _col_letter(ci) for ci, (_h, field) in enumerate(fixed_columns, 1)
        }
        val_letters = [fc.val_l for fc in fy_cols]
        it_letters = [fc.intotal_l for fc in fy_cols]
        _build_xlsx_summary(
            wb,
            items,
            active_years,
            sheet_title,
            field_to_col,
            val_letters,
            it_letters,
            first_data_row,
            last_data_row,
            fmt,
            keywords=keywords,
            fmt_merge=fmt_merge,
            fmt_sub=fmt_sub,
        )

    # ── Keyword co-occurrence matrix ──
    if keywords and len(keywords) > 1:
        _build_keyword_matrix(wb, items, keywords, fmt)

    wb.close()
    return buf.getvalue()


def _build_xlsx_summary(
    wb: Any,
    items: list[dict],
    active_years: list[int],
    data_sheet_name: str,
    field_to_col: dict[str, str],
    val_letters: list[str],
    intotal_letters: list[str],
    first_data_row: int,
    last_data_row: int,
    fmt: dict[str, Any] | None = None,
    keywords: list[str] | None = None,
    fmt_merge: Any | None = None,
    fmt_sub: Any | None = None,
) -> None:
    """Build dynamic Summary sheets using xlsxwriter spill formulas.

    Creates PE Summary, dimension breakdowns (By Service, etc.), Keyword Matrix
    (if keywords provided), and an About sheet with methodology documentation.
    """
    ds = data_sheet_name
    pe_col = field_to_col.get("pe_number", "A")
    n_years = len(active_years)

    pr = f"'{ds}'!${pe_col}${first_data_row}:${pe_col}${last_data_row}"
    vr = [
        f"'{ds}'!${val_letters[yi]}${first_data_row}:${val_letters[yi]}${last_data_row}"
        for yi in range(n_years)
    ]
    ir = [
        f"'{ds}'!${intotal_letters[yi]}${first_data_row}:${intotal_letters[yi]}${last_data_row}"
        for yi in range(n_years)
    ]

    if fmt is None:
        sty = xlsx_base_styles()
        fmt = {
            "header": wb.add_format(sty["header"]),
            "base": wb.add_format(sty["base"]),
            "base_money": wb.add_format(
                {**sty["base"], "num_format": sty["money_fmt"]}
            ),
            "total": wb.add_format(sty["total"]),
            "total_money": wb.add_format(
                {**sty["total"], "num_format": sty["money_fmt"]}
            ),
        }

    # Pre-compute PE→title map for PE Summary sheet (single pass, R-1 wins)
    pe_titles: dict[str, str] = {}
    for row in items:
        pe = row.get("pe_number", "")
        if not pe:
            continue
        if row.get("exhibit_type") == "r1" and row.get("line_item_title"):
            pe_titles[pe] = row["line_item_title"]
        elif pe not in pe_titles:
            pe_titles[pe] = row.get("line_item_title", pe)

    # Reuse caller's format objects if provided; create fallbacks otherwise
    if fmt_merge is None:
        fmt_merge = wb.add_format(
            {
                "bold": True,
                "font_size": 11,
                "font_color": "#FFFFFF",
                "bg_color": "#2C3E50",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
    if fmt_sub is None:
        fmt_sub = wb.add_format(
            {
                "bold": True,
                "font_size": 10,
                "font_color": "#FFFFFF",
                "bg_color": "#34495E",
                "align": "center",
                "border": 1,
            }
        )

    def _write_summary_sheet(
        sheet_name: str,
        label_col: str = "PE Number",
        match_rng: str | None = None,
        include_title: bool = False,
    ) -> None:
        """Write a summary sheet with merged FY headers and Y/P/Total column groups.

        Layout:
        Row 0: Label | (PE Title) |    FY2024 ($K)     |    FY2025 ($K)     |      Row Total      |
        Row 1:       |            |  Y  |  P  | Total  |  Y  |  P  | Total  |  Y  |  P  | Total  |
        Row 2: Total |            | $xx | $xx |  $xx   | ... (SUMPRODUCT)   | $xx | $xx |  $xx   |
        Row 3+: (spill data)
        """
        ws = wb.add_worksheet(sheet_name)
        mr = match_rng or pr
        unique_expr = f"SORT(UNIQUE({mr}))"

        sumifs_y_all = "+".join(
            f'SUMIFS({vr[yi]},{mr},_xlpm.v,{ir[yi]},"Y")' for yi in range(n_years)
        )
        sumifs_p_all = "+".join(
            f'SUMIFS({vr[yi]},{mr},_xlpm.v,{ir[yi]},"P")' for yi in range(n_years)
        )
        filtered = (
            f"FILTER({unique_expr},"
            f"MAP({unique_expr},LAMBDA(_xlpm.v,{sumifs_y_all}+{sumifs_p_all}))<>0,"
            f'"(none)")'
        )

        # Column A: label (PE Number or dimension name)
        col = 0
        ws.merge_range(0, col, 1, col, label_col, fmt_merge)
        ws.write(2, col, "Total", fmt["total"])
        ws.write_dynamic_array_formula(3, col, 3, col, f"={filtered}", fmt["base"])
        ws.set_column(col, col, 16, fmt["base"])
        col += 1

        # Column B: PE Title (only for PE Summary)
        if include_title:
            ws.merge_range(0, col, 1, col, "PE Title", fmt_merge)
            ws.write(2, col, "", fmt["total"])
            # Write PE→title lookup table in far-right columns (ZA/ZB)
            lk_col_pe = HIDDEN_LOOKUP_COL
            lk_col_title = 201
            for ti, (pe, title) in enumerate(sorted(pe_titles.items())):
                ws.write(ti, lk_col_pe, pe)
                ws.write(ti, lk_col_title, title)
            lk_count = len(pe_titles)
            # INDEX/MATCH formula to look up title from PE in column A
            pe_lk = f"${_col_letter(lk_col_pe + 1)}$1:${_col_letter(lk_col_pe + 1)}${lk_count}"
            ti_lk = f"${_col_letter(lk_col_title + 1)}$1:${_col_letter(lk_col_title + 1)}${lk_count}"
            ws.write_dynamic_array_formula(
                3,
                col,
                3,
                col,
                f"=MAP({filtered},LAMBDA(_xlpm.v,IFERROR(INDEX({ti_lk},MATCH(_xlpm.v,{pe_lk},0)),_xlpm.v)))",
                fmt["base"],
            )
            ws.set_column(col, col, 40, fmt["base"])
            # Hide lookup columns
            ws.set_column(lk_col_pe, lk_col_title, None, None, {"hidden": True})
            col += 1

        # FY year groups: each gets 3 columns (Y, P, Total) with merged header
        row_tot_y = []
        row_tot_p = []

        for yi in range(n_years):
            yr = active_years[yi]

            # Merged FY header across 3 columns
            ws.merge_range(0, col, 0, col + 2, f"FY{yr} ($K)", fmt_merge)

            for ci, (sub_label, crit) in enumerate(
                [("Y", "Y"), ("P", "P"), ("Total", None)]
            ):
                c = col + ci
                ws.write(1, c, sub_label, fmt_sub)

                if crit:
                    ws.write_formula(
                        2,
                        c,
                        f'=SUMPRODUCT(({ir[yi]}="{crit}")*{vr[yi]})',
                        fmt["total_money"],
                    )
                    formula = (
                        f"=MAP({filtered},"
                        f'LAMBDA(_xlpm.v,SUMIFS({vr[yi]},{mr},_xlpm.v,{ir[yi]},"{crit}")))'
                    )
                    if crit == "Y":
                        row_tot_y.append(f'SUMIFS({vr[yi]},{mr},_xlpm.v,{ir[yi]},"Y")')
                    else:
                        row_tot_p.append(f'SUMIFS({vr[yi]},{mr},_xlpm.v,{ir[yi]},"P")')
                else:
                    ws.write_formula(
                        2,
                        c,
                        f'=SUMPRODUCT(({ir[yi]}="Y")*{vr[yi]})+SUMPRODUCT(({ir[yi]}="P")*{vr[yi]})',
                        fmt["total_money"],
                    )
                    formula = (
                        f"=MAP({filtered},"
                        f"LAMBDA(_xlpm.v,"
                        f'SUMIFS({vr[yi]},{mr},_xlpm.v,{ir[yi]},"Y")'
                        f'+SUMIFS({vr[yi]},{mr},_xlpm.v,{ir[yi]},"P")))'
                    )

                ws.write_dynamic_array_formula(3, c, 3, c, formula, fmt["base_money"])
                ws.set_column(
                    c, c, 14, fmt["base_money"]
                )  # default format for spill rows

            col += 3

        # Row Total group: Y, P, Total (same 3-column pattern)
        ws.merge_range(0, col, 0, col + 2, "Row Total ($K)", fmt_merge)

        for ci, (sub_label, parts_y, parts_p) in enumerate(
            [
                ("Y", row_tot_y, []),
                ("P", [], row_tot_p),
                ("Total", row_tot_y, row_tot_p),
            ]
        ):
            c = col + ci
            ws.write(1, c, sub_label, fmt_sub)

            if sub_label == "Y":
                sp = "+".join(
                    f'SUMPRODUCT(({ir[yi]}="Y")*{vr[yi]})' for yi in range(n_years)
                )
                sumifs = "+".join(parts_y)
            elif sub_label == "P":
                sp = "+".join(
                    f'SUMPRODUCT(({ir[yi]}="P")*{vr[yi]})' for yi in range(n_years)
                )
                sumifs = "+".join(parts_p)
            else:
                sp = "+".join(
                    f'SUMPRODUCT(({ir[yi]}="Y")*{vr[yi]})+SUMPRODUCT(({ir[yi]}="P")*{vr[yi]})'
                    for yi in range(n_years)
                )
                sumifs = "+".join(row_tot_y) + "+" + "+".join(row_tot_p)

            ws.write_formula(2, c, f"={sp}", fmt["total_money"])
            ws.write_dynamic_array_formula(
                3,
                c,
                3,
                c,
                f"=MAP({filtered},LAMBDA(_xlpm.v,{sumifs}))",
                fmt["base_money"],
            )
            ws.set_column(c, c, 14, fmt["base_money"])

        ws.freeze_panes(3, 1)

    # PE Summary (with title column)
    _write_summary_sheet("PE Summary", include_title=True)

    # Dimension summaries
    svc_col = field_to_col.get("organization_name")
    ba_col = field_to_col.get("budget_activity_norm") or field_to_col.get(
        "budget_activity_title"
    )
    com_col = field_to_col.get("color_of_money")

    for sheet_name, label, dcol in [
        ("By Service", "Service/Agency", svc_col),
        ("By Budget Activity", "Budget Activity", ba_col),
        ("By Color of Money", "Color of Money", com_col),
    ]:
        if not dcol:
            continue  # dimension column not in selected columns
        dim_rng = f"'{ds}'!${dcol}${first_data_row}:${dcol}${last_data_row}"
        _write_summary_sheet(sheet_name, label_col=label, match_rng=dim_rng)

    _build_xlsx_about_sheet(wb, items, ds, keywords)


def _build_xlsx_about_sheet(
    wb: Any,
    items: list[dict],
    data_sheet_name: str,
    keywords: list[str] | None,
) -> None:
    """Write an About sheet documenting the export methodology."""

    ws = wb.add_worksheet("About")
    fmt_title = wb.add_format({"bold": True, "font_size": 14})
    fmt_section = wb.add_format({"bold": True, "font_size": 12, "bottom": 1})
    fmt_label = wb.add_format({"bold": True, "font_size": 10, "valign": "top"})
    fmt_text = wb.add_format({"font_size": 10, "text_wrap": True, "valign": "top"})

    r = 0
    ws.write(r, 0, "DoD Budget Explorer \u2014 Export Documentation", fmt_title)
    r += 1
    ws.write(r, 0, "Generated", fmt_label)
    ws.write(r, 1, time.strftime("%Y-%m-%d %H:%M:%S"), fmt_text)
    r += 2

    ws.write(r, 0, "Search Parameters", fmt_section)
    r += 1
    ws.write(r, 0, "Keywords", fmt_label)
    ws.write(r, 1, ", ".join(keywords) if keywords else "(none)", fmt_text)
    r += 1
    ws.write(r, 0, "Total rows", fmt_label)
    ws.write(r, 1, len(items), fmt_text)
    r += 1
    matching = sum(
        1
        for row in items
        if row.get("matched_keywords_row") or row.get("matched_keywords_desc")
    )
    ws.write(r, 0, "Matching rows", fmt_label)
    ws.write(r, 1, matching, fmt_text)
    r += 1
    unique_pe_count = len(
        {row.get("pe_number") for row in items if row.get("pe_number")}
    )
    ws.write(r, 0, "Unique PEs", fmt_label)
    ws.write(r, 1, unique_pe_count, fmt_text)
    r += 2

    ws.write(r, 0, "Data Source", fmt_section)
    r += 1
    ws.write(
        r,
        0,
        "DoD Comptroller budget justification documents: Excel R-1/R-2 exhibits "
        "and PDF-mined R-2/R-2A sub-element pages. All amounts in thousands of dollars ($K).",
        fmt_text,
    )
    r += 2

    ws.write(r, 0, "Y/N/P Methodology", fmt_section)
    r += 1
    ws.write(r, 0, "Y (Yes)", fmt_label)
    ws.write(
        r,
        1,
        "Row directly matches one or more search keywords. Included in Y totals.",
        fmt_text,
    )
    r += 1
    ws.write(r, 0, "N (No)", fmt_label)
    ws.write(
        r,
        1,
        "Row included for PE context but does not directly match keywords. Excluded from totals.",
        fmt_text,
    )
    r += 1
    ws.write(r, 0, "P (Possible)", fmt_label)
    ws.write(
        r,
        1,
        "User-assigned flag for rows that may be relevant. Change N\u2192P in the data sheet "
        "and the summary sheets will update automatically.",
        fmt_text,
    )
    r += 2

    ws.write(r, 0, "Sheet Descriptions", fmt_section)
    r += 1
    sheets_desc = [
        (
            data_sheet_name,
            "Raw data with per-year In Total (Y/N/P) flags, conditional formatting, "
            "and data validation. Change flags here to update all summary sheets.",
        ),
        (
            "PE Summary",
            "Pivot by Program Element. Shows only PEs with non-zero Y+P totals. "
            "Includes PE title lookup. Columns: Y/P/Total per fiscal year.",
        ),
        ("By Service", "Pivot by Service/Agency (Army, Navy, Air Force, etc.)."),
        ("By Budget Activity", "Pivot by Budget Activity category."),
        (
            "By Color of Money",
            "Pivot by appropriation type (RDT&E, Procurement, etc.).",
        ),
        (
            "Keyword Matrix",
            "NxN co-occurrence table showing how often each pair of search "
            "keywords appears together in the same row.",
        ),
    ]
    for sname, sdesc in sheets_desc:
        ws.write(r, 0, sname, fmt_label)
        ws.write(r, 1, sdesc, fmt_text)
        r += 1
    r += 1

    ws.write(r, 0, "Caveats", fmt_section)
    r += 1
    caveats = [
        "PDF-mined rows (exhibit_type='r2_pdf') may show 'Unknown' for Budget Activity and Color of Money.",
        "Amounts are in thousands of dollars ($K). Multiply by 1,000 for actual dollar values.",
        "Non-matching rows (N) are included because their parent PE matched a keyword. "
        "They provide context but are excluded from Y totals.",
        "Summary sheets use Excel 365 dynamic array formulas (FILTER, MAP, LAMBDA). "
        "They require Microsoft 365 or Excel 2021+.",
    ]
    for caveat in caveats:
        ws.write(r, 0, "\u2022 " + caveat, fmt_text)
        r += 1

    ws.set_column(0, 0, 20)
    ws.set_column(1, 1, 80)


def _build_keyword_matrix(
    wb: Any,
    items: list[dict],
    keywords: list[str],
    fmt: dict[str, Any] | None = None,
) -> None:
    """Build a keyword co-occurrence matrix sheet.

    Shows an NxN table: cell (i,j) = number of rows where keyword i AND keyword j
    both appear. Diagonal = total rows matching that keyword alone.
    """
    if fmt is None:
        sty = xlsx_base_styles()
        fmt = {
            "header": wb.add_format(sty["header"]),
            "base": wb.add_format(sty["base"]),
            "total": wb.add_format(sty["total"]),
        }

    ws = wb.add_worksheet("Keyword Matrix")

    fmt_header_rot = wb.add_format(
        {
            "bold": True,
            "font_size": 11,
            "font_color": "#FFFFFF",
            "bg_color": "#2C3E50",
            "align": "center",
            "rotation": 90,
        }
    )
    fmt_center = wb.add_format({"font_size": 10, "align": "center"})
    fmt_diag = wb.add_format(
        {"bold": True, "font_size": 11, "bg_color": "#D6E4F0", "align": "center"}
    )

    kw_lower = [kw.lower() for kw in keywords]
    kw_display = list(keywords)

    row_kw_sets: list[set[str]] = []
    for row in items:
        kws_r = safe_json_list(row.get("matched_keywords_row", []))
        kws_d = safe_json_list(row.get("matched_keywords_desc", []))
        combined = {k.lower() for k in kws_r} | {k.lower() for k in kws_d}
        if combined:
            row_kw_sets.append(combined)

    n = len(kw_lower)
    matrix = [[0] * n for _ in range(n)]
    for kw_set in row_kw_sets:
        present = [i for i in range(n) if kw_lower[i] in kw_set]
        for i in present:
            for j in present:
                matrix[i][j] += 1

    active = [i for i in range(n) if matrix[i][i] > 0]
    if not active:
        ws.write(0, 0, "No keyword matches found.", fmt["base"])
        return

    ws.write(0, 0, "Keyword", fmt["header"])
    for ci, idx in enumerate(active):
        ws.write(0, 1 + ci, kw_display[idx], fmt_header_rot)
    ws.write(0, 1 + len(active), "Total", fmt["header"])

    for ri, idx_i in enumerate(active):
        ws.write(1 + ri, 0, kw_display[idx_i], fmt["base"])
        for ci, idx_j in enumerate(active):
            val = matrix[idx_i][idx_j]
            cell_fmt = fmt_diag if idx_i == idx_j else fmt_center
            ws.write(1 + ri, 1 + ci, val if val > 0 else "", cell_fmt)
        ws.write(1 + ri, 1 + len(active), matrix[idx_i][idx_i], fmt["total"])

    ws.set_column(0, 0, 28)
    ws.set_column(1, len(active) + 1, 6)
    ws.freeze_panes(1, 1)
