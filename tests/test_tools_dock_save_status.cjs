/* Tools must not confuse persisted Dock XY with readiness for toolchange. */
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const read=name=>fs.readFileSync(path.join(__dirname,'..',name),'utf8');
test('Tools summary reflects accepted saved dock coordinates independent of offsets',()=>{
 const nodes=new Map(['cxmToolSummary','cxmActiveTools','cxmNoTools','cxmSafeY','cxmXAdjust']
    .map(key=>[key,{textContent:'',hidden:false}]));
 const cards=Array.from({length:12},()=>({
   hidden:false,dataset:{},innerHTML:'',
   classList:{toggle(){}},
   style:{setProperty(){}},
   querySelector(){return null}
 }));
 global.document={querySelectorAll(q){return q==='.tool-card'?cards:[]},
                  getElementById(id){return nodes.get(id)||null}};
 try{
  const {render}=require('../web/cxm-tool-cards.js');
  const blank={dock_x:null,dock_y:null,dock_reference_accepted:false,
   offset_xy_accepted:false,offset_z_accepted:false,maintenance_lockout:false};
  const tools=Array.from({length:12},()=>({...blank}));
  // T0-T2 saved as calibrated XY; none has completed Tool XY/Z.
  for(let i=0;i<3;i++)Object.assign(tools[i],{
    dock_x:325.006-i*10,dock_y:65+i*.1,dock_reference_accepted:true});
  render({config:{globals:{tool_count:5,safe_y:120,x_docking_adjust:0},tools}});
  assert.match(nodes.get('cxmToolSummary').textContent,/5 selected · 3 dock XY saved · 0 fully ready/);
  assert.equal(cards[0].hidden,false);
 }finally{delete global.document;}
});
test('Tools labels separate saved XY and rejected pickup geometry',()=>{
 const native=read('web/cxm-native-control.js');
 const bank=read('web/cxm-approved-v1.js');
 assert.match(native,/option\.dataset\.savedDock/);
 assert.match(native,/option\.dataset\.reason/);
 assert.match(bank,/Dock XY saved · pickup unavailable/);
 assert.match(bank,/o\.dataset\.reason/);
});
