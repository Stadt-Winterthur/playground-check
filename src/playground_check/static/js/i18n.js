/* Local catalog only. Text is inserted through textContent, never HTML. */
(() => {
  'use strict';
  const data = document.getElementById('ui-translations');
  const messages = data ? JSON.parse(data.textContent) : {};
  window.spkT = (source, parameters = {}) => (messages[source] || source)
    .replace(/\{(\w+)\}/g, (match, key) => Object.hasOwn(parameters, key) ? String(parameters[key]) : match);
  // Native validation follows the explicit page language as well as the browser default.
  document.addEventListener('invalid', event => {
    const field = event.target;
    if (typeof field.setCustomValidity !== 'function') return;
    field.setCustomValidity('');
    const v = field.validity;
    let message = '';
    if (v.valueMissing) message = window.spkT('Bitte füllen Sie dieses Feld aus.');
    else if (v.typeMismatch && field.type === 'email') message = window.spkT('Bitte geben Sie eine gültige E-Mail-Adresse ein.');
    else if (v.rangeUnderflow) message = window.spkT('Der Wert muss mindestens {min} sein.', {min: field.min});
    else if (v.rangeOverflow) message = window.spkT('Der Wert darf höchstens {max} sein.', {max: field.max});
    else if (v.tooLong) message = window.spkT('Bitte verwenden Sie höchstens {max} Zeichen.', {max: field.maxLength});
    else if (v.typeMismatch || v.patternMismatch || v.badInput || v.stepMismatch) message = window.spkT('Bitte prüfen Sie das Format Ihrer Eingabe.');
    field.setCustomValidity(message);
  }, true);
  const clearValidation = event => {
    if (typeof event.target.setCustomValidity === 'function') event.target.setCustomValidity('');
  };
  document.addEventListener('input', clearValidation);
  document.addEventListener('change', clearValidation);
})();
