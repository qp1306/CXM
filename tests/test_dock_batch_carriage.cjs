/* Dock Batch's carriage UI proxies the existing controller: no new motion route. */
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function el(id=''){
 const handlers={};
 return {id,value:'',textContent:'',disabled:false,options:[],children:[],className:'',
  classList:{add(){}},
  append(...nodes){this.children.push(...nodes);},
  prepend(...nodes){this.children.unshift(...nodes);},
  addEventListener(k,fn){handlers[k]=fn;},
  dispatchEvent(e){handlers[e.type]?.(e);},
  setAttribute(k,v){this[k]=v;},
  click(){if(!this.disabled)handlers.click?.();},
  replaceChildren(...a){this.options=[...a];},
  querySelector(){return null;}
 };
}
test('Dock Batch currently-fitted selector invokes existing Confirm carriage handler exactly once',()=>{
 const src=fs.readFileSync(path.join(__dirname,'../web/cxm-dock-batch.js'),'utf8');
 const slot=el('cxmDockBatchSlot'),panel=el('cxmMultiPanel'),original=el('cxmCarriageIdentity'),
   confirm=el('cxmDeclareCarriage'),mirror=el('cxmBatchCarriageIdentity'),
   proxy=el('cxmBatchConfirmCarriage'),note=el('cxmBatchCarriageStatus'),
   carriage=el('cxmBatchCarriagePanel'),heading=el('heading'),tab=el('tab');
 panel.querySelector=()=>heading;
 original.options=[{value:'',textContent:'Select',cloneNode(){return {...this}}},
   {value:'-1',textContent:'EMPTY',cloneNode(){return {...this}}},
   {value:'1',textContent:'T1',cloneNode(){return {...this}}}];
 original.value='-1';
 carriage.querySelector=sel=>({
  '#cxmBatchCarriageIdentity':mirror,
  '#cxmBatchConfirmCarriage':proxy,
  '#cxmBatchCarriageStatus':note
 })[sel]||null;
 const speed=el('cxmSpeedSimple'),custom=el('cxmCustomSpeedFields');
 speed.options=[{value:'standard',remove(){}},{value:'custom',remove(){}}];
 speed.value='standard';
 let confirmations=0;
 confirm.addEventListener('click',()=>confirmations++);
 const items={cxmDockBatchSlot:slot,cxmMultiPanel:panel,
   cxmCarriageIdentity:original,cxmDeclareCarriage:confirm,
   cxmSpeedSimple:speed,cxmCustomSpeedFields:custom,
   cxmCustomTravel:el(),cxmCustomApproach:el(),cxmCustomLatch:el()};
 const document={
  getElementById:id=>items[id]||null,
  createElement:tag=>tag==='section'?carriage:el(tag),
  querySelector:sel=>sel==='[data-tab="dock-batch"]'?tab:null,
 };
 vm.runInNewContext(src,{document,window:{},
   Event:class{constructor(type,options){this.type=type;this.bubbles=options?.bubbles;}},
   setInterval(){},console},{filename:'cxm-dock-batch.js'});
 assert.equal(slot.children[0],carriage,'fitted control appears above batch tester');
 assert.equal(slot.children[1],panel);
 assert.equal(mirror.value,'-1');
 assert.equal(mirror.options.length,3);
 mirror.value='1';
 proxy.click();
 assert.equal(original.value,'1');
 assert.equal(confirmations,1,'uses the original one native Confirm handler');
 assert.match(note.textContent,/existing native controller/);
 assert.match(src,/existingConfirm\.click\(\)/);
 assert.doesNotMatch(src,/native\/initialize|CXM_SELECT_TOOL|G1 [XYZ]/);
});
