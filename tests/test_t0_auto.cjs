const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const script=fs.readFileSync(path.join(__dirname,'../web/cxm-t0-auto.js'),'utf8');

function setup(initialSignal='PRESSED'){
  const ids=['cxmT0Auto','cxmT0AutoPickup','cxmT0AutoDropoff',
    'cxmT0AutoStatus','cxmT0AutoGeometry','cxmT0AutoResult',
    'cxmT0AutoFaultBox','cxmT0AutoClearFault','cxmDockTool'];
  const nodes={};
  ids.forEach(id=>nodes[id]={
    disabled:true,hidden:id==='cxmT0AutoFaultBox',textContent:'',
    value:id==='cxmDockTool'?'0':'',
    listeners:{},setAttribute(name,value){this[name]=value},
    addEventListener(name,cb){this.listeners[name]=cb;},
  });
  let signal=initialSignal,revision='a'.repeat(64),fault=null;
  const calls=[],intervals=[],listeners={};
  const document={
    hidden:false,
    getElementById:id=>nodes[id]||null,
    querySelector:()=>({addEventListener(){}}),
    addEventListener(name,handler){listeners[name]=handler;}
  };
  const context={
    document,
    window:{confirm:()=>true,addEventListener(){}},
    setInterval:(cb,time)=>intervals.push({cb,time}),
    fetch:async(url,opts={})=>{
      calls.push({url,opts});
      let payload;
      if(url==='/cxm/api/v1/t0/status')payload={
        ready:true,saved_xy_mm:{x:302.19,y:65.97},
        automatic:{enabled:!fault,signal,reason:fault,fault}
      };
      else if(url==='/cxm/api/v1/config')payload={revision};
      else if(url==='/cxm/api/v1/t0/auto'){
        const data=JSON.parse(opts.body);
        assert.equal(opts.headers['X-Requested-With'],'CXM');
        assert.equal(data.expected_revision,revision);
        assert.equal(data.acknowledgement,'I_CONFIRMED_T0_XY_PATH_CLEAR_AND_WILL_SUPERVISE');
        assert.equal(data.kind,signal==='PRESSED'?'dropoff':'pickup');
        signal=signal==='PRESSED'?'RELEASED':'PRESSED';
        payload={status:'T0_'+data.kind.toUpperCase()+'_SENSOR_CONFIRMED',signal};
      }else if(url==='/cxm/api/v1/t0/clear-fault'){
        fault=null;payload={status:'T0_TEST_FAULT_CLEARED_NO_MOVEMENT'};
      }else throw Error('Unexpected URL '+url);
      return {ok:true,json:async()=>payload};
    }
  };
  vm.runInNewContext(script,context,{filename:'cxm-t0-auto.js'});
  const tick=()=>new Promise(resolve=>setImmediate(resolve));
  return {nodes,calls,intervals,tick,signal:()=>signal,setSignal:v=>signal=v,
    setFault:v=>fault=v};
}

test('live PRESSED shows only Dropoff; no manual recording or staging needed',async()=>{
  const t=setup('PRESSED');
  await t.tick();
  assert.equal(t.nodes.cxmT0AutoDropoff.disabled,false);
  assert.equal(t.nodes.cxmT0AutoPickup.disabled,true);
  assert.match(t.nodes.cxmT0AutoStatus.textContent,/PRESSED/);
  assert.equal(t.intervals[0].time,2500);
  assert.equal(t.calls.length,1);
  const click=t.nodes.cxmT0AutoDropoff.listeners.click;
  click();await t.tick();await t.tick();
  const posted=t.calls.find(c=>c.url==='/cxm/api/v1/t0/auto');
  assert.ok(posted,'direct toolchange call should integrate staging on server');
  assert.equal(JSON.parse(posted.opts.body).kind,'dropoff');
  assert.equal(t.signal(),'RELEASED');
  assert.equal(t.nodes.cxmT0AutoDropoff.disabled,true);
  assert.equal(t.nodes.cxmT0AutoPickup.disabled,false);
  assert.ok(!t.calls.some(c=>c.url.includes('/stage')||c.url.includes('/sensor')));
});

test('RELEASED shows only Pickup and changes after completed action',async()=>{
  const t=setup('RELEASED');
  await t.tick();
  assert.equal(t.nodes.cxmT0AutoPickup.disabled,false);
  assert.equal(t.nodes.cxmT0AutoDropoff.disabled,true);
  t.nodes.cxmT0AutoPickup.listeners.click();
  await t.tick();await t.tick();
  assert.equal(t.signal(),'PRESSED');
  assert.equal(t.nodes.cxmT0AutoPickup.disabled,true);
  assert.equal(t.nodes.cxmT0AutoDropoff.disabled,false);
});

test('fault blocks buttons; recovery requires explicit acknowledgement',async()=>{
  const t=setup('PRESSED');
  await t.tick();
  t.setFault('Inspection required');
  t.intervals[0].cb();
  await t.tick();
  assert.equal(t.nodes.cxmT0AutoFaultBox.hidden,false);
  assert.equal(t.nodes.cxmT0AutoPickup.disabled,true);
  assert.equal(t.nodes.cxmT0AutoDropoff.disabled,true);
  t.nodes.cxmT0AutoClearFault.listeners.click();
  await t.tick();await t.tick();
  assert.equal(t.nodes.cxmT0AutoFaultBox.hidden,true);
  assert.equal(t.nodes.cxmT0AutoDropoff.disabled,false);
  assert.ok(t.calls.some(c=>c.url==='/cxm/api/v1/t0/clear-fault'));
});

test('controller is T0-only: other selected hotends keep both buttons disabled',async()=>{
  const t=setup('PRESSED');
  await t.tick();
  t.nodes.cxmDockTool.value='1';
  t.intervals[0].cb();await t.tick();
  assert.equal(t.nodes.cxmT0AutoPickup.disabled,true);
  assert.equal(t.nodes.cxmT0AutoDropoff.disabled,true);
});
