// put site-wide dependencies here.
// HTMX setup: https://htmx.org/docs/#installing
import './htmx';
import './alpine';

window.__cssFramework = 'tailwind';

// Safe wrapper for Google Analytics event tracking
window.trackGAEvent = function(eventName, params) {
  if (typeof window.gtag === 'function') {
    window.gtag('event', eventName, params);
  }
};

// Sidebar state: restore from localStorage, defaulting to open
document.addEventListener('DOMContentLoaded', () => {
  const drawer = document.getElementById('sidebar-drawer');
  if (!drawer) return;

  const saved = localStorage.getItem('sidebarOpen');
  drawer.checked = saved === null ? true : saved === 'true';

  drawer.addEventListener('change', () => {
    localStorage.setItem('sidebarOpen', String(drawer.checked));
  });
});
