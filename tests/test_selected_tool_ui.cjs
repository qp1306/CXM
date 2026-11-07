const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const source=fs.readFileSync(path.join(__dirname,'../web/cxm-tools.js'),'utf8');
const legacy=fs.readFileSync(path.join(__dirname,'../web/cxm-t0-auto.js'),'utf8');
const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');

function harness(initial='1'){
 const nodes={},calls=[],docListeners={},windowListeners={};
 let intervalCallback=null,holdStatus=false,releaseStatus=null;
 const node=id=>nodes[id]||(nodes[id]={
   value:id==='cxmDockTool'?initial:'',disabled:true,hidden:false,checked:false,
   textContent:'',listeners:{},style:{},setAttribute(){},
   addEventListener(type,handler){this.listeners[type]=handler;}
 });
 let signal='RELEASED',mounted=null,fault=null,block=false;
 const config={revision:'a'.repeat(64)};
 async function fetch(url,options={}){
   calls.push({url,options});
   if(url.startsWith('/cxm/api/v1/tools/status?')&&holdStatus){
     holdStatus=false;
     await new Promise(resolve=>{releaseStatus=resolve;});
   }
   let payload;
   if(url==='/cxm/api/v1/config')payload=config;
   else if(url.startsWith('/cxm/api/v1/tools/status?')){
     const n=Number(new URL('http://localhost'+url).searchParams.get('tool'));
     const differentMounted=mounted!==null&&mounted!==n;
     const reason=block?'T0 fault requires inspection':
       differentMounted?'T'+mounted+' is recorded as mounted. Drop it off first.':null;
     payload={tool:n,ready:!reason,
       saved_xy_mm:{x:n===1?267.6:230.31,y:65.94},
       automatic:{enabled:!reason,reason,signal,mounted_tool:mounted,fault,
         identity_source:mounted===n?'verified_pickup':
            signal==='PRESSED'&&mounted===null?'operator_selected':null}};
   }else if(url==='/cxm/api/v1/tools/auto'){
     const body=JSON.parse(options.body);
     assert.equal(body.acknowledgement,'I_CONFIRMED_SELECTED_HOTEND_IDENTITY_AND_FULL_XY_PATH_CLEAR');
     assert.equal(body.expected_revision,config.revision);
     signal=body.kind==='pickup'?'PRESSED':'RELEASED';
     mounted=body.kind==='pickup'?body.tool:null;
     payload={tool:body.tool,signal,kind:body.kind,
       status:'T'+body.tool+'_'+body.kind.toUpperCase()+'_SENSOR_CONFIRMED'};
   }else if(url==='/cxm/api/v1/tools/clear-fault'){
     fault=null;payload={status:'TOOL_FAULT_CLEARED_NO_MOVEMENT'};
   }else throw Error('Unknown API '+url);
   return {ok:true,status:200,json:async()=>payload};
 }
 const document={
   getElementById:node,
   querySelector:q=>q==='[data-tab="calibration"]'?node('calibrationTab'):null,
   addEventListener:(type,fn)=>{docListeners[type]=fn;},
   hidden:false
 };
 const window={addEventListener:(type,fn)=>{windowListeners[type]=fn;},
               confirm:()=>true};
 const context={document,window,fetch,setInterval:fn=>{intervalCallback=fn;}};
 vm.runInNewContext(source,context,{filename:'cxm-tools.js'});
 const tick=()=>new Promise(resolve=>setImmediate(resolve));
 const select=async n=>{
   node('cxmDockTool').value=String(n);
   node('cxmDockTool').listeners.change();
   await tick();await tick();
 };
 const approve=()=>{node('cxmToolMotionAck').checked=true;node('cxmToolMotionAck').listeners.change();};
 return {node,calls,select,approve,tick,
   poll:()=>intervalCallback?.(),holdNextStatus:()=>{holdStatus=true;},
   releaseStatus:()=>{if(!releaseStatus)throw Error('No held status request');releaseStatus();releaseStatus=null;},
   setBlocked:v=>{block=v;},setSignal:v=>{signal=v;}};
}

