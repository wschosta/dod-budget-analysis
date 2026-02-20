/**
 * DoD Budget Explorer — charts.js
 * Extracted from charts.html inline script (FALCON-11).
 * Handles all chart page visualizations: service bar, YoY, top-N,
 * comparison, treemap, appropriation doughnut, and YoY delta.
 */

"use strict";

var CHARTS_API = '/api/v1';

// Colour palette
var CHART_COLORS = [
  '#2563eb','#16a34a','#d97706','#dc2626','#7c3aed',
  '#0891b2','#c2410c','#065f46','#92400e','#1e1b4b',
];

var chartService, chartYoY, chartTopN, chartCompare, chartTreemap, chartAppropPie, chartDelta;

// VIZ-001: Helper to extract FY amount columns dynamically from aggregation rows
function extractFYColumns(rows) {
  if (!rows || !rows.length) return [];
  var keys = Object.keys(rows[0]).filter(function(k) { return /^total_fy\d+/.test(k); });
  return keys.sort();
}

// VIZ-001: Map column name to a readable label
function fyColLabel(col) {
  var m = col.match(/total_fy(\d{4})_(\w+)/);
  if (!m) return col;
  return 'FY' + m[1].slice(-2) + ' ' + m[2].charAt(0).toUpperCase() + m[2].slice(1);
}

// VIZ-002: Show error in a chart card
function showChartError(errId, canvasId, msg) {
  var errEl = document.getElementById(errId);
  var canvas = document.getElementById(canvasId);
  if (errEl) { errEl.textContent = msg; errEl.style.display = ''; }
  if (canvas) canvas.style.display = 'none';
}

function clearChartError(errId, canvasId) {
  var errEl = document.getElementById(errId);
  var canvas = document.getElementById(canvasId);
  if (errEl) { errEl.textContent = ''; errEl.style.display = 'none'; }
  if (canvas) canvas.style.display = '';
}

// VIZ-003: Get selected services
function getSelectedServices() {
  var sel = document.getElementById('chart-service-filter');
  if (!sel) return [];
  return Array.from(sel.selectedOptions).map(function(o) { return o.value; });
}

// Build aggregation URL with optional service filter
function aggURL(groupBy, fy) {
  var url = CHARTS_API + '/aggregations?group_by=' + groupBy;
  if (fy) url += '&fiscal_year=' + fy;
  var services = getSelectedServices();
  services.forEach(function(s) { url += '&service=' + encodeURIComponent(s); });
  return url;
}

// VIZ-002: Loading state
function setChartsLoading(loading) {
  var indicator = document.getElementById('charts-loading');
  var wrapper   = document.getElementById('charts-grid-wrapper');
  if (indicator) indicator.style.display = loading ? '' : 'none';
  if (wrapper)   wrapper.style.opacity   = loading ? '0.4' : '1';
  var fysel = document.getElementById('chart-fy');
  if (fysel) fysel.disabled = loading;
  var svcsel = document.getElementById('chart-service-filter');
  if (svcsel) svcsel.disabled = loading;
}

async function loadCharts() {
  setChartsLoading(true);
  var fy = document.getElementById('chart-fy').value;

  try {
    await Promise.all([
      loadServiceChart(fy),
      loadYoYChart(),
      loadTopNChart(fy),
      loadTreemap(fy),
      loadAppropPie(fy),
      loadDeltaChart(fy),
    ]);
  } finally {
    setChartsLoading(false);
  }
}

