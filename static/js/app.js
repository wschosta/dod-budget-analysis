/**
 * DoD Budget Explorer — app.js
 * Handles: column toggles (3.A4-b), URL query params (3.A3-b),
 *          download link generation (3.A5-a), row selection (3.A6-a).
 *
 * ──────────────────────────────────────────────────────────────────────────
 * JavaScript TODOs
 * ──────────────────────────────────────────────────────────────────────────
 *
 * TODO 3.A5-b / JS-001 [Group: LION] [Complexity: MEDIUM] [Tokens: ~2000] [User: NO]
 *     Add Excel (.xlsx) export support to download modal.
 *     The wireframe shows CSV, JSON, and Excel download options but only
 *     CSV and NDJSON are implemented. Steps:
 *       1. Add a /api/v1/download?fmt=xlsx endpoint in api/routes/download.py
 *          using openpyxl to generate .xlsx in a streaming fashion
 *       2. Add a "Download Excel" button in the download modal (index.html)
 *       3. Wire buildDownloadURL('xlsx') in this file
 *       4. Add Content-Disposition header with .xlsx filename
 *     Acceptance: Excel download produces valid .xlsx with filtered data.
 *
 * TODO 3.A5-c / JS-002 [Group: LION] [Complexity: LOW] [Tokens: ~1500] [User: NO]
 *     Show estimated result count and file size in download modal.
 *     Currently the modal says "up to 50,000 rows" but doesn't show the
 *     actual count for the current filter set. Steps:
 *       1. When download modal opens, fetch current result count from
 *          the #results-container .results-count text
 *       2. Parse the count and display it in the modal
 *       3. Estimate file size (~100 bytes/row for CSV, ~200 for JSON)
 *       4. Update modal text: "4,527 matching rows (~450 KB CSV)"
 *     Acceptance: Modal shows actual result count and estimated file size.
 *
 * TODO 3.A3-f / JS-003 [Group: LION] [Complexity: LOW] [Tokens: ~1000] [User: NO]
 *     Add keyboard shortcut for search focus (Ctrl+K or /).
 *     Steps:
 *       1. Add keydown listener for '/' or 'Ctrl+K'
 *       2. Focus the #q input and prevent default
 *       3. Add visual hint near search box: "Press / to search"
 *     Acceptance: Pressing / anywhere focuses the search input.
 *
 * TODO 3.A6-d / JS-004 [Group: LION] [Complexity: LOW] [Tokens: ~1000] [User: NO]
 *     Add keyboard navigation for detail panel.
 *     Steps:
 *       1. After detail loads via HTMX, focus the detail panel heading
 *       2. Add Escape key handler to close the detail panel
 *       3. Add aria-expanded attribute to the selected table row
 *     Acceptance: Keyboard users can navigate to and dismiss detail panel.
 *
 * TODO OPT-JS-001 [Group: LION] [Complexity: LOW] [Tokens: ~1000] [User: NO]
 *     Debounce filter form changes to reduce API requests.
 *     Currently every checkbox change fires an HTMX request immediately.
 *     For multi-select changes (e.g., selecting 3 services), this sends 3
 *     requests. Steps:
 *       1. Add hx-trigger="change delay:300ms" to multi-select elements
 *       2. Or use a "debounced form submission" pattern: collect changes
 *          for 300ms before sending
 *     Acceptance: Rapid filter changes produce one request, not many.
 */

"use strict";

// ── Column toggle (3.A4-b) ────────────────────────────────────────────────────
// Persist to localStorage so preference survives page reloads.

const COL_KEY = "dod_hidden_cols";

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
  document.querySelectorAll("tr.selected").forEach(r => r.classList.remove("selected"));
  tr.classList.add("selected");
}

// ── URL query params → filter state (3.A3-b) ──────────────────────────────────
// On page load, read URL params and pre-populate form fields.

function restoreFiltersFromURL() {
  const params = new URLSearchParams(window.location.search);
  const form = document.getElementById("filter-form");
  if (!form) return;

  // Text inputs
  ["q"].forEach(name => {
    const el = form.elements[name];
    if (el && params.has(name)) el.value = params.get(name);
  });

  // Multi-selects
  ["fiscal_year", "service", "exhibit_type"].forEach(name => {
    const el = form.elements[name];
    if (!el || !params.has(name)) return;
    const vals = params.getAll(name);
    Array.from(el.options).forEach(opt => {
      opt.selected = vals.includes(opt.value);
    });
  });
}

// ── Download URL builder (3.A5-a) ─────────────────────────────────────────────
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
  return "/api/v1/download?" + params.toString();
}

function updateDownloadLinks() {
  const csv  = document.getElementById("dl-csv");
  const json = document.getElementById("dl-json");
  if (csv)  csv.href  = buildDownloadURL("csv");
  if (json) json.href = buildDownloadURL("json");
}

// ── HTMX events ────────────────────────────────────────────────────────────────
// After every HTMX swap, re-apply column visibility and update download links.

document.addEventListener("htmx:afterSwap", function (evt) {
  if (evt.detail.target.id === "results-container") {
    applyHiddenCols(getHiddenCols());
    updateDownloadLinks();
  }
});

// ── Initialise ─────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", function () {
  restoreFiltersFromURL();
  applyHiddenCols(getHiddenCols());
  updateDownloadLinks();

  // Keep download links fresh when filters change
  const form = document.getElementById("filter-form");
  if (form) {
    form.addEventListener("change", updateDownloadLinks);
    form.addEventListener("input",  updateDownloadLinks);
  }
});
