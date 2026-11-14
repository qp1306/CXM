/* CXM locked-dock commissioning: sensor RELEASED, continuous out/back. */
(()=>{
'use strict';
const page=document.querySelector('[data-panel="calibration"]');
const selector=document.getElementById('cxmDockTool');
const oldSave=document.getElementById('cxmManualCapture');
const oldTravel=document.getElementById('cxmDockTravelCheck');
if(!page||!selector||!oldSave||!oldTravel)return;
const host=page.querySelector('.cxma-stage[data-stage="3"] .cxma-inner')||oldSave.parentElement;
const oldSection=oldSave.closest('.cxma-save-section');
if(oldSection)oldSection.style.display='none';
oldTravel.style.display='none';
const box=document.createElement('section');
box.className='panel';box.id='cxmLockedDockPanel';
box.innerHTML=
 '<div class="panel-heading"><h3>Locked dock · verify then save</h3><span class="panel-label">Continuous out-and-back</span></div>'+
 '<p class="helper">Lock selected hotend in its dock. Confirm FILAMENT ABSENT and a clear +Y path.</p>'+
 '<p class="helper" id="cxmLockedDockState" role="status">Checking carriage…</p>'+
 '<label class="cxm-capture-ack"><input type="checkbox" id="cxmLockedDockAck">'+
 '<span class="cxm-approval-copy"><strong>Hotend locked · carriage EMPTY · path clear</strong>'+
 '<small>ABSENT confirms an empty carriage, not a mechanically locked dock</small></span></label>'+
 '<div class="buttons"><button class="btn primary" id="cxmLockedDockTest" disabled>Test +100 mm → −100 mm</button>'+
 '<button class="btn" id="cxmLockedDockRefresh">Refresh</button></div>'+
 '<p class="helper" id="cxmLockedDockResult" role="status" aria-live="polite">Test not completed.</p>'+
 '<div class="panel-heading"><h3>Fine XY adjustment</h3><span class="panel-label">Retest required</span></div>'+
 '<div class="buttons" id="cxmLockedDockAdjust">'+
 '<button class="btn" data-axis="x" data-distance="-1" disabled>X −1</button>'+
 '<button class="btn" data-axis="x" data-distance="-0.1" disabled>X −0.1</button>'+
 '<button class="btn" data-axis="x" data-distance="0.1" disabled>X +0.1</button>'+
 '<button class="btn" data-axis="x" data-distance="1" disabled>X +1</button>'+
 '<button class="btn" data-axis="y" data-distance="-1" disabled>Y −1</button>'+
 '<button class="btn" data-axis="y" data-distance="-0.1" disabled>Y −0.1</button>'+
 '<button class="btn" data-axis="y" data-distance="0.1" disabled>Y +0.1</button>'+
 '<button class="btn" data-axis="y" data-distance="1" disabled>Y +1</button></div>'+
 '<div class="buttons"><button class="btn primary big" id="cxmLockedDockSave" disabled>Save verified dock XY</button></div>';
host.prepend(box);
const $=id=>document.getElementById(id);
const api='/cxm/api/v1', ack=$('cxmLockedDockAck'),test=$('cxmLockedDockTest'),
 save=$('cxmLockedDockSave'),status=$('cxmLockedDockState'),
 result=$('cxmLockedDockResult'),buttons=Array.from(box.querySelectorAll('[data-axis]'));
let live=null,busy=false,verified=false,tool=-1,refreshVersion=0;
function selected(){let n=Number(selector.value);return selector.value!==''&&Number.isInteger(n)?n:-1;}
function display(message,bad=false){result.textContent=message;result.style.color=bad?'#f4aaaa':'#bed9ec';}
async function request(path,body){
 let opts={credentials:'same-origin',cache:'no-store'};
 if(body){opts.method='POST';opts.headers={'Content-Type':'application/json','X-Requested-With':'CXM'};
  opts.body=JSON.stringify(body);}
 const r=await fetch(api+path,opts),d=await r.json().catch(()=>({error:'Invalid response'}));
 if(!r.ok)throw Error(d.error||'HTTP '+r.status);return d;
}
function controls(){
 let allowed=!!live?.ready&&live?.sensor==='RELEASED'&&!busy&&!page.hidden&&
   !document.hidden&&selected()===tool&&ack.checked;
 test.disabled=!allowed;
 save.disabled=!allowed||!verified||!live?.travel_verified;
 for(const b of buttons)b.disabled=!allowed;
 $('cxmLockedDockRefresh').disabled=busy;
}
async function refresh(){
 if(busy||page.hidden||document.hidden)return;
 const t=selected(),version=++refreshVersion;
 if(t<0){live=null;verified=false;controls();return;}
 try{
  const d=await request('/dock-verify/status?tool='+t);
  if(version!==refreshVersion||selected()!==t)return;
  live=d;tool=t;
  if(!d.travel_verified)verified=false;
  status.textContent='CXM: FILAMENT ABSENT · carriage EMPTY · X'+
   d.xy.x.toFixed(3)+' Y'+d.xy.y.toFixed(3)+' Z'+d.z.toFixed(2)+' mm';
 }catch(e){
  if(version!==refreshVersion)return;
  live=null;verified=false;status.textContent='NOT READY · '+e.message;
 }finally{controls();}
}
async function run(body,path,done){
 if(busy||!live||!ack.checked||selected()!==tool)return;
 const t=tool,rev=live.revision;
 busy=true;controls();
 try{
  let d=await request(path,Object.assign({tool:t,expected_revision:rev,
   acknowledgement:'I_INSPECTED_LOCKED_DOCK_AND_CLEAR_PATH'},body));
  if(selected()!==t)throw Error('Selected tool changed during operation');
  await done(d,t);
 }catch(e){
  verified=false;display('STOP · '+e.message+'. Inspect carriage before retrying.',true);
 }finally{busy=false;await refresh();controls();}
}
test.addEventListener('click',()=>{
 verified=false;
 display('Moving Y +100 then −100 continuously. Verifying sensor and position between legs…');
 run({},'/dock-verify/roundtrip',async d=>{
  if(d.verified!==true||d.sensor!=='RELEASED')throw Error('Round trip not confirmed');
  verified=true;
  display('PASS · +100 and −100 mm · returned to X'+d.end.x.toFixed(3)+
   ' Y'+d.end.y.toFixed(3)+'. Save or adjust and repeat.');
 });
});
for(const b of buttons)b.addEventListener('click',()=>{
 verified=false;
 display('Adjusting '+b.dataset.axis.toUpperCase()+' '+b.dataset.distance+' mm…');
 run({axis:b.dataset.axis,distance:Number(b.dataset.distance)},'/dock-verify/adjust',async d=>{
  if(!d.adjusted||d.sensor!=='RELEASED')throw Error('Adjustment not verified');
  display('Adjusted. Repeat the +100/−100 test before Save.');
 });
});
save.addEventListener('click',()=>run({},'/dock-verify/save',async(d,t)=>{
 if(!d.saved||!d.verified)throw Error('Saved datum unverified');
 const check=await request('/config');
 const actual=check.config.tools[t];
 if(actual.dock_x!==d.xy.x||actual.dock_y!==d.xy.y||
    actual.dock_reference_accepted!==true)throw Error('Saved coordinate readback mismatch');
 verified=false;ack.checked=false;
 display('SAVED T'+t+' · X'+d.xy.x.toFixed(5)+' Y'+d.xy.y.toFixed(5)+
  ' mm · backup created. Synchronize native geometry before tool changes.');
 window.dispatchEvent(new CustomEvent('cxm-dock-save-completed',{
  detail:{tool:t,x:d.xy.x,y:d.xy.y}}));
}));
ack.addEventListener('change',()=>{if(!ack.checked)verified=false;controls();});
selector.addEventListener('change',()=>{
 live=null;verified=false;tool=-1;ack.checked=false;
 display('Select tool and lock it into the dock.');controls();refresh();
});
$('cxmLockedDockRefresh').addEventListener('click',refresh);
document.addEventListener('visibilitychange',()=>{if(document.hidden){ack.checked=false;verified=false;controls();}});
setInterval(()=>{if(!busy)refresh();},1800);
refresh();
})();