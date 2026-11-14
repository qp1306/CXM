/* Native Dock Batch UI reuses proven motions and persists Custom speed locally. */
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');

function el(id=''){
 const events={};
 return {id,disabled:false,value:'',textContent:'',className:'',hidden:false,children:[],
  classList:{add(){}},
  setAttribute(name,v){this[name]=v;},
  addEventListener(name,fn){events[name]=fn;},
  dispatchEvent(e){events[e.type]?.(e);},
  click(){events.click?.({target:this});},
  append(...children){this.children.push(...children);},
  querySelector(){return null;}
 };
}
test('Dock Batch has dedicated nav and native toolchange panel',()=>{
 const html=read('web/index.html');
 const src=read('web/cxm-dock-batch.js');
 assert.match(html,/data-tab="dock-batch">Dock Batch/);
 assert.match(html,/data-panel="dock-batch" hidden/);
 assert.match(html,/id="cxmDockBatchSlot"/);
 assert.match(html,/cxm-dock-batch\.js\?v=/);
 assert.match(src,/slot\.append\(panel\)/);
 const klipper=read('vendor/cxm/cxm_native_toolchange.cfg');
 assert.match(klipper,/\[gcode_macro CXM_TEST_START\]/);
 assert.match(klipper,/\[gcode_macro CXM_SET_PROFILE\]/);
});
test('Dock Batch UI requires live revision 2 and permits six to twelve tools',()=>{
 const native=read('web/cxm-multi.js');
 const backend=read('server/cxm_native.py');
 const html=read('web/index.html');
 assert.match(native,/selection\(\)\.length<=Math\.min\(12,current\?\.max_tool_selection\|\|3\)/);
 assert.match(native,/native_batch_revision===2/);
 assert.match(backend,/CXM_TEST_START MASK=/);
 assert.match(backend,/2\*len\(tools\)\*cycles>120/);
 assert.match(html,/id="cxmBatchUpgrade"/);
 assert.match(html,/cxm-batch-upgrade\.js\?v=/);
});
test('saved Custom speed restores and can be updated without sending Gcode',()=>{
 const src=read('web/cxm-dock-batch.js');
 const slot=el('cxmDockBatchSlot'),panel=el('cxmMultiPanel'),head=el('heading');
 panel.querySelector=()=>head;
 const speed=el('cxmSpeedSimple');
 const removed=[];
 speed.options=['standard','faster','performance','sprint','race','boost','custom']
   .map(v=>({value:v,remove(){removed.push(v);speed.options=speed.options.filter(x=>x.value!==v);}}));
 speed.value='faster';
 const fields=Object.fromEntries(['cxmCustomTravel','cxmCustomApproach','cxmCustomLatch'].map(id=>[id,el(id)]));
 fields.cxmCustomTravel.value='300';
 fields.cxmCustomApproach.value='40';
 fields.cxmCustomLatch.value='10';
 const custom=el('cxmCustomSpeedFields');
 const refresh=el('cxmMultiRefresh'),tab=el('dock-batch');
 const elements={cxmDockBatchSlot:slot,cxmMultiPanel:panel,cxmSpeedSimple:speed,
   cxmCustomSpeedFields:custom,cxmMultiRefresh:refresh,...fields};
 const storage=new Map([['CXM_DOCK_BATCH_CUSTOM_SPEED_V1',
    JSON.stringify({travel:200,approach:40,latch:10})]]);
 const window={localStorage:{getItem:key=>storage.get(key)||null,
   setItem:(k,v)=>storage.set(k,v)}};
 const document={
  getElementById:id=>elements[id]||null,
  querySelector:sel=>sel==='[data-tab="dock-batch"]'?tab:null,
  createElement:tag=>el(tag)
 };
 vm.runInNewContext(src,{document,window,Event:class{constructor(type){this.type=type;}},console},
   {filename:'cxm-dock-batch.js'});
 assert.deepEqual(Array.from(speed.options.map(x=>x.value)),['standard','custom']);
 assert.equal(speed.value,'standard');
 assert.equal(slot.children.includes(panel),true);
 assert.equal(head.textContent,'Dock pickup / dropoff batch test');
 assert.equal(fields.cxmCustomTravel.value,'200');
 assert.equal(fields.cxmCustomApproach.value,'40');
 assert.equal(fields.cxmCustomLatch.value,'10');
 const button=custom.children.find(x=>x.id==='cxmBatchSaveCustom');
 const status=custom.children.find(x=>x.id==='cxmBatchSavedSpeed');
 assert.ok(button);
 assert.match(status.textContent,/Saved on this browser/);
 fields.cxmCustomTravel.value='400';
 fields.cxmCustomApproach.value='80';
 fields.cxmCustomLatch.value='20';
 button.click();
 assert.equal(speed.value,'custom');
 assert.equal(JSON.parse(storage.get('CXM_DOCK_BATCH_CUSTOM_SPEED_V1')).travel,400);
 assert.match(status.textContent,/400 \/ 80 \/ 20 mm\/s/);
});
