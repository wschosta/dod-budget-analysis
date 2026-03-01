/**
 * DoD Budget Explorer — app.js
 * Handles: column toggles (3.A4-b), URL query params (3.A3-b),
 *          download link generation (3.A5-a), row selection (3.A6-a),
 *          keyboard shortcuts (JS-003), detail panel keyboard nav (JS-004),
 *          debounced filter changes (OPT-JS-001), page-size persistence (FE-010),
 *          download modal result count (JS-002), Excel export (JS-001).
 */

// DONE [Group: LION] LION-007: Add URL sharing — sync filter state to URL query params (~1,200 tokens)

"use strict";

// ── Shared fetch wrapper ────────────────────────────────────────────────────
// Centralises the fetch→JSON pattern used throughout the app so callers
// don't need to repeat the `.ok` check / `.json()` parse.

/**
 * Fetch a URL and return parsed JSON, or null on HTTP error.
 * @param {string} url
 * @param {RequestInit} [opts]
 * @returns {Promise<any|null>}
 */
function apiFetch(url, opts) {
  return fetch(url, opts).then(function (r) {
    return r.ok ? r.json() : null;
  });
}

// ── LION-010: Dark mode toggle ──────────────────────────────────────────────

var THEME_KEY = "dod_theme";

function toggleTheme() {
  var html = document.documentElement;
  var current = html.getAttribute("data-theme");
  var next;
  if (current === "dark") {
    next = "light";
  } else if (current === "light") {
    next = "dark";
  } else {
    // No explicit theme set — check system preference
    next = window.matchMedia("(prefers-color-scheme: dark)").matches ? "light" : "dark";
  }
  html.setAttribute("data-theme", next);
  localStorage.setItem(THEME_KEY, next);
  updateChartTheme();
}

function updateChartTheme() {
  // FALCON-8: Use CSS custom properties for chart theme colors
  if (typeof Chart !== "undefined") {
    var style = getComputedStyle(document.documentElement);
    var textColor = style.getPropertyValue("--chart-text").trim() || style.getPropertyValue("--text-secondary").trim() || "#374151";
    var isDark = document.documentElement.getAttribute("data-theme") === "dark" ||
      (!document.documentElement.getAttribute("data-theme") &&
       window.matchMedia("(prefers-color-scheme: dark)").matches);
    var gridColor = isDark ? "rgba(255,255,255,.1)" : "rgba(0,0,0,.1)";
    Chart.defaults.color = textColor;
    Chart.defaults.borderColor = gridColor;
  }
}

// ── Column toggle (3.A4-b) ────────────────────────────────────────────────────
// Persist to localStorage so preference survives page reloads.

const COL_KEY = "dod_hidden_cols";
const PAGE_SIZE_KEY = "dod_page_size";
var AMT_FMT_KEY = "dod_amt_fmt";

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

// ── FALCON-2: Keyboard navigation for search results ────────────────────────

var DENSITY_KEY = "dod_density";

function initResultsKeyboardNav() {
  var container = document.getElementById("results-container");
  if (!container) return;

  container.addEventListener("keydown", function(e) {
    var rows = Array.from(container.querySelectorAll("tbody tr[tabindex]"));
    if (!rows.length) return;

    var current = document.activeElement;
    var idx = rows.indexOf(current);

    if (e.key === "ArrowDown") {
      e.preventDefault();
      var next = idx < rows.length - 1 ? rows[idx + 1] : rows[0];
      next.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      var prev = idx > 0 ? rows[idx - 1] : rows[rows.length - 1];
      prev.focus();
    } else if (e.key === "Enter" || e.key === " ") {
      if (current && rows.includes(current)) {
        e.preventDefault();
        selectRow(current);
        htmx.trigger(current, "click");
      }
    } else if (e.key === "Escape") {
      var detail = document.getElementById("detail-container");
      if (detail && detail.innerHTML.trim()) {
        detail.innerHTML = "";
        if (current && rows.includes(current)) current.focus();
      }
    }
  });
}

// FALCON-2: Density toggle
function setDensity(level) {
  var wrapper = document.getElementById("results-container");
  if (!wrapper) return;
  wrapper.classList.remove("density-compact", "density-spacious");
  if (level === "compact") wrapper.classList.add("density-compact");
  else if (level === "spacious") wrapper.classList.add("density-spacious");
  // comfortable = default (no class)
  localStorage.setItem(DENSITY_KEY, level);
  // Update toggle button states
  document.querySelectorAll(".density-btn").forEach(function(btn) {
    btn.classList.toggle("active", btn.getAttribute("data-density") === level);
  });
}

function restoreDensity() {
  var saved = localStorage.getItem(DENSITY_KEY);
  if (saved) setDensity(saved);
}

// ── FALCON-3: Collapsible filter panel ───────────────────────────────────────

function toggleFilterPanel() {
  var panel = document.getElementById("filter-panel");
  var btn = document.getElementById("filter-collapse-btn");
  if (!panel) return;
  panel.classList.toggle("collapsed");
  var isCollapsed = panel.classList.contains("collapsed");
  if (btn) {
    btn.setAttribute("aria-expanded", String(!isCollapsed));
    btn.setAttribute("aria-label", isCollapsed ? "Expand filters" : "Collapse filters");
  }
}

