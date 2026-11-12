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
test('Tool Z page exposes staged workflow and two supervised modes',()=>{
  for(const id of ['cxmZAutoPanel','cxmZRefSet','cxmZToolsGrid','cxmZAutoApprove',
                    'cxmZAutoPrepare','cxmZAutoStart','cxmZAutoStop','cxmZAutoMode',
                    'cxmZAutoReport','cxmZResultMeta'])
    assert.ok(html.includes('id="'+id+'"'),'Missing '+id);
  assert.match(html,/Quick · 3 Touch per tool/);
  assert.match(html,/Full redock test · 6 Touch per tool/);
  assert.match(html,/value="verify_redock"/);
  assert.match(html,/Provisional/);
});

test('Legacy saved-offset reviewer remains read-only and never claims verification',()=>{
  assert.doesNotMatch(script,/method:\s*['"]POST|\/printer\/gcode|SET_GCODE_OFFSET|G28|SAVE_CONFIG/);
  assert.match(script,/cache:'no-store'/);
  assert.match(script,/CXMToolPicker\?\.sync/);
  assert.match(html,/id="cxmZTable"/);
});

test('Quick calibration makes no direct printer motion call and does not save offsets',()=>{
  const controller=fs.readFileSync(path.join(__dirname,'../web/cxm-z-auto.js'),'utf8');
  const backend=fs.readFileSync(path.join(__dirname,'../server/cxm_z_auto.py'),'utf8');
  assert.match(controller,/z-auto\/start/);
  assert.match(controller,/value==='quick'|value==="quick"|value='quick'/);
  assert.doesNotMatch(controller,/SET_GCODE_OFFSET|SAVE_CONFIG|\/printer\/gcode\/script/);
  assert.match(backend,/RANGE_LIMIT = 0\.050/);
  assert.match(backend,/REDOCK_LIMIT = 0\.050/);
  assert.match(backend,/trial_count=1 if mode=='quick' else 2/);
  assert.match(backend,/'offsets_applied':False/);
  assert.match(backend,/'offsets_saved':False/);
});

test('Tool Z selection and readiness remain distinct guards',()=>{
  const controller=fs.readFileSync(path.join(__dirname,'../web/cxm-z-auto.js'),'utf8');
  const backend=fs.readFileSync(path.join(__dirname,'../server/cxm_z_auto.py'),'utf8');
  assert.match(controller,/max_commissioned_tool/);
  assert.match(controller,/preflight\?tools=/);
  assert.match(backend,/selected_tools\(tool_count\)/);
  assert.match(backend,/if tool_count != sorted\(set\(tool_count\)\)/);
  assert.match(backend,/sensor != \('RELEASED' if fitted==-1 else 'PRESSED'\)/);
});
