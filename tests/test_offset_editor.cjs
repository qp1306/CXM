// Catch broken script syntax and blank XY/Z hotend selectors before release.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const ROOT=path.resolve(__dirname,'..');
const source=(name)=>fs.readFileSync(path.join(ROOT,'web',name),'utf8');

test('all browser JavaScript referenced by Control Centre parses',()=>{
  const html=source('index.html');
  const names=[...html.matchAll(/<script\s+src="([^"?]+\.js)(?:\?[^"]*)?"\s+defer><\/script>/g)]
    .map(m=>m[1]);
  assert.ok(names.includes('cxm-offset-editor.js'));
  assert.ok(names.length>=10,'Expected all site scripts to be covered');
  for(const name of names){
    assert.doesNotThrow(()=>new vm.Script(source(name),{filename:name}),
      name+' must parse before page load');
  }
  assert.match(html,/cxm-offset-editor\.js\?v=1\.0\.1/);
});

function element(){
  return {
    value:'',disabled:true,textContent:'',listeners:{},options:[],
    addEventListener(type,listener){this.listeners[type]=listener;},
    replaceChildren(){this.options=[];},
    appendChild(child){this.options.push(child);},
  };
}
async function launch(count){
  const ids=[
    'cxmXYEditSave','cxmZEditSave',
    'cxmXYEditTool','cxmZEditTool','cxmXYEditX','cxmXYEditY',
    'cxmZEditValue','cxmXYEditStatus','cxmZEditStatus',
    'cxmXYEditReset','cxmZEditReset','cxmOpenDiagnostics'
  ];
  const nodes=Object.fromEntries(ids.map(id=>[id,element()]));
  const pages={'[data-tab="offsets"]':element(),
    '[data-tab="z-calibration"]':element(),'[data-tab="tests"]':element()};
  const profiles=Array.from({length:count},(_,n)=>({
    maintenance_lockout:false,offset_x:n===0?0:0.125,
    offset_y:n===0?0:-0.25,offset_z:n===0?0:0.075,
  }));
  const calls=[];
  const config={revision:'a'.repeat(64),migration_required:false,
    config:{globals:{tool_count:count},tools:profiles}};
  const context={
    document:{getElementById:id=>nodes[id]??null,
      createElement:tag=>element(),
      querySelector:selector=>pages[selector]??null},
    window:{confirm:()=>true,addEventListener(){}},
    fetch:async(url,options)=>{calls.push({url,options});return{
      ok:true,json:async()=>config,
    };},
  };
  vm.runInNewContext(source('cxm-offset-editor.js'),context,
    {filename:'cxm-offset-editor.js'});
  await new Promise(resolve=>setImmediate(resolve));
  return {nodes,calls,profiles};
}

test('single T0 correctly populates both selectors and zero-reference displays',async()=>{
  const {nodes,calls}=await launch(1);
  assert.equal(calls[0].url,'/cxm/api/v1/config');
  assert.deepEqual(nodes.cxmXYEditTool.options.map(o=>o.textContent),
    ['T0 · reference']);
  assert.deepEqual(nodes.cxmZEditTool.options.map(o=>o.textContent),
    ['T0 · reference']);
  assert.equal(nodes.cxmXYEditX.value,'0');
  assert.equal(nodes.cxmXYEditY.value,'0');
  assert.equal(nodes.cxmZEditValue.value,'0');
  assert.match(nodes.cxmXYEditStatus.textContent,/T0 reference/);
  assert.match(nodes.cxmZEditStatus.textContent,/T0 reference/);
  // T0 must stay a zero reference; do not let user change relative offsets.
  assert.equal(nodes.cxmXYEditX.disabled,true);
  assert.equal(nodes.cxmZEditValue.disabled,true);
});

test('with T1 selected, both offset editors become editable',async()=>{
  const {nodes}=await launch(2);
  nodes.cxmXYEditTool.value='1';
  nodes.cxmXYEditTool.listeners.change({target:nodes.cxmXYEditTool});
  nodes.cxmZEditTool.value='1';
  nodes.cxmZEditTool.listeners.change({target:nodes.cxmZEditTool});
  assert.equal(nodes.cxmXYEditTool.options.length,2);
  assert.equal(nodes.cxmZEditTool.options.length,2);
  assert.equal(nodes.cxmXYEditX.value,'0.125');
  assert.equal(nodes.cxmXYEditY.value,'-0.25');
  assert.equal(nodes.cxmZEditValue.value,'0.075');
  assert.equal(nodes.cxmXYEditX.disabled,false);
  assert.equal(nodes.cxmXYEditY.disabled,false);
  assert.equal(nodes.cxmZEditValue.disabled,false);
});
