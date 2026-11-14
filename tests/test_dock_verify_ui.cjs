const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');
const page=read('web/index.html'),ui=read('web/cxm-dock-verify.js'),
      updates=read('web/cxm-dock-verify-update.js'),native=read('vendor/cxm/cxm_native_toolchange.cfg');
test('isolated locked-dock flow requires ABSENT, physical lock acknowledgment and loaded native macro',()=>{
 assert.match(page,/cxm-dock-verify\.js\?v=/);
 assert.match(page,/cxm-dock-verify-update\.js\?v=/);
 assert.match(ui,/macro_loaded===true/);
 assert.match(ui,/sensor==='RELEASED'/);
 assert.match(ui,/I_INSPECTED_LOCKED_DOCK_AND_CLEAR_PATH/);
 assert.match(ui,/Test \+100 mm → −100 mm/);
 assert.match(ui,/Save verified dock XY/);
});
test('any fine adjustment requires a repeat, save is blocked until verified',()=>{
 assert.match(ui,/verified=false/);
 assert.match(ui,/!verified\|\|!live\?\.travel_verified/);
 assert.match(ui,/Repeat the \+100\/−100 test before Save/);
 assert.match(native,/\[gcode_macro CXM_DOCK_VERIFY_MOVE\]/);
 assert.match(native,/G1 \{axis\}\{dist\} F3000/);
});
test('Updates uses a dedicated guarded append-only macro installer',()=>{
 assert.match(updates,/update\/dock-verify\/apply/);
 assert.match(updates,/restart_required/);
 assert.match(updates,/Inspect the printer before installing/);
});
