const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const script=fs.readFileSync(path.join(__dirname,'../web/cxm-t0-auto.js'),'utf8');

function setup(initialSignal='PRESSED'){
  const ids=['cxmT0Auto','cxmT0AutoPickup','cxmT0AutoDropoff',
    'cxmT0AutoStatus','cxmT0AutoGeometry','cxmT0AutoResult',
    'cxmT0AutoFaultBox','cxmT0AutoClearFault','cxmDockTool',
    'cxmT0Cycles','cxmT0StartCycles','cxmT0StopCycles','cxmT0CycleStatus','cxmT0MotionAck'];
  const nodes={};
  ids.forEach(id=>nodes[id]={
    disabled:true,hidden:id==='cxmT0AutoFaultBox',textContent:'',checked:false,
    value:id==='cxmDockTool'?'0':id==='cxmT0Cycles'?'3':'',
    listeners:{},setAttribute(name,value){this[name]=value},
    addEventListener(name,cb){this.listeners[name]=cb;},
  });
  let signal=initialSignal,revision='a'.repeat(64),fault=null;
  const cycle={running:false,requested:0,completed:0,phase:'idle',
    stop_requested:false,error:null,last_result:null};
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
      if(url==='/cxm/api/v1/t0/cycles/status')payload={...cycle};
      else if(url==='/cxm/api/v1/t0/status')payload={
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
      }else if(url==='/cxm/api/v1/t0/cycles'){
        const data=JSON.parse(opts.body);
        assert.equal(data.acknowledgement,'I_CONFIRMED_T0_REPEAT_PATH_CLEAR_AND_WILL_SUPERVISE');
        assert.equal(data.expected_revision,revision);
        assert.equal(data.cycles,3);
        cycle.requested=data.cycles;cycle.completed=data.cycles;
        cycle.phase='Complete';
        signal='RELEASED';
        payload={status:'T0_REPEAT_COMPLETE',completed_cycles:data.cycles,
          requested_cycles:data.cycles,final_sensor:signal};
        cycle.last_result=payload;
      }else if(url==='/cxm/api/v1/t0/cycles/stop'){
        assert.equal(JSON.parse(opts.body).acknowledgement,'STOP_AFTER_CURRENT_T0_CYCLE');
        cycle.stop_requested=true;
        payload={...cycle};
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

function approve(t){t.nodes.cxmT0MotionAck.checked=true;t.nodes.cxmT0MotionAck.listeners.change();}

test('live PRESSED shows only Dropoff; no manual recording or staging needed',async()=>{
  const t=setup('PRESSED');
  await t.tick();
  assert.equal(t.nodes.cxmT0AutoDropoff.disabled,true,'requires fresh approval');
  approve(t);
  assert.equal(t.nodes.cxmT0AutoDropoff.disabled,false);
  assert.equal(t.nodes.cxmT0AutoPickup.disabled,true);
  assert.match(t.nodes.cxmT0AutoStatus.textContent,/PRESSED/);
  assert.equal(t.intervals[0].time,2500);
  assert.equal(t.calls.length,2);
  const click=t.nodes.cxmT0AutoDropoff.listeners.click;
  click();await t.tick();await t.tick();
  const posted=t.calls.find(c=>c.url==='/cxm/api/v1/t0/auto');
  assert.ok(posted,'direct toolchange call should integrate staging on server');
  assert.equal(JSON.parse(posted.opts.body).kind,'dropoff');
  assert.equal(t.signal(),'RELEASED');
  assert.equal(t.nodes.cxmT0AutoDropoff.disabled,true);
  assert.equal(t.nodes.cxmT0AutoPickup.disabled,true,'approval consumed after dropoff');
  assert.equal(t.nodes.cxmT0MotionAck.checked,false);
  assert.ok(!t.calls.some(c=>c.url.includes('/stage')||c.url.includes('/sensor')));
});

test('RELEASED shows only Pickup and changes after completed action',async()=>{
  const t=setup('RELEASED');
  await t.tick();
  assert.equal(t.nodes.cxmT0AutoPickup.disabled,true);
  approve(t);
  assert.equal(t.nodes.cxmT0AutoPickup.disabled,false);
  assert.equal(t.nodes.cxmT0AutoDropoff.disabled,true);
  t.nodes.cxmT0AutoPickup.listeners.click();
  await t.tick();await t.tick();
  assert.equal(t.signal(),'PRESSED');
  assert.equal(t.nodes.cxmT0AutoPickup.disabled,true);
  assert.equal(t.nodes.cxmT0AutoDropoff.disabled,true,'pickup consumes approval');
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
  assert.equal(t.nodes.cxmT0AutoDropoff.disabled,true,'fault clear does not approve motion');
  assert.ok(t.calls.some(c=>c.url==='/cxm/api/v1/t0/clear-fault'));
});

test('repeat three cycles uses one backend cycle command and no manual staging',async()=>{
  const t=setup('RELEASED');
  await t.tick();await t.tick();
  assert.equal(t.nodes.cxmT0StartCycles.disabled,true);
  approve(t);
  assert.equal(t.nodes.cxmT0StartCycles.disabled,false);
  t.nodes.cxmT0StartCycles.listeners.click();
  await t.tick();await t.tick();await t.tick();
  const sent=t.calls.filter(c=>c.url==='/cxm/api/v1/t0/cycles');
  assert.equal(sent.length,1);
  assert.equal(JSON.parse(sent[0].opts.body).cycles,3);
  assert.match(t.nodes.cxmT0CycleStatus.textContent,/3.*3|Complete/i);
  assert.equal(t.signal(),'RELEASED');
  assert.ok(!t.calls.some(c=>/\/t0\/sensor|\/t0\/motion/.test(c.url)));
});
test('repeat count must be a whole number from 1 to 20',async()=>{
  const t=setup('RELEASED');
  await t.tick();await t.tick();
  t.nodes.cxmT0Cycles.value='21';
  t.nodes.cxmT0Cycles.listeners.input();
  assert.equal(t.nodes.cxmT0StartCycles.disabled,true);
  t.nodes.cxmT0Cycles.value='2.5';
  t.nodes.cxmT0Cycles.listeners.input();
  assert.equal(t.nodes.cxmT0StartCycles.disabled,true);
  t.nodes.cxmT0Cycles.value='3';
  t.nodes.cxmT0Cycles.listeners.input();
  assert.equal(t.nodes.cxmT0StartCycles.disabled,true);
  approve(t);
  assert.equal(t.nodes.cxmT0StartCycles.disabled,false);
});

test('unchecked approval blocks direct motion calls',async()=>{
  const t=setup('RELEASED');
  await t.tick();
  await t.nodes.cxmT0AutoPickup.listeners.click();
  assert.equal(t.calls.some(c=>c.url==='/cxm/api/v1/t0/auto'),false);
  approve(t);
  await t.nodes.cxmT0AutoPickup.listeners.click();
  assert.equal(t.calls.some(c=>c.url==='/cxm/api/v1/t0/auto'),true);
  assert.equal(t.nodes.cxmT0MotionAck.checked,false);
});

test('controller is T0-only: other selected hotends keep both buttons disabled',async()=>{
  const t=setup('PRESSED');
  await t.tick();
  t.nodes.cxmDockTool.value='1';
  t.intervals[0].cb();await t.tick();
  assert.equal(t.nodes.cxmT0AutoPickup.disabled,true);
  assert.equal(t.nodes.cxmT0AutoDropoff.disabled,true);
});
