/**
 * DoD Budget Explorer — dark-mode.js
 * Extracted from base.html inline script (FALCON-11).
 * Apply saved theme before first paint to avoid flash of wrong theme.
 */
"use strict";
(function() {
  const saved = localStorage.getItem('dod_theme');
  if (saved) {
    document.documentElement.setAttribute('data-theme', saved);
  }
})();
