const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const script=fs.readFileSync(path.join(__dirname,'../web/cxm-lineux.js'),'utf8');

function harness({released=false,gatewayTimeout=false}={}){
  const nodes={},calls=[];
  const el=id=>nodes[id]||(nodes[id]={
    value:id==='cxmDockTool'?'0':'',checked:false,disabled:true,
    textContent:'',dataset:{},listeners:{},classList:{toggle(){}},
    addEventListener(type,fn){this.listeners[type]=fn;}
  });
  const z={stepper_z:true,stepper_z1:true,stepper_z2:true,stepper_z3:true};
  const status=mode=>{
    const xy={x:!released,y:!released};
    const ready=mode==='home'?true:mode==='prepare'?!released:false;
    return {ready,blockers:ready?[]:released
      ? ['Release only X/Y motors, then hand-align the carriage to the dock',
         'Reported X leaves no safe software margin for Lineux +3 mm jog']
      : ['Not homed'],
      tool:0,engine_present:true,
      status:{xy_motor_enabled:xy,z_motor_enabled:z}};
  };
  async function fetch(url,options={}){
    calls.push({url,options});
    if(url.startsWith('/cxm/api/v1/lineux/status?')){
      const mode=new URL('http://localhost'+url).searchParams.get('mode');
      return {ok:true,status:200,json:async()=>status(mode)};
    }
    if(url==='/cxm/api/v1/config')
      return {ok:true,status:200,json:async()=>({revision:'a'.repeat(64)})};
    if(url==='/cxm/api/v1/lineux/home'){
      if(gatewayTimeout)
        return {ok:false,status:504,json:async()=>{throw Error('The string did not match the expected pattern.')}};
      return {ok:true,status:200,json:async()=>({status:'HOMED_Z20_CENTRE'})};
    }
    throw Error('Unexpected URL '+url);
  }
  vm.runInNewContext(script,{document:{getElementById:el},fetch,
    window:{confirm:()=>true,addEventListener(){}},
    setTimeout:cb=>setImmediate(cb)},{filename:'cxm-lineux.js'});
  return {el,calls,flush:()=>new Promise(resolve=>setImmediate(resolve))};
}

test('released X/Y displays Step 2 COMPLETE, never allows a second release or unsafe homing',async()=>{
  const h=harness({released:true});
  await h.flush();await h.flush();
  assert.match(h.el('cxmLineuxReleaseBadge').textContent,/COMPLETE/);
  assert.match(h.el('cxmLineuxReleaseStatus').textContent,/already OFF/);
  assert.equal(h.el('cxmLineuxReleaseAck').disabled,true);
  assert.equal(h.el('cxmLineuxReleaseXY').disabled,true);
  assert.equal(h.el('cxmLineuxHomeAck').disabled,true);
  assert.equal(h.el('cxmLineuxHome').disabled,true);
  assert.match(h.el('cxmLineuxHomeStatus').textContent,/Do not rehome/);
  await h.el('cxmLineuxReleaseXY').listeners.click();
  await h.el('cxmLineuxHome').listeners.click();
  assert.equal(h.calls.filter(c=>c.options.method==='POST').length,0);
  await h.el('cxmLineuxRefresh').listeners.click();
  assert.match(h.el('cxmLineuxReleaseBadge').textContent,/COMPLETE/);
  assert.equal(h.el('cxmLineuxReleaseXY').disabled,true);
});

test('Safari gateway timeout reports unknown home result, never claims no movement',async()=>{
  const h=harness({gatewayTimeout:true});
  await h.flush();await h.flush();
  h.el('cxmLineuxHomeAck').checked=true;
  h.el('cxmLineuxHomeAck').listeners.change();
  assert.equal(h.el('cxmLineuxHome').disabled,false);
  await h.el('cxmLineuxHome').listeners.click();
  const message=h.el('cxmLineuxHomeStatus').textContent;
  assert.match(message,/HOME RESULT NOT VERIFIED/);
  assert.match(message,/gateway HTTP 504/);
  assert.match(message,/MAY HAVE MOVED/);
  assert.equal(h.calls.filter(c=>c.url.endsWith('/home')&&c.options.method==='POST').length,1);
  assert.equal(h.el('cxmLineuxReleaseXY').disabled,true);
});