// ── FALCON-14: Filter drawer toggle for mobile viewports ──────────────────────
function toggleFilterDrawer(panelId, btnId) {
  panelId = panelId || "filter-panel";
  btnId = btnId || "filter-drawer-toggle";
  var panel = document.getElementById(panelId);
  var btn = document.getElementById(btnId);
  if (!panel) return;
  var isOpen = panel.classList.toggle("drawer-open");
  if (btn) {
    btn.classList.toggle("open", isOpen);
    btn.setAttribute("aria-expanded", String(isOpen));
  }
}

// ── URL query params → filter state (3.A3-b) ──────────────────────────────────
// On page load, read URL params and pre-populate form fields.

function restoreFiltersFromURL() {
  const params = new URLSearchParams(window.location.search);
  const form = document.getElementById("filter-form");
  if (!form) return;

  let hasActiveFilters = false;

  // Text inputs
  ["q", "min_amount", "max_amount"].forEach(name => {
    const el = form.elements[name];
    if (el && params.has(name)) {
      el.value = params.get(name);
      hasActiveFilters = true;
    }
  });

  // Multi-selects — set option.selected then sync checkbox-select UI
  ["fiscal_year", "service", "exhibit_type", "budget_type"].forEach(name => {
    const el = form.elements[name];
    if (!el || !params.has(name)) return;
    const vals = params.getAll(name);
    Array.from(el.options).forEach(opt => {
      opt.selected = vals.includes(opt.value);
    });
    hasActiveFilters = true;
    // Sync checkbox-select component if it wraps this select
    const wrapper = el.closest(".checkbox-select");
    if (wrapper && wrapper._checkboxSelectRefresh) {
      wrapper._checkboxSelectRefresh();
    }
  });

  // Auto-open mobile filter drawer when URL has active filters
  if (hasActiveFilters) {
    const filterPanel = document.getElementById("filter-panel");
    if (filterPanel && !filterPanel.classList.contains("drawer-open")) {
      filterPanel.classList.add("drawer-open");
      const toggleBtn = document.getElementById("filter-drawer-toggle");
      if (toggleBtn) toggleBtn.setAttribute("aria-expanded", "true");
    }
    // Trigger a search with the restored filters
    setTimeout(function () {
      htmx.trigger(form, "filter-debounced");
    }, 100);
  }
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
    // FIX-012: Complete mapping including FY25 total, FY26 total, and source columns
    const colMap = {
      "col-org":     "organization_name",
      "col-fy":      "fiscal_year",
      "col-exhibit": "exhibit_type",
      "col-account": "account",
      "col-pe":      "pe_number",
      "col-fy24":    "amount_fy2024_actual",
      "col-fy25":    "amount_fy2025_enacted",
      "col-fy25tot": "amount_fy2025_total",
      "col-fy26":    "amount_fy2026_request",
      "col-fy26tot": "amount_fy2026_total",
      "col-source":  "source_file",
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

// ── FALCON-6: Quick export with toast notifications ─────────────────────────

function quickExport(fmt) {
  var url = buildDownloadURL(fmt);
  if (typeof showToast === "function") {
    showToast("Preparing " + fmt.toUpperCase() + " download...", "info", 2000);
  }
  // Trigger download via hidden link
  var a = document.createElement("a");
  a.href = url;
  a.download = "";
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  setTimeout(function() { document.body.removeChild(a); }, 100);
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

// ── LION-002: Feedback modal ─────────────────────────────────────────────────

function openFeedbackModal() {
  var modal = document.getElementById("feedback-modal");
  if (modal) {
    modal.classList.add("open");
    // Auto-fill page URL
    var urlInput = document.getElementById("feedback-page-url");
    if (urlInput) urlInput.value = window.location.href;
    // Focus the type select
    var typeSelect = document.getElementById("feedback-type");
    if (typeSelect) typeSelect.focus();
  }
}

function closeFeedbackModal() {
  var modal = document.getElementById("feedback-modal");
  if (modal) modal.classList.remove("open");
}

// FIX-011: Handle feedback form submission — only close on success, show error on failure
(function() {
  document.addEventListener("submit", function(e) {
    if (e.target && e.target.id === "feedback-form") {
      e.preventDefault();
      var form = e.target;
      var submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn) submitBtn.disabled = true;
      var data = new FormData(form);
      var payload = {};
      data.forEach(function(v, k) { payload[k] = v; });
      fetch("/api/v1/feedback", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      }).then(function(resp) {
        if (resp.ok) {
          closeFeedbackModal();
          form.reset();
          if (typeof showToast === "function") showToast("Feedback submitted — thank you!", "success");
        } else {
          if (typeof showToast === "function") showToast("Failed to submit feedback. Please try again.", "error");
        }
      }).catch(function() {
        // Endpoint may not exist yet — close anyway since feedback can't be saved
        closeFeedbackModal();
        form.reset();
        showToast("Feedback saved locally", "info");
      }).finally(function() {
        if (submitBtn) submitBtn.disabled = false;
      });
    }
  });
})();

// ── LION-006 + A4.3: Chart export (PNG download) ────────────────────────────

function downloadChartAsPNG(canvasId, filename) {
  var canvas = document.getElementById(canvasId);
  if (!canvas) return;
  var url = canvas.toDataURL("image/png");
  var a = document.createElement("a");
  a.href = url;
  a.download = filename || (canvasId + ".png");
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

/**
 * A4.3: Reusable helper to add an "Export as PNG" button next to a chart canvas.
 * Inserts the button after the canvas inside its parent container.
 * @param {string} canvasId - The id of the canvas element
 * @param {string} filename - The download filename (e.g. "service-chart.png")
 */
function addChartExportButton(canvasId, filename) {
  var canvas = document.getElementById(canvasId);
  if (!canvas) return;
  // Avoid adding duplicate buttons
  var parent = canvas.parentElement;
  if (!parent) return;
  if (parent.querySelector('.chart-export-btn[data-canvas="' + canvasId + '"]')) return;

  var btn = document.createElement("button");
  btn.className = "btn btn-secondary btn-sm chart-export-btn";
  btn.setAttribute("data-canvas", canvasId);
  btn.textContent = "Export as PNG";
  btn.addEventListener("click", function() {
    downloadChartAsPNG(canvasId, filename || canvasId + ".png");
  });
  parent.appendChild(btn);
}

// ── LION-007: Copy shareable URL with current filters ───────────────────────

function copyShareURL() {
  var url = window.location.href;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(url);
  } else {
    // Fallback for older browsers
    var ta = document.createElement("textarea");
    ta.value = url;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
  // Show "Copied!" tooltip + toast
  var btn = document.getElementById("share-btn");
  if (btn) {
    btn.classList.add("copied");
    setTimeout(function() { btn.classList.remove("copied"); }, 1500);
  }
  if (typeof showToast === "function") showToast("URL copied to clipboard", "success");
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

    // LION-002: Close feedback modal with Escape
    const fbModal = document.getElementById("feedback-modal");
    if (fbModal && fbModal.classList.contains("open")) {
      fbModal.classList.remove("open");
    }
  }
});