// -- Service bar chart (3.B2-a + VIZ-001 + VIZ-002 + VIZ-003) --
async function loadServiceChart(fy) {
  clearChartError('err-service', 'chart-service');
  try {
    var resp = await fetch(aggURL('service', fy));
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    var data = await resp.json();

    var cols = extractFYColumns(data.rows);
    var reqCol = cols.find(function(c) { return c.includes(fy) && c.includes('request'); })
              || cols.find(function(c) { return c.includes('request'); })
              || cols[cols.length - 1];

    if (!reqCol) {
      showChartError('err-service', 'chart-service', 'No amount data available.');
      return;
    }

    var svcRows = data.rows.filter(function(r) { return r[reqCol]; });
    var svcLabels = svcRows.map(function(r) { return r.group_value || 'Unknown'; });
    var svcAmts   = svcRows.map(function(r) { return (r[reqCol] || 0) / 1000; });

    if (chartService) chartService.destroy();
    chartService = new Chart(document.getElementById('chart-service'), {
      type: 'bar',
      data: {
        labels: svcLabels,
        datasets: [{
          label: fyColLabel(reqCol) + ' ($M)',
          data: svcAmts,
          backgroundColor: CHART_COLORS,
          borderRadius: 4,
        }],
      },
      options: {
        indexAxis: 'y',
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { callback: function(v) { return '$' + v.toLocaleString() + 'M'; } } },
        },
        onHover: function(e, elements) {
          e.native.target.style.cursor = elements.length ? 'pointer' : 'default';
        },
        onClick: function(e, elements) {
          if (elements.length) {
            var idx = elements[0].index;
            var service = svcLabels[idx];
            window.location.href = '/?service=' + encodeURIComponent(service);
          }
        },
      },
    });
  } catch (err) {
    showChartError('err-service', 'chart-service', 'Failed to load: ' + err.message);
  }
}

// -- Year-over-year chart (3.B1-a + VIZ-001 + VIZ-002) --
async function loadYoYChart() {
  clearChartError('err-yoy', 'chart-yoy');
  try {
    var resp = await fetch(aggURL('fiscal_year', null));
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    var data = await resp.json();

    var cols = extractFYColumns(data.rows);
    var yoyLabels = data.rows.map(function(r) { return r.group_value || '?'; });

    if (!cols.length) {
      showChartError('err-yoy', 'chart-yoy', 'No amount columns found.');
      return;
    }

    var datasets = cols.map(function(col, i) {
      return {
        label: fyColLabel(col),
        data:  data.rows.map(function(r) { return (r[col] || 0) / 1000; }),
        backgroundColor: CHART_COLORS[i % CHART_COLORS.length],
        borderRadius: 3,
      };
    });

    if (chartYoY) chartYoY.destroy();
    chartYoY = new Chart(document.getElementById('chart-yoy'), {
      type: 'bar',
      data: { labels: yoyLabels, datasets: datasets },
      options: {
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } } },
        scales: { x: { stacked: false }, y: { ticks: { callback: function(v) { return '$' + v.toLocaleString() + 'M'; } } } },
        onHover: function(e, elements) {
          e.native.target.style.cursor = elements.length ? 'pointer' : 'default';
        },
        onClick: function(e, elements) {
          if (elements.length) {
            var idx = elements[0].index;
            var fy = yoyLabels[idx];
            window.location.href = '/?fiscal_year=' + encodeURIComponent(fy);
          }
        },
      },
    });
  } catch (err) {
    showChartError('err-yoy', 'chart-yoy', 'Failed to load: ' + err.message);
  }
}

// -- Top-N chart (3.B3-a + VIZ-001 + VIZ-002) --
async function loadTopNChart(fy) {
  clearChartError('err-topn', 'chart-topn');
  try {
    var services = getSelectedServices();
    var url = CHARTS_API + '/budget-lines?sort_by=amount_fy2026_request&sort_dir=desc&limit=10&fiscal_year=' + fy;
    services.forEach(function(s) { url += '&service=' + encodeURIComponent(s); });

    var resp = await fetch(url);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    var data = await resp.json();

    if (!data.items || !data.items.length) {
      showChartError('err-topn', 'chart-topn', 'No data for selected filters.');
      return;
    }

    var sampleItem = data.items[0];
    var amtKeys = Object.keys(sampleItem).filter(function(k) { return k.startsWith('amount_') && k.includes('request'); });
    var amtCol = amtKeys.find(function(k) { return k.includes('2026'); }) || amtKeys[0] || 'amount_fy2026_request';

    var topLabels = data.items.map(function(r) {
      var title = r.line_item_title || r.account_title || 'Unknown';
      var org   = r.organization_name ? ' (' + r.organization_name + ')' : '';
      return title.length > 40 ? title.slice(0, 38) + '\u2026' + org : title + org;
    });
    var topAmts = data.items.map(function(r) { return (r[amtCol] || 0) / 1000; });
    var topItems = data.items;

    if (chartTopN) chartTopN.destroy();
    chartTopN = new Chart(document.getElementById('chart-topn'), {
      type: 'bar',
      data: {
        labels: topLabels,
        datasets: [{
          label: 'Request ($M)',
          data: topAmts,
          backgroundColor: CHART_COLORS,
          borderRadius: 4,
        }],
      },
      options: {
        indexAxis: 'y',
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { callback: function(v) { return '$' + v.toLocaleString() + 'M'; } } },
        },
        onHover: function(e, elements) {
          e.native.target.style.cursor = elements.length ? 'pointer' : 'default';
        },
        onClick: function(e, elements) {
          if (elements.length) {
            var idx = elements[0].index;
            var item = topItems[idx];
            if (item.pe_number) {
              window.location.href = '/?q=' + encodeURIComponent(item.pe_number);
            } else {
              var q = item.line_item_title || item.account_title || '';
              window.location.href = '/?q=' + encodeURIComponent(q);
            }
          }
        },
      },
    });
  } catch (err) {
    showChartError('err-topn', 'chart-topn', 'Failed to load: ' + err.message);
  }
}