test('T0-only controls are never shown for T1–T11',()=>{
 assert.match(legacy,/root.hidden=!onlyT0\(\)/);
 assert.match(html,/id="cxmToolAuto" hidden/);
 assert.match(html,/src="cxm-tools\.js\?v=0\.1\.2"/);
});

test('T1 selection controls T1 geometry, one supervised pickup and same tool dropoff',async()=>{
 const h=harness('1');await h.tick();await h.tick();
 assert.equal(h.node('cxmToolAuto').hidden,false);
 assert.match(h.node('cxmToolAutoTitle').textContent,/T1/);
 assert.match(h.node('cxmToolGeometry').textContent,/267\.600/);
 assert.equal(h.node('cxmToolPickup').disabled,true);
 h.approve();assert.equal(h.node('cxmToolPickup').disabled,false);
 assert.equal(h.node('cxmToolDropoff').disabled,true);
 await h.node('cxmToolPickup').listeners.click();
 const post=h.calls.find(c=>c.url.endsWith('/tools/auto'));
 assert.equal(JSON.parse(post.options.body).tool,1);
 assert.equal(JSON.parse(post.options.body).kind,'pickup');
 assert.equal(h.node('cxmToolMotionAck').checked,false);
 assert.equal(h.node('cxmToolDropoff').disabled,true);
 h.approve();
 assert.equal(h.node('cxmToolDropoff').disabled,false);
 await h.node('cxmToolDropoff').listeners.click();
 const requests=h.calls.filter(c=>c.url.endsWith('/tools/auto'));
 assert.equal(requests.length,2);
 assert.equal(JSON.parse(requests[1].options.body).tool,1);
 assert.equal(JSON.parse(requests[1].options.body).kind,'dropoff');
});

test('switching from T1 to T2 invalidates prior approval and never sends T1 coordinates',async()=>{
 const h=harness('1');await h.tick();await h.tick();
 h.approve();
 await h.select(2);
 assert.match(h.node('cxmToolAutoTitle').textContent,/T2/);
 assert.match(h.node('cxmToolGeometry').textContent,/230\.310/);
 assert.equal(h.node('cxmToolMotionAck').checked,false);
 assert.equal(h.node('cxmToolPickup').disabled,true);
 h.approve();
 await h.node('cxmToolPickup').listeners.click();
 const post=h.calls.find(c=>c.url.endsWith('/tools/auto'));
 assert.equal(JSON.parse(post.options.body).tool,2);
});

test('backend block keeps all selected-tool motion disabled even when checkbox checked',async()=>{
 const h=harness('1');h.setBlocked(true);
 await h.select(1);
 h.approve();
 assert.equal(h.node('cxmToolPickup').disabled,true);
 assert.equal(h.node('cxmToolDropoff').disabled,true);
 await h.node('cxmToolPickup').listeners.click();
 assert.equal(h.calls.some(c=>c.url.endsWith('/tools/auto')),false);
 assert.match(h.node('cxmToolAutoStatus').textContent,/T0 fault requires inspection/);
});


test('operator-selected T1 with PRESENT enables dropoff after one approval, without prior pickup',async()=>{
 const h=harness('1');h.setSignal('PRESSED');await h.select(1);
 assert.match(h.node('cxmToolAutoStatus').textContent,/T1 SELECTED.*PRESENT/);
 assert.match(h.node('cxmToolAutoStatus').textContent,/physically T1/);
 assert.equal(h.node('cxmToolDropoff').disabled,true);
 assert.equal(h.node('cxmToolMotionAck').disabled,false);
 h.approve();assert.equal(h.node('cxmToolDropoff').disabled,false);
 await h.node('cxmToolDropoff').listeners.click();
 const sent=h.calls.filter(c=>c.url.endsWith('/tools/auto'));
 assert.equal(sent.length,1);
 assert.equal(JSON.parse(sent[0].options.body).tool,1);
 assert.equal(JSON.parse(sent[0].options.body).kind,'dropoff');
 assert.equal(h.node('cxmToolMotionAck').checked,false);
 assert.match(h.node('cxmToolAutoStatus').textContent,/ABSENT/);
});

