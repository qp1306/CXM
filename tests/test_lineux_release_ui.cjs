// Regression for post-home transient Klipper idle state and release gating.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'../web/cxm-lineux.js'),'utf8');

function create(){
  const nodes={};
  const element=id=>nodes[id]||(nodes[id]={
    value:id==='cxmDockTool'?'0':'',checked:false,disabled:true,
    textContent:'',dataset:{},listeners:{},
    addEventListener(type,cb){this.listeners[type]=cb;}
  });
  const document={getElementById:element};
  const state={homed:false,postHomePrepareQueries:0,homeCommands:0,statusQueries:[],revision:'a'.repeat(64)};
  function status(mode){
    state.statusQueries.push(mode);
    let ready=false,blockers=['Home required'];
    if(mode==='home'){ready=true;blockers=[];}
    if(mode==='prepare'){
      if(state.homed){
        state.postHomePrepareQueries++;
        ready=state.postHomePrepareQueries>2;
        blockers=ready?[]:['Klipper motion state not idle'];
      }
    }
    return {ready,blockers,tool:0,engine_present:true,status:{}};
  }
  async function fetch(url,options={}){
    let value;
    if(url==='/cxm/api/v1/config')value={revision:state.revision};
    else if(url.startsWith('/cxm/api/v1/lineux/status?')){
      value=status(new URL('http://localhost'+url).searchParams.get('mode'));
    }else if(url==='/cxm/api/v1/lineux/home'){
      state.homeCommands++;
      const body=JSON.parse(options.body);
      assert.equal(body.tool,0);
      assert.equal(body.expected_revision,state.revision);
      assert.equal(body.acknowledgement,'I_CONFIRM_CLEAR_G28_AND_Z20_PATH');
      state.homed=true;
      value={status:'HOMED_Z20_CENTRE'};
    }else throw Error('Unexpected call '+url);
    return {ok:true,json:async()=>value};
  }
  vm.runInNewContext(code,{
    document,fetch,window:{confirm:()=>true,addEventListener(){}},
    setTimeout:callback=>setImmediate(callback)
  },{filename:'cxm-lineux.js'});
  const flush=()=>new Promise(r=>setImmediate(r));
  return {state,nodes,element,flush};
}

test('Home and Z20 automatically retries transient idle status, no page reload',async()=>{
  const t=create();
  await t.flush();await t.flush();
  const home=t.element('cxmLineuxHome');
  const homeAck=t.element('cxmLineuxHomeAck');
  assert.equal(home.disabled,true,'physical home confirmation required');
  homeAck.checked=true;
  homeAck.listeners.change();
  assert.equal(home.disabled,false);
  await home.listeners.click();
  assert.equal(t.state.homeCommands,1);
  assert.equal(t.state.postHomePrepareQueries,3);
  assert.match(t.element('cxmLineuxHomeStatus').textContent,/HOMED/);
  assert.match(t.element('cxmLineuxReleaseStatus').textContent,/four Z motors powered/);
  assert.equal(t.element('cxmLineuxReleaseXY').disabled,true,
    'must still physically confirm XY release');
  assert.equal(t.state.statusQueries.filter(x=>x==='dock').length,1,
    'do not run full preflight or reset state after Home');
  const releaseAck=t.element('cxmLineuxReleaseAck');
  releaseAck.checked=true;
  await releaseAck.listeners.change();
  assert.equal(t.element('cxmLineuxReleaseXY').disabled,false,
    'button should become available after a live check without reloading');
});

test('physical XY release acknowledgement triggers live refresh after Mainsail homing',async()=>{
  const t=create();
  await t.flush();await t.flush();
  assert.equal(t.element('cxmLineuxReleaseXY').disabled,true);
  t.state.homed=true; // User homed directly in Mainsail after loading page.
  const releaseAck=t.element('cxmLineuxReleaseAck');
  releaseAck.checked=true;
  await releaseAck.listeners.change();
  assert.equal(t.state.postHomePrepareQueries,3);
  assert.equal(t.element('cxmLineuxReleaseXY').disabled,false);
  assert.equal(t.state.homeCommands,0,'read-only refresh never homes printer');
});
