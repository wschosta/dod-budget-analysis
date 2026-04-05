/**
 * Sparkline — inline SVG funding timeline for search result rows.
 *
 * Reads data-raw attributes from .td-amount cells in each table row and
 * renders a mini bar chart showing the funding trend across fiscal years.
 * Uses CSS custom properties for theming (light/dark mode).
 *
 * Call initSparklines() after page load and each HTMX swap.
 */
(function () {
  "use strict";

  var SPARK_KEY = "dod_sparklines";
  var W = 120;
  var H = 28;
  var BAR_GAP = 1;

  /**
   * Build an SVG sparkline string from an array of numeric values.
   * @param {number[]} values - amounts in $K (may include NaN/null)
   * @param {{bar: string, neg: string, bg: string}} colors - resolved CSS colors
   * @returns {string} SVG markup, or empty string if no data
   */
  function buildSparklineSVG(values, colors) {
    var hasData = false;
    var maxVal = 0;
    for (var i = 0; i < values.length; i++) {
      var v = values[i];
      if (v != null && !isNaN(v)) {
        hasData = true;
        if (Math.abs(v) > maxVal) maxVal = Math.abs(v);
      }
    }
    if (!hasData) return "";
    if (maxVal === 0) maxVal = 1;

    var totalSlots = values.length;
    var barW = Math.max(2, (W - BAR_GAP * (totalSlots - 1)) / totalSlots);

    var rects = "";
    for (var k = 0; k < values.length; k++) {
      var x = k * (barW + BAR_GAP);
      var v2 = values[k];
      if (v2 == null || isNaN(v2)) {
        rects += '<rect x="' + x + '" y="' + (H - 2) + '" width="' + barW +
          '" height="2" fill="' + colors.bg + '" rx="0.5"/>';
        continue;
      }
      var barH = Math.max(2, (Math.abs(v2) / maxVal) * (H - 2));
      var y = H - barH;
      var fill = v2 >= 0 ? colors.bar : colors.neg;
      rects += '<rect x="' + x + '" y="' + y + '" width="' + barW +
        '" height="' + barH + '" fill="' + fill + '" rx="1"/>';
    }

    return '<svg width="' + W + '" height="' + H +
      '" viewBox="0 0 ' + W + ' ' + H +
      '" role="img" aria-label="Funding trend">' + rects + '</svg>';
  }

  function sparklinesEnabled() {
    return localStorage.getItem(SPARK_KEY) !== "off";
  }

  /**
   * Render sparklines for all table rows in the results container.
   */
  function renderSparklines() {
    if (!sparklinesEnabled()) return;

    var cells = document.querySelectorAll(".td-sparkline");
    if (cells.length === 0) return;

    // Resolve CSS colors once for the entire batch
    var styles = getComputedStyle(document.documentElement);
    var colors = {
      bar: styles.getPropertyValue("--clr-blue").trim() || "#1a5bd6",
      neg: styles.getPropertyValue("--clr-red").trim() || "#c42b2b",
      bg:  styles.getPropertyValue("--border-color").trim() || "#e5e7eb"
    };

    cells.forEach(function (cell) {
      var row = cell.closest("tr");
      if (!row) return;
      var values = [];
      row.querySelectorAll(".td-amount").forEach(function (td) {
        var raw = td.getAttribute("data-raw");
        values.push(raw != null ? parseFloat(raw) : NaN);
      });
      cell.innerHTML = buildSparklineSVG(values, colors);
    });
  }

  /**
   * Apply sparkline column visibility and sync toggle button state.
   */
  function applySparklineVisibility() {
    var show = sparklinesEnabled();
    document.querySelectorAll(".col-sparkline").forEach(function (el) {
      el.style.display = show ? "" : "none";
    });
    var btn = document.querySelector('[data-col="sparkline"]');
    if (btn) btn.classList.toggle("active", show);
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
  }

  /**
   * Initialize sparklines: apply visibility, sync button, render if enabled.
   * Call from DOMContentLoaded and htmx:afterSwap.
   */
  function initSparklines() {
    applySparklineVisibility();
    renderSparklines();
  }

  window.renderSparklines = renderSparklines;
  window.toggleSparklines = toggleSparklines;
  window.initSparklines = initSparklines;
})();
