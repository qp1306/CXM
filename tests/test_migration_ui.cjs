const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
const dockSource=fs.readFileSync(path.join(__dirname,'../web/cxm-dock.js'),'utf8');
const settingsSource=fs.readFileSync(path.join(__dirname,'../web/cxm-settings.js'),'utf8');
const lineuxSource=fs.readFileSync(path.join(__dirname,'../web/cxm-lineux.js'),'utf8');

function fakeNode(){
  return {
    value:'',textContent:'',disabled:false,hidden:false,style:{},handlers:{},
    classList:{add(){},remove(){}},
    addEventListener(type,fn){this.handlers[type]=fn;},
    replaceChildren(){},append(){},setAttribute(){},
  };
}
function environment({backedUp=true}={}){
  const nodes={},events={},requests=[];
  const node=id=>nodes[id]??(nodes[id]=fakeNode());
  const root={querySelectorAll:()=>[]};
  let current={
    revision:'a'.repeat(64),migration_required:true,
    config:{schema:3,globals:{tool_count:6,safe_y:120},
      tools:Array.from({length:12},(_,n)=>({
        dock_x:n===0?301.8:null,dock_y:n===0?65.62:null,
        offset_x:n===0?0.125:0,offset_y:0,offset_z:0,
        maintenance_lockout:false,dock_reference_accepted:false,
        lineux_raw_x:null,lineux_raw_y:null,dock_z:null,
      }))}
  };
  const backup='snapshot-before-schema3.cfg';
  const document={
    createElement:()=>fakeNode(),
    getElementById:node,
    querySelector:q=>q==='[data-panel="calibration"]'?root:fakeNode(),
  };
  const window={
    confirm(){return true;},
    addEventListener(type,cb){events[type]=cb;},
    dispatchEvent(e){events[e.type]?.(e);},
  };
  async function fetch(url,opts={}){
    requests.push({url,opts});
    let payload;
    if(url==='/cxm/api/v1/config')payload=structuredClone(current);
    else if(url==='/cxm/api/v1/history')payload={backups:backedUp?[backup]:[]};
    else if(url==='/cxm/api/v1/migrate'){
      assert.equal(opts.method,'POST');
      assert.equal(opts.headers['X-Requested-With'],'CXM');
      assert.equal(JSON.parse(opts.body).expected_revision,'a'.repeat(64));
      current={...current,migration_required:false,revision:'b'.repeat(64)};
      payload={saved:true,backup,revision:current.revision,migration_required:false};
    }
    else if(url==='/printer/info')payload={result:{state:'error'}};
    else throw Error('Unexpected test request '+url);
    return {ok:true,json:async()=>payload};
  }
  vm.runInNewContext(dockSource,{document,window,fetch,
    Event:class{constructor(type){this.type=type;}},setTimeout:()=>{}},
    {filename:'cxm-dock.js'});
  return {nodes,node,requests,getCurrent:()=>current,wait:()=>new Promise(r=>setImmediate(r))};
}

test('schema 3 migration is visible directly on Dock XY; no motion or auto-migration',async()=>{
  const t=environment();
  await t.wait();await t.wait();
  assert.match(html,/id="cxmDockMigration" hidden/);
  assert.match(html,/id="cxmDockMigrate" disabled/);
  assert.equal(t.node('cxmDockMigration').hidden,false);
  assert.equal(t.node('cxmDockMigrate').disabled,false);
  assert.equal(t.node('cxmDockAccept').disabled,true);
  assert.equal(t.requests.some(q=>q.url==='/cxm/api/v1/migrate'),false);
  await t.node('cxmDockMigrate').handlers.click();
  const writes=t.requests.filter(q=>q.opts.method==='POST');
  assert.deepEqual(writes.map(q=>q.url),['/cxm/api/v1/migrate']);
  assert.equal(t.getCurrent().migration_required,false);
  assert.equal(t.node('cxmDockMigration').hidden,true);
  assert.equal(t.node('cxmDockX').value,'301.8');
  assert.equal(t.node('cxmDockY').value,'65.62');
  assert.equal(t.getCurrent().config.tools[0].offset_x,0.125);
  assert.equal(t.getCurrent().config.tools[0].dock_reference_accepted,false);
  assert.match(t.node('cxmDockFeedback').textContent,/verified backup/);
});

test('missing backup in history prevents declaring migration verified',async()=>{
  const t=environment({backedUp:false});
  await t.wait();await t.wait();
  await t.node('cxmDockMigrate').handlers.click();
  assert.equal(t.getCurrent().migration_required,false);
  assert.doesNotMatch(t.node('cxmDockFeedback').textContent,/with verified backup/);
  assert.match(t.node('cxmDockFeedback').textContent,/Review backup history/);
});

test('Settings and Dock XY agree on schema 3; blocked approvals are not green',()=>{
  assert.match(settingsSource,/fresh\.config\?\.schema!==3/);
  assert.match(settingsSource,/schema 3\?/);
  assert.doesNotMatch(settingsSource,/fresh\.config\?\.schema!==2/);
  assert.match(lineuxSource,/input\.disabled=busy\|\|ready!==true/);
  assert.match(lineuxSource,/window\.addEventListener\('cxm-config-migrated',preflight\)/);
  assert.match(dockSource,/window\.addEventListener\('cxm-config-migrated'/);
});