// -- VIZ-005: Budget Comparison chart --
async function loadComparison() {
  var a = document.getElementById('compare-a').value;
  var b = document.getElementById('compare-b').value;
  clearChartError('err-compare', 'chart-compare');

  if (!a || !b) {
    if (chartCompare) { chartCompare.destroy(); chartCompare = null; }
    return;
  }

  try {
    var responses = await Promise.all([
      fetch(CHARTS_API + '/aggregations?group_by=fiscal_year&service=' + encodeURIComponent(a)),
      fetch(CHARTS_API + '/aggregations?group_by=fiscal_year&service=' + encodeURIComponent(b)),
    ]);
    if (!responses[0].ok || !responses[1].ok) throw new Error('API error');
    var results = await Promise.all([responses[0].json(), responses[1].json()]);
    var dataA = results[0];
    var dataB = results[1];

    var cols = extractFYColumns(dataA.rows);
    var reqCols = cols.filter(function(c) { return c.includes('request'); });
    var col = reqCols[reqCols.length - 1] || cols[cols.length - 1];

    if (!col) {
      showChartError('err-compare', 'chart-compare', 'No amount data available for comparison.');
      return;
    }

    var labelsA = dataA.rows.map(function(r) { return r.group_value || '?'; });
    var labelsB = dataB.rows.map(function(r) { return r.group_value || '?'; });
    var allLabels = Array.from(new Set(labelsA.concat(labelsB))).sort();

    function getAmt(rows, label) {
      var row = rows.find(function(r) { return r.group_value === label; });
      return row ? (row[col] || 0) / 1000 : 0;
    }

    var amtsA = allLabels.map(function(l) { return getAmt(dataA.rows, l); });
    var amtsB = allLabels.map(function(l) { return getAmt(dataB.rows, l); });

    if (chartCompare) chartCompare.destroy();
    chartCompare = new Chart(document.getElementById('chart-compare'), {
      type: 'bar',
      data: {
        labels: allLabels,
        datasets: [
          { label: a, data: amtsA, backgroundColor: CHART_COLORS[0], borderRadius: 3 },
          { label: b, data: amtsB, backgroundColor: CHART_COLORS[1], borderRadius: 3 },
        ],
      },
      options: {
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
          tooltip: {
            callbacks: {
              afterLabel: function(ctx) {
                var idxA = ctx.datasetIndex === 0 ? 0 : 1;
                var idxB = idxA === 0 ? 1 : 0;
                var valA = ctx.chart.data.datasets[idxA].data[ctx.dataIndex] || 0;
                var valB = ctx.chart.data.datasets[idxB].data[ctx.dataIndex] || 0;
                if (valB === 0) return '';
                var pct = ((valA - valB) / valB * 100).toFixed(1);
                return 'vs other: ' + (pct > 0 ? '+' : '') + pct + '%';
              },
            },
          },
        },
        scales: {
          y: { ticks: { callback: function(v) { return '$' + v.toLocaleString() + 'M'; } } },
        },
      },
    });
  } catch (err) {
    showChartError('err-compare', 'chart-compare', 'Failed to load comparison: ' + err.message);
  }
}

