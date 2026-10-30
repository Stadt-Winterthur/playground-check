// Push-only service worker for the native Django UI. Never cache private HTML.
const BASE_PATH = new URL(self.registration.scope).pathname.replace(/\/$/, '');
const scoped = path => `${BASE_PATH}${path}` || '/';
self.addEventListener('install', event => event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', event => event.waitUntil(
  Promise.all([
    caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('spielplatzkontrolle-')).map(key => caches.delete(key)))),
    self.clients.claim()
  ])
));
self.addEventListener('push', event => {
  let payload = {};
  try { payload = event.data ? event.data.json() : {}; } catch (_) {}
  const notification = payload.notification || payload;
  const tasks = [];
  if (notification && notification.title) {
    tasks.push(self.registration.showNotification(notification.title, {
      body: notification.body || '', icon: notification.icon, badge: notification.badge,
      data: notification.data || {}
    }));
  }
  tasks.push(clients.matchAll({type: 'window', includeUncontrolled: true}).then(all =>
    Promise.all(all.map(client => client.postMessage({type: 'push-message', message: payload})))));
  event.waitUntil(Promise.all(tasks));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  const data = event.notification.data || {};
  let path = '/__ui/defects/';
  if (data.defectTid) path = '/__ui/defect/?tid=' + encodeURIComponent(data.defectTid);
  else if (typeof data.url === 'string' && data.url.startsWith('/__ui/')) path = data.url;
  const target = new URL(scoped(path), self.location.origin).href;
  event.waitUntil(clients.matchAll({type: 'window', includeUncontrolled: true}).then(async all => {
    if (all.length) {
      const client = all[0];
      if ('navigate' in client) await client.navigate(target);
      return client.focus();
    }
    return clients.openWindow ? clients.openWindow(target) : undefined;
  }));
});
