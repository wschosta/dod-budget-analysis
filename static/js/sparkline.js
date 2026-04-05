/**
 * Sparkline — inline SVG funding timeline for search result rows.
 *
 * Reads data-raw attributes from .td-amount cells in each table row and
 * renders a mini bar chart showing the funding trend across fiscal years.
 * Uses CSS custom properties for theming (light/dark mode).
 *
 * Call renderSparklines() after each HTMX swap to (re-)draw all sparklines.
 */
(function () {
  "use strict";

  var SPARK_KEY = "dod_sparklines";
  var W = 120;
  var H = 28;
  var BAR_GAP = 1;

  /**
   * Get the computed value of a CSS custom property.
   * @param {string} prop - e.g. "--clr-blue"
   * @param {string} fallback
   * @returns {string}
   */
  function cssVar(prop, fallback) {
    var val = getComputedStyle(document.documentElement).getPropertyValue(prop).trim();
    return val || fallback;
  }

  /**
   * Build an SVG sparkline string from an array of numeric values.
   * @param {number[]} values - amounts in $K (may include NaN/null)
   * @returns {string} SVG markup, or empty string if no data
   */
  function buildSparklineSVG(values) {
    // Filter to numeric values but keep track of positions
    var pairs = [];
    for (var i = 0; i < values.length; i++) {
      var v = values[i];
      if (v != null && !isNaN(v)) {
        pairs.push({ idx: i, val: v });
      }
    }
    if (pairs.length === 0) return "";

    var maxVal = 0;
    for (var j = 0; j < pairs.length; j++) {
      if (Math.abs(pairs[j].val) > maxVal) maxVal = Math.abs(pairs[j].val);
    }
    if (maxVal === 0) maxVal = 1; // avoid division by zero

    var totalSlots = values.length;
    var barW = Math.max(2, (W - BAR_GAP * (totalSlots - 1)) / totalSlots);
    var barColor = cssVar("--clr-blue", "#1a5bd6");
    var negColor = cssVar("--clr-red", "#c42b2b");
    var bgColor = cssVar("--border-color", "#e5e7eb");

    var rects = "";
    for (var k = 0; k < values.length; k++) {
      var x = k * (barW + BAR_GAP);
      var v2 = values[k];
      if (v2 == null || isNaN(v2)) {
        // Render a thin placeholder for missing values
        rects += '<rect x="' + x + '" y="' + (H - 2) + '" width="' + barW +
          '" height="2" fill="' + bgColor + '" rx="0.5"/>';
        continue;
      }
      var barH = Math.max(2, (Math.abs(v2) / maxVal) * (H - 2));
      var y = H - barH;
      var fill = v2 >= 0 ? barColor : negColor;
      rects += '<rect x="' + x + '" y="' + y + '" width="' + barW +
        '" height="' + barH + '" fill="' + fill + '" rx="1"/>';
    }

    return '<svg width="' + W + '" height="' + H +
      '" viewBox="0 0 ' + W + ' ' + H +
      '" role="img" aria-label="Funding trend">' + rects + '</svg>';
  }

  /**
   * Render sparklines for all table rows in the results container.
   * Reads data-raw from each .td-amount cell per row.
   */
  function renderSparklines() {
    var cells = document.querySelectorAll(".td-sparkline");
    if (cells.length === 0) return;

    cells.forEach(function (cell) {
      var row = cell.closest("tr");
      if (!row) return;
      var amountCells = row.querySelectorAll(".td-amount[data-raw]");
      var values = [];
      // Collect all amount columns in order (including those without data-raw)
      var allAmountCells = row.querySelectorAll(".td-amount");
      allAmountCells.forEach(function (td) {
        var raw = td.getAttribute("data-raw");
        values.push(raw != null ? parseFloat(raw) : NaN);
      });
      cell.innerHTML = buildSparklineSVG(values);
    });
  }

  /**
   * Check if sparklines are enabled (persisted in localStorage).
   * @returns {boolean}
   */
  function sparklinesEnabled() {
    return localStorage.getItem(SPARK_KEY) !== "off";
  }

  /**
   * Toggle sparkline column visibility.
   * @param {boolean} [show] - force on/off; omit to toggle
   */
  function toggleSparklines(show) {
    if (show === undefined) show = !sparklinesEnabled();
    localStorage.setItem(SPARK_KEY, show ? "on" : "off");
    applySparklineVisibility();
    if (show) renderSparklines();
    // Update toggle button state
    var btn = document.querySelector('[data-col="sparkline"]');
    if (btn) btn.classList.toggle("active", show);
  }

  /**
   * Apply sparkline column visibility based on saved preference.
   */
  function applySparklineVisibility() {
    var show = sparklinesEnabled();
    document.querySelectorAll(".col-sparkline").forEach(function (el) {
      el.style.display = show ? "" : "none";
    });
  }

  // Expose globals
  window.renderSparklines = renderSparklines;
  window.toggleSparklines = toggleSparklines;
  window.applySparklineVisibility = applySparklineVisibility;
  window.sparklinesEnabled = sparklinesEnabled;
})();
