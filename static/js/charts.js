/**
 * DoD Budget Explorer — charts.js
 * Extracted from charts.html inline script (FALCON-11).
 * Handles all chart page visualizations: service bar, YoY stacked bar,
 * top-N, multi-entity comparison, treemap, and appropriation doughnut.
 */

"use strict";

var CHARTS_API = '/api/v1';

// Colour palette — provided by fmt.js (loaded from base.html).
var CHART_COLORS = BUDGET_COLORS;

var chartService, chartYoY, chartTopN, chartCompare, chartTreemap, chartAppropPie;

// VIZ-001: Helper to extract FY amount columns dynamically from aggregation rows
function extractFYColumns(rows) {
  if (!rows || !rows.length) return [];
  // Look for fy_totals first (preferred), then fall back to top-level keys
  var sample = rows[0];
  if (sample.fy_totals && typeof sample.fy_totals === 'object') {
    return Object.keys(sample.fy_totals).sort();
  }
  var keys = Object.keys(sample).filter(function(k) { return /^total_fy\d+/.test(k); });
  return keys.sort();
}

// Helper: get amount from a row using fy_totals or top-level key
function getFYValue(row, col) {
  if (row.fy_totals && row.fy_totals[col] !== undefined) return row.fy_totals[col];
  // Try with total_ prefix for backward compat
  var topKey = 'total_' + col.replace('amount_', '');
  if (row[topKey] !== undefined) return row[topKey];
  if (row[col] !== undefined) return row[col];
  return null;
}

// VIZ-001: Map column name to a readable label
function fyColLabel(col) {
  var m = col.match(/(?:amount_|total_)?fy(\d{4})_(\w+)/);
  if (!m) return col;
  return 'FY' + m[1].slice(-2) + ' ' + m[2].charAt(0).toUpperCase() + m[2].slice(1);
}

// showChartError provided by fmt.js (loaded from base.html).

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

    var svcRows = data.rows.filter(function(r) { return getFYValue(r, reqCol); });
    var svcLabels = svcRows.map(function(r) { return r.group_value || 'Unknown'; });
    var svcAmts   = svcRows.map(function(r) { return (getFYValue(r, reqCol) || 0) / 1000; });

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
          x: { ticks: { callback: tickDollarsM } },
        },
        onHover: function(e, elements) {
          chartPointerHover(e, elements);
        },
        onClick: function(e, elements) {
          if (elements.length) {
            var idx = elements[0].index;
            var service = svcLabels[idx];
            window.location.href = '/?service=' + encodeURIComponent(service) + '#results-container';
          }
        },
      },
    });
  } catch (err) {
    showChartError('err-service', 'chart-service', 'Failed to load: ' + err.message);
  }
}

// -- Year-over-year stacked bar by service (3.4 redesign) --
// Shows budget totals by service across all FY columns (FY24 Actual, FY25 Enacted, FY26 Request)
async function loadYoYChart() {
  clearChartError('err-yoy', 'chart-yoy');
  try {
    // Fetch service aggregation without FY filter to get all services with fy_totals
    var url = CHARTS_API + '/aggregations?group_by=service';
    var services = getSelectedServices();
    services.forEach(function(s) { url += '&service=' + encodeURIComponent(s); });

    var resp = await fetch(url);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    var data = await resp.json();

    if (!data.rows || !data.rows.length) {
      showChartError('err-yoy', 'chart-yoy', 'No service data available.');
      return;
    }

    // Get FY amount columns from first row's fy_totals
    var cols = extractFYColumns(data.rows);
    // Filter to the main columns users care about (actual, enacted, request)
    var mainCols = cols.filter(function(c) {
      return c.includes('actual') || c.includes('enacted') || c.includes('request');
    });
    if (!mainCols.length) mainCols = cols;

    // X axis = FY amount columns as labels
    var xLabels = mainCols.map(function(c) { return fyColLabel(c); });

    // Take top 8 services by latest column value
    var latestCol = mainCols[mainCols.length - 1];
    var sortedRows = data.rows.slice().sort(function(a, b) {
      return (getFYValue(b, latestCol) || 0) - (getFYValue(a, latestCol) || 0);
    });
    var topServices = sortedRows.slice(0, 8);

    // One dataset per service, stacked
    var datasets = topServices.map(function(row, i) {
      return {
        label: row.group_value || 'Unknown',
        data: mainCols.map(function(col) { return (getFYValue(row, col) || 0) / 1000; }),
        backgroundColor: CHART_COLORS[i % CHART_COLORS.length],
        borderRadius: 2,
      };
    });

    if (chartYoY) chartYoY.destroy();
    chartYoY = new Chart(document.getElementById('chart-yoy'), {
      type: 'bar',
      data: { labels: xLabels, datasets: datasets },
      options: {
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
          tooltip: {
            callbacks: {
              label: tooltipDollarsM
            }
          }
        },
        scales: {
          x: { stacked: true },
          y: {
            stacked: true,
            ticks: { callback: tickDollarsM }
          }
        },
        onHover: function(e, elements) {
          chartPointerHover(e, elements);
        },
        onClick: function(e, elements) {
          if (elements.length) {
            var service = elements[0].element.$context.dataset.label;
            window.location.href = '/?service=' + encodeURIComponent(service) + '#results-container';
          }
        },
      },
    });
  } catch (err) {
    showChartError('err-yoy', 'chart-yoy', 'Failed to load: ' + err.message);
  }
}

