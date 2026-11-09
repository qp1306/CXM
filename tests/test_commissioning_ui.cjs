/* Manual dock alignment replaces deprecated MCU counter calculation. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
const tests=fs.readFileSync(path.join(__dirname,'../web/cxm-testing.js'),'utf8');
const manual=fs.readFileSync(path.join(__dirname,'../web/cxm-manual.js'),'utf8');
const dock=fs.readFileSync(path.join(__dirname,'../web/cxm-dock.js'),'utf8');

test('Testing diagnostics remain available without old MCU capture UI',()=>{
 assert.match(html,/data-panel="tests"/);
 for(const id of ['cxmTestRun','cxmTestBaseline','cxmTestCompare',
                   'cxmTestDownload','cxmTestHomed','cxmTestHoming',
                   'cxmTestThermistor','cxmTestRestartResult'])
  assert.match(html,new RegExp('id="'+id+'"'));
 assert.match(html,/cxm-testing\.js\?v=0\.9\.3/);
 assert.doesNotMatch(html,/cxm-test-math\.js|cxm-dock-review\.js|cxm-lineux\.js/);
 assert.doesNotMatch(html,/id="cxmTestXYReview"|id="cxmDockCaptureToDraft"/);
 assert.match(tests,/getJSON\('\/cxm\/api\/v1\/runtime'\)/);
 assert.match(tests,/getJSON\('\/cxm\/api\/v1\/config'\)/);
 assert.match(tests,/getJSON\('\/printer\/info'\)/);
});
test('dock Save is one action: capture, backed-up store and verification',()=>{
 assert.match(html,/id="cxmManualCapture" disabled>Save aligned dock XY/);
 assert.match(manual,/\/manual\/capture/);
 assert.match(manual,/request\('\/dock'/);
 assert.match(manual,/if\(!saved\.saved\)/);
 assert.match(manual,/actual\.dock_x!==result\.xy\.x/);
 assert.match(manual,/cxm-dock-save-completed/);
 assert.match(dock,/cxm-dock-save-completed/);
 assert.doesNotMatch(manual,/CXМ_SELECT_TOOL/);
});
test('manual jog is approved per operator and restored to prior modal state by backend',()=>{
 const backend=fs.readFileSync(path.join(__dirname,'../server/cxm_manual.py'),'utf8');
 assert.match(manual,/I_APPROVE_SUPERVISED_MOTOR_ON_JOG/);
 assert.match(backend,/SAVE_GCODE_STATE NAME=CXM_MANUAL_JOG/);
 assert.match(backend,/RESTORE_GCODE_STATE NAME=CXM_MANUAL_JOG MOVE=0/);
 assert.match(backend,/M400/);
 assert.match(backend,/stepper_z3/);
 assert.match(backend,/print_stats/);
 assert.match(backend,/PRESSED/);
 assert.doesNotMatch(backend,/SET_KINEMATIC_POSITION|DOCK_LOCATE_CALIBRATE/);
});
