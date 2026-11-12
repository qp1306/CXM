const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/cxm-approved-v1.js'),'utf8');
const start=source.indexOf('// A slot is not permission to move.');
const end=source.indexOf('function updateBank(bank,stats){',start);
assert.ok(start>=0&&end>start,'slot setup source must exist');
const slotFns=source.slice(start,end);
function harness(count,confirm=true){
 const events=[],control={value:String(count),disabled:false,dispatchEvent(e){events.push({type:'input',value:this.value,event:e.type})}},notice={textContent:''};
 const handlers=new Map();const window={confirm:()=>confirm,addEventListener:(n,fn)=>handlers.set(n,fn),dispatchEvent:e=>events.push({type:'navigation',name:e.type,tool:e.detail?.tool})};
 function CustomEvent(type,{detail}){this.type=type;this.detail=detail}
 function Event(type){this.type=type}
 const ids={cxmCountSelect:control,cxmaToolSetupNotice:notice};
 const $=n=>ids[n];
 const sandbox={window,$,CustomEvent,Event,Number,String};
 vm.runInNewContext(slotFns+'\nthis.__test={setupSlot,setupNotice};',sandbox);
 // attach handler map to VM sandbox without exposing host resources
 return {setup:n=>sandbox.__test.setupSlot(n),fire:(name,detail)=>handlers.get(name)({detail}),events,notice,control};
}
test('configured unaccepted T3 opens Dock XY without settings mutation or motion',()=>{
 const s=harness(5);s.setup(3);
 assert.equal(s.control.value,'5');assert.equal(s.events.length,1);
 assert.deepEqual(s.events[0],{type:'navigation',name:'cxm-calibrate-tool',tool:3});
});
test('T11 adds all missing slots then navigates only after verified save',()=>{
 const s=harness(5);s.setup(11);
 assert.equal(s.control.value,'12');assert.equal(s.events.length,1);
 assert.equal(s.events[0].event,'change');
 s.fire('cxm-tool-count-saved',{tool_count:12});
 assert.equal(s.events.length,2);assert.equal(s.events[1].tool,11);
 assert.equal(s.events[1].name,'cxm-calibrate-tool');
});
test('count mismatch or failed save does not open any dock',()=>{
 const a=harness(5);a.setup(10);a.fire('cxm-tool-count-saved',{tool_count:7});
 assert.equal(a.events.filter(e=>e.name==='cxm-calibrate-tool').length,0);
 const b=harness(5);b.setup(10);b.fire('cxm-tool-count-save-failed',{error:'revision conflict'});
 assert.equal(b.events.filter(e=>e.name==='cxm-calibrate-tool').length,0);
});
test('jumping slots requires explicit confirmation; invalid indexes cannot act',()=>{
 const s=harness(5,false);s.setup(11);s.setup(-1);s.setup(12);
 assert.equal(s.control.value,'5');assert.equal(s.events.length,0);
});
