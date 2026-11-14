/* Fresh CXM reset cannot create motion or silently reuse old calibration. */
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const read=(dir,file)=>fs.readFileSync(path.join(__dirname,'..',dir,file),'utf8');
const html=read('web','index.html'),js=read('web','cxm-fresh-reset.js');
const approved=read('web','cxm-approved-v1.js'),settings=read('web','cxm-settings.js');
const css=read('web','cxm-approved-v1.css'),svc=read('server','cxm_service.py');
const native=read('server','cxm_native.py'),db=read('server','cxm_config.py');
const macro=read('vendor/cxm','cxm_native_toolchange.cfg');

test('Settings visibly offers full reset and explicit consent',()=>{
 for(const id of ['cxmCommissionResetPanel','cxmFreshAck','cxmFreshReset',
                   'cxmFreshStatus','cxmFreshResult']) assert.match(html,new RegExp('id="'+id+'"'));
 assert.match(html,/All 12 saved dock XY positions, tool XY\/Z offsets/);
 assert.match(html,/return it to its dock/);
 assert.match(approved,/fromId\('cxmCommissionResetPanel'/);
 assert.match(html,/cxm-fresh-reset\.js\?v=1/);
 assert.match(html,/cxm-approved-v1\.js\?v=1\.3-fresh-start/);
 assert.match(css,/\.cxm-fresh-start/);
});
test('UI confirms both physical EMPTY and server-side full readback',()=>{
 assert.match(js,/native\.sensor!=='RELEASED'/);
 assert.match(js,/!window\.confirm\(/);
 assert.match(js,/reset_commissioning!==true/);
 assert.match(js,/cleared_tools!==12/);
 assert.match(js,/native_inhibited!==true/);
 assert.match(js,/confirmed\.config\.tools\.some/);
 assert.match(js,/live\.native_ready!==false/);
 assert.match(js,/result\.backup/);
 assert.doesNotMatch(js,/\/printer\/gcode|\bG1 [XYZ]|\bG0 [XYZ]/);
});
test('Backend atomic backup and invalidated Klipper state required',()=>{
 assert.match(svc,/\/v1\/commissioning\/reset/);
 assert.match(svc,/native_reset_commissioning\(self\.server\.store/);
 assert.match(db,/def reset_commissioning\(self, expected_revision\):/);
 assert.match(db,/result = self\._commit\(old, new\)/);
 assert.match(db,/self\._hash\(\(self\.backups\[result\['backup'\]\]\)/);
 assert.match(native,/def reset_commissioning\(store, expected_revision, acknowledgement\):/);
 assert.match(native,/if sensor != 'RELEASED':/);
 assert.match(native,/native\.get\('protocol'\) != 2/);
 assert.match(native,/if test\.get\('running'\) != 0:/);
 assert.match(native,/VARIABLE=ready VALUE=0/);
 assert.match(native,/VARIABLE=t'/);
 assert.match(native,/store\.reset_commissioning\(expected_revision\)/);
 assert.match(native,/z_controller\.reset_idle_history\(\)/);
});
test('Old T1 exact dock-position guard has been removed, other geometry gates remain',()=>{
 assert.doesNotMatch(macro,/T1 synchronized coordinates differ from the proven release point/);
 assert.doesNotMatch(macro,/t == 1 and \(\(x-264\.70\)/);
 assert.match(macro,/pos\.y < safe-0\.001/);
 assert.match(macro,/st\.shift_x\|float-4\.4/);
 assert.match(macro,/CXM_FAST_VERIFY EXPECT=\{expect\}/);
});
test('Clear All errors remains independent and old accepted coordinates are not reused',()=>{
 assert.match(html,/id="cxmClearAllButton"/);
 assert.match(settings,/window\.dispatchEvent\(new CustomEvent\('cxm-tool-count-saved'/);
 const reset=native.split('def reset_commissioning(')[1].split('CLEAR_ALL_ACK =')[0];
 assert.doesNotMatch(reset,/(?:^|\n)\s*['"]G[0128]\s/i);
 assert.match(reset,/f't\{n\}_accepted'/);
});
