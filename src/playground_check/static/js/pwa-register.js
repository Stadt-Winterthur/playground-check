/* Register application support without requesting notification permission. */
(() => {
  const script = document.currentScript;
  if (!window.isSecureContext || !('serviceWorker' in navigator) || !script) return;
  navigator.serviceWorker.register(script.dataset.workerUrl, {
    scope: script.dataset.workerScope
  }).catch(error => console.warn('Service Worker konnte nicht registriert werden:', error));
})();
