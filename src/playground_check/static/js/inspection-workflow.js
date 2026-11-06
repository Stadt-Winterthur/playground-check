/* Small progressive enhancement: the server remains the authority for inspection data. */
(function () {
  const t = window.spkT || ((source, parameters = {}) => source.replace(/\{(\w+)\}/g, (match, key) => parameters[key] ?? match));

  const form = document.getElementById('inspection-form');
  if (!form) return;
  form.querySelectorAll('.inspection-checkability').forEach(editor => {
    const checkbox = editor.querySelector('[data-checkability-flag]');
    const reason = editor.querySelector('textarea');
    const updateCheckability = () => {
      editor.querySelector('[data-checkability-reason]').hidden = !checkbox.checked;
      reason.required = checkbox.checked;
      editor.querySelector('[data-checkability-save]').disabled = checkbox.checked && !reason.value.trim();
    };
    checkbox.addEventListener('change', updateCheckability);
    reason.addEventListener('input', updateCheckability);
    updateCheckability();
  });
  form.querySelectorAll('[data-inspection-history]').forEach(history => {
    const selector = history.querySelector('[data-history-filter]');
    if (!selector) return;
    const filter = () => history.querySelectorAll('[data-history-type]').forEach(group => {
      group.hidden = group.dataset.historyType !== selector.value;
    });
    selector.addEventListener('change', filter);
    filter();
  });
  const panels = Array.from(form.querySelectorAll('[data-inspection-device]'));
  const selectors = Array.from(form.querySelectorAll('[data-inspection-select]'));
  const chips = Array.from(form.querySelectorAll('button[data-inspection-chip]'));
  const finish = document.getElementById('inspection-submit');
  const finishWarning = document.getElementById('inspection-finish-warning');
  const progress = document.getElementById('inspection-progress');

  const submit = finish?.querySelector('button[type="submit"]');
  if (!panels.length) return;

  function checks(panel) {
    if (panel.dataset.notToCheck === 'true' || panel.dataset.cannotCheck === 'true') return [];
    return Array.from(panel.querySelectorAll('input[type="checkbox"][name^="inspection_done_"], input[type="checkbox"][name^="maintenance_done_"]'));
  }
  function update(panel) {
    const id = panel.dataset.inspectionDevice;
    const all = checks(panel);
    const complete = all.length > 0 && all.every(box => box.checked);
    const status = complete ? t("erledigt") : t("pendent");
    const chooser = selectors.find(button => button.dataset.inspectionSelect === id);
    const chip = chips.find(button => button.dataset.inspectionChip === id);
    if (chip && all.length) {
      chip.textContent = status;
      chip.classList.toggle('is-done', complete);
      chip.setAttribute('aria-label', (complete ? t("Alle Prüf- und Wartungsschritte auf pendent setzen: ") : t("Alle Prüf- und Wartungsschritte als erledigt markieren: ")) + (chooser?.textContent || '').trim());
    }
    refreshProgress();
    panel.querySelectorAll('.inspection-criterion').forEach(criterion => {
      const itemChecks = checks(criterion);
      const done = itemChecks.length > 0 && itemChecks.every(box => box.checked);
      criterion.classList.toggle('is-done', done);
      const itemChip = criterion.querySelector('[data-inspection-criterion-chip]');
      if (itemChip) {
        itemChip.textContent = done ? t("erledigt") : t("pendent");
        itemChip.classList.toggle('is-done', done);
      }
    });
  }
  function refreshProgress() {
    if (!progress || !finishWarning || !submit) return;
    const unreasoned = panels.filter(panel => panel.dataset.notToCheck !== 'true' && panel.dataset.cannotCheck === 'true' && panel.dataset.cannotReason !== 'true');
    const relevant = panels.filter(panel => checks(panel).length > 0);
    const completed = relevant.filter(panel => checks(panel).every(box => box.checked)).length;
    progress.textContent = t('{completed} von {total} kontrollierbaren Spielgeräten erledigt', {completed, total: relevant.length});
    const incomplete = relevant.filter(panel => !checks(panel).every(box => box.checked));
    finishWarning.textContent = unreasoned.length ? t("Mindestens ein nicht prüfbares Spielgerät benötigt noch eine Begründung.") : (incomplete.length ? t('Noch {count} Spielgerät(e) pendent. Bitte alle Prüf- und Wartungsschritte erledigen.', {count: incomplete.length}) : t("Alle erforderlichen Prüf- und Wartungsschritte sind erledigt."));
    submit.disabled = !!incomplete.length || !!unreasoned.length || !relevant.length;
  }
  function toggleDevice(id) {
    const panel = panels.find(item => item.dataset.inspectionDevice === id);
    if (!panel) return;
    const all = checks(panel);
    if (!all.length) return;
    const newValue = !all.every(box => box.checked);
    all.forEach(box => { box.checked = newValue; });
    update(panel);
    form.dispatchEvent(new Event("inspection-change"));
  }
  panels.forEach(panel => panel.querySelectorAll('[data-inspection-tab]').forEach(tab => tab.addEventListener('click', () => {
    const selected = tab.dataset.inspectionTab;
    panel.querySelector('[data-inspection-current]').hidden = selected !== 'current';
    panel.querySelectorAll('[data-inspection-history]').forEach(history => { history.hidden = history.dataset.inspectionHistory !== selected; });
    panel.querySelectorAll('[data-inspection-tab]').forEach(other => other.classList.toggle('is-active', other === tab));
  })));
  chips.forEach(button => button.addEventListener('click', () => toggleDevice(button.dataset.inspectionChip)));
  panels.forEach(panel => {
    panel.addEventListener('change', event => {
      if (event.target.matches('input[type="checkbox"]')) update(panel);
    });
    update(panel);
    form.dispatchEvent(new Event("inspection-change"));
  });
  form.addEventListener('draft-restored', () => panels.forEach(update));
  form.addEventListener('inspection-change', () => form.dispatchEvent(new Event('change', {bubbles:true})));
})();
