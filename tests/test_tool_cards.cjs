/* Run: node --test tests/test_tool_cards.cjs */
const test=require('node:test');
const assert=require('node:assert/strict');
const cards=require('../web/cxm-tool-cards.js');

const T={enabled:true,dock_x:null,dock_y:null,dock_z:null,
  offset_x:0,offset_y:0,offset_z:0,approach_speed:1200,dock_speed:800};
const make=(changes={})=>({...T,...changes});
test('uncalibrated defaults remain explicitly unverified',()=>{
  const x=cards.card(make(),0,6);
  assert.equal(x.state,'unconfigured');
  assert.match(x.html,/Dock not calibrated/);
  assert.match(x.html,/— \/ — \/ —/);
  assert.match(x.html,/Pickup unavailable/);
  assert.match(x.html,/disabled/);
});
test('saved XYZ and speeds are displayed without claiming successful pickup',()=>{
  const x=cards.card(make({dock_x:172.00625,dock_y:175.00625,dock_z:291.5,offset_x:0.03}),2,6);
  assert.equal(x.state,'configured');
  assert.match(x.html,/172\.006 \/ 175\.006 \/ 291\.500/);
  assert.match(x.html,/0\.030 \/ 0\.000 \/ 0\.000/);
  assert.match(x.html,/1200 mm\/min/);
  assert.match(x.html,/800 mm\/min/);
  assert.match(x.html,/Saved · not verified/);
  assert.doesNotMatch(x.html,/Verified pickup|Tool on carriage/);
});
test('unused or disabled tools cannot be treated as active',()=>{
  assert.equal(cards.card(make(),8,6).state,'inactive');
  assert.match(cards.card(make(),8,6).html,/Outside tool count/);
  assert.equal(cards.card(make({enabled:false}),2,6).state,'inactive');
  assert.match(cards.card(make({enabled:false}),2,6).html,/Disabled/);
});
test('config unavailable keeps temperature unknown and disables actions',()=>{
  const x=cards.card(null,0,0);
  assert.match(x.html,/Config unavailable/);
  assert.match(x.html,/— \(not connected\)/);
  assert.match(x.html,/disabled>Edit/);
});
test('every card is constructed from the supplied configuration, not fixed T0 values',()=>{
  const a=cards.card(make({dock_x:22,dock_y:3,dock_z:4}),0,6);
  const b=cards.card(make({dock_x:94,dock_y:5,dock_z:6}),1,6);
  assert.match(a.html,/22\.000/);
  assert.match(b.html,/94\.000/);
  assert.notEqual(a.html,b.html);
});

test('tool count displays selected T0–T11 including safely disabled profiles',()=>{
  const nodes=Array.from({length:12},()=>({
    hidden:false,dataset:{},innerHTML:'',querySelector(){return null;}
  }));
  const el={
    cxmToolSummary:{textContent:''},cxmActiveTools:{textContent:''},
    cxmSafeY:{textContent:''},cxmXAdjust:{textContent:''},
    cxmNoTools:{hidden:true}
  };
  const previous=global.document;
  global.document={
    querySelectorAll:()=>nodes,
    getElementById:id=>el[id]||null
  };
  try{
    const profiles=Array.from({length:12},(_,i)=>make({enabled:i<6}));
    // Reproduces the user's original case: 12 selected; T6–T11 disabled.
    cards.render({config:{globals:{tool_count:12,safe_y:120,x_docking_adjust:3},tools:profiles}});
    assert.deepEqual(nodes.map((x,i)=>x.hidden?null:i).filter(x=>x!=null),[0,1,2,3,4,5,6,7,8,9,10,11]);
    assert.match(el.cxmToolSummary.textContent,/12 shown \/ 12 selected · 6 enabled/);
    assert.equal(el.cxmActiveTools.textContent,'6 active');
    for(let n=6;n<12;n++){
      assert.match(nodes[n].innerHTML,/Disabled/);
      assert.match(nodes[n].innerHTML,/disabled title="Tool not enabled">Calibrate/);
      assert.match(nodes[n].innerHTML,/data-cxm-edit/);
    }
    assert.equal(el.cxmNoTools.hidden,true);
    // Lowering count hides cards but never modifies the enabled flags.
    cards.render({config:{globals:{tool_count:4,safe_y:120,x_docking_adjust:3},tools:profiles}});
    assert.deepEqual(nodes.map((x,i)=>x.hidden?null:i).filter(x=>x!=null),[0,1,2,3]);
    assert.match(el.cxmToolSummary.textContent,/4 shown \/ 4 selected · 4 enabled/);
    assert.equal(profiles[6].enabled,false);
    // A disabled hotend within the count must remain visible and protected.
    profiles[1].enabled=false;
    cards.render({config:{globals:{tool_count:4,safe_y:120,x_docking_adjust:3},tools:profiles}});
    assert.equal(nodes[1].hidden,false);
    assert.match(nodes[1].innerHTML,/Disabled/);
    assert.equal(el.cxmActiveTools.textContent,'3 active');
    for(const profile of profiles) profile.enabled=false;
    cards.render({config:{globals:{tool_count:4,safe_y:120,x_docking_adjust:3},tools:profiles}});
    assert.equal(nodes.filter(x=>!x.hidden).length,4);
    assert.equal(el.cxmNoTools.hidden,false);
  }finally{if(previous===undefined)delete global.document;else global.document=previous;}
});

test('tool count selection exists in Tools and uses revision-protected AutoSave',()=>{
  const fs=require('node:fs'),path=require('node:path');
  const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
  const settings=fs.readFileSync(path.join(__dirname,'../web/cxm-settings.js'),'utf8');
  assert.match(html, /id="cxmCountSelect"/);
  assert.match(html, /<option value="12">12<\/option>/);
  assert.match(settings, /key:'tool_count',value:next/);
  assert.match(settings, /expected_revision:snapshot.revision/);
  assert.match(settings, /Saved count could not be verified/);
});

test('overview tool count and summary have legible blue-highlight styling',()=>{
  const fs=require('node:fs');
  const html=fs.readFileSync(require('node:path').join(__dirname,'../web/index.html'),'utf8');
  assert.match(html, /\.tool-count-control label\{font-size:16px;font-weight:700;color:#a8d7ff\}/);
  assert.match(html, /#cxmToolSummary\{font-size:15px;/);
  assert.match(html, /background:#20334b;border:1px solid #42698f/);
  assert.match(html, /\.tool-count-control select\{[^}]*font-size:17px/);
  assert.match(html, /CXM starter <span>v[0-9]+\.[0-9]+\.[0-9]+<\/span>/);
});
