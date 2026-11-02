/* CXM V0.6 tool identity, readiness and count regression tests */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const cards=require('../web/cxm-tool-cards.js');
const status=require('../web/cxm-tool-state.js');
const T={maintenance_lockout:false,dock_x:null,dock_y:null,dock_z:null,
 offset_x:0,offset_y:0,offset_z:0,approach_speed:1200,dock_speed:800,
 offset_xy_accepted:false,offset_z_accepted:false,dock_verified:false,
 offset_xy_verified:false,offset_z_verified:false,pickup_verified:false,
 dropoff_verified:false,heater_verified:false,sensor_verified:false,
 reference_verified:false,commissioned:false};
const make=changes=>({...T,...changes});
test('selected tool with missing dock is red NOT READY and remains editable',()=>{
 const result=cards.card(make(),10,12);
 assert.equal(result.state,'NOT_CALIBRATED');
 assert.match(result.html,/NOT CALIBRATED/);
 assert.match(result.html,/Dock XYZ and tool offsets require calibration/);
 assert.match(result.html,/data-cxm-calibrate="10"/);
 assert.match(result.html,/data-cxm-edit="10"/);
 assert.match(result.html,/disabled title="Pickup unavailable/);
});
test('saved XYZ and zero offsets never assert physical calibration',()=>{
 const x=cards.card(make({dock_x:172.00625,dock_y:175.00625,dock_z:291.5,offset_x:0.03}),2,12);
 assert.equal(x.state,'INCOMPLETE');
 assert.match(x.html,/172\.006 \/ 175\.006 \/ 291\.500/);
 assert.match(x.html,/0\.030 \/ 0\.000 \/ 0\.000/);
 assert.match(x.html,/CALIBRATION INCOMPLETE/);
 assert.doesNotMatch(x.html,/Verified pickup|Tool on carriage/);
});
test('lockout blocks editing and calibration; unselected is never active',()=>{
 const locked=cards.card(make({maintenance_lockout:true}),4,12);
 assert.equal(locked.state,'LOCKED_OUT');
 assert.match(locked.html,/LOCKED OUT/);
 assert.match(locked.html,/disabled title="Calibration locked"/);
 assert.equal(cards.card(make(),8,6).state,'NOT_SELECTED');
 assert.match(cards.card(null,0,12).html,/CONFIG UNAVAILABLE/);
});
test('12 selected means all cards; no Ready without physical verification',()=>{
 const nodes=Array.from({length:12},()=>({hidden:false,dataset:{},innerHTML:'',
 style:{setProperty(){}},classList:{toggle(){}},querySelector(){return null}}));
 const out={cxmToolSummary:{textContent:''},cxmActiveTools:{textContent:''},
 cxmNoTools:{hidden:true},cxmSafeY:{textContent:''},cxmXAdjust:{textContent:''}};
 const prev=global.document;global.document={querySelectorAll:()=>nodes,getElementById:id=>out[id]||null};
 try{
  const profiles=Array.from({length:12},()=>make());
  cards.render({config:{globals:{tool_count:12,safe_y:120,x_docking_adjust:3},tools:profiles}});
  assert.equal(nodes.filter(x=>!x.hidden).length,12);
  assert.match(out.cxmToolSummary.textContent,/12 selected/);
  assert.match(out.cxmToolSummary.textContent,/0 ready · 12 not ready/);
  assert.equal(out.cxmActiveTools.textContent,'0 READY / 12 selected');
  assert.match(nodes[10].innerHTML,/NOT CALIBRATED/);
  cards.render({config:{globals:{tool_count:6,safe_y:120,x_docking_adjust:3},tools:profiles}});
  assert.equal(nodes.filter(x=>!x.hidden).length,6);
  assert.equal(profiles[10].maintenance_lockout,false);
  cards.render({config:{globals:{tool_count:12,safe_y:120,x_docking_adjust:3},tools:profiles},
    migration_required:true});
  assert.match(nodes[10].innerHTML,/disabled>Edit/);
 }finally{if(prev===undefined)delete global.document;else global.document=prev;}
});
test('red overlay, preserved palette and control count',()=>{
 const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
 assert.match(html,/\.tool-card\.cxm-needs-attention::after\{content:"NOT READY"/);
 assert.match(html,/pointer-events:none/);
 assert.match(html,/cxm-tool-state\.js\?v=0\.7\.1/);
 assert.match(html,/cxm-tool-picker\.js\?v=0\.7\.1/);
 assert.match(html,/id="cxmCountSelect"/);
 assert.match(html,/<option value="12">12<\/option>/);
 assert.match(html,/CXM starter <span>v0\.7\.1<\/span>/);
 const script=fs.readFileSync(path.join(__dirname,'../web/cxm-settings.js'),'utf8');
 assert.match(script,/key:'tool_count',value:next/);
 assert.match(script,/snapshot\.migration_required/);
 assert.match(script,/maintenance_lockout/);
 assert.doesNotMatch(script,/\['enabled', 'Enabled'/);
});
test('generic card policy and pure state module agree',()=>{
 const result=status.classify(make({dock_x:2,dock_y:3,dock_z:4}),4,12);
 assert.equal(result.code,'INCOMPLETE');
 assert.equal(cards.card(make({dock_x:2,dock_y:3,dock_z:4}),4,12).state,result.code);
});