// -- Treemap: Hierarchical budget breakdown --
async function loadTreemap(fy) {
  clearChartError('err-treemap', 'chart-treemap');
  try {
    var url = CHARTS_API + '/aggregations/hierarchy';
    if (fy) url += '?fiscal_year=' + fy;
    var resp = await fetch(url);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    var data = await resp.json();

    if (!data.items || !data.items.length) {
      showChartError('err-treemap', 'chart-treemap', 'No hierarchy data available.');
      return;
    }

    var services = [];
    var seen = {};
    data.items.forEach(function(i) {
      if (!seen[i.service]) { seen[i.service] = true; services.push(i.service); }
    });
    var svcColorMap = {};
    services.forEach(function(s, i) { svcColorMap[s] = CHART_COLORS[i % CHART_COLORS.length]; });

    var treeData = data.items.slice(0, 200).map(function(item) {
      return {
        service: item.service || 'Unknown',
        approp: item.approp_title || item.approp || 'Unknown',
        program: (item.program || 'Unknown').slice(0, 40),
        v: item.amount || 0,
      };
    });

    if (chartTreemap) chartTreemap.destroy();

    if (typeof Chart.controllers === 'undefined' || !Chart.registry.controllers.get('treemap')) {
      showChartError('err-treemap', 'chart-treemap', 'Treemap plugin not loaded.');
      return;
    }

    chartTreemap = new Chart(document.getElementById('chart-treemap'), {
      type: 'treemap',
      data: {
        datasets: [{
          tree: treeData,
          key: 'v',
          groups: ['service', 'approp'],
          spacing: 1,
          borderWidth: 1,
          borderColor: 'rgba(0,0,0,.15)',
          backgroundColor: function(ctx) {
            if (!ctx.raw || !ctx.raw._data) return CHART_COLORS[0];
            var svc = ctx.raw._data.service || (ctx.raw._data.children && ctx.raw._data.children[0] ? ctx.raw._data.children[0].service : undefined);
            return svcColorMap[svc] || CHART_COLORS[0];
          },
          labels: {
            display: true,
            align: 'left',
            position: 'top',
            color: '#fff',
            font: { size: 11, weight: 'bold' },
            formatter: function(ctx) {
              if (!ctx.raw || !ctx.raw._data) return '';
              return ctx.raw._data.approp || ctx.raw._data.service || '';
            }
          }
        }]
      },
      options: {
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: function(items) {
                if (!items.length || !items[0].raw || !items[0].raw._data) return '';
                var d = items[0].raw._data;
                return d.service + ' > ' + (d.approp || '');
              },
              label: function(item) {
                if (!item.raw || !item.raw._data) return '';
                var amt = (item.raw._data.v || 0) / 1000;
                return '$' + amt.toLocaleString(undefined, {maximumFractionDigits: 0}) + 'M';
              }
            }
          }
        },
        onClick: function(e, elements) {
          if (elements.length && elements[0].element && elements[0].element.$context) {
            var raw = elements[0].element.$context.raw;
            if (raw && raw._data && raw._data.service) {
              window.location.href = '/?service=' + encodeURIComponent(raw._data.service);
            }
          }
        }
      }
    });
  } catch (err) {
    showChartError('err-treemap', 'chart-treemap', 'Failed to load treemap: ' + err.message);
  }
}

// -- Appropriation breakdown doughnut --
async function loadAppropPie(fy) {
  clearChartError('err-approp-pie', 'chart-approp-pie');
  try {
    var resp = await fetch(aggURL('appropriation', fy));
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    var data = await resp.json();

    if (!data.rows || !data.rows.length) {
      showChartError('err-approp-pie', 'chart-approp-pie', 'No appropriation data.');
      return;
    }

    var labels = data.rows.map(function(r) { return r.group_value || 'Unknown'; });
    var cols = extractFYColumns(data.rows);
    var reqCol = cols.find(function(c) { return c.includes('request'); }) || cols[cols.length - 1];
    if (!reqCol) {
      showChartError('err-approp-pie', 'chart-approp-pie', 'No amount data.');
      return;
    }
    var amounts = data.rows.map(function(r) { return (r[reqCol] || 0) / 1000; });

    if (chartAppropPie) chartAppropPie.destroy();
    chartAppropPie = new Chart(document.getElementById('chart-approp-pie'), {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: amounts,
          backgroundColor: CHART_COLORS.slice(0, labels.length),
          borderWidth: 2,
          borderColor: getComputedStyle(document.documentElement).getPropertyValue('--bg-surface').trim() || '#fff'
        }]
      },
      options: {
        plugins: {
          legend: { position: 'right', labels: { boxWidth: 12, font: { size: 11 } } },
          tooltip: {
            callbacks: {
              label: function(ctx) {
                var total = ctx.dataset.data.reduce(function(a, b) { return a + b; }, 0);
                var pct = total > 0 ? (ctx.parsed / total * 100).toFixed(1) : 0;
                return ctx.label + ': $' + ctx.parsed.toLocaleString() + 'M (' + pct + '%)';
              }
            }
          }
        },
        onHover: function(e, elements) {
          e.native.target.style.cursor = elements.length ? 'pointer' : 'default';
        },
        onClick: function(e, elements) {
          if (elements.length) {
            var idx = elements[0].index;
            var approp = data.rows[idx].group_value;
            if (approp) window.location.href = '/?appropriation_code=' + encodeURIComponent(approp);
          }
        }
      }
    });
  } catch (err) {
    showChartError('err-approp-pie', 'chart-approp-pie', 'Failed: ' + err.message);
  }
}