// ── FALCON-5: URL-based state management ─────────────────────────────────────
// Handle back/forward navigation by re-fetching results from the URL.

window.addEventListener("popstate", function () {
  restoreFiltersFromURL();
  // Reload results via HTMX to match the URL
  var container = document.getElementById("results-container");
  var form = document.getElementById("filter-form");
  if (container && form) {
    var url = "/partials/results" + window.location.search;
    htmx.ajax("GET", url, {
      target: "#results-container",
      swap: "innerHTML"
    });
  }
});

// FALCON-5: Sync URL from form state before HTMX pushes
document.addEventListener("htmx:beforeRequest", function(evt) {
  var form = document.getElementById("filter-form");
  if (!form || evt.detail.target.id !== "results-container") return;

  // Build canonical URL from current form state
  var data = new FormData(form);
  var params = new URLSearchParams();
  for (var pair of data.entries()) {
    if (pair[1]) params.append(pair[0], pair[1]);
  }
  // Preserve sort/page from htmx vals if present
  var htmxVals = evt.detail.requestConfig && evt.detail.requestConfig.parameters;
  if (htmxVals) {
    if (htmxVals.sort_by) params.set("sort_by", htmxVals.sort_by);
    if (htmxVals.sort_dir) params.set("sort_dir", htmxVals.sort_dir);
    if (htmxVals.page) params.set("page", htmxVals.page);
    if (htmxVals.page_size) params.set("page_size", htmxVals.page_size);
  }
});

// ── HTMX events ────────────────────────────────────────────────────────────────
// After every HTMX swap, re-apply column visibility and update download links.

