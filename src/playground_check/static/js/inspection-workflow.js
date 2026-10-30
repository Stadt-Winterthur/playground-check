/* Small progressive enhancement: the server remains the authority for inspection data. */
(function () {
  const form = document.getElementById('inspection-form');
  if (!form) return;
  const panels = Array.from(form.querySelectorAll('[data-inspection-device]'));
  const selectors = Array.from(form.querySelectorAll('[data-inspection-select]'));
  const chips = Array.from(form.querySelectorAll('button[data-inspection-chip]'));
  const overview = document.getElementById('inspection-overview');
  const finish = document.getElementById('inspection-submit');
  const finishWarning = document.getElementById('inspection-finish-warning');
  const progress = document.getElementById('inspection-progress');
  const submit = finish.querySelector('button[type="submit"]');
  if (!panels.length) return;
  const fieldName = 'selected_device';
  const chosen = document.createElement('input');
  chosen.type = 'hidden'; chosen.name = fieldName;
  form.appendChild(chosen);
  function checks(panel) {
    return Array.from(panel.querySelectorAll('input[type="checkbox"][name^="inspection_done_"], input[type="checkbox"][name^="maintenance_done_"]'));
  }
  function update(panel) {
    const id = panel.dataset.inspectionDevice;
    const all = checks(panel);
    const complete = all.length > 0 && all.every(box => box.checked);
    const status = !all.length ? (panel.querySelector('.inspection-chip-toggle') ? 'keine Kontrollen' : null) : (complete ? 'erledigt' : 'pendent');
    const toggle = panel.querySelector('[data-inspection-toggle]');
    const chooser = selectors.find(button => button.dataset.inspectionSelect === id);
    const chip = chips.find(button => button.dataset.inspectionChip === id);
    if (toggle) {
      toggle.textContent = status;
      toggle.classList.toggle('is-done', complete);
      toggle.setAttribute('aria-label', complete ? 'Alle Prüf- und Wartungsschritte dieses Geräts auf pendent setzen' : 'Alle Prüf- und Wartungsschritte dieses Geräts als erledigt markieren');
    }
    if (chip && all.length) {
      chip.textContent = status;
      chip.classList.toggle('is-done', complete);
      chip.setAttribute('aria-label', (complete ? 'Alle Prüf- und Wartungsschritte auf pendent setzen: ' : 'Alle Prüf- und Wartungsschritte als erledigt markieren: ') + (chooser?.textContent || '').trim());
    }
    refreshProgress();
    panel.querySelectorAll('.inspection-criterion').forEach(criterion => {
      const itemChecks = checks(criterion);
      const done = itemChecks.length > 0 && itemChecks.every(box => box.checked);
      const itemChip = criterion.querySelector('[data-inspection-criterion-chip]');
      if (itemChip) {
        itemChip.textContent = done ? 'erledigt' : 'pendent';
        itemChip.classList.toggle('is-done', done);
      }
    });
  }
  function refreshProgress() {
    const unreasoned = panels.filter(panel => panel.dataset.cannotCheck === 'true' && panel.dataset.cannotReason !== 'true');
    const relevant = panels.filter(panel => checks(panel).length > 0);
    const completed = relevant.filter(panel => checks(panel).every(box => box.checked)).length;
    progress.textContent = `${completed} von ${relevant.length} kontrollierbaren Spielgeräten erledigt`;
    const incomplete = relevant.filter(panel => !checks(panel).every(box => box.checked));
    finishWarning.textContent = unreasoned.length ? 'Mindestens ein nicht prüfbares Spielgerät benötigt noch eine Begründung.' : (incomplete.length ? `Noch ${incomplete.length} Spielgerät(e) pendent. Bitte alle Prüf- und Wartungsschritte erledigen.` : 'Alle erforderlichen Prüf- und Wartungsschritte sind erledigt.');
    submit.disabled = !!incomplete.length || !!unreasoned.length || !relevant.length;
  }
  function overviewView(focus) {
    chosen.value = '';
    overview.hidden = false;
    finish.hidden = false;
    panels.forEach(panel => { panel.hidden = true; });
    selectors.forEach(button => { button.setAttribute('aria-pressed', 'false'); button.classList.remove('is-selected'); });
    refreshProgress();
    if (focus) overview.scrollIntoView({block:'start'});
  }
  function select(id, focus) {
    chosen.value = id;
    overview.hidden = true;
    finish.hidden = true;
    panels.forEach(panel => { panel.hidden = panel.dataset.inspectionDevice !== id; });
    selectors.forEach(button => {
      const active = button.dataset.inspectionSelect === id;
      button.setAttribute('aria-pressed', String(active));
      button.classList.toggle('is-selected', active);
    });
    const activePanel = panels.find(panel => panel.dataset.inspectionDevice === id);
    if (focus && activePanel) activePanel.querySelector('h2')?.scrollIntoView({block:'start', behavior:'smooth'});
  }
  function toggleDevice(id) {
    const panel = panels.find(item => item.dataset.inspectionDevice === id);
    if (!panel) return;
    const all = checks(panel);
    if (!all.length) return;
    const newValue = !all.every(box => box.checked);
    all.forEach(box => { box.checked = newValue; });
    update(panel);
  }
  form.querySelectorAll('[data-inspection-back], [data-inspection-overview]').forEach(button => button.addEventListener('click', () => overviewView(true)));
  panels.forEach(panel => panel.querySelectorAll('[data-inspection-tab]').forEach(tab => tab.addEventListener('click', () => {
    const selected = tab.dataset.inspectionTab;
    panel.querySelector('[data-inspection-current]').hidden = selected !== 'current';
    panel.querySelectorAll('[data-inspection-history]').forEach(history => { history.hidden = history.dataset.inspectionHistory !== selected; });
    panel.querySelectorAll('[data-inspection-tab]').forEach(other => other.classList.toggle('is-active', other === tab));
  })));
  selectors.forEach(button => button.addEventListener('click', () => select(button.dataset.inspectionSelect, true)));
  chips.forEach(button => button.addEventListener('click', () => toggleDevice(button.dataset.inspectionChip)));
  panels.forEach(panel => {
    panel.addEventListener('change', event => {
      if (event.target.matches('input[type="checkbox"]')) update(panel);
    });
    const toggle = panel.querySelector('[data-inspection-toggle]');
    if (toggle) toggle.addEventListener('click', () => toggleDevice(toggle.dataset.inspectionToggle));
    update(panel);
  });
  const previous = form.dataset.selectedDevice || '';
  if (previous && panels.some(p => p.dataset.inspectionDevice === previous)) select(previous, false);
  else overviewView(false);
  if (form.dataset.formError === 'true') overviewView(false);
})();
