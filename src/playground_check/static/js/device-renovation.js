/* Hide the confirmation three seconds after the saved form is displayed. */
(() => {
  'use strict';
  const status = document.querySelector('[data-renovation-saved]');
  if (status) window.setTimeout(() => { status.hidden = true; }, 3000);
})();
