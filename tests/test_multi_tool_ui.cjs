const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
const source=fs.readFileSync(path.join(__dirname,'../web/cxm-multi.js'),'utf8');

function harness({lockedTwo=false}={}){
 const nodes={},listeners={},calls=[],allChoices=[],windowListeners={};
 let timer=null,state='idle',step=0,selected=[],blockedStart=false,travelProfile='standard';
 let requestedCycles=1,completedCycles=0,currentCycle=null;
 const mk=(tag='div')=>({
   tagName:tag,textContent:'',value:'',checked:false,disabled:false,hidden:false,
   children:[],style:{},dataset:{},className:'',listeners:{},
   setAttribute(){},
   addEventListener(event,fn){this.listeners[event]=fn;},
   replaceChildren(){this.children=[];},
   append(...items){this.children.push(...items);}
 });
 function get(id){return nodes[id]||(nodes[id]=mk());}
 function candidates(){
   return [
    {tool:0,eligible:true,xy:{x:306.79,y:65.99},dock_accepted:true,reason:null},
    {tool:1,eligible:true,xy:{x:267.19,y:65.68},dock_accepted:true,reason:null},
    {tool:2,eligible:!lockedTwo,xy:{x:226.01,y:65.21},
     dock_accepted:!lockedTwo,reason:lockedTwo?'Dock XY not measured and accepted':null}
   ];
 }
 function snapshot(){
   return {running:state==='running',state,stop_requested:false,
     travel_profile:travelProfile,revision:'a'.repeat(64),candidates:candidates(),
     max_repeat_cycles:20,max_total_movements:240,
     requested_cycles:requestedCycles,completed_cycles:completedCycles,
     current_cycle:currentCycle,
     tools:selected,total_steps:Math.max(0,selected.length*2*requestedCycles),
     completed_steps:step,last_event:state==='running'?'T0 pickup started':'No pass started',
     error:null,results:[]};
 }
 async function fetch(url,options={}){
   calls.push({url,options});
   let reply;
   if(url==='/cxm/api/v1/tools/multi/status')reply=snapshot();
   else if(url==='/cxm/api/v1/tools/multi/start'){
     const body=JSON.parse(options.body);
     assert.equal(body.acknowledgement,'I_CHECKED_EMPTY_CARRIAGE_ALL_SELECTED_DOCKS_AND_FULL_XY_PATH');
     assert.equal(body.expected_revision,'a'.repeat(64));
     assert.ok(['standard','faster'].includes(body.travel_profile));
     assert.ok(Number.isInteger(body.cycles)&&body.cycles>=1&&body.cycles<=20);
     requestedCycles=body.cycles;currentCycle=1;completedCycles=0;
     travelProfile=body.travel_profile;
     if(blockedStart)return {ok:false,status:400,json:async()=>({error:'Carriage FILAMENT PRESENT'})};
     selected=body.tools;state='running';step=0;
     reply={started:true,tools:selected,cycles:requestedCycles,
            total_steps:selected.length*2*requestedCycles};
   }else if(url==='/cxm/api/v1/tools/multi/stop'){
     assert.equal(JSON.parse(options.body).acknowledgement,'STOP_AFTER_CURRENT_TOOL_PAIR');
     state='stopped';step=2;reply={stop_requested:true};
   }else throw Error('Unexpected '+url);
   return {ok:true,status:200,json:async()=>reply};
 }
 const document={
   hidden:false,
   getElementById:get,
   querySelector(selector){return selector==='[data-tab="tools"]'?get('toolsTab'):null;},
   querySelectorAll(selector){
     if(selector==='#cxmMultiChoices input')return get('cxmMultiChoices').children.map(c=>c.children[0]);
     return [];
   },
   createElement:mk,
   addEventListener(type,fn){listeners[type]=fn;}
 };
 vm.runInNewContext(source,{document,fetch,window:{addEventListener(type,fn){windowListeners[type]=fn;}},
   setInterval(fn){timer=fn;}},{filename:'cxm-multi.js'});
 const tick=()=>new Promise(resolve=>setImmediate(resolve));
 const click=async id=>{get(id).listeners.click();await tick();await tick();};
 const choose=(n,checked)=>{
   const card=get('cxmMultiChoices').children.find(c=>c.children[0].value===String(n));
   if(!card)throw Error('No candidate card T'+n);
   const input=card.children[0];input.checked=checked;
   input.listeners.change();
 };
 return {get,calls,tick,click,choose,poll:()=>timer(),setBlockedStart:v=>{blockedStart=v;},
         getCandidates:()=>get('cxmMultiChoices').children,
         setStep:v=>{step=v;completedCycles=Math.floor(v/(selected.length*2));
           currentCycle=Math.min(requestedCycles,Math.floor(v/(selected.length*2))+1);},
         setState:v=>{state=v;}};
}

