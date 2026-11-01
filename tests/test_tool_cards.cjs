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
