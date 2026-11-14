/* Dock XY hotend cards must replace the dropdown without moving the printer. */
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');

function el(id=''){
 const handlers={};
 return {
  id,disabled:false,value:'',checked:false,hidden:false,dataset:{},
  textContent:'',title:'',innerHTML:'',options:[],
  classList:{add(){},toggle(){}},
  addEventListener(type,fn){handlers[type]=fn;},
  setAttribute(name,value){this[name]=value;},
  querySelector(selector){return selector==='small'?this.small:null;},
  click(){if(!this.disabled)handlers.click?.({target:this});},
  append(){}
 };
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
test('Dock XY T0–T11 card bank selects saved or unsaved tools with no motion',async()=>{
 const src=fs.readFileSync(path.join(__dirname,'../web/cxm-dock-simple.js'),'utf8');
 const styles=fs.readFileSync(path.join(__dirname,'../web/cxm-dock-simple.css'),'utf8');
 assert.match(src,/cxma-toolbank cxms-toolbank/);
 assert.match(src,/id="cxmsTool" type="hidden"/);
 assert.doesNotMatch(src,/<select id="cxmsTool"/);
 assert.match(styles,/repeat\(6,minmax\(0,1fr\)\)/);
 const ids=['cxmsPosition','cxmsSaved','cxmsPrinter','cxmsHome','cxmsTool',
    'cxmsEnable','cxmsTest','cxmsSave','cxmsNext','cxmsMessage'];
 const elements=new Map(ids.map(id=>[id,el(id)]));
 elements.get('cxmsTool').value='0';
 const cards=Array.from({length:12},(_,i)=>{
  const b=el('card'+i);b.dataset.dockTool=String(i);
  b.small=el('hint'+i);return b;
 });
 const root=el('dockRoot');
 root.querySelectorAll=selector=>selector==='[data-dock-tool]'?cards:
    selector==='[data-axis]'?[]:[];
 const page=el('calibration');
 const config={tool_count:5,tool_cards:Array.from({length:12},(_,i)=>({
  tool:i,enabled:i<5,saved:[0,2].includes(i)}))};
 const visited=[],posts=[];
 const document={hidden:false,
  querySelector(q){return q==='[data-panel="calibration"]'?page:null;},
  getElementById(id){return elements.get(id)||null;},
  createElement(type){return type==='div'?root:el(type);}
 };
 async function fetch(url,options){
  if(options?.method==='POST'){posts.push(url);throw Error('Selecting must never command motion');}
  const tool=Number(url.split('tool=')[1]);visited.push(tool);
  const saved=[0,2].includes(tool);
  return {ok:true,json:async()=>({...config,tool,revision:'rev',
    xyz:{x:299.5,y:65.5,z:22},homed:true,idle:true,
    accepted:saved,saved_xy:{x:saved?299.5:null,y:saved?65.5:null}})};
 }
 const windows={};
 const window={CXM_SIMPLE_DOCK_XY:true,
   addEventListener(name,cb){windows[name]=cb;},
   dispatchEvent(event){windows[event.type]?.(event);}
 };
 vm.runInNewContext(src,{document,fetch,window,
    setInterval(){},CustomEvent:class {constructor(type,opts){this.type=type;this.detail=opts?.detail;}},console},
    {filename:'cxm-dock-simple.js'});
 await tick();await tick();
 assert.equal(cards[0].disabled,false);
 assert.equal(cards[1].disabled,false,'unsaved, enabled T1 is calibratable');
 assert.equal(cards[6].disabled,true,'slots above configured count are not enabled');
 assert.equal(cards[0]['aria-pressed'],'true');
 assert.match(cards[0].small.textContent,/Dock XY saved/);
 assert.match(cards[1].small.textContent,/Set up dock XY/);
 cards[2].click();
 await tick();await tick();
 assert.equal(elements.get('cxmsTool').value,'2');
 assert.equal(cards[2]['aria-pressed'],'true');
 assert.equal(cards[0]['aria-pressed'],'false');
 assert.equal(elements.get('cxmsEnable').checked,false);
 cards[1].click();
 await tick();await tick();
 assert.equal(elements.get('cxmsTool').value,'1','unsaved hotend selected for commissioning');
 assert.equal(cards[1]['aria-pressed'],'true');
 cards[6].click();
 assert.equal(elements.get('cxmsTool').value,'1','unconfigured card cannot change target');
 assert.deepEqual(posts,[]);
 assert.deepEqual(visited,[0,2,1]);
 elements.get('cxmsNext').click();
 await tick();await tick();
 assert.equal(elements.get('cxmsTool').value,'2','Next hotend uses same selection state');
 // A Tools-page click must target the LIVE eight-step calibration selector.
 // The previous implementation updated only the retired hidden editor.
 const requestCount=posts.length;
 window.dispatchEvent({type:'cxm-calibrate-tool',detail:{tool:3}});
 await tick();await tick();await tick();
 assert.equal(elements.get('cxmsTool').value,'3','Tools T3 routes to Dock XY T3');
 assert.equal(cards[3]['aria-pressed'],'true');
 assert.equal(elements.get('cxmsEnable').checked,false);
 assert.deepEqual(posts,[],'changing target is read-only, never a T0 pickup');
 assert.equal(posts.length,requestCount);
});
