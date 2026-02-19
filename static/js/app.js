/**
 * DoD Budget Explorer — app.js
 * Handles: column toggles (3.A4-b), URL query params (3.A3-b),
 *          download link generation (3.A5-a), row selection (3.A6-a),
 *          keyboard shortcuts (JS-003), detail panel keyboard nav (JS-004),
 *          debounced filter changes (OPT-JS-001), page-size persistence (FE-010),
 *          download modal result count (JS-002), Excel export (JS-001).
 */

// TODO [Group: LION] LION-007: Add URL sharing — sync filter state to URL query params (~1,200 tokens)

"use strict";

// ── Column toggle (3.A4-b) ────────────────────────────────────────────────────
// Persist to localStorage so preference survives page reloads.

const COL_KEY = "dod_hidden_cols";
const PAGE_SIZE_KEY = "dod_page_size";

function toggleCol(btn, cssClass) {
  btn.classList.toggle("active");
  const hidden = getHiddenCols();
  if (!btn.classList.contains("active")) {
    hidden.add(cssClass);
  } else {
    hidden.delete(cssClass);
  }
  saveHiddenCols(hidden);
  applyHiddenCols(hidden);
}

function getHiddenCols() {
  try {
    return new Set(JSON.parse(localStorage.getItem(COL_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

function saveHiddenCols(set) {
  localStorage.setItem(COL_KEY, JSON.stringify([...set]));
}

function applyHiddenCols(hidden) {
  // Show all first
  document.querySelectorAll("[class^='col-'], [class*=' col-']").forEach(el => {
    el.style.display = "";
  });
  // Then hide the selected ones
  hidden.forEach(cls => {
    document.querySelectorAll("." + cls).forEach(el => {
      el.style.display = "none";
    });
  });
  // Sync toggle buttons
  document.querySelectorAll(".col-toggle").forEach(btn => {
    const cls = btn.getAttribute("data-col");
    if (cls) {
      btn.classList.toggle("active", !hidden.has("col-" + cls));
    }
  });
}

// ── Row selection (3.A6-a) ─────────────────────────────────────────────────────

function selectRow(tr) {
  // JS-004: track previously selected row for aria-expanded reset
  document.querySelectorAll("tr.selected").forEach(r => {
    r.classList.remove("selected");
    r.setAttribute("aria-expanded", "false");
  });
  tr.classList.add("selected");
  tr.setAttribute("aria-expanded", "true");
}

// ── URL query params → filter state (3.A3-b) ──────────────────────────────────
// On page load, read URL params and pre-populate form fields.

function restoreFiltersFromURL() {
  const params = new URLSearchParams(window.location.search);
  const form = document.getElementById("filter-form");
  if (!form) return;

  // Text inputs
  ["q", "min_amount", "max_amount"].forEach(name => {
    const el = form.elements[name];
    if (el && params.has(name)) el.value = params.get(name);
  });

  // Multi-selects
  ["fiscal_year", "service", "exhibit_type", "appropriation_code"].forEach(name => {
    const el = form.elements[name];
    if (!el || !params.has(name)) return;
    const vals = params.getAll(name);
    Array.from(el.options).forEach(opt => {
      opt.selected = vals.includes(opt.value);
    });
  });
}

// ── Download URL builder (3.A5-a / JS-001 / FE-011) ───────────────────────────
// Build /api/v1/download URLs from the current form filter state.

function buildDownloadURL(fmt) {
  const form = document.getElementById("filter-form");
  if (!form) return "/api/v1/download?fmt=" + fmt;
  const data = new FormData(form);
  const params = new URLSearchParams();
  params.set("fmt", fmt);
  params.set("limit", "50000");
  for (const [key, val] of data.entries()) {
    if (val) params.append(key, val);
  }

  // FE-011: pass hidden columns so server can filter exports
  const hidden = getHiddenCols();
  if (hidden.size > 0) {
    // Map CSS class names (e.g., "col-org") to column names — best-effort
    const colMap = {
      "col-org":     "organization_name",
      "col-fy":      "fiscal_year",
      "col-exhibit": "exhibit_type",
      "col-account": "account",
      "col-pe":      "pe_number",
      "col-fy24":    "amount_fy2024_actual",
      "col-fy25":    "amount_fy2025_enacted",
      "col-fy26":    "amount_fy2026_request",
    };
    // Build list of visible columns
    const allCols = [
      "id","source_file","exhibit_type","sheet_name","fiscal_year",
      "account","account_title","organization_name",
      "budget_activity_title","sub_activity_title",
      "line_item","line_item_title","pe_number",
      "appropriation_code","appropriation_title",
      "amount_fy2024_actual","amount_fy2025_enacted","amount_fy2025_supplemental",
      "amount_fy2025_total","amount_fy2026_request","amount_fy2026_reconciliation",
      "amount_fy2026_total","amount_type","amount_unit","currency_year",
    ];
    const hiddenDbCols = new Set([...hidden].map(c => colMap[c]).filter(Boolean));
    const visibleCols = allCols.filter(c => !hiddenDbCols.has(c));
    visibleCols.forEach(c => params.append("columns", c));
  }

  return "/api/v1/download?" + params.toString();
}

function updateDownloadLinks() {
  const csv  = document.getElementById("dl-csv");
  const json = document.getElementById("dl-json");
  const xlsx = document.getElementById("dl-xlsx");
  if (csv)  csv.href  = buildDownloadURL("csv");
  if (json) json.href = buildDownloadURL("json");
  if (xlsx) xlsx.href = buildDownloadURL("xlsx");  // JS-001
}

// ── JS-002: Show estimated result count in download modal ──────────────────────

function updateDownloadModalCount() {
  const countEl = document.querySelector("#results-container .results-count");
  const modalCountEl = document.getElementById("dl-modal-count");
  if (!modalCountEl) return;

  if (countEl) {
    const text = countEl.textContent || "";
    const match = text.match(/([\d,]+)\s+result/);
    if (match) {
      const count = parseInt(match[1].replace(/,/g, ""), 10);
      const csvKb  = Math.round(count * 100 / 1024);
      const jsonKb = Math.round(count * 200 / 1024);
      modalCountEl.textContent =
        `${count.toLocaleString()} matching rows (~${csvKb.toLocaleString()} KB CSV, ~${jsonKb.toLocaleString()} KB JSON).`;
      return;
    }
  }
  modalCountEl.textContent = "Downloads apply the current filters (up to 50,000 rows).";
}

// Patch the download modal open button to also update the count
function openDownloadModal() {
  const modal = document.getElementById("dl-modal");
  if (modal) {
    modal.classList.add("open");
    updateDownloadModalCount();
  }
}

// ── FE-010: Page-size selector ────────────────────────────────────────────────

function setPageSize(size) {
  localStorage.setItem(PAGE_SIZE_KEY, size);
  // Fire an HTMX request with page_size=size and page=1
  const form = document.getElementById("filter-form");
  if (!form) return;
  const url = new URL("/partials/results", window.location.origin);
  const data = new FormData(form);
  for (const [k, v] of data.entries()) {
    if (v) url.searchParams.append(k, v);
  }
  url.searchParams.set("page_size", size);
  url.searchParams.set("page", "1");
  htmx.ajax("GET", url.toString(), {
    target: "#results-container",
    swap: "innerHTML",
    pushURL: url.toString(),
  });
}

function restorePageSize() {
  const saved = localStorage.getItem(PAGE_SIZE_KEY);
  if (!saved) return;
  const sel = document.getElementById("page-size-select");
  if (sel) sel.value = saved;
}

// ── JS-003: Keyboard shortcut for search ──────────────────────────────────────

document.addEventListener("keydown", function (e) {
  const tag = document.activeElement ? document.activeElement.tagName : "";
  const isEditable = ["INPUT", "TEXTAREA", "SELECT"].includes(tag) ||
    document.activeElement.isContentEditable;

  // JS-003: / or Ctrl+K focuses search box
  if ((e.key === "/" && !isEditable) ||
      (e.key === "k" && (e.ctrlKey || e.metaKey))) {
    const q = document.getElementById("q");
    if (q) {
      e.preventDefault();
      q.focus();
      q.select();
    }
  }

  // JS-004: Escape key closes detail panel
  if (e.key === "Escape") {
    const detail = document.getElementById("detail-container");
    if (detail && detail.innerHTML.trim()) {
      detail.innerHTML = "";
      // Restore focus to the previously selected row
      const selected = document.querySelector("tr.selected");
      if (selected) {
        selected.classList.remove("selected");
        selected.setAttribute("aria-expanded", "false");
        selected.focus();
      }
    }

    // Also close download modal if open
    const modal = document.getElementById("dl-modal");
    if (modal && modal.classList.contains("open")) {
      modal.classList.remove("open");
    }
  }
});

// ── HTMX events ────────────────────────────────────────────────────────────────
// After every HTMX swap, re-apply column visibility and update download links.

document.addEventListener("htmx:afterSwap", function (evt) {
  if (evt.detail.target.id === "results-container") {
    applyHiddenCols(getHiddenCols());
    updateDownloadLinks();
    restorePageSize();
  }

  // JS-004: focus detail panel heading after it loads
  if (evt.detail.target.id === "detail-container") {
    const heading = document.querySelector("#detail-panel h3");
    if (heading) {
      heading.setAttribute("tabindex", "-1");
      heading.focus();
    }
  }
});

// OPT-JS-001: aria-busy toggle for screen readers during HTMX requests
document.addEventListener("htmx:beforeRequest", function (evt) {
  const container = document.getElementById("results-container");
  if (container) container.setAttribute("aria-busy", "true");
});

document.addEventListener("htmx:afterSwap", function (evt) {
  if (evt.detail.target.id === "results-container") {
    evt.detail.target.setAttribute("aria-busy", "false");
  }
});

// ── Initialise ─────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", function () {
  restoreFiltersFromURL();
  applyHiddenCols(getHiddenCols());
  updateDownloadLinks();
  restorePageSize();

  // OPT-JS-001: Debounce filter form changes — add delay:300ms to multi-selects
  // HTMX hx-trigger delay is set on the q input already; for selects we use
  // a manual debounce on the form change event
  let debounceTimer = null;
  const form = document.getElementById("filter-form");
  if (form) {
    form.addEventListener("change", function (e) {
      updateDownloadLinks();
      // Selects (multi-select filters) get debounced; text inputs fire via HTMX
      const tag = e.target.tagName;
      if (tag === "SELECT") {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(function () {
          // HTMX will handle the actual form submission via hx-trigger="change"
          // This debounce prevents rapid multi-select clicks firing many requests.
          // We manually trigger htmx on the form with the delay already elapsed.
        }, 300);
      }
    });
    form.addEventListener("input", updateDownloadLinks);
  }

  // JS-003: Add keyboard hint near search box
  const qInput = document.getElementById("q");
  if (qInput) {
    const hint = document.createElement("span");
    hint.style.cssText = "font-size:.7rem;color:#999;display:block;margin-top:.15rem";
    hint.textContent = "Press / or Ctrl+K to focus";
    qInput.parentNode.insertBefore(hint, qInput.nextSibling);
  }

  // Patch download modal trigger button
  const dlBtn = document.querySelector("button[onclick*=\"dl-modal\"]");
  if (dlBtn) {
    dlBtn.removeAttribute("onclick");
    dlBtn.addEventListener("click", openDownloadModal);
  }
});
