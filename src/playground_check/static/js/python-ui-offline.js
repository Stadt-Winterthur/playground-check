/* Offline inspection drafts. Explicit save/restore; no automatic POST/retry. */
(() => {
  'use strict';
  const root = document.getElementById('offline-drafts');
  const form = document.getElementById('inspection-form');
  if (!root || !form) return;
  const status = document.getElementById('draft-status');
  const key = ['spk-inspection-v1', location.origin, root.dataset.path || '',
    root.dataset.user || '', root.dataset.playground || '', root.dataset.inspection || ''].join(':');
  const dbName = 'spielplatzkontrolle-private-drafts';
  let database;
  const notice = message => { status.textContent = message; };
  const open = () => new Promise((resolve, reject) => {
    const req = indexedDB.open(dbName, 1);
    req.onupgradeneeded = () => { if (!req.result.objectStoreNames.contains('drafts')) req.result.createObjectStore('drafts'); };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  const transaction = (mode, work) => new Promise((resolve, reject) => {
    const tx = database.transaction('drafts', mode);
    const request = work(tx.objectStore('drafts'));
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    tx.onabort = () => reject(tx.error);
  });
  const fields = () => Array.from(form.elements).filter(element => element.name &&
    !['csrfmiddlewaretoken', 'confirm'].includes(element.name) &&
    !['file', 'password', 'submit'].includes(element.type) &&
    !element.disabled &&
    (element.name.startsWith('comment_') || element.name.startsWith('maintenance_comment_') ||
     element.name.startsWith('inspection_done_') || element.name.startsWith('maintenance_done_')));
  const snapshot = () => fields().map(element => ({name: element.name,
    type: element.type, value: element.type === 'checkbox' ? element.checked : element.value}));
  const restore = records => {
    const byName = new Map(records.map(entry => [entry.name, entry]));
    for (const element of fields()) {
      const saved = byName.get(element.name);
      if (!saved || saved.type !== element.type) continue;
      if (element.type === 'checkbox') element.checked = saved.value === true;
      else element.value = String(saved.value).slice(0, element.maxLength > 0 ? element.maxLength : 2000);
    }
  };
  const button = id => document.getElementById(id);
  const run = handler => async () => { try { await handler(); } catch (error) {
    notice('Offline-Speicher nicht verfügbar. Browser-Einstellungen prüfen.');
  }};
  if (!('indexedDB' in window)) { notice('Dieser Browser unterstützt keinen lokalen Entwurfsspeicher.'); return; }
  open().then(db => {
    database = db;
    notice('Lokaler Entwurfsspeicher bereit. Nicht auf gemeinsam genutzten Geräten verwenden.');
    button('draft-save').addEventListener('click', run(async () => {
      const values = snapshot();
      if (JSON.stringify(values).length > 180000) throw new Error('draft too large');
      await transaction('readwrite', store => store.put({values, updated: Date.now()}, key));
      notice('Lokal gespeichert – nicht an den Server übermittelt.');
    }));
    button('draft-restore').addEventListener('click', run(async () => {
      const data = await transaction('readonly', store => store.get(key));
      if (!data || !Array.isArray(data.values)) { notice('Kein lokaler Entwurf vorhanden.'); return; }
      restore(data.values);
      notice('Entwurf wiederhergestellt. Vor dem endgültigen Speichern alle Kriterien prüfen.');
    }));
    button('draft-delete').addEventListener('click', run(async () => {
      await transaction('readwrite', store => store.delete(key));
      notice('Lokaler Entwurf gelöscht.');
    }));
    // Server acknowledgement only: a successful real navigation leaves this page.
    // Never auto-repeat a possibly accepted POST after timeout/network failure.
    window.addEventListener('online', () => notice('Verbindung vorhanden. Entwurf prüfen und bewusst speichern.'));
  }).catch(() => notice('Lokaler Entwurfsspeicher nicht verfügbar.'));
})();
