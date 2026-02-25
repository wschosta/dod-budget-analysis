/**
 * DoD Budget Explorer — program-detail.js
 * Renders the funding trend chart on the Program Element detail page.
 */

"use strict";

(async function () {
  var pathParts = window.location.pathname.split("/");
  var pe = pathParts[pathParts.length - 1];
  if (!pe) return;

  var canvas = document.getElementById("pe-funding-chart");
  if (!canvas) return;

  var COLORS = [
    "#2563eb", "#16a34a", "#d97706", "#dc2626", "#7c3aed",
    "#0891b2", "#c2410c", "#065f46"
  ];

  try {
    var resp = await fetch("/api/v1/pe/" + encodeURIComponent(pe) + "/years");
    if (!resp.ok) return;
    var data = await resp.json();

    if (!data.years || !data.years.length) {
      canvas.parentElement.innerHTML = '<p style="color:var(--text-secondary);font-size:.85rem">No funding data available for chart.</p>';
      return;
    }

    // Detect all FY amount keys dynamically
    var sampleYear = data.years[0];
    var fyKeys = Object.keys(sampleYear).filter(function(k) {
      return /^fy\d{4}_/.test(k);
    }).sort();

    if (!fyKeys.length) {
      canvas.parentElement.innerHTML = '<p style="color:var(--text-secondary);font-size:.85rem">No funding data available for chart.</p>';
      return;
    }

    // Group by fiscal year, summing amounts
    var byFY = {};
    data.years.forEach(function (y) {
      var fy = y.fiscal_year || "Unknown";
      if (!byFY[fy]) {
        byFY[fy] = {};
        fyKeys.forEach(function(k) { byFY[fy][k] = 0; });
      }
      fyKeys.forEach(function(k) { byFY[fy][k] += (y[k] || 0); });
    });

    var labels = Object.keys(byFY).sort();

    // Build datasets dynamically
    var datasets = fyKeys.map(function(key, i) {
      var label = key.replace(/^fy/, 'FY').replace(/_actual/, ' Actual').replace(/_enacted/, ' Enacted').replace(/_request/, ' Request').replace(/_total/, ' Total').replace(/_supplemental/, ' Supp.').replace(/_reconciliation/, ' Recon.');
      return {
        label: label + " ($M)",
        data: labels.map(function(l) { return byFY[l][key] / 1000; }),
        backgroundColor: COLORS[i % COLORS.length],
        borderRadius: 3
      };
    });

    new Chart(canvas, {
      type: "bar",
      data: { labels: labels, datasets: datasets },
      options: {
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } }
        },
        scales: {
          y: {
            ticks: {
              callback: function (v) { return "$" + v.toLocaleString() + "M"; }
            }
          }
        }
      }
    });

    // A4.3: Add export button for funding trend chart
    if (typeof addChartExportButton === "function") {
      addChartExportButton("pe-funding-chart", "program-" + pe + "-funding-trend.png");
    }
  } catch (e) {
    // Silently fail — chart is a nice-to-have enhancement
  }

  // ── Quantity column toggle ──────────────────────────────────────────────────
  var qtyToggle = document.getElementById("qty-toggle");
  if (qtyToggle) {
    qtyToggle.addEventListener("click", function() {
      var cells = document.querySelectorAll(".qty-col");
      var show = this.getAttribute("aria-pressed") !== "true";
      this.setAttribute("aria-pressed", String(show));
      this.textContent = show ? "Hide Quantities" : "Show Quantities";
      cells.forEach(function(c) { c.style.display = show ? "" : "none"; });
    });
  }
})();