test('background status polling never replaces a useful PRESSED message with Checking',async()=>{
 const h=harness('1');h.setSignal('PRESSED');await h.select(1);
 const original=h.node('cxmToolAutoStatus').textContent;
 h.node('calibrationTab').listeners.click();
 assert.equal(h.node('cxmToolAutoStatus').textContent,original);
 await h.tick();await h.tick();
 assert.equal(h.node('cxmToolAutoStatus').textContent,original);
});

test('T1 successful pickup blocks T2 dropoff despite PRESSED shared switch',async()=>{
 const h=harness('1');await h.tick();await h.tick();
 h.approve();await h.node('cxmToolPickup').listeners.click();
 await h.select(2);
 assert.match(h.node('cxmToolAutoStatus').textContent,/T1 is recorded as mounted/);
 h.approve();assert.equal(h.node('cxmToolDropoff').disabled,true);
 assert.equal(h.node('cxmToolPickup').disabled,true);
 assert.equal(h.calls.filter(c=>c.url.endsWith('/tools/auto')).length,1);
});


test('background status polling never disables an approved T1 dropoff or clears the checkbox',async()=>{
 const h=harness('1');h.setSignal('PRESSED');await h.select(1);
 h.approve();
 assert.equal(h.node('cxmToolDropoff').disabled,false);
 const message=h.node('cxmToolAutoStatus').textContent;
 h.holdNextStatus();
 h.poll();await h.tick();
 assert.equal(h.node('cxmToolMotionAck').checked,true);
 assert.equal(h.node('cxmToolMotionAck').disabled,false);
 assert.equal(h.node('cxmToolDropoff').disabled,false);
 assert.equal(h.node('cxmToolAutoStatus').textContent,message,
   'polling must not replace a valid status with Checking...');
 h.releaseStatus();await h.tick();await h.tick();
 assert.equal(h.node('cxmToolMotionAck').checked,true);
 assert.equal(h.node('cxmToolDropoff').disabled,false);
});

test('a real switch transition revokes approval and updates available action',async()=>{
 const h=harness('1');h.setSignal('PRESSED');await h.select(1);
 h.approve();
 assert.equal(h.node('cxmToolDropoff').disabled,false);
 h.setSignal('RELEASED');h.poll();await h.tick();await h.tick();
 assert.equal(h.node('cxmToolMotionAck').checked,false);
 assert.equal(h.node('cxmToolDropoff').disabled,true);
 assert.equal(h.node('cxmToolPickup').disabled,true);
 assert.match(h.node('cxmToolAutoStatus').textContent,/FILAMENT ABSENT/);
 h.approve();
 assert.equal(h.node('cxmToolPickup').disabled,false);
});

test('an operator can start approved movement while read-only polling is in flight',async()=>{
 const h=harness('1');h.setSignal('PRESSED');await h.select(1);
 h.approve();
 h.holdNextStatus();
 h.poll();await h.tick();
 assert.equal(h.node('cxmToolDropoff').disabled,false);
 await h.node('cxmToolDropoff').listeners.click();
 const sent=h.calls.filter(c=>c.url.endsWith('/tools/auto'));
 assert.equal(sent.length,1);
 assert.equal(JSON.parse(sent[0].options.body).kind,'dropoff');
 assert.equal(h.node('cxmToolMotionAck').checked,false,'approval is one-time');
 h.releaseStatus();await h.tick();await h.tick();
 assert.match(h.node('cxmToolAutoStatus').textContent,/FILAMENT ABSENT/);
 assert.equal(h.node('cxmToolDropoff').disabled,true);
});

test('selection T0 hides selected-tool panel; no T1 request can be issued',async()=>{
 const h=harness('1');await h.tick();await h.tick();
 await h.select(0);
 assert.equal(h.node('cxmToolAuto').hidden,true);
 h.approve();await h.node('cxmToolPickup').listeners.click();
 assert.equal(h.calls.some(c=>c.url.endsWith('/tools/auto')),false);
});
