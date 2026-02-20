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

    // Group by fiscal year, summing amounts
    var byFY = {};
    data.years.forEach(function (y) {
      var fy = y.fiscal_year || "Unknown";
      if (!byFY[fy]) {
        byFY[fy] = { fy24: 0, fy25: 0, fy26: 0 };
      }
      byFY[fy].fy24 += (y.fy2024_actual || 0);
      byFY[fy].fy25 += (y.fy2025_enacted || 0);
      byFY[fy].fy26 += (y.fy2026_request || 0);
    });

    var labels = Object.keys(byFY).sort();
    var fy24Data = labels.map(function (l) { return byFY[l].fy24 / 1000; });
    var fy25Data = labels.map(function (l) { return byFY[l].fy25 / 1000; });
    var fy26Data = labels.map(function (l) { return byFY[l].fy26 / 1000; });

    new Chart(canvas, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          { label: "FY24 Actual ($M)", data: fy24Data, backgroundColor: COLORS[0], borderRadius: 3 },
          { label: "FY25 Enacted ($M)", data: fy25Data, backgroundColor: COLORS[1], borderRadius: 3 },
          { label: "FY26 Request ($M)", data: fy26Data, backgroundColor: COLORS[2], borderRadius: 3 }
        ]
      },
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
  } catch (e) {
    // Silently fail — chart is a nice-to-have enhancement
  }
})();
