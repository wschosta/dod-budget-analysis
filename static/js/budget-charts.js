/**
 * DoD Budget Explorer -- budget-charts.js
 * Shared budget type doughnut chart utility.
 *
 * Used by both the home page (app.js) and charts page (charts.js) to render
 * the "By Budget Type" doughnut chart.  Extracts to a single function so that
 * both pages use identical data-fetching and rendering logic.
 */

"use strict";

/**
 * Fetch budget_type aggregation data and render a doughnut chart.
 *
 * @param {string} canvasId  - ID of the <canvas> element to render into
 * @param {object} [opts]    - Options:
 *   @param {function} [opts.onClick]       - callback(budgetType) when slice clicked
 *   @param {string[]} [opts.colors]        - colour palette (defaults to CHART_COLORS or LANDING_COLORS)
 *   @param {string[]} [opts.serviceFilter] - service names to pass as aggregation filter
 *   @param {function} [opts.onError]       - callback(errMsg) on failure
 *   @param {function} [opts.onEmpty]       - callback() when no data
 * @returns {Promise<Chart|null>} - The Chart.js instance, or null on failure
 */
async function renderBudgetTypeDoughnut(canvasId, opts) {
  opts = opts || {};
  var canvas = document.getElementById(canvasId);
  if (!canvas) return null;

  // Build URL
  var url = "/api/v1/aggregations?group_by=budget_type";
  if (opts.serviceFilter && opts.serviceFilter.length) {
    opts.serviceFilter.forEach(function(s) {
      url += "&service=" + encodeURIComponent(s);
    });
  }

  try {
    var resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    var data = await resp.json();

    if (!data || !data.rows || !data.rows.length) {
      if (opts.onEmpty) opts.onEmpty();
      return null;
    }

    // Find the best FY request column from fy_totals.
    // Prefer FY2026 request, but if it has data for fewer than 3 budget types,
    // fall back to the latest request column with broad coverage.
    var amtKey = "amount_fy2026_request";
    if (data.rows[0] && data.rows[0].fy_totals) {
      var ftKeys = Object.keys(data.rows[0].fy_totals).sort();
      var reqKeys = ftKeys.filter(function(k) { return k.includes("request"); });

      // Check coverage of preferred key
      var prefCoverage = data.rows.filter(function(r) {
        return r.fy_totals && r.fy_totals[amtKey] && r.fy_totals[amtKey] > 0;
      }).length;

      if (prefCoverage < 3) {
        // Pick the latest request column with data for 3+ budget types
        for (var i = reqKeys.length - 1; i >= 0; i--) {
          var k = reqKeys[i];
          var cov = data.rows.filter(function(r) {
            return r.fy_totals && r.fy_totals[k] && r.fy_totals[k] > 0;
          }).length;
          if (cov >= 3) { amtKey = k; break; }
        }
      }
    }

    // Extract amounts from fy_totals, filter out null/zero and "Unknown"
    var filtered = data.rows.filter(function(r) {
      var val = r.fy_totals ? r.fy_totals[amtKey] : null;
      return val && val > 0 && r.group_value !== "Unknown";
    });

    if (!filtered.length) {
      if (opts.onEmpty) opts.onEmpty();
      return null;
    }

    var labels = filtered.map(function(r) { return r.group_value || "Unknown"; });
    var amounts = filtered.map(function(r) { return (r.fy_totals[amtKey] || 0) / 1000; });

    // Use provided colours or fall back to common palettes
    var defaultColors = (typeof BUDGET_COLORS !== "undefined") ? BUDGET_COLORS
                      : ["#2563eb", "#16a34a", "#d97706", "#dc2626", "#7c3aed",
                         "#0891b2", "#c2410c", "#065f46", "#92400e", "#1e1b4b"];
    var colors = opts.colors || defaultColors;

    var borderColor = getComputedStyle(document.documentElement)
      .getPropertyValue("--bg-surface").trim() || "#fff";

    var chart = new Chart(canvas, {
      type: "doughnut",
      data: {
        labels: labels,
        datasets: [{
          data: amounts,
          backgroundColor: colors.slice(0, labels.length),
          borderWidth: 2,
          borderColor: borderColor,
        }],
      },
      options: {
        plugins: {
          legend: {
            position: "right",
            labels: { boxWidth: 12, font: { size: 11 } },
          },
          tooltip: {
            callbacks: {
              label: function(ctx) {
                var total = ctx.dataset.data.reduce(function(a, b) { return a + b; }, 0);
                var pct = total > 0 ? (ctx.parsed / total * 100).toFixed(1) : 0;
                return ctx.label + ": $" + ctx.parsed.toLocaleString() + "M (" + pct + "%)";
              },
            },
          },
        },
        onHover: function(e, elements) {
          e.native.target.style.cursor = elements.length ? "pointer" : "default";
        },
        onClick: function(e, elements) {
          if (elements.length && opts.onClick) {
            var idx = elements[0].index;
            var budgetType = filtered[idx].group_value;
            if (budgetType) opts.onClick(budgetType);
          }
        },
      },
    });

    return chart;
  } catch (err) {
    if (opts.onError) opts.onError(err.message);
    return null;
  }
}
