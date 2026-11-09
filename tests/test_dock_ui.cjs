/* V0.4 safety and dock editor regression checks: node --test tests/test_dock_ui.cjs */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
const dock=fs.readFileSync(path.join(__dirname,'../web/cxm-dock.js'),'utf8');
const cards=fs.readFileSync(path.join(__dirname,'../web/cxm-tool-cards.js'),'utf8');

test('dock wizard loads and includes required user controls',()=>{
  for(const id of ['cxmDockTool','cxmDockX','cxmDockY',
                   'cxmDockAccept','cxmDockReset','cxmDockBackups',
                   'cxmDockFeedback']) {
    assert.match(html,new RegExp('id="'+id+'"'));
  }
  assert.match(html,/cxm-dock\.js\?v=0\.9\.6/);
  assert.doesNotMatch(html,/id="cxmDockZ"/);
  assert.match(html,/data-panel="calibration"/);
  assert.match(cards,/data-cxm-calibrate/);
});
test('gantry dock coordinates require only X/Y, deliberate approval and server validation',()=>{
  assert.match(dock,/const axis = \['x','y'\]/);
  assert.match(dock,/!Number\.isFinite\(Number\(v\)\)/);
  assert.match(dock,/window\.confirm\(/);
  assert.match(dock,/postJSON\('\/dock',\{tool:selected,xy,expected_revision:snapshot\.revision/);
  assert.match(dock,/stored\['dock_'\+name\] === xy\[name\]/);
  assert.match(dock,/fill\(\); \/\/ Re-enable inputs after the request and show the saved values/);
});
test('V0.4 cannot issue motion or falsely verify hardware pickup',()=>{
  assert.doesNotMatch(dock,/\/printer\/gcode\/script|\/printer\/gcode\/help|postJSON\('\/printer\//);
  assert.match(html,/id="cxmT0Stage" disabled/);
  assert.match(html,/id="cxmT0Pickup" disabled/);
  assert.match(html,/id="cxmT0Dropoff" disabled/);
  assert.match(html,/Crosshair is a visual reference only/);
  assert.match(dock,/NOT accepted|NOT physically verified|unverified/i);
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
  assert.match(dock,/Discard unsaved dock XY draft and switch hotends/);
});

test('all selected hotends remain visible; maintenance-locked tools cannot save dock XY',()=>{
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

test('manual motor-on calibration is gated and preserves independent save',()=>{
 const manual=fs.readFileSync(path.join(__dirname,'../web/cxm-manual.js'),'utf8');
 assert.match(html,/<h3>Manual dock alignment<\/h3>/);
 assert.match(html,/cxm-manual\.js\?v=1\.0\.2/);
 for(const id of ['cxmManualApproval','cxmManualStep','cxmManualCapture',
                  'cxmManualReadiness','cxmManualCaptureAck','cxmManualFeedback',
                  'cxmManualX','cxmManualY','cxmManualSensor'])
   assert.match(html,new RegExp('id="'+id+'"'));
 assert.match(html,/id="cxmManualCapture" disabled/);
 assert.match(html,/data-manual-axis="x"/);
 assert.match(html,/data-manual-axis="y"/);
 assert.match(manual,/I_APPROVE_SUPERVISED_MOTOR_ON_JOG/);
 assert.match(manual,/I_INSPECTED_DOCK_ALIGNMENT_WITH_MOTORS_ON/);
 assert.match(manual,/request\\('\\/dock'/);
 assert.match(dock,/proposal\.source!=='motor-on-capture'/);
 assert.match(dock,/postJSON\('\/dock',\{tool:selected,xy,expected_revision:snapshot\.revision/);
 assert.doesNotMatch(manual,/DOCK_LOCATE_CALIBRATE|SET_KINEMATIC_POSITION/);
 assert.doesNotMatch(html,/id="cxmLineuxStart"|id="cxmLineuxReleaseXY"/);
});
test('dock layout has manual align then provisional save and native toolchange',()=>{
 const section=html.split('<section data-panel="calibration" hidden>')[1].split('</section>')[0];
 const align=section.indexOf('<h3>Manual dock alignment</h3>');
 const save=section.indexOf('<h3>Save dock XY</h3>');
 const native=section.indexOf('T0 · Pickup / Dropoff');
 assert.ok(align>=0 && save>align && native>save);
 assert.match(section,/Review X\/Y before saving/);
 for(const id of ['cxmDockTool','cxmDockAccept','cxmDockReset','cxmDockBackups','cxmDockFeedback'])
   assert.equal(section.split('id="'+id+'"').length-1,1);
});
test('read-only dock preflight remains independent of motor-on jog',()=>{
 for(const id of ['cxmDockLiveKlipper','cxmDockLiveHoming','cxmDockLiveState',
                  'cxmDockLivePosition','cxmDockLiveUpdated'])
   assert.match(html,new RegExp('id="'+id+'"'));
 assert.match(dock,/async function moonrakerRead\(path\)/);
 assert.match(dock,/await moonrakerRead\('\/printer\/info'\)/);
 assert.doesNotMatch(dock,/\/printer\/gcode\/script|\/printer\/gcode\/help|CARTOGRAPHER_TOUCH|SET_GCODE_OFFSET/);
 assert.match(html,/id="cxmManualCapture" disabled/);
});
test('old Python T0 movement interfaces are retired and native controls are exposed',()=>{
 assert.match(html,/id="cxmNativeToolPanel"/);
 assert.match(html,/id="cxmNativeSync"/);
 assert.match(html,/id="cxmNativeConfirm"/);
 assert.match(html,/id="cxmNativeToolAck"/);
 assert.match(html,/id="cxmNativeSelect"/);
 assert.match(html,/id="cxmNativeUnload"/);
 assert.doesNotMatch(html,/<script src="cxm-t0\.js/);
 assert.doesNotMatch(html,/<script src="cxm-t0-auto\.js/);
 assert.doesNotMatch(html,/<script src="cxm-tools\.js/);
 assert.match(html,/src="cxm-native-control\.js\?v=/);
 assert.match(html,/data-retired-python-control="true"/);
});
