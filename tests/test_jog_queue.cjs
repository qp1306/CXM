const test=require('node:test'), assert=require('node:assert/strict');
const vm=require('node:vm'), fs=require('node:fs'), path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/cxm-manual.js'),'utf8');
async function setup(axiscope=false){
  const nodes={}, moves=[], replies=[];
  function node(id){return nodes[id] ||= {style:{}, value:'', handlers:{},
    classList:{add(){},remove(){}}, addEventListener(k,f){this.handlers[k]=f;}};}
  const buttons=['x','y'].map((axis,i)=>Object.assign(node(axis),{dataset:{manualAxis:axis,distance:i?'-.01':'.1'}}));
  node('cxmManualDock').querySelectorAll=()=>buttons;
  node('cxmDockTool').value='2';
  const axisRoot=node('cxmAxisJog');
  axisRoot.querySelectorAll=()=>buttons;
  node('cxmAxisTool').value='1';
  node('cxmManualDock').querySelector=()=>({cloneNode:()=>({})});
  node('cxmAxisJogRows').append=()=>{};
  if(axiscope)node('cxmManualDock').querySelectorAll=()=>[];
  let initial;
  vm.runInNewContext(source,{window:{addEventListener(){}},document:{getElementById:node,querySelector:s=>axiscope&&s==='#cxmAxisJog'?axisRoot:null,addEventListener(){}},
    performance, setInterval(){},setTimeout(fn){initial=fn;},async fetch(url,opts){
      if(!opts.body)return {ok:true,json:async()=>({ready:true,revision:'r',xy:{x:10,y:20},z:25})};
      moves.push(JSON.parse(opts.body));
      return await new Promise(resolve=>replies.push(ok=>resolve({ok,json:async()=>({jogged:ok,revision:'r',position:{x:10,y:20}})})));
    }});
  await initial();
  node(axiscope?'cxmManualApprovalXY':'cxmManualApproval').checked=true;
  return {tap:i=>buttons[i].handlers.click(),node,moves,replies};
}
test('clearing waiting taps spares the in-flight jog',async()=>{
  const t=await setup(), run=t.tap(0);
  for(const i of [1,0,1])t.tap(i);
  assert.equal(t.node('x').disabled,false);
  t.tap(0);
  assert.equal(t.moves.length,1);
  t.replies.shift()(true);
  await new Promise(r=>setImmediate(r));
  assert.deepEqual(t.moves.map(v=>v.axis),['x','y']);
  t.node('cxmJogClear').handlers.click();
  t.replies.shift()(true);
  await run;
  assert.equal(t.moves.length,2);
  assert.equal(t.node('x').disabled,false);
});
test('uncertain reply discards pending moves and revokes jog approval',async()=>{
  const t=await setup(),run=t.tap(0);
  t.tap(1);
  t.replies.shift()(false);
  await run;
  assert.equal(t.moves.length,1);
  assert.equal(t.node('cxmManualApproval').checked,false);
});

test('a burst of taps executes exactly once in order',async()=>{
  const t=await setup(), run=t.tap(0);
  const taps=Array.from({length:25},(_,i)=>i%2);
  for(const i of taps.slice(1))t.tap(i);
  assert.match(t.node('cxmJogQueue').textContent,/24 queued/);
  for(let i=0;i<taps.length;i++){
    assert.equal(t.moves.length,i+1);
    assert.equal(t.replies.length,1);
    t.replies.shift()(true);
    await new Promise(r=>setImmediate(r));
  }
  await run;
  assert.deepEqual(t.moves.map(v=>v.axis),taps.map(i=>i?'y':'x'));
});

test('Tool XY uses its own selected hotend, approval and queue',async()=>{
  const t=await setup(true),run=t.tap(0);
  t.tap(1);
  assert.equal(t.node('cxmJogQueueXY').textContent,'Jog in progress · 1 queued');
  for(const axis of ['x','y']){
    assert.equal(t.moves.at(-1).tool,1);
    assert.equal(t.moves.at(-1).axis,axis);
    t.replies.shift()(true);
    await new Promise(r=>setImmediate(r));
  }
  await run;
  assert.match(t.node('cxmManualFeedbackXY').textContent,/confirmed/);
});
