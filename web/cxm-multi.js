/* CXM mechanically supervised one-pass T0..T11 dock test; not printing readiness. */
(()=>{
'use strict';
const $=id=>document.getElementById(id);
if(!$('cxmMultiPanel'))return;
const base='/cxm/api/v1/tools/multi';
const ack='I_CHECKED_EMPTY_CARRIAGE_ALL_SELECTED_DOCKS_AND_FULL_XY_PATH';
let current=null,chosen=new Set(),snapshotRevision=null,requestBusy=false,polling=false,lastError='';
const text=(id,message)=>{$(id).textContent=message;};
function selection(){
 return [...chosen].sort((a,b)=>a-b);
}
function eligible(){
 return (current?.candidates||[]).filter(t=>t.eligible);
}
function chooseControls(){
 const running=current?.running===true;
 const valid=selection().length>=2&&
   selection().every(n=>current.candidates.some(t=>t.tool===n&&t.eligible));
 const ready=!requestBusy&&!running&&valid&&!!current?.revision;
 $('cxmMultiAck').disabled=!ready;
 if(!ready)$('cxmMultiAck').checked=false;
 $('cxmMultiStart').disabled=!ready||!$('cxmMultiAck').checked;
 $('cxmMultiStop').disabled=!running||current?.stop_requested===true||requestBusy;
 $('cxmMultiRefresh').disabled=requestBusy;
 $('cxmMultiPanel').setAttribute('aria-busy',requestBusy?'true':'false');
 for(const input of document.querySelectorAll('#cxmMultiChoices input')){
   input.disabled=requestBusy||running||input.dataset.eligible!=='yes';
 }
}
function drawChoices(){
 const root=$('cxmMultiChoices');
 root.replaceChildren();
 for(const tool of current.candidates||[]){
   const card=document.createElement('label');
   card.className='cxm-multi-choice';
   const input=document.createElement('input');
   input.type='checkbox';input.value=String(tool.tool);
   input.dataset.eligible=tool.eligible?'yes':'no';
   input.checked=tool.eligible&&chosen.has(tool.tool);
   input.disabled=requestBusy||current.running||!tool.eligible;
   const info=document.createElement('span');
   const title=document.createElement('strong');
   title.textContent='T'+tool.tool;
   const detail=document.createElement('small');
   detail.textContent=tool.eligible&&tool.xy
      ?'Dock X'+Number(tool.xy.x).toFixed(3)+' / Y'+Number(tool.xy.y).toFixed(3)+' · accepted XY'
      :(tool.reason||'Dock not eligible');
   info.append(title,detail);card.append(input,info);root.append(card);
   input.addEventListener('change',()=>{
     if(input.checked)chosen.add(tool.tool);else chosen.delete(tool.tool);
     $('cxmMultiAck').checked=false;
     lastError='';
     chooseControls();
     if(!current.running){
       text('cxmMultiStatus','Selected '+selection().map(n=>'T'+n).join(' → ')+
         '. Start checks Klipper, real empty carriage and every dock again before any movement.');
     }
   });
 }
 if(!(current.candidates||[]).length)root.textContent='No configured hotends available.';
}
function showStatus(){
 if(!current)return;
 const run=current;
 const total=run.total_steps||0;
 const done=run.completed_steps||0;
 $('cxmMultiProgressFill').style.width=(total?Math.round(100*done/total):0)+'%';
 text('cxmMultiProgressText',done+' of '+total+' pickup/dropoff movements sensor-confirmed');
 $('cxmMultiFault').hidden=run.state!=='failed';
 if(run.state==='failed')
   text('cxmMultiFault','TEST HALTED · '+(run.error||'Unknown motion state')+
        ' · Inspect physical carriage and dock; do not start another pass blindly.');
 const events=run.results||[];
 const root=$('cxmMultiLog');root.replaceChildren();
 for(const event of events.slice(-9).reverse()){
   const el=document.createElement('div');
   el.textContent=event.message;
   root.append(el);
 }
 if(lastError){
   text('cxmMultiStatus',lastError);
 }else if(run.running){
   text('cxmMultiStatus',run.stop_requested
      ?'STOP REQUESTED · current tool pair must complete, or use physical E-stop for immediate danger.'
      :'RUNNING · '+run.last_event+' · supervise all movement');
 }else if(run.state==='complete'){
   text('cxmMultiStatus','PASS COMPLETE · '+run.last_event);
 }else if(run.state==='failed'){
   text('cxmMultiStatus','FAILED · '+run.last_event);
 }else if(run.state==='stopped'){
   text('cxmMultiStatus','STOPPED · '+run.last_event);
 }else{
   const selected=selection().map(n=>'T'+n).join(' → ');
   text('cxmMultiStatus',selected
      ?'Ready to PRECHECK '+selected+' · carriage must be EMPTY and all physical paths clear'
      :'Choose at least two accepted docks to run a supervised mechanical test.');
 }
}
async function request(path,body){
 const args=body?{
   method:'POST',credentials:'same-origin',cache:'no-store',
   headers:{'Content-Type':'application/json','X-Requested-With':'CXM'},
   body:JSON.stringify(body)
 }:{credentials:'same-origin',cache:'no-store'};
 const r=await fetch(base+path,args);
 if(r.status===502||r.status===504)throw Error('CXM gateway '+r.status+' · result unknown; inspect the printer');
 let data;
 try{data=await r.json();}catch{throw Error('Non-JSON CXM response; check the actual printer before retrying');}
 if(!r.ok)throw Error(data.error||'HTTP '+r.status);
 return data;
}
async function refresh(){
 if(polling||requestBusy)return;
 polling=true;
 try{
   const next=await request('/status');
   const existing=!!current;
   const wasRunning=current?.running;
   const revisionChanged=snapshotRevision!==null&&snapshotRevision!==next.revision;
   const eligibleSet=new Set((next.candidates||[]).filter(x=>x.eligible).map(x=>x.tool));
   if(!existing||revisionChanged){
     chosen=new Set(eligibleSet);
     $('cxmMultiAck').checked=false;
   }else{
     chosen=new Set([...chosen].filter(n=>eligibleSet.has(n)));
   }
   snapshotRevision=next.revision;
   current=next;
   if(revisionChanged||!existing||wasRunning!==next.running)
     drawChoices();
   else if(current.running)chooseControls();
   if(next.running || next.state==='complete' || next.state==='stopped')lastError='';
   chooseControls();showStatus();
 }catch(e){
   current=null;lastError='Multi-tool controller unavailable: '+e.message;
   $('cxmMultiAck').checked=false;
   $('cxmMultiStart').disabled=true;
   $('cxmMultiStop').disabled=true;
   text('cxmMultiStatus',lastError);
 }finally{polling=false;}
}
async function start(){
 if(requestBusy||!current||current.running||!$('cxmMultiAck').checked)return;
 const list=selection();
 if(list.length<2||list.some(n=>!current.candidates.some(t=>t.tool===n&&t.eligible)))return;
 requestBusy=true;$('cxmMultiAck').checked=false;chooseControls();
 text('cxmMultiStatus','Checking live Klipper readiness, real EMPTY carriage, and all '+list.length+' docks…');
 try{
   const reply=await request('/start',{tools:list,expected_revision:current.revision,acknowledgement:ack});
   if(!reply.started)throw Error('Backend did not confirm a started run');
   lastError='';
 }catch(e){
   lastError='NO CYCLE STARTED / UNCONFIRMED RESULT · '+e.message+
     '. If a gateway error occurred, inspect printer state before any repeat.';
 }finally{
   requestBusy=false;
   await refresh();
   if(lastError)text('cxmMultiStatus',lastError);
 }
}
async function stop(){
 if(requestBusy||!current?.running||current.stop_requested)return;
 requestBusy=true;chooseControls();
 try{
   await request('/stop',{acknowledgement:'STOP_AFTER_CURRENT_TOOL_PAIR'});
   lastError='';
 }catch(e){
   lastError='Stop request not verified: '+e.message+
     '. Use the physical emergency stop for immediate danger.';
 }finally{requestBusy=false;await refresh();}
}
$('cxmMultiAck').addEventListener('change',chooseControls);
$('cxmMultiStart').addEventListener('click',start);
$('cxmMultiStop').addEventListener('click',stop);
$('cxmMultiRefresh').addEventListener('click',refresh);
document.querySelector('[data-tab="tools"]')?.addEventListener('click',refresh);
window.addEventListener('cxm-config-migrated',()=>{snapshotRevision=null;refresh();});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
setInterval(()=>{if(!document.hidden)refresh();},1500);
refresh();
})();