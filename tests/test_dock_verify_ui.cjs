/* The old ABSENT-locked-dock UI is retired from Dock XY.
 * These tests guard that it does not reappear as a second workflow.
 */
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');
const html=read('web/index.html');
const dock=read('web/cxm-dock-simple.js');
const service=read('server/cxm_dock_simple.py');

test('one visible Dock XY workflow without standalone native installers',()=>{
 assert.match(html,/CXM_SIMPLE_DOCK_XY=true/);
 assert.match(html,/cxm-dock-simple\.js\?v=/);
 assert.doesNotMatch(html,/script src="cxm-dock-verify(?:-update)?\.js/);
 assert.doesNotMatch(html,/script src="cxm-jog-update\.js/);
 assert.match(dock,/Home printer/);
 assert.match(dock,/Enable jogging/);
 assert.match(dock,/Test docking \/ undocking/);
 assert.match(dock,/Save coordinates/);
 assert.match(dock,/Next hotend/);
});
test('Dock XY does not use filament state or old 10mm loop',()=>{
 assert.doesNotMatch(dock,/FILAMENT|sensor|cxm_tool_detect/i);
 assert.doesNotMatch(service,/cxm_tool_detect|gcode_button|FILAMENT/i);
 assert.doesNotMatch(service,/for.*range\(10\)/);
 assert.match(service,/SAVE_GCODE_STATE NAME=CXM_SIMPLE_DOCK/);
 assert.match(service,/G1 Z22 F1500/);
});
test('automatic native toolchanges retain their separate safety checks',()=>{
 const native=read('vendor/cxm/cxm_native_toolchange.cfg');
 assert.match(native,/CXM_FAST_VERIFY EXPECT=PRESSED/);
 assert.match(native,/CXM_FAST_VERIFY EXPECT=RELEASED/);
 assert.match(native,/\[gcode_macro _CXM_PICKUP_MOTION\]/);
 assert.match(native,/\[gcode_macro _CXM_RELEASE_MOTION\]/);
});
