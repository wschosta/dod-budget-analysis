/**
 * DoD Budget Explorer — fmt.js
 *
 * Shared formatting utilities and color palette used by dashboard.js,
 * charts.js, app.js, and program-detail.js.  Load this BEFORE any page-
 * specific JS file that needs formatting or chart helpers.
 *
 * Previously each file duplicated its own fmtDollarsM / formatAmount /
 * CHART_COLORS / tick callback.  Now they all import from here.
 */

"use strict";

// ── Color palette ────────────────────────────────────────────────────────────
// 10-color palette matching the CSS design tokens.
var BUDGET_COLORS = [
  "#2563eb", "#16a34a", "#d97706", "#dc2626", "#7c3aed",
  "#0891b2", "#c2410c", "#065f46", "#92400e", "#1e1b4b"
];

// ── Number formatters ────────────────────────────────────────────────────────

/**
 * Format a dollar amount (in $K) for display.
 *
 * - >= 1 000 000 K  → "$X.XB"
 * - >= 1 000 K      → "$X,XXXM"  (locale-grouped, no decimals)
 * - < 1 000 K       → "$XXXK"
 * - null / NaN       → "—"
 *
 * @param {number|null} valK - Amount in thousands of dollars.
 * @returns {string}
 */
function fmtDollars(valK) {
  if (valK == null || isNaN(valK)) return "\u2014";
  var m = valK / 1000;
  if (Math.abs(m) >= 1000) {
    return "$" + (m / 1000).toFixed(1) + "B";
  }
  return "$" + m.toLocaleString(undefined, { maximumFractionDigits: 0 }) + "M";
}

/**
 * Format an integer count with locale grouping (e.g. 1,234,567).
 * Returns "—" for null/undefined.
 *
 * @param {number|null} val
 * @returns {string}
 */
function fmtInt(val) {
  if (val == null) return "\u2014";
  return val.toLocaleString();
}

/**
 * Format a percentage with sign prefix (e.g. "+12.3%" or "−4.0%").
 *
 * @param {number|null} pct
 * @param {number} [digits=1] - decimal places
 * @returns {string}
 */
function fmtPct(pct, digits) {
  if (pct == null || isNaN(pct)) return "\u2014";
  if (digits === undefined) digits = 1;
  return (pct >= 0 ? "+" : "") + pct.toFixed(digits) + "%";
}

// ── Chart.js helpers ─────────────────────────────────────────────────────────

/**
 * Reusable Chart.js tick callback that formats values as "$X,XXXM".
 * Use directly: `ticks: { callback: tickDollarsM }`.
 *
 * @param {number} v - Axis value (already in $M).
 * @returns {string}
 */
function tickDollarsM(v) {
  return "$" + v.toLocaleString() + "M";
}

/**
 * Reusable Chart.js tooltip label callback for dollar amounts in $M.
 *
 * @param {object} ctx - Chart.js tooltip context.
 * @returns {string}
 */
function tooltipDollarsM(ctx) {
  var val = ctx.parsed !== undefined ? ctx.parsed : (ctx.raw || 0);
  if (typeof val === "object" && val !== null) val = val.y || val.x || 0;
  var label = ctx.dataset ? ctx.dataset.label : "";
  return (label ? label + ": " : "") +
    "$" + Number(val).toLocaleString(undefined, { maximumFractionDigits: 0 }) + "M";
}

/**
 * Chart.js doughnut tooltip callback showing "$X,XXXM (XX.X%)".
 * Computes percentage from the dataset total automatically.
 *
 * @param {object} ctx - Chart.js tooltip context.
 * @returns {string}
 */
function tooltipDoughnutPct(ctx) {
  var total = ctx.dataset.data.reduce(function(a, b) { return a + b; }, 0);
  var pct = total > 0 ? (ctx.parsed / total * 100).toFixed(1) : 0;
  return ctx.label + ": $" + ctx.parsed.toLocaleString() + "M (" + pct + "%)";
}

/**
 * Chart.js onHover callback that sets pointer cursor over chart elements.
 * Previously duplicated 8 times across dashboard.js, charts.js, app.js,
 * and budget-charts.js.
 *
 * Usage: `onHover: chartPointerHover`
 */
function chartPointerHover(e, elements) {
  e.native.target.style.cursor = elements.length ? "pointer" : "default";
}

/**
 * Show an error message in place of a chart canvas.
 * Previously duplicated as showDashError (dashboard.js) and
 * showChartError (charts.js).
 *
 * @param {string} errId   - ID of the error text element.
 * @param {string} canvasId - ID of the canvas to hide.
 * @param {string} msg     - Error message to display.
 */
function showChartError(errId, canvasId, msg) {
  var el = document.getElementById(errId);
  var canvas = document.getElementById(canvasId);
  if (el) { el.textContent = msg; el.style.display = ""; }
  if (canvas) canvas.style.display = "none";
}

// ── DOM helpers ──────────────────────────────────────────────────────────────

/**
 * Escape HTML special characters to prevent XSS when inserting into the DOM.
 * Previously duplicated in app.js (_escapeHtml) and dashboard.js (escapeHtml).
 *
 * @param {string} s
 * @returns {string}
 */
function escapeHtml(s) {
  if (!s) return "";
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
