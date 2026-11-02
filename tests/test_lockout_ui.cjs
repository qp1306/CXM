/* V0.6.1 regression: maintenance lockout must be prominent and safe. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
const settings=fs.readFileSync(path.join(__dirname,'../web/cxm-settings.js'),'utf8');
const {classify}=require('../web/cxm-tool-state.js');

test('large, distinct switch replaces the tiny checkbox',()=>{
  assert.match(settings,/function lockoutControl\(profile\)/);
  assert.match(settings,/id="cxmMaintenanceLockout"/);
  assert.match(settings,/role="switch"/);
  assert.match(settings,/data-key="maintenance_lockout"/);
  assert.match(settings,/SAFETY OVERRIDE · HOTEND T/);
  assert.match(settings,/MAINTENANCE LOCKOUT/);
  assert.match(settings,/LOCKED OUT — calibration blocked/);
  assert.match(settings,/UNLOCKED — calibration permitted/);
  assert.match(settings,/lockoutControl\(cfg\.tools\[tool\]\)/);
  assert.doesNotMatch(settings,/\['maintenance_lockout', 'Maintenance lockout/);
  assert.match(html,/\.cxm-lockout-panel\{/);
  assert.match(html,/min-height:158px/);
  assert.match(html,/\.cxm-lockout-title\{[^}]*font-size:/);
  assert.match(html,/\.cxm-lockout-track\{[^}]*width:82px;height:46px/);
  assert.match(html,/\.cxm-lockout-panel\.is-locked\{/);
  assert.match(html,/\.cxm-lockout-panel:focus-within\{/);
});

test('AutoSave uses existing API and cancellation preserves lockout',()=>{
  assert.match(settings,/status\(key==='maintenance_lockout'\?'Saving T'/);
  assert.match(settings,/localFeedback\.textContent='Saving to CXM_variables.cfg/);
  assert.match(settings,/key,value,expected_revision:snapshot\.revision/);
  assert.match(settings,/window\.confirm\('Remove maintenance lockout from T'/);
  assert.match(settings,/input\.checked=true/);
  assert.match(settings,/if\(!snapshot\|\|saving\|\|snapshot\.migration_required\)return/);
  assert.match(settings,/readonly\?'disabled':''/);
  assert.match(settings,/await loadAfterSave\(\)/);
});

test('unlock does not bypass tool readiness or enable motion',()=>{
  const t={maintenance_lockout:false,dock_x:null,dock_y:null,dock_z:null,
    offset_xy_accepted:false,offset_z_accepted:false};
  assert.equal(classify(t,10,12).code,'NOT_CALIBRATED');
  assert.equal(classify({...t,maintenance_lockout:true},10,12).code,'LOCKED_OUT');
  assert.equal(classify(t,10,12).canPickup,false);
  assert.match(html,/CXM starter <span>v0\.6\.1<\/span>/);
  assert.match(html,/cxm-settings\.js\?v=0\.6\.1/);
});
