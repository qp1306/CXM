const test=require('node:test'), assert=require('node:assert/strict');
const vm=require('node:vm'), fs=require('node:fs'), path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/cxm-manual.js'),'utf8');
async function setup(){
  const nodes={}, moves=[], replies=[];
  function node(id){return nodes[id] ||= {style:{}, value:'', handlers:{},
    classList:{add(){},remove(){}}, addEventListener(k,f){this.handlers[k]=f;}};}
  const buttons=['x','y'].map((axis,i)=>Object.assign(node(axis),{dataset:{manualAxis:axis,distance:i?'-.01':'.1'}}));
  node('cxmManualDock').querySelectorAll=()=>buttons;
  node('cxmDockTool').value='2';
  let initial;
  vm.runInNewContext(source,{window:{addEventListener(){}},document:{getElementById:node,querySelector:()=>null,addEventListener(){}},
    performance, setInterval(){},setTimeout(fn){initial=fn;},async fetch(url,opts){
      if(!opts.body)return {ok:true,json:async()=>({ready:true,revision:'r',xy:{x:10,y:20},z:25})};
      moves.push(JSON.parse(opts.body));
      return await new Promise(resolve=>replies.push(ok=>resolve({ok,json:async()=>({jogged:ok,revision:'r',position:{x:10,y:20}})})));
    }});
  await initial();
  node('cxmManualApproval').checked=true;
  return {tap:i=>buttons[i].handlers.click(),node,moves,replies};
}
test('queued taps run in order; overflow is ignored and clearing spares the in-flight jog',async()=>{
  const t=await setup(), run=t.tap(0);
  for(const i of [1,0,1])t.tap(i);
  assert.ok(t.node('x').disabled);
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
