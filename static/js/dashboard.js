/**
 * DoD Budget Explorer — dashboard.js
 * Fetches /api/v1/dashboard/summary and renders stat cards + charts.
 */

"use strict";

var DASH_COLORS = [
  "#2563eb", "#16a34a", "#d97706", "#dc2626", "#7c3aed",
  "#0891b2", "#c2410c", "#065f46", "#92400e", "#1e1b4b"
];

function fmtDollarsM(val) {
  if (val == null) return "--";
  var m = val / 1000;  // amounts are in $K, convert to $M
  if (Math.abs(m) >= 1000) {
    return "$" + (m / 1000).toFixed(1) + "B";
  }
  return "$" + m.toLocaleString(undefined, {maximumFractionDigits: 0}) + "M";
}

function fmtCount(val) {
  if (val == null) return "--";
  return val.toLocaleString();
}

function showDashError(id, canvasId, msg) {
  var el = document.getElementById(id);
  var canvas = document.getElementById(canvasId);
  if (el) { el.textContent = msg; el.style.display = ""; }
  if (canvas) canvas.style.display = "none";
}

(async function initDashboard() {
  var loadingEl = document.getElementById("dash-loading");
  var chartsEl = document.getElementById("dash-charts");
  var programsEl = document.getElementById("dash-programs");

  try {
    var resp = await fetch("/api/v1/dashboard/summary");
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

    // ── Service bar chart ───────────────────────────────────────────────────
    if (data.by_service && data.by_service.length) {
      var svcLabels = data.by_service.map(function(r) { return r.service || "Unknown"; });
      var svcAmounts = data.by_service.map(function(r) { return (r.total || 0) / 1000; }); // $M

      new Chart(document.getElementById("dash-service-chart"), {
        type: "bar",
        data: {
          labels: svcLabels,
          datasets: [{
            label: "FY2026 Request ($M)",
            data: svcAmounts,
            backgroundColor: DASH_COLORS,
            borderRadius: 4
          }]
        },
        options: {
          indexAxis: "y",
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { callback: function(v) { return "$" + v.toLocaleString() + "M"; } } }
          },
          onHover: function(e, elements) {
            e.native.target.style.cursor = elements.length ? "pointer" : "default";
          },
          onClick: function(e, elements) {
            if (elements.length) {
              var idx = elements[0].index;
              window.location.href = "/?service=" + encodeURIComponent(svcLabels[idx]);
            }
          }
        }
      });
    } else {
      showDashError("err-dash-service", "dash-service-chart", "No service data available.");
    }

    // ── Appropriation doughnut chart ────────────────────────────────────────
    if (data.by_appropriation && data.by_appropriation.length) {
      var appLabels = data.by_appropriation.map(function(r) {
        return r.appropriation_title || r.appropriation_code || "Unknown";
      });
      var appAmounts = data.by_appropriation.map(function(r) { return (r.total || 0) / 1000; });

      new Chart(document.getElementById("dash-approp-chart"), {
        type: "doughnut",
        data: {
          labels: appLabels,
          datasets: [{
            data: appAmounts,
            backgroundColor: DASH_COLORS.slice(0, appLabels.length),
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
            tooltip: {
              callbacks: {
                label: function(ctx) {
                  var total = ctx.dataset.data.reduce(function(a, b) { return a + b; }, 0);
                  var pct = total > 0 ? (ctx.parsed / total * 100).toFixed(1) : 0;
                  return ctx.label + ": $" + ctx.parsed.toLocaleString() + "M (" + pct + "%)";
                }
              }
            }
          },
          onHover: function(e, elements) {
            e.native.target.style.cursor = elements.length ? "pointer" : "default";
          },
          onClick: function(e, elements) {
            if (elements.length) {
              var idx = elements[0].index;
              var approp = data.by_appropriation[idx];
              if (approp.appropriation_code) {
                window.location.href = "/?appropriation_code=" + encodeURIComponent(approp.appropriation_code);
              }
            }
          }
        }
      });
    } else {
      showDashError("err-dash-approp", "dash-approp-chart", "No appropriation data available.");
    }

    // ── Top 10 programs table ───────────────────────────────────────────────
    var container = document.getElementById("dash-top-programs");
    if (container && data.top_programs && data.top_programs.length) {
      var html = '<table class="top-programs-table">';
      html += "<thead><tr><th>#</th><th>Program</th><th>Service</th><th>PE #</th>";
      html += '<th class="td-amount">FY26 Request ($K)</th>';
      html += '<th class="td-amount">FY25 Enacted ($K)</th>';
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

  function escapeHtml(s) {
    if (!s) return "";
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
})();
