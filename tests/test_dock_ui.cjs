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
  assert.match(html,/cxm-dock\.js\?v=0\.8\.1/);
  assert.match(html,/data-panel="calibration"/);
  assert.match(cards,/data-cxm-calibrate/);
});
test('dock coordinates require three axes, deliberate approval and server validation',()=>{
  assert.match(dock,/const axis = \['x','y','z'\]/);
  assert.match(dock,/!Number\.isFinite\(Number\(v\)\)/);
  assert.match(dock,/window\.confirm\(/);
  assert.match(dock,/postJSON\('\/dock',\{tool:selected,xyz,expected_revision:snapshot\.revision\}\)/);
  assert.match(dock,/stored\['dock_'\+name\] === xyz\[name\]/);
  assert.match(dock,/fill\(\); \/\/ Re-enable inputs after the request and show the saved values/);
});
test('V0.4 cannot issue motion or falsely verify hardware pickup',()=>{
  assert.doesNotMatch(dock,/\/printer\/gcode\/script|\/printer\/gcode\/help|postJSON\('\/printer\//);
  assert.match(html,/button class="btn" disabled title="Requires safe Klipper macros">Approach dock/);
  assert.match(html,/button class="btn" disabled title="Requires physical pickup sensor testing">Test pickup/);
  assert.match(html,/Crosshair is a visual reference only/);
  assert.match(dock,/NOT verified in Klipper/);
});
 
test('accept button remains disabled for blank, invalid or unchanged drafts',()=>{
  assert.match(dock,/function validDraft\(\)/);
  assert.match(dock,/if \(!snapshot \|\| busy \|\| !dirty \|\| !canEdit\(\)\) return false/);
  assert.match(dock,/get\('cxmDockAccept'\)\.disabled=!validDraft\(\)/);
  assert.match(dock,/if \(!validDraft\(\)\)/);
  assert.match(dock,/function updateActions\(\)/);
});
test('successful save re-enables coordinate fields; failed save retains draft',()=>{
  assert.match(dock,/busy = false;[\s\S]*?if \(verified\) \{[\s\S]*?fill\(\)/);
  assert.match(dock,/for \(const name of axis\) get\('cxmDock'\+name\.toUpperCase\(\)\)\.disabled=!canEdit\(\)/);
  assert.match(dock,/Discard unsaved dock XYZ draft and switch hotends/);
});

test('all selected hotends remain visible; maintenance-locked tools cannot save XYZ',()=>{
  const script=fs.readFileSync(path.join(__dirname,'../web/cxm-dock.js'),'utf8');
  assert.match(script,/\.filter\(p => p\.n < count\)/);
  assert.match(script,/get\('cxmDockStatus'\)\.textContent = [\s\S]*?'LOCKED \/ MIGRATION · read only'/);
  assert.match(script,/node\.textContent = 'T'\+option\.n/);
  assert.match(script,/get\('cxmDockAccept'\)\.disabled=!validDraft\(\)/);
  assert.match(script,/if \(!snapshot \|\| busy \|\| !dirty \|\| !canEdit\(\)\) return false/);
});

test('Dock editor requires migration completed and no manual lockout',()=>{
 assert.match(dock,/!snapshot\.migration_required/);
 assert.match(dock,/maintenance_lockout !== true/);
 assert.match(dock,/CXMToolPicker\?\.sync\(select,snapshot\.config\)/);
 assert.match(dock,/window\.CXMToolState\?\.classify\(option\.tool/);
});

test('V0.7 offline XY measurement lab is read-only and never offers live motion',()=>{
 const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
 assert.match(html,/1 · Automatic XY dock measurement/);
 assert.match(html,/Offline calculator available · Hardware pending/);
 assert.match(html,/Measure dock XY · unavailable<\/button>/);
 assert.match(html,/button class="btn" disabled title="Requires MCU, safe homing and verified capture adapter"/);
 assert.match(html,/python3 ~\/CXM\/scripts\/cxm_xy_review\.py --example/);
 assert.match(html,/without moving motors or saving a calibration/);
});

test('dock layout follows measure → align → verify, with the same safety controls',()=>{
 const section=html.split('<section data-panel="calibration" hidden>')[1]
                   .split('</section>')[0];
 const auto=section.indexOf('<h3>1 · Automatic XY dock measurement</h3>');
 const align=section.indexOf('<h3>2 · Align dock position</h3>');
 const verify=section.indexOf('<h3>3 · Test and verify</h3>');
 const recovery=section.indexOf('<h3>Recovery</h3>');
 assert.ok(auto>=0 && align>auto && verify>align && recovery>verify);
 assert.match(section,/After obtaining verified dock X\/Y in step 1, enter the separately established dock Z/);
 assert.match(section,/button class="btn" disabled title="Requires MCU, safe homing and verified capture adapter"/);
 assert.match(section,/button class="btn" disabled title="Requires safe Klipper macros"/);
 assert.match(section,/button class="btn" disabled title="Requires physical pickup sensor testing"/);
 for(const id of ['cxmDockTool','cxmDockAccept','cxmDockReset','cxmDockBackups','cxmDockFeedback'])
   assert.equal(section.split('id="'+id+'"').length-1,1);
});