// -- YoY delta by service (% change bar chart) --
async function loadDeltaChart(fy) {
  clearChartError('err-delta', 'chart-delta');
  try {
    var resp = await fetch(aggURL('service', fy));
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    var data = await resp.json();

    if (!data.rows || !data.rows.length) {
      showChartError('err-delta', 'chart-delta', 'No service data for delta chart.');
      return;
    }

    var withDelta = data.rows.filter(function(r) { return r.yoy_change_pct != null; });
    if (!withDelta.length) {
      showChartError('err-delta', 'chart-delta', 'No year-over-year data available.');
      return;
    }

    var deltaLabels = withDelta.map(function(r) { return r.group_value || 'Unknown'; });
    var deltaValues = withDelta.map(function(r) { return r.yoy_change_pct; });
    var deltaColors = deltaValues.map(function(v) { return v >= 0 ? '#16a34a' : '#dc2626'; });

    if (chartDelta) chartDelta.destroy();
    chartDelta = new Chart(document.getElementById('chart-delta'), {
      type: 'bar',
      data: {
        labels: deltaLabels,
        datasets: [{
          label: 'YoY Change (%)',
          data: deltaValues,
          backgroundColor: deltaColors,
          borderRadius: 4
        }]
      },
      options: {
        indexAxis: 'y',
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function(ctx) {
                return (ctx.parsed.x >= 0 ? '+' : '') + ctx.parsed.x.toFixed(1) + '%';
              }
            }
          }
        },
        scales: {
          x: {
            ticks: { callback: function(v) { return (v >= 0 ? '+' : '') + v + '%'; } },
            grid: { color: 'rgba(128,128,128,.15)' }
          }
        },
        onHover: function(e, elements) {
          e.native.target.style.cursor = elements.length ? 'pointer' : 'default';
        },
        onClick: function(e, elements) {
          if (elements.length) {
            var idx = elements[0].index;
            window.location.href = '/?service=' + encodeURIComponent(deltaLabels[idx]);
          }
        }
      }
    });
  } catch (err) {
    showChartError('err-delta', 'chart-delta', 'Failed: ' + err.message);
  }
}

// -- Populate service dropdowns (VIZ-003 + VIZ-005) --
async function populateServiceDropdowns() {
  try {
    var resp = await fetch(CHARTS_API + '/reference/services');
    if (!resp.ok) return;
    var data = await resp.json();
    var services = data.services || data.items || data;

    var filterSel = document.getElementById('chart-service-filter');
    if (filterSel) {
      services.forEach(function(svc) {
        var opt = document.createElement('option');
        opt.value = svc.code || svc;
        opt.textContent = svc.code || svc;
        filterSel.appendChild(opt);
      });
    }

    ['compare-a', 'compare-b'].forEach(function(id) {
      var sel = document.getElementById(id);
      if (!sel) return;
      services.forEach(function(svc) {
        var opt = document.createElement('option');
        opt.value = svc.code || svc;
        opt.textContent = svc.code || svc;
        sel.appendChild(opt);
      });
    });
  } catch (e) {
    // Silently ignore if reference endpoint unavailable
  }
}

// -- Initial load --
(async function chartsInit() {
  await populateServiceDropdowns();
  await loadCharts();
})();
