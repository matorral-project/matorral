import htmx from "htmx.org";
import "htmx-ext-ws";

// Make htmx globally available
window.htmx = htmx;

// Fix stale page parameter in bulk actions by using URL as source of truth
document.addEventListener('htmx:configRequest', function(evt) {
  const path = evt.detail.path;
  if (path.includes('bulk')) {
    const urlParams = new URLSearchParams(window.location.search);
    const currentPage = urlParams.get('page') || '1';
    evt.detail.parameters.page = currentPage;
  }
});