document.addEventListener("htmx:afterSwap", function (evt) {
  if (evt.detail.target.id === "results-container") {
    applyHiddenCols(getHiddenCols());
    updateDownloadLinks();
    restorePageSize();
    restoreDensity();
    restoreAmountFormat();
    if (currentAmtFmt !== "K") applyAmountFormat();
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

// ── FALCON-10: Toast notifications ───────────────────────────────────────────

var TOAST_ICONS = {
  success: "\u2713",
  info: "\u2139",
  warning: "\u26A0",
  error: "\u2717"
};

/**
 * Show a toast notification.
 * @param {string} message - The message to display
 * @param {string} type - One of: success, info, warning, error
 * @param {number} duration - Auto-dismiss after ms (default 4000, 0 to disable)
 */
function showToast(message, type, duration) {
  type = type || "info";
  if (duration === undefined) duration = 4000;

  var container = document.getElementById("toast-container");
  if (!container) return;

  var toast = document.createElement("div");
  toast.className = "toast toast-" + type;
  toast.setAttribute("role", "alert");

  var icon = document.createElement("span");
  icon.className = "toast-icon";
  icon.textContent = TOAST_ICONS[type] || TOAST_ICONS.info;
  icon.setAttribute("aria-hidden", "true");

  var msg = document.createElement("span");
  msg.textContent = message;

  var dismiss = document.createElement("button");
  dismiss.className = "toast-dismiss";
  dismiss.textContent = "\u00D7";
  dismiss.setAttribute("aria-label", "Dismiss");
  dismiss.addEventListener("click", function() { removeToast(toast); });

  toast.appendChild(icon);
  toast.appendChild(msg);
  toast.appendChild(dismiss);
  container.appendChild(toast);

  if (duration > 0) {
    setTimeout(function() { removeToast(toast); }, duration);
  }
}

function removeToast(toast) {
  if (!toast || !toast.parentNode) return;
  toast.classList.add("removing");
  setTimeout(function() {
    if (toast.parentNode) toast.parentNode.removeChild(toast);
  }, 200);
}

// ── FALCON-9: Amount formatting toggle ($K / $M / $B) ───────────────────────

var currentAmtFmt = localStorage.getItem(AMT_FMT_KEY) || "K";

/**
 * Format amount in $K to the selected display unit.
 * @param {number} valK - Amount in thousands of dollars
 * @returns {string} Formatted string
 */
function formatAmount(valK) {
  if (valK == null || isNaN(valK)) return "\u2014";
  var fmt = currentAmtFmt;
  if (fmt === "M") {
    return "$" + (valK / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 }) + "M";
  } else if (fmt === "B") {
    return "$" + (valK / 1000000).toLocaleString(undefined, { maximumFractionDigits: 2 }) + "B";
  }
  // Default: $K
  return "$" + Number(valK).toLocaleString(undefined, { maximumFractionDigits: 0 }) + "K";
}

function setAmountFormat(fmt) {
  currentAmtFmt = fmt;
  localStorage.setItem(AMT_FMT_KEY, fmt);
  // Update toggle button states
  document.querySelectorAll(".amt-fmt-btn").forEach(function(btn) {
    btn.classList.toggle("active", btn.getAttribute("data-fmt") === fmt);
  });
  // Re-format all visible amounts in the results table
  applyAmountFormat();
}

function applyAmountFormat() {
  document.querySelectorAll(".td-amount[data-raw]").forEach(function(el) {
    var raw = parseFloat(el.getAttribute("data-raw"));
    if (!isNaN(raw)) {
      el.textContent = formatAmount(raw);
    }
  });
}

function restoreAmountFormat() {
  var saved = localStorage.getItem(AMT_FMT_KEY);
  if (saved) {
    currentAmtFmt = saved;
    document.querySelectorAll(".amt-fmt-btn").forEach(function(btn) {
      btn.classList.toggle("active", btn.getAttribute("data-fmt") === saved);
    });
  }
}

// ── FALCON-7: Footer metadata ────────────────────────────────────────────────

function loadFooterMetadata() {
  var el = document.getElementById("footer-meta");
  if (!el) return;
  apiFetch("/api/v1/metadata")
    .then(function(data) {
      if (!data) return;
      var parts = [];
      if (data.version) parts.push("v" + data.version);
      if (data.last_refresh) {
        var d = data.last_refresh.slice(0, 10);
        parts.push("Updated " + d);
      }
      if (data.budget_lines) parts.push(data.budget_lines.toLocaleString() + " budget lines");
      if (data.pe_count) parts.push(data.pe_count.toLocaleString() + " PEs");
      if (data.fiscal_years && data.fiscal_years.length) {
        parts.push(data.fiscal_years.join(", "));
      }
      if (parts.length) el.textContent = parts.join(" \u00B7 ");

      // A4.1: Populate data freshness indicator
      populateDataFreshness(data);
    })
    .catch(function() { /* silently ignore — footer just stays empty */ });
}

// ── A4.1: Data freshness indicator ──────────────────────────────────────────

function populateDataFreshness(data) {
  var el = document.getElementById("data-freshness");
  if (!el) return;

  var dateStr = data.last_refresh || data.last_build_time || data.build_date;
  if (!dateStr) {
    el.textContent = "";
    return;
  }

  var dateOnly = dateStr.slice(0, 10);
  var refreshDate = new Date(dateOnly);
  var now = new Date();
  var daysDiff = Math.floor((now - refreshDate) / (1000 * 60 * 60 * 24));

  // Green dot if fresh (within 7 days), amber if stale
  var dot = document.createElement("span");
  dot.className = "data-freshness-dot" + (daysDiff > 7 ? " stale" : "");
  dot.setAttribute("aria-hidden", "true");

  var text = document.createElement("span");
  text.textContent = "Data last updated: " + dateOnly;
  if (daysDiff > 7) {
    text.textContent += " (" + daysDiff + " days ago)";
  }

  el.innerHTML = "";
  el.appendChild(dot);
  el.appendChild(text);
}

// ── FALCON-1: Landing page summary visuals ──────────────────────────────────

// Colour palette — provided by fmt.js (loaded from base.html).
var LANDING_COLORS = BUDGET_COLORS;

function loadLandingVisuals() {
  var svcCanvas = document.getElementById("landing-service-chart");
  var appCanvas = document.getElementById("landing-approp-chart");
  if (!svcCanvas && !appCanvas) return; // not on landing page

  // Load service breakdown chart
  if (svcCanvas) {
    apiFetch("/api/v1/aggregations?group_by=service")
      .then(function(data) {
        if (!data || !data.rows || !data.rows.length) return;
        var cols = Object.keys(data.rows[0]).filter(function(k) { return /^total_fy\d+/.test(k); }).sort();
        var reqCol = cols.find(function(c) { return c.includes("request"); }) || cols[cols.length - 1];
        if (!reqCol) return;

        var labels = data.rows.filter(function(r) { return r[reqCol]; }).map(function(r) { return r.group_value || "Unknown"; });
        var amounts = data.rows.filter(function(r) { return r[reqCol]; }).map(function(r) { return (r[reqCol] || 0) / 1000; });

        new Chart(svcCanvas, {
          type: "bar",
          data: {
            labels: labels,
            datasets: [{
              label: "FY Request ($M)",
              data: amounts,
              backgroundColor: LANDING_COLORS,
              borderRadius: 4
            }]
          },
          options: {
            indexAxis: "y",
            plugins: { legend: { display: false } },
            scales: { x: { ticks: { callback: tickDollarsM } } },
            onHover: function(e, el) { e.native.target.style.cursor = el.length ? "pointer" : "default"; },
            onClick: function(e, el) {
              if (el.length) {
                var idx = el[0].index;
                window.location.href = "/?service=" + encodeURIComponent(labels[idx]) + "#results-container";
              }
            }
          }
        });
      })
      .catch(function() {});
  }

  // Load budget type doughnut chart (shared utility from budget-charts.js)
  if (appCanvas) {
    renderBudgetTypeDoughnut("landing-approp-chart", {
      colors: LANDING_COLORS,
      onClick: function(budgetType) {
        window.location.href = "/?budget_type=" + encodeURIComponent(budgetType) + "#results-container";
      },
    });
  }
}

// ── A4.4: Tag cloud on Programs page ─────────────────────────────────────────

function loadTagCloud() {
  var container = document.getElementById("tag-cloud");
  var countEl = document.getElementById("tag-cloud-count");
  if (!container) return;

  apiFetch("/api/v1/pe/tags/all")
    .then(function(data) {
      if (!data) {
        container.innerHTML = '<p style="font-size:.85rem;color:var(--text-secondary)">Tags not available.</p>';
        return;
      }

      // data is expected to be an array of {tag, pe_count} objects
      var tags = Array.isArray(data) ? data : (data.tags || data.items || []);
      if (!tags.length) {
        container.innerHTML = '<p style="font-size:.85rem;color:var(--text-secondary)">No tags found. Run enrichment to generate tags.</p>';
        return;
      }

      if (countEl) countEl.textContent = "(" + tags.length + " tags)";

      // Compute min/max pe_count for proportional sizing
      var counts = tags.map(function(t) { return t.pe_count || 1; });
      var minCount = Math.min.apply(null, counts);
      var maxCount = Math.max.apply(null, counts);
      var range = maxCount - minCount || 1;

      // Font size scale: 0.72rem to 1.4rem
      var minSize = 0.72;
      var maxSize = 1.4;

      container.innerHTML = "";
      tags.forEach(function(t) {
        var ratio = (t.pe_count - minCount) / range;
        var fontSize = minSize + ratio * (maxSize - minSize);

        var link = document.createElement("a");
        link.className = "tag-cloud-item";
        link.textContent = t.tag + " (" + t.pe_count + ")";
        link.style.fontSize = fontSize.toFixed(2) + "rem";
        link.href = "/programs?tag=" + encodeURIComponent(t.tag);
        link.title = t.tag + ": " + t.pe_count + " program" + (t.pe_count !== 1 ? "s" : "");
        link.setAttribute("role", "link");

        // Clicking a tag filters the program list via HTMX
        link.addEventListener("click", function(e) {
          e.preventDefault();
          var tagSelect = document.getElementById("pe-tag");
          if (tagSelect) {
            // Select the matching tag option
            Array.from(tagSelect.options).forEach(function(opt) {
              opt.selected = (opt.value === t.tag);
            });
            // Trigger the filter form
            var form = document.getElementById("pe-filter-form");
            if (form && typeof htmx !== "undefined") {
              htmx.trigger(form, "change");
            }
          }
          // Update URL
          window.history.pushState({}, "", "/programs?tag=" + encodeURIComponent(t.tag));
        });

        container.appendChild(link);
      });
    })
    .catch(function() {
      container.innerHTML = '<p style="font-size:.85rem;color:var(--text-secondary)">Could not load tags.</p>';
    });
}

// ── 3.1: Faceted counts — show result counts per filter option ────────────────

var _facetTimer = null;

function loadFacetCounts() {
  // Only on the home page with filters
  var form = document.getElementById("filter-form");
  if (!form) return;

  // Debounce to avoid rapid-fire fetches
  clearTimeout(_facetTimer);
  _facetTimer = setTimeout(function() { _doLoadFacets(form); }, 200);
}

function _doLoadFacets(form) {
  // Build query from current filter state
  var params = new URLSearchParams();
  var fySelect = document.getElementById("fiscal_year");
  if (fySelect) {
    Array.from(fySelect.selectedOptions).forEach(function(o) {
      params.append("fiscal_year", o.value);
    });
  }
  var svcSelect = document.getElementById("service");
  if (svcSelect) {
    Array.from(svcSelect.selectedOptions).forEach(function(o) {
      params.append("service", o.value);
    });
  }
  var etSelect = document.getElementById("exhibit_type");
  if (etSelect) {
    Array.from(etSelect.selectedOptions).forEach(function(o) {
      params.append("exhibit_type", o.value);
    });
  }
  var btSelect = document.getElementById("budget_type");
  if (btSelect) {
    Array.from(btSelect.selectedOptions).forEach(function(o) {
      params.append("budget_type", o.value);
    });
  }

  apiFetch("/api/v1/facets?" + params.toString())
    .then(function(data) {
      if (!data) return;
      _applyFacetCounts("fiscal_year", data.fiscal_year || []);
      _applyFacetCounts("service", data.service || []);
      _applyFacetCounts("exhibit_type", data.exhibit_type || []);
      _applyFacetCounts("budget_type", data.budget_type || []);
    })
    .catch(function() { /* ignore facet errors */ });
}

function _applyFacetCounts(selectId, facets) {
  var sel = document.getElementById(selectId);
  if (!sel) return;

  // Build a map of value -> count
  var countMap = {};
  facets.forEach(function(f) { countMap[f.value] = f.count; });

  Array.from(sel.options).forEach(function(opt) {
    if (!opt.value) return; // skip placeholder
    var count = countMap[opt.value];
    // Strip any existing count suffix like " (1,234)"
    var baseText = opt.textContent.replace(/\s*\(\d[\d,]*\s*rows?\)$/, "")
                                   .replace(/\s*\(\d[\d,]*\)$/, "");
    if (count !== undefined) {
      opt.textContent = baseText + " (" + count.toLocaleString() + ")";
      opt.disabled = false;
      opt.style.color = "";
    } else {
      opt.textContent = baseText + " (0)";
      opt.disabled = !opt.selected;
      opt.style.color = opt.selected ? "" : "var(--text-secondary)";
    }
  });
}

// ── Initialise ─────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", function () {
  // LION-010: Apply chart theme on init
  updateChartTheme();

  // Mobile hamburger toggle
  var hamburger = document.querySelector(".hamburger");
  var navLinks = document.querySelector(".nav-links");
  if (hamburger && navLinks) {
    hamburger.addEventListener("click", function () {
      var expanded = this.getAttribute("aria-expanded") === "true";
      this.setAttribute("aria-expanded", String(!expanded));
      navLinks.classList.toggle("open");
    });
  }

  restoreFiltersFromURL();
  applyHiddenCols(getHiddenCols());
  updateDownloadLinks();
  restorePageSize();
  restoreDensity();
  restoreAmountFormat();
  initResultsKeyboardNav();

  // FALCON-7: Fetch metadata for footer
  loadFooterMetadata();

  // FALCON-1: Load landing page summary visuals
  loadLandingVisuals();

  // A4.4: Load tag cloud on Programs page
  loadTagCloud();

  // OPT-JS-001: Debounce filter form changes — multi-selects get a 300ms
  // debounce before firing HTMX. The form's hx-trigger listens for a custom
  // "filter-debounced" event (not raw "change") so rapid clicks don't cause
  // duplicate requests. Number inputs also debounce on change.
  // Suppress debounce while a checkbox-select dropdown is open to prevent
  // HTMX swaps from closing the dropdown mid-interaction.
  let debounceTimer = null;
  const form = document.getElementById("filter-form");
  if (form) {
    form.addEventListener("change", function (e) {
      updateDownloadLinks();
      const tag = e.target.tagName;
      if (tag === "SELECT" || e.target.type === "number") {
        clearTimeout(debounceTimer);
        var anyDropdownOpen = document.querySelector(".checkbox-select.open");
        var delay = anyDropdownOpen ? 800 : 300;
        debounceTimer = setTimeout(function () {
          htmx.trigger(form, "filter-debounced");
        }, delay);
      }
    });
    form.addEventListener("input", updateDownloadLinks);
  }

  // 3.1: Load faceted counts to show result counts on filter options
  loadFacetCounts();
  // Re-load facets after HTMX swap (filter change)
  document.body.addEventListener("htmx:afterSwap", function() {
    loadFacetCounts();
  });

  // JS-003: Add keyboard hint near search box
  const qInput = document.getElementById("q");
  if (qInput) {
    const hint = document.createElement("span");
    hint.style.cssText = "font-size:.7rem;color:var(--text-secondary);display:block;margin-top:.15rem";
    hint.textContent = "Press / or Ctrl+K to focus";
    qInput.parentNode.insertBefore(hint, qInput.nextSibling);
  }

  // Patch download modal trigger button
  const dlBtn = document.querySelector("button[onclick*=\"dl-modal\"]");
  if (dlBtn) {
    dlBtn.removeAttribute("onclick");
    dlBtn.addEventListener("click", openDownloadModal);
  }

  // Toast on download link clicks
  document.querySelectorAll("#dl-csv, #dl-json, #dl-xlsx").forEach(function (el) {
    el.addEventListener("click", function () {
      var fmt = el.id.replace("dl-", "").toUpperCase();
      showToast("Downloading " + fmt + "…", "info");
    });
  });

  // ── Back to top button ───────────────────────────────────────────────
  var backToTop = document.getElementById("back-to-top");
  if (backToTop) {
    window.addEventListener("scroll", function () {
      backToTop.classList.toggle("visible", window.scrollY > 400);
    }, { passive: true });
  }

  // ── Search autocomplete ─────────────────────────────────────────────────
  initAutocomplete();
  initHeroAutocomplete();

  // ── Saved searches ──────────────────────────────────────────────────────
  renderSavedSearches();
});

