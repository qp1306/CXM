/* Dock XY's 100mm test reuses the guarded native jog; no second motion engine. */
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');
const html=read('web/index.html'),layout=read('web/cxm-approved-v1.js'),jog=read('web/cxm-manual.js');
const native=read('vendor/cxm/cxm_native_toolchange.cfg');
test('Dock XY contains supervised 100mm retreat and return controls',()=>{
  for(const id of ['cxmDockRetreat100','cxmDockReturn100','cxmDockTravelStatus'])
    assert.match(html,new RegExp('id="'+id+'"'));
  assert.match(html,/Move back \+100 mm Y/);
  assert.match(html,/Return −100 mm Y/);
});
test('Reliability and reset reuse existing DOM handlers on the Dock XY page',()=>{
  assert.match(layout,/const test=\$\('cxmMultiPanel'\)/);
  assert.match(layout,/const recovery=\$\('cxmClearAllBox'\)/);
  assert.match(layout,/const reset=\$\('cxmCommissionResetPanel'\)/);
  assert.match(layout,/const s6=p\.stage\(6,'Reset and recommission'/);
  assert.doesNotMatch(layout,/Open Tools · Load \/ Unload/);
});
test('100mm travel has ten separately verified native 10mm moves',()=>{
  assert.match(jog,/for\(let step=1;step<=10;step\+\+\)/);
  assert.match(jog,/request\('\/manual\/jog'/);
  assert.match(jog,/distance:returning\?-10:10/);
  assert.match(jog,/latest\.sensor!=='PRESSED'/);
  assert.match(jog,/latest\.native_tool_identity!==identity/);
  assert.match(jog,/!close\(latest\.xy\.y,goal\)/);
  assert.match(jog,/retreatAnchor=null/);
  assert.doesNotMatch(jog,/\bG1\b|\/printer\/gcode\/script/);
  assert.match(native,/\[gcode_macro CXM_MANUAL_DOCK_JOG\]/);
});
