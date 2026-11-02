/* CXM V0.7.1: Z calibration preparation must never imply verified nozzle height. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const z=require('../web/cxm-z.js');
const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
const script=fs.readFileSync(path.join(__dirname,'../web/cxm-z.js'),'utf8');
const tool=changes=>({maintenance_lockout:false,offset_z:0,
  offset_z_accepted:false,offset_z_verified:false,
  reference_verified:false,...changes});

test('T0 stored zero can never masquerade as a calibrated reference',()=>{
 assert.deepEqual(z.zState(tool(),0),{code:'T0_UNVERIFIED',label:'T0 REFERENCE NOT VERIFIED'});
 assert.equal(z.zState(tool({offset_z_accepted:true,offset_z_verified:true}),0).code,'T0_UNVERIFIED');
 assert.equal(z.zState(tool({reference_verified:true}),0).code,'NOT_MEASURED');
 assert.equal(z.zState(tool({reference_verified:true,offset_z_accepted:true}),0).code,'SAVED_UNVERIFIED');
 assert.equal(z.zState(tool({reference_verified:true,offset_z_accepted:true,offset_z_verified:true}),0).code,'VERIFIED_RECORD');
});
test('T1..T11 require explicit accepted and verified flags and respect maintenance lockout',()=>{
 assert.equal(z.zState(tool({offset_z:0}),10).code,'NOT_MEASURED');
 assert.equal(z.zState(tool({offset_z:0.089,offset_z_accepted:true}),10).code,'SAVED_UNVERIFIED');
 assert.equal(z.zState(tool({offset_z:-0.023,offset_z_accepted:true,offset_z_verified:true}),10).code,'VERIFIED_RECORD');
 assert.equal(z.zState(tool({maintenance_lockout:true,offset_z_verified:true}),10).code,'LOCKED_OUT');
 assert.equal(z.zState(null,9).code,'UNAVAILABLE');
});
test('only selected tool count appears and zero offset formatting is clearly stored only',()=>{
 const snap={config:{globals:{tool_count:12},tools:Array.from({length:12},()=>tool())}};
 assert.equal(z.rows(snap).length,12);
 assert.equal(z.rows(snap)[10].offset,'+0.000 mm');
 assert.equal(z.rows(snap)[10].state.code,'NOT_MEASURED');
 snap.config.globals.tool_count=6;
 assert.equal(z.rows(snap).length,6);
 assert.deepEqual(z.rows(null),[]);
 assert.deepEqual(z.rows({config:{globals:{tool_count:20},tools:snap.config.tools}}),[]);
});
test('distinct Z Calibration tab, T0 and all-hotend comparison are visible',()=>{
 assert.match(html,/data-tab="z-calibration">Z Calibration<\/button>/);
 assert.match(html,/data-panel="z-calibration"/);
 for(const id of ['cxmZTool','cxmZSaved','cxmZStatus','cxmZTable','cxmZProgress','cxmZFeedback'])
  assert.ok(html.includes('id="'+id+'"'),'Missing '+id);
 assert.match(html,/T0 nozzle-to-bed reference · T1–T11 nozzle heights relative to T0/);
 assert.match(html,/Z calibration and dock Z are different/);
 assert.match(html,/Cartographer model\/firmware supports a safe nozzle-contact method/);
 assert.match(html,/id="cxmZTool" disabled/);
 assert.match(html,/Start Z calibration · unavailable<\/button>/);
 assert.match(html,/Accept measured Z · unavailable<\/button>/);
});
test('no runtime motion, writes, fabricated optical measurements, or automatic verification',()=>{
 assert.doesNotMatch(script,/method:\s*['"]POST|\/printer\/gcode|SET_GCODE_OFFSET|G28|SAVE_CONFIG|CXM_variables\.cfg.*write/);
 assert.doesNotMatch(script,/document\.createElement\(['"]input['"]\)/);
 assert.match(script,/cache:'no-store'/);
 assert.match(script,/CXMToolPicker\?\.sync/);
 assert.match(script,/status\.textContent=.*read-only|Read-only saved profiles/);
 assert.match(html,/cxm-z\.js\?v=0\.8\.0/);
 assert.match(html,/CXM starter <span>v0\.8\.0<\/span>/);
});

test('V0.8.0 Touch statistics and offline test are visible, but physical Z is locked',()=>{
 assert.match(html,/Cartographer Touch · offline Z calculations/);
 assert.match(html,/140°C nozzle · 70°C bed/);
 assert.match(html,/3 complete Touch results\/tool/);
 assert.match(html,/5 readings · tightest 3/);
 assert.match(html,/±0\.025 mm/);
 assert.match(html,/≤ 0\.020 mm/);
 assert.match(html,/≤ 0\.040 mm/);
 assert.match(html,/0\.750 mm/);
 assert.match(html,/cxm_z_review\.py --example/);
 assert.match(html,/cxm_z_review\.py --input/);
 assert.match(html,/PHYSICAL Z CALIBRATION REMAINS DISABLED/);
 assert.match(html,/Start Z calibration · unavailable<\/button>/);
 assert.match(html,/Accept measured Z · unavailable<\/button>/);
 assert.doesNotMatch(script,/CARTOGRAPHER_TOUCH_PROBE|G28|SET_GCODE_OFFSET|\/printer\/gcode/);
});
