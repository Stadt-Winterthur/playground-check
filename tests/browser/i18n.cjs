/* No browser installation needed: catalog interpolation and validation messages. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../..');
const catalogs = JSON.parse(fs.readFileSync(path.join(root, 'src/playground_check/django_project/translations.json'), 'utf8'));
const script = fs.readFileSync(path.join(root, 'src/playground_check/static/js/i18n.js'), 'utf8');
for (const language of ['de', 'fr', 'it', 'rm', 'en']) {
  const handlers = {};
  const messages = Object.fromEntries(catalogs.js_keys.map(source => [source, catalogs[language]?.[source] || source]));
  const window = {};
  const document = {
    getElementById: () => ({textContent: JSON.stringify(messages)}),
    addEventListener: (name, callback) => { handlers[name] = callback; }
  };
  vm.runInNewContext(script, {window, document});
  const source = '{completed} von {total} kontrollierbaren Spielgeräten erledigt';
  const progress = window.spkT(source, {completed: 2, total: 5});
  assert.ok(progress.includes('2') && progress.includes('5'));
  assert.ok(!progress.includes('{'));
  if (language !== 'de') assert.notEqual(progress, source.replace('{completed}', '2').replace('{total}', '5'));
  const field = {validity: {valueMissing: true}, setCustomValidity(message) { this.message = message; }};
  handlers.invalid({target: field});
  assert.equal(field.message, messages['Bitte füllen Sie dieses Feld aus.']);
  handlers.input({target: field});
  assert.equal(field.message, '');
  field.validity = {rangeUnderflow: true}; field.min = 1900;
  handlers.invalid({target: field});
  assert.ok(field.message.includes('1900'));
  handlers.change({target: field});
  assert.equal(field.message, '');
  // Substitution returns text and never evaluates or interprets parameters.
  assert.equal(window.spkT('{value}', {value: '<script>test</script>'}), '<script>test</script>');
}
console.log('Five languages: interpolation, validation messages and validation reset passed.');