// ── Autocomplete for keyword search ─────────────────────────────────────────

// _escapeHtml provided by fmt.js as escapeHtml(); alias kept for local refs.
var _escapeHtml = escapeHtml;

function initAutocomplete() {
  var qInput = document.getElementById("q");
  if (!qInput) return;

  var dropdown = document.createElement("div");
  dropdown.className = "autocomplete-dropdown";
  dropdown.setAttribute("role", "listbox");
  dropdown.id = "autocomplete-list";
  qInput.parentNode.style.position = "relative";
  qInput.parentNode.appendChild(dropdown);
  qInput.setAttribute("role", "combobox");
  qInput.setAttribute("aria-autocomplete", "list");
  qInput.setAttribute("aria-owns", "autocomplete-list");

  var acTimer = null;
  qInput.addEventListener("input", function () {
    clearTimeout(acTimer);
    var val = qInput.value.trim();
    if (val.length < 2) {
      dropdown.innerHTML = "";
      dropdown.style.display = "none";
      return;
    }
    acTimer = setTimeout(function () {
      fetch("/api/v1/search/suggest?q=" + encodeURIComponent(val) + "&limit=8")
        .then(function (r) { return r.json(); })
        .then(function (items) {
          if (!items || !items.length) {
            dropdown.style.display = "none";
            return;
          }
          dropdown.innerHTML = items.map(function (item) {
            return '<div class="autocomplete-item" role="option">' +
              '<span class="autocomplete-value">' + _escapeHtml(item.value) + "</span>" +
              '<span class="autocomplete-field">' + _escapeHtml((item.field || "").replace(/_/g, " ")) + "</span></div>";
          }).join("");
          dropdown.style.display = "block";
        })
        .catch(function () {
          dropdown.style.display = "none";
        });
    }, 250);
  });

  dropdown.addEventListener("click", function (e) {
    var item = e.target.closest(".autocomplete-item");
    if (item) {
      qInput.value = item.querySelector(".autocomplete-value").textContent;
      dropdown.style.display = "none";
      if (typeof htmx !== "undefined") htmx.trigger(qInput, "search");
    }
  });

  qInput.addEventListener("blur", function () {
    setTimeout(function () { dropdown.style.display = "none"; }, 200);
  });
}