test('Tools page exposes explicit one-pass mechanical test, not a printing readiness flag',()=>{
 assert.match(html,/id="cxmMultiPanel"/);
 assert.match(html,/id="cxmMultiAck" type="checkbox" disabled/);
 assert.match(html,/id="cxmMultiStop" disabled/);
 assert.match(html,/src="cxm-multi\.js\?v=0\.1\.2"/);
 assert.match(html,/NOT READY.*printing commissioning is incomplete/);
 assert.match(html,/physical emergency stop/);
});

test('three eligible docks are shown selected with saved coordinates and no motion until approval',async()=>{
 const h=harness();await h.tick();await h.tick();
 assert.equal(h.getCandidates().length,3);
 assert.equal(h.get('cxmMultiAck').disabled,false);
 assert.equal(h.get('cxmMultiStart').disabled,true);
 assert.equal(h.get('cxmMultiStop').disabled,true);
 assert.equal(h.getCandidates().filter(c=>c.children[0].checked).length,3);
 assert.match(h.getCandidates()[1].children[1].children[1].textContent,/267\.190/);
 assert.equal(h.calls.some(c=>c.options.method==='POST'),false);
 h.get('cxmMultiAck').checked=true;
 h.get('cxmMultiAck').listeners.change();
 assert.equal(h.get('cxmMultiStart').disabled,false);
 await h.click('cxmMultiStart');
 const motionRequests=h.calls.filter(c=>c.url.endsWith('/start'));
 assert.equal(motionRequests.length,1);
 assert.equal(JSON.parse(motionRequests[0].options.body).tools.join(','),'0,1,2');
 assert.equal(h.get('cxmMultiStop').disabled,false);
 assert.equal(h.get('cxmMultiAck').checked,false);
 assert.match(h.get('cxmMultiStatus').textContent,/RUNNING/);
});


test('faster option is explicitly opt-in and revokes an already-ticked movement approval',async()=>{
 const h=harness();await h.tick();await h.tick();
 assert.equal(h.get('cxmMultiFastTransfer').checked,false,'default must stay original proven speed');
 h.get('cxmMultiAck').checked=true;h.get('cxmMultiAck').listeners.change();
 assert.equal(h.get('cxmMultiStart').disabled,false);
 h.get('cxmMultiFastTransfer').checked=true;
 h.get('cxmMultiFastTransfer').listeners.change();
 assert.equal(h.get('cxmMultiAck').checked,false);
 assert.equal(h.get('cxmMultiStart').disabled,true);
 assert.match(h.get('cxmMultiStatus').textContent,/30 mm\/s/);
 h.get('cxmMultiAck').checked=true;h.get('cxmMultiAck').listeners.change();
 await h.click('cxmMultiStart');
 const post=h.calls.find(c=>c.url.endsWith('/multi/start'));
 assert.equal(JSON.parse(post.options.body).travel_profile,'faster');
 assert.equal(h.get('cxmMultiFastTransfer').disabled,true,'speed is immutable while moving');
 assert.match(h.get('cxmMultiStatus').textContent,/FASTER CLEAR TRAVEL/);
});

test('without faster opt-in the server receives standard profile',async()=>{
 const h=harness();await h.tick();await h.tick();
 h.get('cxmMultiAck').checked=true;h.get('cxmMultiAck').listeners.change();
 await h.click('cxmMultiStart');
 const post=h.calls.find(c=>c.url.endsWith('/multi/start'));
 assert.equal(JSON.parse(post.options.body).travel_profile,'standard');
 assert.match(h.get('cxmMultiStatus').textContent,/STANDARD TRAVEL/);
});


test('repeat count defaults to 1, changes approval and posts 5 full cycles',async()=>{
 const h=harness();await h.tick();await h.tick();
 assert.equal(h.get('cxmMultiRepeats').value,'1');
 assert.equal(h.get('cxmMultiRepeats').max,'20');
 assert.equal(h.get('cxmMultiStart').textContent,'Start 1 cycle');
 h.get('cxmMultiAck').checked=true;h.get('cxmMultiAck').listeners.change();
 assert.equal(h.get('cxmMultiStart').disabled,false);
 h.get('cxmMultiRepeats').value='5';
 h.get('cxmMultiRepeats').listeners.input();
 assert.equal(h.get('cxmMultiAck').checked,false,'changing count revokes earlier approval');
 assert.equal(h.get('cxmMultiStart').disabled,true);
 assert.equal(h.get('cxmMultiStart').textContent,'Start 5 cycles');
 h.get('cxmMultiAck').checked=true;h.get('cxmMultiAck').listeners.change();
 await h.click('cxmMultiStart');
 const posts=h.calls.filter(c=>c.url.endsWith('/multi/start'));
 assert.equal(posts.length,1);
 assert.equal(JSON.parse(posts[0].options.body).cycles,5);
 assert.equal(JSON.parse(posts[0].options.body).tools.join(','),'0,1,2');
 assert.equal(h.get('cxmMultiRepeats').disabled,true);
 assert.match(h.get('cxmMultiCycleText').textContent,/Cycle 1 of 5/);
 assert.match(h.get('cxmMultiProgressText').textContent,/0 of 30/);
 h.setStep(10);
 await h.poll();await h.tick();await h.tick();
 assert.match(h.get('cxmMultiCycleText').textContent,/Cycle 2 of 5/);
 assert.match(h.get('cxmMultiCycleText').textContent,/1 completed/);
 assert.match(h.get('cxmMultiProgressText').textContent,/10 of 30/);
 assert.equal(h.get('cxmMultiProgressFill').style.width,'33%');
});

