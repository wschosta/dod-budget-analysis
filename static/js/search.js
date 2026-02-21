/**
 * DoD Budget Explorer — search.js (FALCON-4)
 * Advanced search UI: structured query builder with field-specific conditions.
 */

"use strict";

var ADV_FIELDS = [
  { value: "q",          label: "Keyword (any field)" },
  { value: "pe_number",  label: "PE Number" },
  { value: "service",    label: "Service / Agency" },
  { value: "fiscal_year",label: "Fiscal Year" },
  { value: "exhibit_type",label: "Exhibit Type" },
  { value: "appropriation_code", label: "Appropriation" },
  { value: "min_amount", label: "Min Amount ($K)" },
  { value: "max_amount", label: "Max Amount ($K)" },
  { value: "line_item_title", label: "Line Item Title" },
  { value: "account_title", label: "Account Title" }
];

var ADV_OPERATORS = [
  { value: "contains",   label: "contains" },
  { value: "equals",     label: "equals" },
  { value: "starts_with",label: "starts with" },
  { value: "gte",        label: ">=" },
  { value: "lte",        label: "<=" }
];

var advConditionCount = 0;

function toggleAdvancedSearch() {
  var el = document.getElementById("advanced-search");
  if (!el) return;
  var isHidden = el.style.display === "none";
  el.style.display = isHidden ? "" : "none";
  if (isHidden && advConditionCount === 0) {
    addAdvancedCondition();
  }
}

function addAdvancedCondition() {
  var container = document.getElementById("adv-conditions");
  if (!container) return;

  var id = advConditionCount++;
  var row = document.createElement("div");
  row.className = "adv-condition-row";
  row.id = "adv-row-" + id;

  var fieldSelect = '<select class="adv-field" data-id="' + id + '">';
  ADV_FIELDS.forEach(function(f) {
    fieldSelect += '<option value="' + f.value + '">' + f.label + '</option>';
  });
  fieldSelect += '</select>';

  var opSelect = '<select class="adv-op" data-id="' + id + '">';
  ADV_OPERATORS.forEach(function(o) {
    opSelect += '<option value="' + o.value + '">' + o.label + '</option>';
  });
  opSelect += '</select>';

  row.innerHTML = fieldSelect +
    opSelect +
    '<input type="text" class="adv-value" data-id="' + id + '" placeholder="Value...">' +
    '<button type="button" class="adv-remove-btn" onclick="removeAdvancedCondition(' + id + ')" aria-label="Remove condition">&times;</button>';

  container.appendChild(row);
}

function removeAdvancedCondition(id) {
  var row = document.getElementById("adv-row-" + id);
  if (row) row.parentNode.removeChild(row);
}

function clearAdvancedConditions() {
  var container = document.getElementById("adv-conditions");
  if (container) container.innerHTML = "";
  advConditionCount = 0;
  addAdvancedCondition();
}

function executeAdvancedSearch() {
  var rows = document.querySelectorAll(".adv-condition-row");
  var params = new URLSearchParams();

  rows.forEach(function(row) {
    var field = row.querySelector(".adv-field");
    var op = row.querySelector(".adv-op");
    var value = row.querySelector(".adv-value");
    if (!field || !value || !value.value.trim()) return;

    var fieldName = field.value;
    var opName = op ? op.value : "contains";
    var val = value.value.trim();

    // Map field + operator to URL params
    if (fieldName === "q") {
      // For keyword, handle different operators
      if (opName === "equals") {
        params.set("q", '"' + val + '"');
      } else {
        params.set("q", val);
      }
    } else if (fieldName === "min_amount" || fieldName === "max_amount") {
      params.set(fieldName, val);
    } else if (opName === "gte") {
      params.set("min_amount", val);
    } else if (opName === "lte") {
      params.set("max_amount", val);
    } else {
      // Standard filter params
      params.append(fieldName, val);
    }
  });

  // Navigate to search results with the constructed query
  var url = "/?" + params.toString();
  window.location.href = url;
}