// ── Hero search autocomplete ─────────────────────────────────────────────────

function initHeroAutocomplete() {
  var input = document.getElementById("hero-search-input");
  var dropdown = document.getElementById("hero-autocomplete-list");
  if (!input || !dropdown) return;

  // Remove hidden attribute since CSS .autocomplete-dropdown uses display:none
  dropdown.removeAttribute("hidden");

  var acTimer = null;
  var activeIdx = -1;

  function hideDropdown() {
    dropdown.innerHTML = "";
    dropdown.style.display = "none";
    input.setAttribute("aria-expanded", "false");
    activeIdx = -1;
  }

  function renderItems(items) {
    if (!items || !items.length) {
      hideDropdown();
      return;
    }
    dropdown.innerHTML = items.map(function(item, i) {
      return '<li role="option" class="autocomplete-item" data-index="' + i + '" data-value="' + _escapeHtml(item.value) + '">' +
        '<span class="autocomplete-value">' + _escapeHtml(item.value) + '</span>' +
        (item.label ? '<span class="autocomplete-label">' + _escapeHtml(item.label) + '</span>' : '') +
        '</li>';
    }).join("");
    dropdown.style.display = "block";
    input.setAttribute("aria-expanded", "true");
    activeIdx = -1;
  }

  function setActive(idx) {
    var items = dropdown.querySelectorAll("li");
    items.forEach(function(li) { li.classList.remove("active"); li.removeAttribute("aria-selected"); });
    if (idx >= 0 && idx < items.length) {
      items[idx].classList.add("active");
      items[idx].setAttribute("aria-selected", "true");
      items[idx].scrollIntoView({ block: "nearest" });
      activeIdx = idx;
    } else {
      activeIdx = -1;
    }
  }

  function selectItem(li) {
    if (!li) return;
    input.value = li.getAttribute("data-value") || li.querySelector(".autocomplete-value").textContent;
    hideDropdown();
    // Submit the hero search form
    var form = input.closest("form");
    if (form) form.submit();
  }

  input.addEventListener("input", function() {
    clearTimeout(acTimer);
    var val = input.value.trim();
    if (val.length < 2) {
      hideDropdown();
      return;
    }
    acTimer = setTimeout(function() {
      fetch("/api/v1/search/suggest?q=" + encodeURIComponent(val) + "&limit=5")
        .then(function(r) { return r.json(); })
        .then(function(items) { renderItems(items); })
        .catch(function() { hideDropdown(); });
    }, 200);
  });

  input.addEventListener("keydown", function(e) {
    var items = dropdown.querySelectorAll("li");
    if (!items.length || dropdown.style.display === "none") return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive(activeIdx < items.length - 1 ? activeIdx + 1 : 0);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive(activeIdx > 0 ? activeIdx - 1 : items.length - 1);
    } else if (e.key === "Enter") {
      if (activeIdx >= 0 && activeIdx < items.length) {
        e.preventDefault();
        selectItem(items[activeIdx]);
      }
      // Otherwise let the form submit naturally
    } else if (e.key === "Escape") {
      hideDropdown();
    }
  });

  dropdown.addEventListener("click", function(e) {
    var li = e.target.closest("li");
    if (li) selectItem(li);
  });

  // Close on click outside
  document.addEventListener("click", function(e) {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) {
      hideDropdown();
    }
  });
}

