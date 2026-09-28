// MY HOT RADAR — minimal vanilla JS
(() => {
  'use strict';

  // Mobile nav toggle
  const toggle = document.querySelector('[data-nav-toggle]');
  const panel  = document.querySelector('[data-mobile-nav]');
  if (toggle && panel) {
    toggle.addEventListener('click', () => {
      const open = panel.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', String(open));
    });
    // Close on link click
    panel.querySelectorAll('a').forEach(a => {
      a.addEventListener('click', () => {
        panel.classList.remove('is-open');
        toggle.setAttribute('aria-expanded', 'false');
      });
    });
  }
})();