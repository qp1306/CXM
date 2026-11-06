/* Regression tests for CXM V0.9.0 read-only commissioning diagnostics. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
const js=fs.readFileSync(path.join(__dirname,'../web/cxm-testing.js'),'utf8');
const math=require('../web/cxm-test-math.js');
const sample={
 step_mm:5,xA:800,xB:800,yA:800,yB:-800,endX:335,endY:362,
 knownX:295,knownY:100,
 start:'mcu: stepper_x:4814 stepper_y:27252 stepper_z:1877',
 afterY:'mcu: stepper_x:46739 stepper_y:-14673 stepper_z:9877',
 afterX:'mcu: stepper_x:53139 stepper_y:-8273 stepper_z:17877'
};
test('pure maths reconstructs actual 6 November known-position capture',()=>{
 const r=math.review(sample);
 assert.equal(r.status,'PROVISIONAL_UNVERIFIED');
 assert.equal(r.save_permitted,false);
 assert.equal(r.active_in_klipper,false);
 assert.equal(r.raw_dock_xy_mm.x,295);
 assert.equal(r.raw_dock_xy_mm.y,99.96875);
 assert.equal(r.known_position_math_pass,true);
 assert.equal(r.travel_mm.x,40);
 assert.equal(r.travel_mm.y,262.03125);
 assert.equal(r.cross_axis_mm.during_y_home_x,0);
 assert.equal(r.cross_axis_mm.during_x_home_y,0);
});
test('reviewer fails closed on bad counters, impossible travel and cross-axis drift',()=>{
 assert.throws(()=>math.review({...sample,start:'stepper_x:4814 stepper_y:27252'}),/exactly one MCU/);
 assert.throws(()=>math.review({...sample,afterX:sample.afterY}),/positive-endstop/);
 assert.throws(()=>math.review({...sample,afterX:'mcu: stepper_x:53139 stepper_y:-8000'}),/Cross-axis/);
 assert.throws(()=>math.review({...sample,knownX:100,endX:10}),/outside/);
 assert.throws(()=>math.review({...sample,xA:0,xB:0,yA:0,yB:0}),/invalid\/singular/);
 assert.throws(()=>math.parseMCU(sample.start+'\n'+sample.afterY),/exactly one MCU/);
 assert.throws(()=>math.parseMCU('mcu: stepper_x:2 stepper_y:3 stepper_y:4'),/duplicated/);
});
test('Testing page has live reads, restart evidence and real input controls',()=>{
 assert.match(html,/data-panel="tests"/);
 for(const id of ['cxmTestRun','cxmTestBaseline','cxmTestCompare','cxmTestXYReview',
                   'cxmTestStart','cxmTestAfterY','cxmTestAfterX','cxmTestEndX',
                   'cxmTestEndY','cxmTestLoadKnown','cxmTestDownload',
                   'cxmTestHomed','cxmTestHoming','cxmTestThermistor','cxmTestRestartResult'])
  assert.match(html,new RegExp('id="'+id+'"'));
 assert.match(html,/cxm-testing\.js\?v=0\.9\.0/);
 assert.match(html,/cxm-test-math\.js\?v=0\.9\.0/);
 assert.match(js,/getJSON\('\/cxm\/api\/v1\/runtime'\)/);
 assert.match(js,/getJSON\('\/cxm\/api\/v1\/config'\)/);
 assert.match(js,/getJSON\('\/printer\/info'\)/);
 assert.match(js,/getJSON\('\/printer\/objects\/query\?'/);
 assert.match(js,/after\.run\.identity!==baseline\.run\.identity/);
 assert.match(js,/after\.revision===baseline\.revision/);
 assert.match(js,/NO Klipper process restart\. Disk settings are NOT applied live/);
 assert.match(js,/Mainsail homing override|homing_override/);
 assert.doesNotMatch(js,/method:\s*['"]POST|\/printer\/gcode|(?:^|\\n)\\s*(?:G28|SET_KINEMATIC_POSITION|FIRMWARE_RESTART)(?:\\s|$)/m);
 assert.doesNotMatch(html,/planned for later release/i);
});
