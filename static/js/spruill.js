/**
 * DoD Budget Explorer — spruill.js
 * Handles the Spruill funding comparison page:
 *   - Detail toggle (summary vs sub-element detail)
 *   - HTMX re-fetch on toggle change
 *   - CSV export link generation
 */

"use strict";

/**
 * Build the hx-vals object for the Spruill table HTMX request.
 * Reads PE numbers from the URL query string and the detail checkbox state.
 * @returns {object} - Object with pe[] and detail keys
 */
function spruillHxVals() {
  var params = new URLSearchParams(window.location.search);
  var pes = params.getAll("pe");
  var detail = document.getElementById("spruill-detail");
  var obj = {};
  // HTMX hx-vals 'js:' expects a plain object; arrays need special handling
  // We build the query string manually and return it as individual pe params
  if (pes.length) {
    obj.pe = pes;
  }
  if (detail && detail.checked) {
    obj.detail = "true";
  }
  return obj;
}

/**
 * Update the CSV export link based on current PE selection and detail state.
 */
function updateSpruillExportLink() {
  var exportLink = document.getElementById("spruill-export");
  if (!exportLink) return;

  var params = new URLSearchParams(window.location.search);
  var pes = params.getAll("pe");
  var detail = document.getElementById("spruill-detail");

  var exportParams = new URLSearchParams();
  exportParams.set("fmt", "csv");
  pes.forEach(function(pe) {
    exportParams.append("pe", pe);
  });
  if (detail && detail.checked) {
    exportParams.set("detail", "true");
  }

  exportLink.href = "/api/v1/pe/spruill/export?" + exportParams.toString();
}

// Handle detail toggle checkbox changes
(function() {
  var detailCheckbox = document.getElementById("spruill-detail");
  if (!detailCheckbox) return;

  detailCheckbox.addEventListener("change", function() {
    // Re-fetch the table via HTMX
    var container = document.getElementById("spruill-table-container");
    if (container && typeof htmx !== "undefined") {
      var params = new URLSearchParams(window.location.search);
      var pes = params.getAll("pe");

      var url = "/partials/spruill-table?";
      url += pes.map(function(pe) { return "pe=" + encodeURIComponent(pe); }).join("&");
      if (detailCheckbox.checked) {
        url += "&detail=true";
      }

      htmx.ajax("GET", url, {
        target: "#spruill-table-container",
        swap: "innerHTML",
        indicator: "#spruill-loading"
      });
    }

    // Update export link
    updateSpruillExportLink();
  });

  // Initial export link update
  updateSpruillExportLink();
})();
