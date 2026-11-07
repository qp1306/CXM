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

test('Lineux live measurement is gated, provisional, and separate from protected dock AutoSave',()=>{
 const lineux=fs.readFileSync(path.join(__dirname,'../web/cxm-lineux.js'),'utf8');
 assert.match(html,/<h3>Automatic dock measurement<\/h3>/);
 assert.match(html,/cxm-lineux\.js\?v=0\.9\.14/);
 for(const id of ['cxmLineuxAck','cxmLineuxPreflight','cxmLineuxStart',
                  'cxmLineuxResult','cxmLineuxToDraft',
                  'cxmLineuxReleaseXY','cxmLineuxReleaseAck','cxmLineuxReleaseStatus',
                  'cxmLineuxHome','cxmLineuxHomeAck','cxmLineuxHomeStatus'])
   assert.match(html,new RegExp('id="'+id+'"'));
 assert.match(html,/id="cxmLineuxStart" disabled/);
 assert.match(html,/id="cxmLineuxHomeAck" type="checkbox"/);
 assert.match(html,/id="cxmLineuxReleaseAck" type="checkbox"/);
 assert.match(html,/id="cxmLineuxAck" type="checkbox"/);
 assert.doesNotMatch(lineux,/window\.confirm\('HOME AND PREPARE|window\.confirm\('RELEASE COREXY|window\.confirm\('START LINEUX DOCK MEASUREMENT/);
 assert.match(html,/id="cxmLineuxToDraft" disabled/);
 assert.match(html,/id="cxmLineuxKnownStart" disabled/);
 assert.match(html,/id="cxmLineuxKnownAck"/);
 assert.match(html,/Advanced diagnostic · known-position Lineux accuracy check \(optional\)/);
 assert.match(html,/1 · Home printer/);
 assert.match(html,/Advanced: old MCU step-count calculator/);
 assert.match(html,/2 · Release X\/Y/);
 assert.match(html,/3 · Align dock by hand/);
 assert.match(html,/4 · Measure dock XY/);
 assert.match(lineux,/I_CONFIRM_Z_SUPPORTED_RELEASE_XY/);
 assert.match(lineux,/I_CONFIRM_CLEAR_G28_AND_Z20_PATH/);
 assert.match(lineux,/call\('\/home'/);
 assert.match(lineux,/refreshReleaseReadiness/);
 assert.match(lineux,/mode=prepare/);
 assert.doesNotMatch(lineux,/await preflight\(\);\s*el\('cxmLineuxHomeStatus'\)/);
 assert.doesNotMatch(lineux,/!state\?\.known_verified/);
 assert.match(lineux,/I_CONFIRM_CLEAR_DOCK_PATH/);
 assert.match(lineux,/expected_revision:snapshot\.revision/);
 assert.match(lineux,/status!=='PROVISIONAL_LINEUX_UNVERIFIED'/);
 assert.match(lineux,/source:'lineux-live'/);
 assert.match(lineux,/raw_xy:result\.raw_xy_mm/);
 assert.match(dock,/rawDraft/);
 assert.match(dock,/dock_reference_accepted/);
 assert.doesNotMatch(lineux,/\/printer\/gcode\/script/);
 assert.match(dock,/\['manual-mcu-review','lineux-live'\]/);
});

test('dock layout follows measure → save and optional T0 tests, with all safety controls',()=>{
 const section=html.split('<section data-panel="calibration" hidden>')[1]
                   .split('</section>')[0];
 const auto=section.indexOf('<h3>Automatic dock measurement</h3>');
 const align=section.indexOf('<h3>Save dock XY</h3>');
 const verify=section.indexOf('T0 · Pickup / Dropoff');
 const advanced=section.indexOf('Advanced T0 motion &amp; sensor tests');
 const recovery=section.indexOf('Recovery and backups');
 assert.ok(auto>=0 && align>auto && verify>align && advanced>verify && recovery>advanced);
 assert.match(section,/Review X\/Y before saving/);
 assert.match(section,/id="cxmLineuxStart" disabled/);
 assert.match(section,/id="cxmLineuxToDraft" disabled/);
 assert.match(section,/id="cxmT0Stage" disabled/);
 assert.match(section,/id="cxmT0Pickup" disabled/);
 for(const id of ['cxmDockTool','cxmDockAccept','cxmDockReset','cxmDockBackups','cxmDockFeedback'])
   assert.equal(section.split('id="'+id+'"').length-1,1);
});

test('V0.8.2 dock preflight reads real Klipper status but cannot authorise motion',()=>{
 for(const id of ['cxmDockLiveKlipper','cxmDockLiveHoming','cxmDockLiveState',
                  'cxmDockLivePosition','cxmDockLiveHomingTest','cxmDockLiveUpdated'])
  assert.match(html,new RegExp('id="'+id+'"'));
 assert.doesNotMatch(html,/No MCU connected/);
 assert.match(html,/id="activeTool" hidden>Not integrated<\/span>/);
 assert.match(html,/Printer diagnostics \(optional\)/);
 assert.match(html,/XYZ is the CURRENT carriage position|read-only Klipper hardware preflight/i);
 assert.match(dock,/async function moonrakerRead\(path\)/);
 assert.match(dock,/await moonrakerRead\('\/printer\/info'\)/);
 assert.match(dock,/await moonrakerRead\('\/printer\/objects\/list'\)/);
 assert.match(dock,/await moonrakerRead\('\/printer\/objects\/query\?'\+queries\.join\('&'\)\)/);
 assert.match(dock,/xyz\?'XYZ homed \(reported\)'/);
 assert.match(dock,/XYZ reported homed · physical validation pending/);
 assert.match(dock,/await updateLiveStatus\(\)/);
 assert.match(dock,/no motion or verification is authorised/i);
 assert.doesNotMatch(dock,/\/printer\/gcode\/script|\/printer\/gcode\/help|CARTOGRAPHER_TOUCH|SET_GCODE_OFFSET/);
 assert.match(html,/id="cxmLineuxStart" disabled/);
 assert.match(html,/id="cxmT0Stage" disabled/);
});

test('T0 test controls are hardware-gated and never mark a tool verified',()=>{
 const t0=fs.readFileSync(path.join(__dirname,'../web/cxm-t0.js'),'utf8');
 assert.match(html,/cxm-t0\.js\?v=[\w.-]+/);
 assert.match(html,/id="cxmT0ConfirmStage" hidden disabled/);
 for(const id of ['cxmT0Sensor','cxmT0RecordEmpty','cxmT0RecordMounted',
   'cxmT0Stage','cxmT0Pickup','cxmT0Dropoff','cxmT0Plan'])
   assert.match(html,new RegExp('id="'+id+'"'));
 assert.match(t0,/state\?\.sensor_calibrated===true/);
 assert.match(t0,/state\?\.stage==='staged'/);
 assert.match(t0,/I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH/);
 assert.match(t0,/first_dropoff_ready/);
 const auto=fs.readFileSync(path.join(__dirname,'../web/cxm-t0-auto.js'),'utf8');
 assert.match(html,/cxm-t0-auto\.js\?v=[\w.-]+/);
 for(const id of ['cxmT0AutoPickup','cxmT0AutoDropoff','cxmT0AutoStatus',
   'cxmT0AutoFaultBox','cxmT0AutoClearFault',
   'cxmT0Cycles','cxmT0StartCycles','cxmT0StopCycles','cxmT0CycleStatus'])
   assert.match(html,new RegExp('id="'+id+'"'));
 assert.match(auto,/request|send\('\/auto'/);
 assert.match(auto,/setInterval/);
 assert.match(html,/id="cxmT0AutoFaultBox" class="cxm-t0-auto-fault" hidden/);
 assert.match(html,/value="-4\.8"/);
 assert.doesNotMatch(auto,/SET_GCODE_OFFSET|SET_HEATER_TEMPERATURE|G1 Z|printer\/gcode\/script/);
 assert.match(t0,/can_confirm_staging/);
 assert.match(t0,/request\('\/confirm-stage'/);
 assert.match(t0,/I_PHYSICALLY_CONFIRMED_T0_STAGED_AND_XY_NOT_HAND_MOVED/);
 assert.match(html,/first supervised dropoff/);
 assert.doesNotMatch(t0,/SET_GCODE_OFFSET|SET_HEATER_TEMPERATURE|G1 Z|printer\/gcode\/script/);
});

