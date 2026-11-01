// Regression tests for CXM's no-MCU update gate.
// Run: node --test tests/test_web_update_safety.cjs
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8');
function extract(name) {
  const start = html.indexOf('function ' + name + '(');
  assert.notEqual(start, -1, name + ' not found');
  const end = html.indexOf('\n}', start) + 2;
  assert.ok(end > start + 2, name + ' end not found');
  return html.slice(start, end);
}
const identify = vm.runInNewContext('(' + extract('detectedMcuSetupFailure') + ')');
const gateSource = extract('validForInstall');

test('accepts only the two explicit primary MCU startup fault signatures', () => {
  const error = (state_message) => ({state: 'error', state_message});
  assert.equal(identify(error("mcu 'mcu': Unable to connect\nError configuring printer")), true);
  assert.equal(identify(error("Option 'serial' in section 'mcu' must be specified")), true);
  assert.equal(identify(error("mcu 'toolboard1': Unable to connect")), false);
  assert.equal(identify(error("mcu 'mcu': Timer too close")), false);
  assert.equal(identify({state: 'ready', state_message: "mcu 'mcu': Unable to connect"}), false);
});

test('development update requires explicit per-session confirmation', () => {
  const context = {
    currentUpdate: {repo: {is_valid: true, is_dirty: false, warnings: []}, busy: false},
    lastRepoCheck: true, busy: false, mcuSetupError: true, devConfirmed: false,
    klipperReady: false, idleState: null, printingState: null,
    hasUpdate: () => true
  };
  const gate = vm.runInNewContext('(' + gateSource + ')', context);
  assert.equal(gate(), false);
  context.devConfirmed = true;
  assert.equal(gate(), true);
  context.currentUpdate.repo.is_dirty = true;
  assert.equal(gate(), false);
});

test('other errors fail closed; a ready and idle printer is allowed', () => {
  const context = {
    currentUpdate: {repo: {is_valid: true, is_dirty: false, warnings: []}, busy: false},
    lastRepoCheck: true, busy: false, mcuSetupError: false, devConfirmed: true,
    klipperReady: false, idleState: null, printingState: null,
    hasUpdate: () => true
  };
  const gate = vm.runInNewContext('(' + gateSource + ')', context);
  assert.equal(gate(), false);
  context.klipperReady = true;
  context.idleState = 'Printing';
  assert.equal(gate(), false);
  context.idleState = 'Idle';
  assert.equal(gate(), true);
  context.printingState = 'paused';
  assert.equal(gate(), false);
});