// -- Top-N chart (3.B3-a + VIZ-001 + VIZ-002 + exclude_summary) --
async function loadTopNChart(fy) {
  clearChartError('err-topn', 'chart-topn');
  try {
    var services = getSelectedServices();
    var sortCol = 'amount_fy' + fy.replace(/\D/g, '') + '_request';
    // 3.3: exclude_summary=true to avoid double-counting from summary exhibits
    var url = CHARTS_API + '/budget-lines?sort_by=' + sortCol + '&sort_dir=desc&limit=10&fiscal_year=' + fy + '&exclude_summary=true';
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
    var amtCol = amtKeys.find(function(k) { return k.includes(fy.replace(/\D/g, '')); }) || amtKeys[0] || sortCol;

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
          x: { ticks: { callback: tickDollarsM } },
        },
        onHover: function(e, elements) {
          chartPointerHover(e, elements);
        },
        onClick: function(e, elements) {
          if (elements.length) {
            var idx = elements[0].index;
            var item = topItems[idx];
            if (item.pe_number) {
              window.location.href = '/programs/' + encodeURIComponent(item.pe_number);
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

// -- VIZ-005: Multi-entity Budget Comparison (3.5 redesign) --
// Supports 2-6 entities with all FY columns as X axis
async function loadComparison() {
  clearChartError('err-compare', 'chart-compare');

  // Collect selected entities from all compare dropdowns
  var entities = [];
  var compareEls = document.querySelectorAll('.compare-entity-select');
  compareEls.forEach(function(sel) {
    if (sel.value) entities.push(sel.value);
  });

  // Fallback: check old compare-a / compare-b elements
  if (!entities.length) {
    var a = document.getElementById('compare-a');
    var b = document.getElementById('compare-b');
    if (a && a.value) entities.push(a.value);
    if (b && b.value) entities.push(b.value);
  }

  if (entities.length < 2) {
    if (chartCompare) { chartCompare.destroy(); chartCompare = null; }
    return;
  }

  try {
    // Fetch aggregation data for each entity
    var fetches = entities.map(function(entity) {
      return fetch(CHARTS_API + '/aggregations?group_by=service&service=' + encodeURIComponent(entity));
    });
    var responses = await Promise.all(fetches);
    for (var i = 0; i < responses.length; i++) {
      if (!responses[i].ok) throw new Error('API error for ' + entities[i]);
    }
    var results = await Promise.all(responses.map(function(r) { return r.json(); }));

    // Get the FY columns from first result
    var cols = [];
    for (var ri = 0; ri < results.length; ri++) {
      if (results[ri].rows && results[ri].rows.length) {
        cols = extractFYColumns(results[ri].rows);
        break;
      }
    }

    // Filter to main columns (actual, enacted, request)
    var mainCols = cols.filter(function(c) {
      return c.includes('actual') || c.includes('enacted') || c.includes('request');
    });
    if (!mainCols.length) mainCols = cols;

    if (!mainCols.length) {
      showChartError('err-compare', 'chart-compare', 'No amount data available for comparison.');
      return;
    }

    // X axis = FY column labels
    var xLabels = mainCols.map(function(c) { return fyColLabel(c); });

    // One dataset per entity — sum across all rows for that entity
    var datasets = entities.map(function(entity, i) {
      var result = results[i];
      var rowData = mainCols.map(function(col) {
        var total = 0;
        if (result.rows) {
          result.rows.forEach(function(r) {
            total += (getFYValue(r, col) || 0);
          });
        }
        return total / 1000;
      });
      return {
        label: entity,
        data: rowData,
        backgroundColor: CHART_COLORS[i % CHART_COLORS.length],
        borderColor: CHART_COLORS[i % CHART_COLORS.length],
        borderWidth: 2,
        borderRadius: 3,
      };
    });

    if (chartCompare) chartCompare.destroy();
    chartCompare = new Chart(document.getElementById('chart-compare'), {
      type: 'bar',
      data: { labels: xLabels, datasets: datasets },
      options: {
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
          tooltip: {
            callbacks: {
              label: tooltipDollarsM
            }
          }
        },
        scales: {
          y: { ticks: { callback: tickDollarsM } },
        },
        onHover: function(e, elements) {
          chartPointerHover(e, elements);
        },
        onClick: function(e, elements) {
          if (elements.length) {
            var service = elements[0].element.$context.dataset.label;
            window.location.href = '/?service=' + encodeURIComponent(service) + '#results-container';
          }
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
            color: getComputedStyle(document.documentElement).getPropertyValue('--text-on-primary').trim() || '#fff',
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
              window.location.href = '/?service=' + encodeURIComponent(raw._data.service) + '#results-container';
            }
          }
        }
      }
    });
  } catch (err) {
    showChartError('err-treemap', 'chart-treemap', 'Failed to load treemap: ' + err.message);
  }
}

// -- Appropriation breakdown doughnut (uses shared utility from budget-charts.js) --
async function loadAppropPie(fy) {
  clearChartError('err-approp-pie', 'chart-approp-pie');
  if (chartAppropPie) { chartAppropPie.destroy(); chartAppropPie = null; }
  chartAppropPie = await renderBudgetTypeDoughnut('chart-approp-pie', {
    colors: CHART_COLORS,
    serviceFilter: getSelectedServices(),
    onClick: function(budgetType) {
      window.location.href = '/?budget_type=' + encodeURIComponent(budgetType) + '#results-container';
    },
    onError: function(msg) {
      showChartError('err-approp-pie', 'chart-approp-pie', 'Failed: ' + msg);
    },
    onEmpty: function() {
      showChartError('err-approp-pie', 'chart-approp-pie', 'No budget type data available.');
    },
  });
}

// -- Populate service dropdowns (VIZ-003 + VIZ-005) --
async function populateServiceDropdowns() {
  try {
    var resp = await fetch(CHARTS_API + '/reference/services');
    if (!resp.ok) return;
    var data = await resp.json();
    var services = data.services || data.items || data;

    // 3.2: Use code for value, full_name for display text
    var filterSel = document.getElementById('chart-service-filter');
    if (filterSel) {
      services.forEach(function(svc) {
        var opt = document.createElement('option');
        opt.value = svc.code || svc;
        opt.textContent = svc.full_name || svc.code || svc;
        filterSel.appendChild(opt);
      });
    }

    // Populate all compare entity dropdowns
    var compareSels = document.querySelectorAll('.compare-entity-select');
    compareSels.forEach(function(sel) {
      services.forEach(function(svc) {
        var opt = document.createElement('option');
        opt.value = svc.code || svc;
        opt.textContent = svc.full_name || svc.code || svc;
        sel.appendChild(opt);
      });
    });

    // Fallback: old compare-a / compare-b elements
    ['compare-a', 'compare-b'].forEach(function(id) {
      var sel = document.getElementById(id);
      if (!sel || sel.classList.contains('compare-entity-select')) return;
      services.forEach(function(svc) {
        var opt = document.createElement('option');
        opt.value = svc.code || svc;
        opt.textContent = svc.full_name || svc.code || svc;
        sel.appendChild(opt);
      });
    });
  } catch (e) {
    // Silently ignore if reference endpoint unavailable
  }
}

// -- Add/remove comparison entity --
function addCompareEntity() {
  var container = document.getElementById('compare-entities');
  if (!container) return;
  var existing = container.querySelectorAll('.compare-entity-select');
  if (existing.length >= 6) return; // max 6 entities

  var wrapper = document.createElement('div');
  wrapper.style.cssText = 'display:inline-flex;gap:.25rem;align-items:center';

  var sel = document.createElement('select');
  sel.className = 'compare-entity-select';
  sel.style.cssText = 'padding:.3rem .5rem;border-radius:4px;border:1px solid var(--border-color)';
  sel.onchange = loadComparison;

  var defaultOpt = document.createElement('option');
  defaultOpt.value = '';
  defaultOpt.textContent = '-- Select service --';
  sel.appendChild(defaultOpt);

  // Copy options from first compare dropdown
  var firstSel = container.querySelector('.compare-entity-select');
  if (firstSel) {
    Array.from(firstSel.options).forEach(function(opt) {
      if (!opt.value) return;
      var newOpt = document.createElement('option');
      newOpt.value = opt.value;
      newOpt.textContent = opt.textContent;
      sel.appendChild(newOpt);
    });
  }

  var removeBtn = document.createElement('button');
  removeBtn.className = 'btn btn-secondary btn-sm';
  removeBtn.textContent = '\u00d7';
  removeBtn.title = 'Remove';
  removeBtn.style.cssText = 'padding:.15rem .4rem;font-size:.9rem;line-height:1';
  removeBtn.onclick = function() {
    wrapper.remove();
    loadComparison();
  };

  wrapper.appendChild(sel);
  wrapper.appendChild(removeBtn);
  container.appendChild(wrapper);
}

// -- Initial load --
(async function chartsInit() {
  await populateServiceDropdowns();
  await loadCharts();
})();
