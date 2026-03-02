/**
 * DoD Budget Explorer — dashboard.js
 * Fetches /api/v1/dashboard/summary and renders stat cards + charts.
 */

"use strict";

// Colors and formatters provided by fmt.js (loaded from base.html).
var DASH_COLORS = BUDGET_COLORS;
var fmtDollarsM = fmtDollars;
var fmtCount = fmtInt;

// showDashError provided by fmt.js as showChartError(); alias kept.
var showDashError = showChartError;

(async function initDashboard() {
  var loadingEl = document.getElementById("dash-loading");
  var chartsEl = document.getElementById("dash-charts");
  var programsEl = document.getElementById("dash-programs");

  // 3.6: Show extended loading message after 3 seconds
  var loadingTimer = setTimeout(function() {
    if (loadingEl) {
      loadingEl.innerHTML = '<span class="spinner"></span> Still loading dashboard data&hellip; This may take a moment for large datasets.';
    }
  }, 3000);

  try {
    var resp = await fetch("/api/v1/dashboard/summary");
    clearTimeout(loadingTimer);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    var data = await resp.json();

    // Hide loading, show charts
    if (loadingEl) loadingEl.style.display = "none";
    if (chartsEl) chartsEl.style.display = "";
    if (programsEl) programsEl.style.display = "";

    // ── Stat cards ──────────────────────────────────────────────────────────
    var t = data.totals || {};
    var statFy26 = document.getElementById("stat-total-fy26");
    var statFy25 = document.getElementById("stat-total-fy25");
    var statYoy = document.getElementById("stat-yoy-change");
    var statCount = document.getElementById("stat-line-count");

    if (statFy26) statFy26.textContent = fmtDollarsM(t.total_fy26_request);
    if (statFy25) statFy25.textContent = fmtDollarsM(t.total_fy25_enacted);
    if (statCount) statCount.textContent = fmtCount(t.total_lines);

    if (statYoy && t.total_fy25_enacted && t.total_fy26_request) {
      var pct = ((t.total_fy26_request - t.total_fy25_enacted) / Math.abs(t.total_fy25_enacted) * 100);
      statYoy.textContent = (pct >= 0 ? "+" : "") + pct.toFixed(1) + "%";
      statYoy.parentElement.classList.add(pct >= 0 ? "stat-positive" : "stat-negative");
    }

    // Display data freshness
    if (data.freshness && data.freshness.last_build) {
      var freshnessEl = document.getElementById("stat-freshness");
      if (freshnessEl) {
        var d = new Date(data.freshness.last_build);
        freshnessEl.textContent = d.toLocaleDateString();
      }
    }

    // ── Service bar chart ───────────────────────────────────────────────────
    if (data.by_service && data.by_service.length) {
      var svcLabels = data.by_service.map(function(r) { return r.service || "Unknown"; });
      var svcAmounts = data.by_service.map(function(r) { return (r.total || 0) / 1000; }); // $M

      new Chart(document.getElementById("dash-service-chart"), {
        type: "bar",
        data: {
          labels: svcLabels,
          datasets: [{
            label: "Latest Request ($M)",
            data: svcAmounts,
            backgroundColor: DASH_COLORS,
            borderRadius: 4
          }]
        },
        options: {
          indexAxis: "y",
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { callback: tickDollarsM } }
          },
          onHover: chartPointerHover,
          onClick: function(e, elements) {
            if (elements.length) {
              var idx = elements[0].index;
              window.location.href = "/?service=" + encodeURIComponent(svcLabels[idx]);
            }
          }
        }
      });
      // A4.3: Add export button for service chart
      if (typeof addChartExportButton === "function") {
        addChartExportButton("dash-service-chart", "dashboard-service-chart.png");
      }
    } else {
      showDashError("err-dash-service", "dash-service-chart", "No service data available.");
    }

    // ── Budget Type doughnut chart ───────────────────────────────────────────
    if (data.by_budget_type && data.by_budget_type.length) {
      var btLabels = data.by_budget_type.map(function(r) {
        return r.budget_type || "Unknown";
      });
      var btAmounts = data.by_budget_type.map(function(r) { return (r.total || 0) / 1000; });

      new Chart(document.getElementById("dash-approp-chart"), {
        type: "doughnut",
        data: {
          labels: btLabels,
          datasets: [{
            data: btAmounts,
            backgroundColor: DASH_COLORS.slice(0, btLabels.length),
            borderWidth: 2,
            borderColor: getComputedStyle(document.documentElement).getPropertyValue("--bg-surface").trim() || "#fff"
          }]
        },
        options: {
          plugins: {
            legend: {
              position: "right",
              labels: { boxWidth: 12, font: { size: 11 } }
            },
            tooltip: { callbacks: { label: tooltipDoughnutPct } }
          },
          onHover: chartPointerHover,
          onClick: function(e, elements) {
            if (elements.length) {
              var idx = elements[0].index;
              var bt = data.by_budget_type[idx];
              if (bt.budget_type) {
                window.location.href = "/?budget_type=" + encodeURIComponent(bt.budget_type);
              }
            }
          }
        }
      });
      if (typeof addChartExportButton === "function") {
        addChartExportButton("dash-approp-chart", "dashboard-budget-type-chart.png");
      }
    } else {
      showDashError("err-dash-approp", "dash-approp-chart", "No budget type data available.");
    }

    // ── Top 10 programs table ───────────────────────────────────────────────
    var container = document.getElementById("dash-top-programs");
    if (container && data.top_programs && data.top_programs.length) {
      var html = '<table class="top-programs-table">';
      html += "<thead><tr><th>#</th><th>Program</th><th>Service</th><th>PE #</th>";
      html += '<th class="td-amount">Request ($K)</th>';
      html += '<th class="td-amount">Prior Enacted ($K)</th>';
      html += '<th class="td-amount">Delta</th></tr></thead><tbody>';

      data.top_programs.forEach(function(p, i) {
        var title = p.line_item_title || "Unknown";
        var org = p.organization_name || "—";
        var pe = p.pe_number || "—";
        var fy26 = p.fy26_request;
        var fy25 = p.fy25_enacted;
        var deltaHtml = "—";
        if (fy25 && fy26 && fy25 !== 0) {
          var deltaPct = ((fy26 - fy25) / Math.abs(fy25)) * 100;
          var cls = deltaPct >= 0 ? "delta positive" : "delta negative";
          deltaHtml = '<span class="' + cls + '">' + (deltaPct >= 0 ? "+" : "") + deltaPct.toFixed(1) + "%</span>";
        }

        var href = pe !== "—" ? "/programs/" + encodeURIComponent(pe) : "/?q=" + encodeURIComponent(title);
        html += "<tr>";
        html += "<td>" + (i + 1) + "</td>";
        html += '<td><a href="' + href + '">' + escapeHtml(title.length > 50 ? title.slice(0, 48) + "…" : title) + "</a></td>";
        html += "<td>" + escapeHtml(org) + "</td>";
        html += '<td style="font-family:monospace;font-size:.8rem">' + escapeHtml(pe) + "</td>";
        html += '<td class="td-amount">' + (fy26 != null ? Number(fy26).toLocaleString() : "—") + "</td>";
        html += '<td class="td-amount">' + (fy25 != null ? Number(fy25).toLocaleString() : "—") + "</td>";
        html += '<td class="td-amount">' + deltaHtml + "</td>";
        html += "</tr>";
      });

      html += "</tbody></table>";
      container.innerHTML = html;
    }

  } catch (err) {
    clearTimeout(loadingTimer);
    if (loadingEl) {
      loadingEl.innerHTML =
        '<div class="empty-state">' +
        '<div class="empty-state-icon" aria-hidden="true">&#128202;</div>' +
        '<p><strong>Dashboard data unavailable</strong></p>' +
        '<p style="font-size:.85rem;max-width:480px;margin:.5rem auto">Could not load dashboard summary (' + escapeHtml(err.message) + '). ' +
        'Make sure the database has been built by running <code>python build_budget_db.py</code> ' +
        'and the API server is running.</p>' +
        '<div style="margin-top:1rem">' +
        '<a href="/" class="btn btn-primary btn-sm">Go to Search</a>' +
        '</div></div>';
    }
  }
  // escapeHtml provided by fmt.js (loaded from base.html).
})();
