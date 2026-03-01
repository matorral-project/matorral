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
  document.querySelectorAll('.notification').forEach((notification) => {
    const deleteBtn = notification.querySelector('.delete');
    if (deleteBtn) {
      deleteBtn.addEventListener('click', () => {
        notification.remove();
      });
    }
    setTimeout(() => {
      notification.remove();
    }, 5000);
  });
}

document.addEventListener('DOMContentLoaded', initNotifications);
document.body.addEventListener('htmx:oobAfterSwap', (event) => {
  if (event.detail.target.id === 'messages') {
    initNotifications();
  }
});