// ── Multi-PE selection for Spruill comparison ────────────────────────────────

function updatePeCompareBar() {
  var checkboxes = document.querySelectorAll(".pe-select-checkbox:checked");
  var bar = document.getElementById("pe-compare-bar");
  var countEl = document.getElementById("pe-compare-count");
  var linkEl = document.getElementById("pe-compare-link");
  if (!bar) return;
  if (checkboxes.length > 0) {
    bar.hidden = false;
    countEl.textContent = checkboxes.length;
    var pes = Array.from(checkboxes).map(function(cb) { return cb.value; });
    linkEl.href = "/spruill?" + pes.map(function(pe) { return "pe=" + encodeURIComponent(pe); }).join("&");
  } else {
    bar.hidden = true;
  }
}

function clearPeSelection() {
  document.querySelectorAll(".pe-select-checkbox:checked").forEach(function(cb) { cb.checked = false; });
  updatePeCompareBar();
}

// Delegate click events for checkboxes (works with HTMX swaps)
document.addEventListener("change", function(e) {
  if (e.target.classList.contains("pe-select-checkbox")) {
    updatePeCompareBar();
  }
});

// ── Programs page sort direction helper ──────────────────────────────────────

(function() {
  var sortSelect = document.getElementById("pe-sort");
  if (sortSelect) {
    sortSelect.addEventListener("change", function() {
      var dirInput = document.getElementById("pe-sort-dir");
      if (dirInput) {
        dirInput.value = this.value === "funding" ? "desc" : "asc";
      }
    });
  }
})();

