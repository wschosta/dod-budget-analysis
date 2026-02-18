/**
 * DoD Budget Explorer — app.js
 * Handles: column toggles (3.A4-b), URL query params (3.A3-b),
 *          download link generation (3.A5-a), row selection (3.A6-a).
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
