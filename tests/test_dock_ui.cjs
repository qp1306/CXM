/* V0.4 safety and dock editor regression checks: node --test tests/test_dock_ui.cjs */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
const dock=fs.readFileSync(path.join(__dirname,'../web/cxm-dock.js'),'utf8');
const cards=fs.readFileSync(path.join(__dirname,'../web/cxm-tool-cards.js'),'utf8');

test('dock wizard loads and includes required user controls',()=>{
  for(const id of ['cxmDockTool','cxmDockX','cxmDockY','cxmDockZ',
                   'cxmDockAccept','cxmDockReset','cxmDockBackups',
                   'cxmDockFeedback']) {
    assert.match(html,new RegExp('id="'+id+'"'));
  }
  assert.match(html,/cxm-dock\.js\?v=0\.4\.0/);
  assert.match(html,/data-panel="calibration"/);
  assert.match(cards,/data-cxm-calibrate/);
});
test('dock coordinates require three axes, deliberate approval and server validation',()=>{
  assert.match(dock,/const axis = \['x','y','z'\]/);
  assert.match(dock,/!Number\.isFinite\(Number\(v\)\)/);
  assert.match(dock,/window\.confirm\(/);
  assert.match(dock,/postJSON\('\/dock',\{tool:selected,xyz,expected_revision:snapshot\.revision\}\)/);
  assert.match(dock,/stored\['dock_'\+name\] === xyz\[name\]/);
  assert.match(dock,/fill\(\); \/\/ Show the freshly verified saved values/);
});
test('V0.4 cannot issue motion or falsely verify hardware pickup',()=>{
  assert.doesNotMatch(dock,/\/printer\/gcode\/script|\/printer\/gcode\/help|postJSON\('\/printer\//);
  assert.match(html,/button class="btn" disabled title="Requires safe Klipper macros">Approach dock/);
  assert.match(html,/button class="btn" disabled title="Requires physical pickup sensor testing">Test pickup/);
  assert.match(html,/Saved positions are provisional/);
  assert.match(dock,/not verified or active in Klipper/);
});
