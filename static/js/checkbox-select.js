/**
 * DoD Budget Explorer — checkbox-select.js
 * Replaces native <select multiple> elements with checkbox dropdown components.
 * Provides a better UX than Ctrl+click for multi-select.
 */

"use strict";

function initCheckboxSelect(selectEl) {
  // Skip if already initialized or not a multi-select
  if (selectEl.dataset.checkboxInit || !selectEl.multiple) return;
  selectEl.dataset.checkboxInit = "true";

  // Hide the original select
  selectEl.style.display = "none";

  // Create wrapper
  var wrapper = document.createElement("div");
  wrapper.className = "checkbox-select";
  selectEl.parentNode.insertBefore(wrapper, selectEl);
  wrapper.appendChild(selectEl);

  // Create trigger button
  var trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "checkbox-select-trigger";
  trigger.setAttribute("aria-haspopup", "listbox");
  trigger.setAttribute("aria-expanded", "false");
  wrapper.insertBefore(trigger, selectEl);

  // Create dropdown
  var dropdown = document.createElement("div");
  dropdown.className = "checkbox-select-dropdown";
  dropdown.setAttribute("role", "listbox");
  dropdown.setAttribute("aria-multiselectable", "true");
  wrapper.appendChild(dropdown);

  // Populate checkboxes from select options
  function buildOptions() {
    dropdown.innerHTML = "";
    Array.from(selectEl.options).forEach(function (opt, i) {
      var label = document.createElement("label");
      label.className = "checkbox-select-item";

      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.value = opt.value;
      cb.checked = opt.selected;
      cb.dataset.index = String(i);

      var span = document.createElement("span");
      span.textContent = opt.textContent;

      label.appendChild(cb);
      label.appendChild(span);
      dropdown.appendChild(label);

      cb.addEventListener("change", function () {
        opt.selected = cb.checked;
        updateTriggerText();
        // Dispatch change event on the original select for HTMX
        var evt = new Event("change", { bubbles: true });
        selectEl.dispatchEvent(evt);
      });
    });
  }

  // FIX-018: Create chevron once and reuse to prevent duplication on each update
  var chevron = document.createElement("span");
  chevron.textContent = " \u25BE";
  chevron.style.fontSize = ".7rem";

  function updateTriggerText() {
    var selected = Array.from(selectEl.selectedOptions);
    if (selected.length === 0) {
      trigger.textContent = "All";
    } else if (selected.length <= 2) {
      trigger.textContent = selected.map(function (o) { return o.textContent.split(" (")[0]; }).join(", ");
    } else {
      trigger.textContent = selected.slice(0, 2).map(function (o) {
        return o.textContent.split(" (")[0];
      }).join(", ") + " +" + (selected.length - 2) + " more";
    }
    trigger.appendChild(chevron);
  }

  // Toggle dropdown
  trigger.addEventListener("click", function (e) {
    e.preventDefault();
    var isOpen = wrapper.classList.contains("open");
    // Close all other dropdowns
    document.querySelectorAll(".checkbox-select.open").forEach(function (w) {
      if (w !== wrapper) w.classList.remove("open");
    });
    wrapper.classList.toggle("open");
    trigger.setAttribute("aria-expanded", String(!isOpen));
  });

  // Close on click outside
  document.addEventListener("click", function (e) {
    if (!wrapper.contains(e.target)) {
      wrapper.classList.remove("open");
      trigger.setAttribute("aria-expanded", "false");
    }
  });

  // Close on Escape
  dropdown.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      wrapper.classList.remove("open");
      trigger.setAttribute("aria-expanded", "false");
      trigger.focus();
    }
  });

  buildOptions();
  updateTriggerText();
}

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("select[multiple]").forEach(initCheckboxSelect);
});

// Re-initialize after HTMX swaps (in case new selects are added)
document.addEventListener("htmx:afterSwap", function () {
  document.querySelectorAll("select[multiple]").forEach(initCheckboxSelect);
});