test('reject empty, fractional, negative and too-large repeat counts before network motion',async()=>{
 const h=harness();await h.tick();await h.tick();
 for(const invalid of ('', '0','-1','2.5','21','abc')){
   h.get('cxmMultiRepeats').value=invalid;
   h.get('cxmMultiRepeats').listeners.input();
   assert.equal(h.get('cxmMultiAck').disabled,true,'invalid: '+invalid);
   assert.equal(h.get('cxmMultiStart').disabled,true,'invalid: '+invalid);
 }
 assert.equal(h.calls.filter(c=>c.url.endsWith('/multi/start')).length,0);
 h.get('cxmMultiRepeats').value='20';
 h.get('cxmMultiRepeats').listeners.input();
 assert.equal(h.get('cxmMultiAck').disabled,false);
 assert.match(h.get('cxmMultiRepeatHelp').textContent,/1–20/);
});

test('repeat mode stays independent of faster corridor checkbox',async()=>{
 const h=harness();await h.tick();await h.tick();
 h.get('cxmMultiRepeats').value='3';
 h.get('cxmMultiRepeats').listeners.input();
 h.get('cxmMultiFastTransfer').checked=true;
 h.get('cxmMultiFastTransfer').listeners.change();
 h.get('cxmMultiAck').checked=true;h.get('cxmMultiAck').listeners.change();
 await h.click('cxmMultiStart');
 const post=h.calls.find(c=>c.url.endsWith('/multi/start'));
 const body=JSON.parse(post.options.body);
 assert.equal(body.travel_profile,'faster');
 assert.equal(body.cycles,3);
 assert.equal(body.tools.length,3);
});

test('ineligible T2 cannot be included; selecting fewer than two disables Start',async()=>{
 const h=harness({lockedTwo:true});await h.tick();await h.tick();
 assert.equal(h.getCandidates().length,3);
 assert.equal(h.getCandidates()[2].children[0].disabled,true);
 assert.equal(h.getCandidates()[2].children[0].checked,false);
 assert.match(h.getCandidates()[2].children[1].children[1].textContent,/not measured and accepted/);
 h.choose(1,false);
 h.get('cxmMultiAck').checked=true;
 h.get('cxmMultiAck').listeners.change();
 assert.equal(h.get('cxmMultiStart').disabled,true);
 assert.equal(h.calls.some(c=>c.url.endsWith('/start')),false);
});

test('a denied preflight never claims movement started or enables Stop',async()=>{
 const h=harness();await h.tick();await h.tick();
 h.get('cxmMultiAck').checked=true;h.get('cxmMultiAck').listeners.change();
 h.setBlockedStart(true);
 await h.click('cxmMultiStart');
 assert.match(h.get('cxmMultiStatus').textContent,/FILAMENT PRESENT/);
 assert.equal(h.get('cxmMultiStop').disabled,true);
 assert.equal(h.get('cxmMultiAck').checked,false);
});

test('stop only uses explicit stop-after-current-tool request',async()=>{
 const h=harness();await h.tick();await h.tick();
 h.get('cxmMultiAck').checked=true;h.get('cxmMultiAck').listeners.change();
 await h.click('cxmMultiStart');
 await h.click('cxmMultiStop');
 assert.equal(h.calls.filter(c=>c.url.endsWith('/stop')).length,1);
 assert.equal(h.get('cxmMultiStop').disabled,true);
 assert.match(h.get('cxmMultiStatus').textContent,/STOPPED/);
});

test('live progress follows backend confirmed sensor movements, never estimates',async()=>{
 const h=harness();await h.tick();await h.tick();
 h.get('cxmMultiAck').checked=true;h.get('cxmMultiAck').listeners.change();
 await h.click('cxmMultiStart');
 h.setStep(4);
 await h.poll();await h.tick();await h.tick();
 assert.equal(h.get('cxmMultiProgressFill').style.width,'67%');
 assert.match(h.get('cxmMultiProgressText').textContent,/4 of 6/);
});
