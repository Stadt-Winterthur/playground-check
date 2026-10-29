/* Browser-only push integration for the Django template GUI. No business logic. */
(() => {
  'use strict';
  const root = document.getElementById('push-controls');
  if (!root) return;
  const status = document.getElementById('push-status');
  const enable = document.getElementById('push-enable');
  const disable = document.getElementById('push-disable');
  const prefix = root.dataset.basePath || '';
  const key = root.dataset.vapidKey || '';
  const supported = window.isSecureContext && 'serviceWorker' in navigator &&
    'PushManager' in window && 'Notification' in window;

  const notice = text => { status.textContent = text; };
  const bytes = value => {
    const padded = (value + '='.repeat((4 - value.length % 4) % 4))
      .replace(/-/g, '+').replace(/_/g, '/');
    return Uint8Array.from(atob(padded), x => x.charCodeAt(0));
  };
  const encoded = value => {
    const array = new Uint8Array(value);
    let binary = '';
    for (const n of array) binary += String.fromCharCode(n);
    return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
  };
  const payload = subscription => ({
    endpoint: subscription.endpoint,
    p256dh: encoded(subscription.getKey('p256dh')),
    auth: encoded(subscription.getKey('auth')),
    userAgent: navigator.userAgent
  });
  const request = async (endpoint, method, body) => {
    const response = await fetch(prefix + endpoint, {
      method, credentials: 'same-origin', cache: 'no-store',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    });
    if (!response.ok) throw new Error('Serverfehler (' + response.status + ')');
    const result = await response.json();
    if (result.errorMessage) throw new Error('Vorgang serverseitig abgelehnt.');
  };
  const refresh = async () => {
    if (!supported) { notice('Push wird von diesem Browser nicht unterstützt.'); return; }
    try {
      const registration = await navigator.serviceWorker.ready;
      const current = await registration.pushManager.getSubscription();
      enable.disabled = Boolean(current);
      disable.disabled = !current;
      notice(current ? 'Benachrichtigungen auf diesem Gerät aktiviert.' :
        'Benachrichtigungen auf diesem Gerät deaktiviert.');
    } catch (error) { notice('Push-Status konnte nicht geladen werden.'); }
  };
  if (!supported || !key) { notice('Push wird hier nicht unterstützt oder ist nicht konfiguriert.'); return; }
  // Register the already deployed service worker under the reverse-proxy scope.
  navigator.serviceWorker.register(prefix + '/static/sw.js', { scope: prefix + '/' })
    .then(refresh).catch(() => notice('Service Worker konnte nicht registriert werden.'));
  enable.addEventListener('click', async () => {
    enable.disabled = true;
    try {
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') throw new Error('Benachrichtigungen wurden nicht erlaubt.');
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true, applicationServerKey: bytes(key)
      });
      try { await request('/PushSubscription/Register/', 'POST', payload(subscription)); }
      catch (error) { await subscription.unsubscribe(); throw error; }
      notice('Benachrichtigungen aktiviert.');
    } catch (error) { notice(error.message || 'Aktivierung fehlgeschlagen.'); }
    await refresh();
  });
  disable.addEventListener('click', async () => {
    disable.disabled = true;
    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();
      if (!subscription) { await refresh(); return; }
      await request('/PushSubscription/Unregister/', 'DELETE', { endpoint: subscription.endpoint });
      await subscription.unsubscribe();
      notice('Benachrichtigungen deaktiviert.');
    } catch (error) { notice(error.message || 'Deaktivierung fehlgeschlagen.'); }
    await refresh();
  });
})();
