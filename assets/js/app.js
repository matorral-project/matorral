import * as JsCookie from "js-cookie";
export const Cookies = JsCookie.default;

// Ensure SiteJS global exists
if (typeof window.SiteJS === 'undefined') {
  window.SiteJS = {};
}

// Assign this entry's exports to SiteJS.app
window.SiteJS.app = {
  Cookies: JsCookie.default,
};

function initNotifications() {
  document.querySelectorAll('.notification:not([data-initialized])').forEach((notification) => {
    notification.setAttribute('data-initialized', 'true');
    setTimeout(() => {
      notification.remove();
    }, 5000);
  });
}

// Event delegation for delete buttons - works for both existing and dynamically added notifications
document.body.addEventListener('click', (event) => {
  const deleteBtn = event.target.closest('.notification-delete');
  if (deleteBtn) {
    event.preventDefault();
    event.stopPropagation();
    const notification = deleteBtn.closest('.notification');
    if (notification) {
      notification.remove();
    }
  }
});

document.addEventListener('DOMContentLoaded', initNotifications);
document.body.addEventListener('htmx:oobAfterSwap', (event) => {
  if (event.detail.target.id === 'messages') {
    initNotifications();
  }
});
