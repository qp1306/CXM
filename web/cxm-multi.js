/* CXM mechanically supervised bounded multi-pass T0..T11 dock test; not printing readiness. */
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
function repeatMaximum(){
 const tools=selection().length;
 const maxCycles=Number(current?.max_repeat_cycles)||20;
 const maxMoves=Number(current?.max_total_movements)||240;
 return tools>0?Math.min(maxCycles,Math.floor(maxMoves/(tools*2))):maxCycles;
}
function repeatCount(){
 const value=String($('cxmMultiRepeats').value).trim();
 if(!/^[1-9][0-9]*$/.test(value))return null;
 const count=Number(value);
 return Number.isSafeInteger(count)&&count<=repeatMaximum()?count:null;
}
function chooseControls(){
 const running=current?.running===true;
 const valid=selection().length>=2&&
   selection().every(n=>current.candidates.some(t=>t.tool===n&&t.eligible));
 const maxRepeat=repeatMaximum();
 $('cxmMultiRepeats').max=String(maxRepeat);
 text('cxmMultiRepeatHelp','Allowed 1–'+maxRepeat+' complete cycles for '+
   selection().length+' selected hotends (maximum 240 movements).');
 const cycles=repeatCount();
 const ready=!requestBusy&&!running&&valid&&cycles!==null&&!!current?.revision;
 $('cxmMultiAck').disabled=!ready;
 if(!ready)$('cxmMultiAck').checked=false;
 $('cxmMultiStart').disabled=!ready||!$('cxmMultiAck').checked;
 $('cxmMultiStop').disabled=!running||current?.stop_requested===true||requestBusy;
 $('cxmMultiRefresh').disabled=requestBusy;
 $('cxmMultiFastTransfer').disabled=requestBusy||running;
 $('cxmMultiPerformance').disabled=requestBusy||running;
 $('cxmMultiSprint').disabled=requestBusy||running;
 $('cxmMultiRace').disabled=requestBusy||running;
 $('cxmMultiRapid').disabled=requestBusy||running;
 $('cxmMultiRepeats').disabled=requestBusy||running;
 text('cxmMultiStart',running?'Cycle test running…':
   'Start '+(cycles===null?'—':cycles)+' '+(cycles===1?'cycle':'cycles'));
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
 const requested=Number(run.requested_cycles)||1;
 const completed=Number(run.completed_cycles)||0;
 text('cxmMultiCycleText',run.running
   ?'Cycle '+(run.current_cycle||1)+' of '+requested+' · '+completed+' completed'
   :completed+' of '+requested+' complete cycles verified');
 $('cxmMultiFault').hidden=run.state!=='failed';
 if(run.state==='failed')
   text('cxmMultiFault','TEST HALTED · '+(run.error||'Unknown motion state')+
        ' · Inspect physical carriage and dock; do not start another pass blindly.');
 const events=run.results||[];
 const root=$('cxmMultiLog');root.replaceChildren();
 for(const event of events.slice(-48).reverse()){
   const el=document.createElement('div');
   el.textContent=event.message;
   root.append(el);
 }
 if(lastError){
   text('cxmMultiStatus',lastError);
 }else if(run.running){
   const speed=(run.execution_mode==='rapid'?'RAPID KLIPPER · ':'')+
     (run.travel_profile==='race'?'STAGE 2 RACE (400 / 80 / 20 mm/s)':
      run.travel_profile==='sprint'?'STAGE 1 SPRINT (200 / 40 / 10 mm/s)':
      run.travel_profile==='performance'?'PERFORMANCE (80 / 8 / 3 mm/s)':
      run.travel_profile==='faster'?'FASTER CLEAR TRAVEL (30 mm/s)':'STANDARD TRAVEL (10 mm/s)');
   text('cxmMultiStatus',run.stop_requested
      ?'STOP REQUESTED · current tool pair must complete, or use physical E-stop for immediate danger.'
      :'RUNNING · '+speed+' · '+run.last_event+' · supervise all movement');
 }else if(run.state==='complete'){
   text('cxmMultiStatus','CYCLE TEST COMPLETE · '+run.last_event);
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
 const cycles=repeatCount();
 if(cycles===null)return;
 const travelProfile=$('cxmMultiRace').checked?'race':
   $('cxmMultiSprint').checked?'sprint':
   $('cxmMultiPerformance').checked?'performance':
   $('cxmMultiFastTransfer').checked?'faster':'standard';
 const rapid=$('cxmMultiRapid').checked;
 requestBusy=true;$('cxmMultiAck').checked=false;chooseControls();
 text('cxmMultiStatus','Checking live Klipper readiness, real EMPTY carriage, and all '+list.length+' docks…');
 try{
   const requestBody={tools:list,expected_revision:current.revision,
     acknowledgement:ack,travel_profile:travelProfile,cycles};
   if(rapid)requestBody.execution_mode='rapid';
   const reply=await request('/start',requestBody);
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
$('cxmMultiRepeats').addEventListener('input',()=>{
 $('cxmMultiAck').checked=false;
 chooseControls();
 if(!current?.running){
   const cycles=repeatCount();
   text('cxmMultiStatus',cycles===null
     ?'Select a whole number of cycles within the displayed safety limit.'
     :'Selected '+cycles+' complete '+(cycles===1?'cycle':'cycles')+
      '. Verify the machine, approve, then start.');
 }
});
function clearOtherSpeedModes(active){
 for(const id of ['cxmMultiFastTransfer','cxmMultiPerformance','cxmMultiSprint','cxmMultiRace']){
   if(id!==active)$(id).checked=false;
 }
}
$('cxmMultiFastTransfer').addEventListener('change',()=>{
 if($('cxmMultiFastTransfer').checked)clearOtherSpeedModes('cxmMultiFastTransfer');
 $('cxmMultiAck').checked=false;
 chooseControls();
 if(!current?.running)text('cxmMultiStatus',$('cxmMultiFastTransfer').checked
   ?'FASTER MODE selected · 30 mm/s clear corridor only. Inspect the path, approve, then start.'
   :'STANDARD MODE selected · original 10 mm/s staging and existing dock approach.');
});
$('cxmMultiPerformance').addEventListener('change',()=>{
 if($('cxmMultiPerformance').checked)clearOtherSpeedModes('cxmMultiPerformance');
 $('cxmMultiAck').checked=false;
 chooseControls();
 if(!current?.running)text('cxmMultiStatus',$('cxmMultiPerformance').checked
   ?'EXPERIMENTAL PERFORMANCE: 80 mm/s clear corridor, 8 mm/s approach, unchanged 3 mm/s latch. One supervised T0/T1 cycle ONLY after Faster succeeds.'
   :'Performance disabled · select Standard or 30 mm/s Faster for proven movement.');
});
$('cxmMultiSprint').addEventListener('change',()=>{
 if($('cxmMultiSprint').checked)clearOtherSpeedModes('cxmMultiSprint');
 $('cxmMultiAck').checked=false;chooseControls();
 if(!current?.running)text('cxmMultiStatus',$('cxmMultiSprint').checked
   ?'STAGE 1 SPRINT selected: 200 clear / 40 guided / 10 latch mm/s. Experimental; inspect the dock and test one T0/T1 cycle before Race.'
   :'Sprint disabled · choose an individually verified movement profile.');
});
$('cxmMultiRace').addEventListener('change',()=>{
 if($('cxmMultiRace').checked)clearOtherSpeedModes('cxmMultiRace');
 $('cxmMultiAck').checked=false;chooseControls();
 if(!current?.running)text('cxmMultiStatus',$('cxmMultiRace').checked
   ?'STAGE 2 RACE selected: 400 clear / 80 guided / 20 latch mm/s. HIGH-LOAD trial only after physical Sprint pass; one supervised T0/T1 cycle.'
   :'Race disabled · choose an individually verified movement profile.');
});
$('cxmMultiRapid').addEventListener('change',()=>{
 $('cxmMultiAck').checked=false;
 chooseControls();
 if(!current?.running)text('cxmMultiStatus',$('cxmMultiRapid').checked
   ?'RAPID KLIPPER selected · requires installed CXM_FAST_VERIFY macro and Klipper restart; approve only after inspection.'
   :'ORIGINAL MECHANICAL TEST selected · proven commissioning sequence.');
});
$('cxmMultiStart').addEventListener('click',start);
$('cxmMultiStop').addEventListener('click',stop);
$('cxmMultiRefresh').addEventListener('click',refresh);
document.querySelector('[data-tab="tools"]')?.addEventListener('click',refresh);
window.addEventListener('cxm-config-migrated',()=>{snapshotRevision=null;refresh();});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
setInterval(()=>{if(!document.hidden)refresh();},1500);
refresh();
})();