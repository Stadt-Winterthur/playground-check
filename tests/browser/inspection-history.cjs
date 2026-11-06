/* Unit test of the real history filter, independent of a browser installation. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function history(value) {
  const listeners = {};
  const selector = {value, addEventListener: (event, handler) => {listeners[event] = handler;}};
  const groups = ['VI', 'HI', 'OI'].map(kind => ({dataset: {historyType: kind}}));
  return {
    selector, groups, listeners,
    querySelector: () => selector,
    querySelectorAll: () => groups,
  };
}
const last = history('VI');
const previous = history('HI');
const form = {querySelectorAll: selector => selector === '[data-inspection-history]' ? [last, previous] : []};
vm.runInNewContext(fs.readFileSync(path.resolve(__dirname, '../../src/playground_check/static/js/inspection-workflow.js'), 'utf8'), {
  window: {}, document: {getElementById: id => id === 'inspection-form' ? form : null},
});
const visible = item => item.groups.filter(group => !group.hidden).map(group => group.dataset.historyType);
assert.deepEqual(visible(last), ['VI']);
assert.deepEqual(visible(previous), ['HI']);
last.selector.value = 'OI';
last.listeners.change();
assert.deepEqual(visible(last), ['OI']);
assert.deepEqual(visible(previous), ['HI']);
previous.selector.value = 'VI';
previous.listeners.change();
assert.deepEqual(visible(last), ['OI']);
assert.deepEqual(visible(previous), ['VI']);
console.log('History filters preserve independent last/previous inspection type selections.');
