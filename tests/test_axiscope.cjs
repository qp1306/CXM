/* CXM V0.5 regression checks: axis camera is view-only and tools have stable identity. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
const axis=fs.readFileSync(path.join(__dirname,'../web/cxm-axiscope.js'),'utf8');
const card=fs.readFileSync(path.join(__dirname,'../web/cxm-tool-cards.js'),'utf8');
const colors=require('../web/cxm-tool-style.js');

test('12 stable tool colours with T0 reference label',()=>{
  assert.equal(colors.palette.length,12);
  assert.equal(new Set(colors.palette).size,12);
  assert.equal(colors.color(0),'#B6C4D5');
  assert.equal(colors.color(12),'#B6C4D5');
  assert.match(card,/class="cxm-tool-chip"/);
  assert.match(card,/CXMToolStyle\?\.color\(n\)/);
  assert.match(axis,/n===0\?' REF'/);
});
test('Axiscope camera supports same-origin webcam discovery but no remote embedding',()=>{
  assert.match(axis,/\/server\/webcams\/list/);
  assert.match(axis,/url\.origin!==origin/);
  assert.match(axis,/url\.username \|\| url\.password/);
  assert.match(axis,/!webcams\.length/);
  assert.match(axis,/cameraURL\(entry\.stream_url,window\.location\.origin\)/);
});
test('all motion and capture controls are disabled with no G-code paths',()=>{
  assert.match(html,/id="cxmAxisFrame"/);
  assert.match(html,/id="cxmAxisTable"/);
  assert.match(html,/button class="btn" disabled>Y\+/);
  assert.match(html,/button class="btn" disabled>X−/);
  assert.match(html,/button class="btn" disabled>X\+/);
  assert.match(html,/button class="btn" disabled>Y−/);
  assert.match(html,/button class="btn" disabled>Capture measurement/);
  assert.doesNotMatch(axis,/\/printer\/gcode\/script|G1\s+[XY]|SET_GCODE_OFFSET|postJSON\(/);
  assert.match(html,/crosshair|Crosshair/i);
  assert.match(html,/CXM starter <span>v[0-9]+\.[0-9]+\.[0-9]+<\/span>/);
});
