/* Dock XY interactive contract: fast successive clicks stay enabled and queue in order. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function element(id=''){
 const events={};
 return {
  id,disabled:false,checked:false,textContent:'',innerHTML:'',value:'',
  dataset:{},
  classList:{add(){},toggle(){}},
  options:[],
  addEventListener(type,handler){events[type]=handler;},
  click(){events.click?.({target:this});},
  change(){events.change?.({target:this});},
  append(){},
  setAttribute(name,value){this[name]=value;},
  querySelector(){return this.small||null;},
  replaceChildren(){this.options=[];}
 };
}
function result(data){
 return {ok:true,json:async()=>data};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('green Enable jogging and rapid jog clicks do not grey buttons or overlap HTTP movements',async()=>{
 const source=fs.readFileSync(path.join(__dirname,'../web/cxm-dock-simple.js'),'utf8');
 const css=fs.readFileSync(path.join(__dirname,'../web/cxm-dock-simple.css'),'utf8');
 assert.match(source,/cxms-step-enable cxms-wide/);
 assert.match(css,/\.cxms-step-enable\{background/);
 assert.match(css,/\.cxms-enable-copy strong/);
 const ids=['cxmsPosition','cxmsSaved','cxmsPrinter','cxmsHome','cxmsTool',
  'cxmsEnable','cxmsTest','cxmsSave','cxmsNext','cxmsMessage'];
 const elements=new Map(ids.map(id=>[id,element(id)]));
 const selector=elements.get('cxmsTool');
 selector.value='0';selector.options=[{value:'0'}];
 const jogA=element('jogA'),jogB=element('jogB');
 jogA.dataset={axis:'x',dist:'0.1'};
 jogB.dataset={axis:'x',dist:'1'};
 const page=element('page');page.hidden=false;
 const cards=Array.from({length:12},(_,n)=>{
  const card=element('card'+n);
  card.dataset.dockTool=String(n);
  card.small=element('hint'+n);
  return card;
 });
 const root=element('root');
 root.querySelectorAll=css=>css==='[data-axis]'?[jogA,jogB]:
  css==='[data-dock-tool]'?cards:[];
 const document={
  hidden:false,
  querySelector(query){return query==='[data-panel="calibration"]'?page:null;},
  getElementById(id){return elements.get(id)||null;},
  createElement(tag){return tag==='div'?root:element(tag);}
 };
 const position={x:299.5,y:65.5,z:22};
 let pending=[],seen=[];
 function snapshot(){return {tool:0,xyz:{...position},homed:true,idle:true,revision:'rev',
  accepted:false,saved_xy:{x:null,y:null},tool_count:1,
  tool_cards:Array.from({length:12},(_,n)=>({tool:n,enabled:n===0,saved:false}))};}
 async function fetch(url,opts){
  if(url.endsWith('/status?tool=0'))return result(snapshot());
  if(url.endsWith('/enable'))return result(snapshot());
  if(url.endsWith('/jog')){
   const body=JSON.parse(opts.body);
   seen.push(body.distance);
   return new Promise(resolve=>pending.push(()=>{
    position[body.axis]+=body.distance;
    resolve(result(snapshot()));
   }));
  }
  throw Error('Unexpected request '+url);
 }
 const context={
  document,fetch,window:{CXM_SIMPLE_DOCK_XY:true,dispatchEvent(){}},
  setInterval(){},CustomEvent:class {},console
 };
 vm.runInNewContext(source,context,{filename:'cxm-dock-simple.js'});
 await tick();await tick();
 const checkbox=elements.get('cxmsEnable');
 assert.equal(checkbox.disabled,false,'homed XYZ enables the control');
 assert.equal(cards[0].disabled,false,'T0 is selectable in Dock XY');
 assert.equal(cards[1].disabled,true,'unconfigured T1 cannot be selected');
 checkbox.checked=true;checkbox.change();
 await tick();await tick();
 assert.equal(checkbox.checked,true,'Z22 preparation completes');
 assert.equal(jogA.disabled,false);
 jogA.click();
 assert.equal(jogA.disabled,false,'button must stay active during first request');
 jogB.click();
 assert.equal(jogB.disabled,false,'button must stay active after second click');
 assert.deepEqual(seen,[0.1],'second command waits in queue rather than overlapping server');
 pending.shift()();
 await tick();await tick();
 assert.deepEqual(seen,[0.1,1],'second queued click runs automatically');
 assert.equal(jogA.disabled,false);
 pending.shift()();
 await tick();await tick();
 assert.equal(position.x,300.6);
 assert.equal(elements.get('cxmsPosition').textContent.includes('300.600'),true);
 assert.equal(jogB.disabled,false);
 assert.equal(elements.get('cxmsTest').disabled,false);
});
