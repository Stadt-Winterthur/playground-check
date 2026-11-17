/* Small, accessible edit controls; the existing photo thumbnails are unchanged. */
(() => {
  'use strict';
  document.querySelectorAll('form[data-photo-upload]').forEach(form => {
    const picker = form.querySelector('input[type="file"]');
    const button = form.querySelector('button[type="submit"]');
    picker?.addEventListener('change', () => {
      if (picker.files?.length && button && !button.disabled) form.requestSubmit(button);
    });
  });
  document.querySelectorAll('form[data-photo-delete]').forEach(form => {
    form.addEventListener('submit', event => {
      if (!window.confirm(form.dataset.confirm || 'Dieses Foto wirklich löschen?')) event.preventDefault();
    });
  });
})();
