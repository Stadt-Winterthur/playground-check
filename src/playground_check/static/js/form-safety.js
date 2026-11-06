/* Per-tab, per-account inspection drafts and navigation protection. No external storage. */
(() => {
  'use strict';
  const t = window.spkT || ((source, parameters = {}) => source.replace(/\{(\w+)\}/g, (match, key) => parameters[key] ?? match));
  const imageFallback = image => {
    if (!(image instanceof HTMLImageElement) || !image.dataset.fallbackSrc) return;
    const fallback = image.dataset.fallbackSrc;
    delete image.dataset.fallbackSrc;
    image.src = fallback;
  };
  document.addEventListener('error', event => imageFallback(event.target), true);
  document.querySelectorAll('img[data-fallback-src]').forEach(image => {
    if (image.complete && !image.naturalWidth) imageFallback(image);
  });
  // Make the common server-rendered error visible to keyboard and assistive
  // technology users. Do not navigate away or reset any form field. HTMX may
  // insert a new fragment without reloading the page.
  const focusFormError = root => {
    const target = root?.matches?.('.app-form-error') ? root : root?.querySelector?.('.app-form-error');
    if (target && target.isConnected && !target.hasAttribute('hidden')) {
      target.focus({preventScroll: true});
      target.scrollIntoView({block: 'nearest', behavior: 'instant'});
    }
  };
  focusFormError(document);
  document.addEventListener('htmx:afterSwap', event => focusFormError(event.detail?.target));
  const prefixKey = 'spk-inspection-draft:';
  const forms = [...document.querySelectorAll('form[data-inspection-draft],form[data-protect-changes]')];
  let loggingOut = false;
  const now = () => Date.now();
  const expireMs = 4 * 60 * 60 * 1000;
  const getKey = form => prefixKey + JSON.stringify([document.body.dataset.userFid || '',
    new URL(form.action).pathname, form.elements.namedItem('name')?.value || '',
    form.elements.namedItem('inspectiontype')?.value || '']);
  const storage = {
    get(key) { try { return JSON.parse(sessionStorage.getItem(key)); } catch (_) { return null; } },
    set(key, value) { try { sessionStorage.setItem(key, JSON.stringify(value)); return true; } catch (_) { return false; } },
    remove(key) { try { sessionStorage.removeItem(key); } catch (_) {} }
  };
  const fields = form => [...form.querySelectorAll('input,textarea')].filter(el =>
    /^(inspection_done_|maintenance_done_|comment_|maintenance_comment_)/.test(el.name));
  forms.forEach(form => {
    let dirty = form.dataset.formError === 'true';
    const draft = form.hasAttribute('data-inspection-draft');
    const key = draft ? getKey(form) : null;
    const schema = [...form.querySelectorAll('[data-inspection-device]')].map(panel =>
      panel.dataset.inspectionDevice + ':' + [...panel.querySelectorAll('input[name^="inspection_done_"],.inspection-instruction')].map(el => el.name || el.textContent.trim()).join('\n')).join('\n');
    let status;
    if (draft) {
      status = document.createElement('p'); status.className = 'form-draft-status';
      status.setAttribute('role', 'status');
      status.textContent = t("Ein Entwurf wird in diesem Browsertab bis zu vier Stunden gesichert.");
      form.before(status);
      const saved = storage.get(key);
      if (saved && saved.schema === schema && now() - saved.time < expireMs && form.dataset.formError !== 'true' && form.dataset.serverValues !== 'true') {
        fields(form).forEach(el => {
          if (Object.hasOwn(saved.values || {}, el.name)) {
            if (el.type === 'checkbox') el.checked = saved.values[el.name] === true;
            else el.value = saved.values[el.name];
          }
        });
        dirty = true; status.textContent = t("Ihr Entwurf aus diesem Browsertab wurde wiederhergestellt. Bitte Prüfkriterien vor dem Abschluss kontrollieren.");
        // The workflow script is deferred too and may initialise after this script.
        setTimeout(() => form.dispatchEvent(new Event('draft-restored')), 0);
      } else if (saved && (saved.schema !== schema || now() - saved.time >= expireMs)) {
        storage.remove(key);
        status.textContent = t("Ein früherer Entwurf ist abgelaufen oder die Prüfkriterien haben sich geändert. Bitte die Kontrolle neu bearbeiten.");
      }
    }
    const changed = () => {
      dirty = true;
      if (draft) {
        const values = Object.fromEntries(fields(form).map(el => [el.name, el.type === 'checkbox' ? el.checked : el.value]));
        const ok = storage.set(key, {time: now(), schema, values});
        status.textContent = ok ? t("Entwurf in diesem Browsertab gesichert. Der Bericht ist noch nicht eingereicht.") :
          t("Der Entwurf konnte nicht gesichert werden. Bitte diese Seite bis zum Abschluss geöffnet lassen.");
      }
    };
    form.addEventListener('input', changed); form.addEventListener('change', changed);
    form.addEventListener('submit', () => { dirty = false; });
    window.addEventListener('beforeunload', event => { if (dirty && !loggingOut) { event.preventDefault(); event.returnValue = ''; } });
  });
  const success = document.querySelector('[data-inspection-saved]');
  if (success) storage.remove(prefixKey + JSON.stringify([document.body.dataset.userFid || '',
    success.dataset.action, success.dataset.name, success.dataset.kind]));
  document.querySelectorAll('form[data-logout]').forEach(form => form.addEventListener('submit', () => {
    loggingOut = true;
    try { Object.keys(sessionStorage).filter(k => k.startsWith(prefixKey)).forEach(k => sessionStorage.removeItem(k)); } catch (_) {}
  }));
})();