// ── Saved searches (localStorage) ───────────────────────────────────────────

function showSaveSearchInput() {
  var panel = document.getElementById("save-search-inline");
  var nameInput = document.getElementById("save-search-name");
  if (panel) {
    panel.style.display = "";
    if (nameInput) { nameInput.value = ""; nameInput.focus(); }
  }
}

function hideSaveSearchInput() {
  var panel = document.getElementById("save-search-inline");
  if (panel) panel.style.display = "none";
}

function confirmSaveSearch() {
  var nameInput = document.getElementById("save-search-name");
  var name = nameInput ? nameInput.value.trim() : "";
  if (name) {
    saveCurrentSearch(name);
    hideSaveSearchInput();
  } else {
    nameInput && nameInput.focus();
  }
}

// Allow Enter key to confirm save
document.addEventListener("keydown", function (e) {
  if (e.key === "Enter" && e.target.id === "save-search-name") {
    e.preventDefault();
    confirmSaveSearch();
  }
});

var SAVED_SEARCHES_KEY = "dod_saved_searches";

function getSavedSearches() {
  try { return JSON.parse(localStorage.getItem(SAVED_SEARCHES_KEY) || "[]"); }
  catch (e) { return []; }
}

function saveCurrentSearch(name) {
  if (!name) return;
  var searches = getSavedSearches();
  searches.push({
    name: name,
    query: window.location.search,
    date: new Date().toISOString().slice(0, 10)
  });
  if (searches.length > 20) searches = searches.slice(-20);
  localStorage.setItem(SAVED_SEARCHES_KEY, JSON.stringify(searches));
  renderSavedSearches();
  if (typeof showToast === "function") showToast('Search "' + name + '" saved', "success");
}

function deleteSavedSearch(index) {
  var searches = getSavedSearches();
  searches.splice(index, 1);
  localStorage.setItem(SAVED_SEARCHES_KEY, JSON.stringify(searches));
  renderSavedSearches();
}

function renderSavedSearches() {
  var container = document.getElementById("saved-searches-list");
  if (!container) return;
  var searches = getSavedSearches();
  if (!searches.length) {
    container.innerHTML = '<p style="font-size:.78rem;color:var(--text-secondary)">No saved searches yet.</p>';
    return;
  }
  container.innerHTML = searches.map(function (s, i) {
    var qs = (s.query || "").replace(/^\?/, "");
    return '<div class="saved-search-item">' +
      '<a href="/?' + _escapeHtml(qs) + '" style="font-size:.82rem">' + _escapeHtml(s.name) + "</a>" +
      '<span style="font-size:.7rem;color:var(--text-secondary);margin-left:.25rem">' + (s.date || "") + "</span>" +
      '<button class="remove" onclick="deleteSavedSearch(' + i + ')" aria-label="Delete" ' +
      'style="margin-left:auto;background:none;border:none;cursor:pointer;color:var(--clr-red);font-size:.85rem">&times;</button>' +
      "</div>";
  }).join("");
}
