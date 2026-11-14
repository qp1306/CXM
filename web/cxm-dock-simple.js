/* Dock XY — eight steps, no filament gating, no extra Klipper macro install. */
(()=>{
'use strict';
const page=document.querySelector('[data-panel="calibration"]');
if(!page||!window.CXM_SIMPLE_DOCK_XY)return;
page.classList.add('cxm-dock-simple-active');
const root=document.createElement('div');
root.id='cxmSimpleDock';
root.innerHTML=`
<header class="cxms-header"><h1>Dock XY Calibration</h1><p>Home · Select · Enable · Jog · Test · Adjust · Save · Next</p></header>
<div class="cxms-status"><span id="cxmsPosition">X — · Y — · Z —</span><span id="cxmsSaved">Not saved</span><span id="cxmsPrinter">Checking Klipper…</span></div>
<div class="cxms-grid">
<section class="cxms-step"><div class="cxms-heading"><b>1</b><h2>Home printer</h2></div><button class="btn primary" id="cxmsHome">Home XYZ</button></section>
<section class="cxms-step"><div class="cxms-heading"><b>2</b><h2>Select hotend</h2></div><select id="cxmsTool" aria-label="Hotend"><option value="0">T0</option></select></section>
<section class="cxms-step cxms-step-enable cxms-wide"><div class="cxms-heading"><b>3</b><h2>Enable jogging</h2></div><label class="cxms-enable"><input type="checkbox" id="cxmsEnable"><span class="cxms-enable-copy"><strong>Enable jogging</strong><small>Automatically raises Z to 22 mm. Jog X/Y below to align the selected hotend.</small></span></label></section>
<section class="cxms-step cxms-wide"><div class="cxms-heading"><b>4</b><h2>Jog carriage into position</h2></div><div id="cxmsJogs">
<div class="cxms-jogrow"><strong>X</strong><button data-axis="x" data-dist="-10">−10</button><button data-axis="x" data-dist="-1">−1</button><button data-axis="x" data-dist="-0.1">−0.1</button><button data-axis="x" data-dist="-0.01">−0.01</button><button data-axis="x" data-dist="0.01">+0.01</button><button data-axis="x" data-dist="0.1">+0.1</button><button data-axis="x" data-dist="1">+1</button><button data-axis="x" data-dist="10">+10</button></div>
<div class="cxms-jogrow"><strong>Y</strong><button data-axis="y" data-dist="-10">−10</button><button data-axis="y" data-dist="-1">−1</button><button data-axis="y" data-dist="-0.1">−0.1</button><button data-axis="y" data-dist="-0.01">−0.01</button><button data-axis="y" data-dist="0.01">+0.01</button><button data-axis="y" data-dist="0.1">+0.1</button><button data-axis="y" data-dist="1">+1</button><button data-axis="y" data-dist="10">+10</button></div>
</div></section>
<section class="cxms-step"><div class="cxms-heading"><b>5</b><h2>Test docking / undocking</h2></div><button class="btn primary" id="cxmsTest">Test dock &amp; undock</button></section>
<section class="cxms-step"><div class="cxms-heading"><b>6</b><h2>Adjust X/Y if needed</h2></div><p>Use the X/Y jog controls above. Test again if needed.</p></section>
<section class="cxms-step"><div class="cxms-heading"><b>7</b><h2>Save coordinates</h2></div><button class="btn primary" id="cxmsSave">Save dock XY</button></section>
<section class="cxms-step"><div class="cxms-heading"><b>8</b><h2>Next hotend</h2></div><button class="btn" id="cxmsNext">Next hotend</button></section>
</div>
<p class="cxms-message" id="cxmsMessage" role="status" aria-live="polite">Select T0 and home the printer.</p>`;
page.append(root);
const get=id=>document.getElementById(id);
const select=get('cxmsTool'),checkbox=get('cxmsEnable');
const buttons=Array.from(root.querySelectorAll('[data-axis]'));
const api='/cxm/api/v1/dock-simple';
let live=null,busy=false,enabled=false,revision='',seq=0,savedAtDock=false;
const jogQueue=[];
let jogRunning=false;
const selected=()=>Number(select.value);
function say(msg,error=false){const el=get('cxmsMessage');el.textContent=msg;el.classList.toggle('cxms-error',error);}
async function request(url,body){
 const opts={cache:'no-store',credentials:'same-origin'};
 if(body){opts.method='POST';opts.headers={'Content-Type':'application/json','X-Requested-With':'CXM'};opts.body=JSON.stringify(body);}
 const r=await fetch(url,opts);
 const d=await r.json().catch(()=>({error:'Invalid CXM response'}));
 if(!r.ok)throw Error(d.error||'CXM request failed');
 return d;
}
function controls(){
 const blocked=busy||jogRunning||jogQueue.length>0;
 get('cxmsHome').disabled=blocked||!live;
 select.disabled=blocked;
 checkbox.disabled=blocked||!live?.homed;
 const moving=enabled&&!blocked&&live?.homed===true;
 // Queued jog requests execute in order. Do not grey out the jog buttons
 // while a previous click is travelling, just like Mainsail's jog UI.
 const canJog=enabled&&live?.homed===true&&(!busy||jogRunning);
 for(const b of buttons)b.disabled=!canJog;
 get('cxmsTest').disabled=!moving;
 get('cxmsSave').disabled=!moving||savedAtDock;
 get('cxmsNext').disabled=blocked||!live||selected()>=live.tool_count-1;
}
function display(){
 if(!live){controls();return;}
 const p=live.xyz;
 get('cxmsPosition').textContent='X '+p.x.toFixed(3)+' · Y '+p.y.toFixed(3)+' · Z '+p.z.toFixed(2)+' mm';
 get('cxmsSaved').textContent=live.accepted&&live.saved_xy.x!==null?
  'Saved X '+live.saved_xy.x.toFixed(3)+' · Y '+live.saved_xy.y.toFixed(3):'Not saved';
 get('cxmsPrinter').textContent=live.homed?'XYZ homed':'Needs homing';
 controls();
}
async function refresh(silent=false){
 if(busy||page.hidden||document.hidden)return;
 const marker=++seq,tool=selected();
 try{
  const d=await request(api+'/status?tool='+tool);
  if(marker!==seq||tool!==selected())return;
  live=d;revision=d.revision;
  if(select.options.length!==d.tool_count){
   const prior=select.value;
   select.replaceChildren();
   for(let n=0;n<d.tool_count;n++){const op=document.createElement('option');op.value=String(n);op.textContent='T'+n;select.append(op);}
   select.value=Number(prior)<d.tool_count?prior:'0';
  }
  display();
 }catch(e){
  if(marker!==seq)return;
  live=null;enabled=false;checkbox.checked=false;
  if(!silent)say(e.message,true);
  controls();
 }
}
async function act(kind,fields={},done){
 if(busy||!live)return;
 const tool=selected(),before=revision;
 busy=true;controls();
 try{
  const d=await request(api+'/'+kind,{tool,expected_revision:before,...fields});
  if(selected()!==tool)throw Error('Hotend changed during operation');
  if(kind==='enable'){enabled=true;checkbox.checked=true;}
  if(kind==='jog')savedAtDock=false;
  if(kind==='save'&&d.saved===true){savedAtDock=true;
   window.dispatchEvent(new CustomEvent('cxm-dock-save-completed',{detail:{tool,x:d.xy.x,y:d.xy.y}}));}
  if(done)say(done(d));
 }catch(e){
  if(kind==='enable'){enabled=false;checkbox.checked=false;}
  say(kind.toUpperCase()+' · '+e.message,true);
 }finally{busy=false;await refresh();controls();}
}
get('cxmsHome').addEventListener('click',()=>{enabled=false;savedAtDock=false;checkbox.checked=false;act('home',{},()=> 'XYZ homed. Select a hotend and enable jogging.');});
checkbox.addEventListener('change',()=>{
 if(!checkbox.checked){enabled=false;controls();return;}
 enabled=false;
 act('enable',{},d=>'Z '+d.xyz.z.toFixed(2)+' mm · jogging enabled.');
});
async function runQueuedJogs(){
 if(jogRunning||busy||!enabled||!live||!live.homed)return;
 jogRunning=true;busy=true;controls();
 const startTool=selected();
 try{
  while(jogQueue.length){
   const next=jogQueue.shift();
   if(selected()!==startTool)throw Error('Selected hotend changed');
   // Await completion in request order. Multiple clicks are accepted instantly
   // and never issue conflicting parallel Klipper commands.
   const d=await request(api+'/jog',{
    tool:startTool,expected_revision:revision,
    axis:next.axis,distance:next.distance
   });
   if(selected()!==startTool)throw Error('Selected hotend changed');
   live=d;revision=d.revision;savedAtDock=false;
   display();
   say('X '+d.xyz.x.toFixed(3)+' · Y '+d.xyz.y.toFixed(3)+
       (jogQueue.length?' · '+jogQueue.length+' jog(s) queued':''));
  }
 }catch(e){
  jogQueue.length=0;
  say('JOG · '+e.message,true);
  jogRunning=false;busy=false;
  controls();
  await refresh();
  return;
 }finally{
  // Successful jog responses already contain fresh, server-verified XYZ.
  // No extra status request or momentary disabled state between clicks.
  jogRunning=false;busy=false;
  controls();
 }
}
for(const b of buttons)b.addEventListener('click',()=>{
 if(!enabled||!live||!live.homed||busy&&!jogRunning)return;
 jogQueue.push({axis:b.dataset.axis,distance:Number(b.dataset.dist)});
 if(!jogRunning)runQueuedJogs();
});
get('cxmsTest').addEventListener('click',()=>act('test',{},
 ()=> 'Dock/undock movement completed; returned to original X/Y. Inspect the result.'));
get('cxmsSave').addEventListener('click',()=>act('save',{},d=>
 'Saved T'+d.tool+' · X '+d.xy.x.toFixed(3)+' · Y '+d.xy.y.toFixed(3)+
 (d.retreated?' · Y +100 mm complete. Ready for next hotend.':
 ' · Y +100 mm NOT confirmed: '+(d.retreat_error||'Check carriage position'))));
function changeTool(next){
 if(next<0||next>=Number(live?.tool_count||0))return;
 select.value=String(next);enabled=false;savedAtDock=false;checkbox.checked=false;
 say('T'+next+' selected. Enable jogging to continue.');refresh();
}
get('cxmsNext').addEventListener('click',()=>changeTool(selected()+1));
select.addEventListener('change',()=>{enabled=false;savedAtDock=false;checkbox.checked=false;say('T'+selected()+' selected. Enable jogging to continue.');refresh();});
setInterval(()=>{if(!busy&&!page.hidden&&!document.hidden)refresh(true);},1800);
refresh();
})();