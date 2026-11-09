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
function selectedProfile(){
 return $('cxmSpeedSimple').value;
}
function customSpeeds(){
 const values=['cxmCustomTravel','cxmCustomApproach','cxmCustomLatch'].map(id=>Number($(id).value));
 if(values.some((v,i)=>!Number.isFinite(v)||$( ['cxmCustomTravel','cxmCustomApproach','cxmCustomLatch'][i] ).value.trim()===''))return null;
 const [travel,approach,latch]=values;
 return travel>=10&&travel<=1200&&approach>=1&&approach<=600&&latch>=1&&latch<=300&&travel>=approach&&approach>=latch
   ? {travel,approach,latch}:null;
}
function selectedMode(){return 'native';}
function profileLabel(profile){
 const names={
   standard:'STANDARD (10 / 4 / 3 mm/s)',
   faster:'FASTER (30 / 4 / 3 mm/s)',
   performance:'PERFORMANCE (80 / 8 / 3 mm/s)',
   sprint:'SPRINT (200 / 40 / 10 mm/s)',
   race:'RACE (400 / 80 / 20 mm/s)',
   boost:'BOOST requested (600 / 120 / 40 mm/s)',
   custom:'CUSTOM ('+(customSpeeds()?Object.values(customSpeeds()).join(' / '):'INVALID')+' mm/s)'
 };
 return names[profile]||'UNKNOWN PROFILE';
}
function modeLabel(mode){return mode==='native'?'NATIVE KLIPPER':String(mode||'UNKNOWN').toUpperCase();}
function chooseControls(){
 const running=current?.running===true;
 const valid=selection().length>=2&&selection().length<=3&&
   selection().every(n=>current.candidates.some(t=>t.tool===n&&t.eligible));
 const maxRepeat=repeatMaximum();
 $('cxmMultiRepeats').max=String(maxRepeat);
 text('cxmMultiRepeatHelp','Allowed 1–'+maxRepeat+' complete cycles for '+
   selection().length+' selected hotends (maximum 240 movements).');
 const cycles=repeatCount();
 const streaming=false;
 text('cxmMultiPlanned','NEXT TEST (not previous run): '+
   modeLabel(selectedMode())+' · '+profileLabel(selectedProfile())+
   ' · '+(cycles??'INVALID')+' cycle(s) · '+selection().length+' tools');
 const experimental=['sprint','race','boost','custom'].includes(selectedProfile());
 const customValid=selectedProfile()!=='custom'||customSpeeds()!==null;
 const ready=!requestBusy&&!running&&valid&&cycles!==null&&customValid&&(!experimental||cycles===1)&&
   current?.native_ready===true&&current?.current_tool===-1&&current?.fault===0&&!!current?.revision;
 $('cxmMultiAck').disabled=!ready;
 if(!ready)$('cxmMultiAck').checked=false;
 $('cxmMultiStart').disabled=!ready;
 $('cxmMultiStop').disabled=!running||current?.stop_requested===true||requestBusy;
 text('cxmMultiStop','Stop after current tool');
 $('cxmMultiRefresh').disabled=requestBusy;
 $('cxmMultiFastTransfer').disabled=requestBusy||running;
 $('cxmMultiPerformance').disabled=requestBusy||running;
 $('cxmMultiSprint').disabled=requestBusy||running;
 $('cxmMultiRace').disabled=requestBusy||running;
 $('cxmMultiBoost').disabled=requestBusy||running;
 $('cxmMultiRapid').disabled=requestBusy||running;
 $('cxmMultiStream').disabled=requestBusy||running;
 $('cxmMultiRepeats').disabled=requestBusy||running;
 $('cxmNativeSync').disabled=requestBusy||running;
 $('cxmNativeEmptyAck').disabled=requestBusy||running;
 $('cxmNativeConfirm').disabled=requestBusy||running||!$('cxmNativeEmptyAck').checked||current?.native_ready!==true;
 $('cxmNativeRecover').disabled=requestBusy||!$('cxmNativeEmptyAck').checked||current?.native_ready!==true||current?.sensor!=='RELEASED';
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
 text('cxmMultiLastRun','LAST RECORDED RUN (not current checkbox selection): '+
   (run.run_id
     ?modeLabel(run.execution_mode)+' · '+profileLabel(run.travel_profile)+
      ' · '+run.state.toUpperCase()+' · '+(run.tools||[]).map(t=>'T'+t).join(' → ')
     :'No run recorded in this CXM service session'));
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
   const speed=(run.execution_mode==='stream'?'UNINTERRUPTED KLIPPER STREAM · ':
     run.execution_mode==='rapid'?'RAPID KLIPPER · ':'')+
     (run.travel_profile==='boost'?'STAGE 3 BOOST (600 / 120 / 40 mm/s requested)':
      run.travel_profile==='race'?'STAGE 2 RACE (400 / 80 / 20 mm/s)':
      run.travel_profile==='sprint'?'STAGE 1 SPRINT (200 / 40 / 10 mm/s)':
      run.travel_profile==='performance'?'PERFORMANCE (80 / 8 / 3 mm/s)':
      run.travel_profile==='faster'?'FASTER CLEAR TRAVEL (30 mm/s)':'STANDARD TRAVEL (10 mm/s)');
   text('cxmMultiStatus',run.execution_mode==='stream'
      ?'STREAM RUNNING · '+speed+' · NO software Stop-after-pair. Physical emergency stop ONLY. '+run.last_event
      :run.stop_requested
      ?'STOP REQUESTED · current tool pair must complete, or use physical E-stop for immediate danger.'
      :'RUNNING · '+speed+' · '+run.last_event+' · supervise all movement');
 }else if(run.state==='complete'){
   text('cxmMultiStatus','CYCLE TEST COMPLETE · '+run.last_event);
 }else if(run.state==='failed'){
   text('cxmMultiStatus','FAILED · '+modeLabel(run.execution_mode)+' · '+
     profileLabel(run.travel_profile)+' · '+run.last_event);
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
   const carrier=$('cxmCarriageIdentity');
   if(carrier.options.length!==next.candidates.length+2){
     const prev=carrier.value;
     carrier.replaceChildren(new Option('Choose EMPTY or mounted tool',''),new Option('EMPTY — no hotend fitted','-1'));
     for(const t of next.candidates){
       carrier.append(new Option('T'+t.tool+(t.eligible?'':' · not calibrated'),String(t.tool)));
     }
     carrier.value=prev;
   }
   text('cxmNativeStatus',next.native_ready&&next.fault===0&&next.current_tool===-1
     ?'READY · Carriage EMPTY'
     :next.native_ready&&next.fault===0&&Number.isInteger(next.current_tool)&&next.current_tool>=0
     ?'READY · T'+next.current_tool+' mounted · sensor '+next.sensor
     :next.native_ready?'Select the actual carriage state above to verify it'
     :'Choose EMPTY or mounted tool above to prepare Klipper automatically.');
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
 if(requestBusy||!current||current.running)return;
 const list=selection();
 if(list.length<2||list.some(n=>!current.candidates.some(t=>t.tool===n&&t.eligible)))return;
 const cycles=repeatCount();
 if(cycles===null)return;
 const travelProfile=selectedProfile();
 if(['sprint','race','boost','custom'].includes(travelProfile)&&cycles!==1){
  text('cxmMultiStatus','High-speed and Custom profiles require exactly one supervised cycle.');
  return;
 }
 const streaming=$('cxmMultiStream').checked;
 if(streaming&&(cycles!==1||list.length>3)){
  text('cxmMultiStatus','Uninterrupted Stream requires 2–3 selected tools and exactly 1 cycle.');
  return;
 }
 const rapid=false;
 requestBusy=true;$('cxmMultiAck').checked=false;chooseControls();
 text('cxmMultiStatus','SUBMITTING '+modeLabel(selectedMode())+' · '+
   profileLabel(travelProfile)+' · '+list.map(n=>'T'+n).join(' → ')+
   '. Checking Klipper readiness and real EMPTY carriage…');
 try{
   const requestBody={tools:list,expected_revision:current.revision,
     acknowledgement:ack,travel_profile:travelProfile,cycles};
   requestBody.execution_mode='native';
   if(travelProfile==='custom'){
     const values=customSpeeds();
     if(!values)throw Error('Custom speeds are invalid; check three speed limits and ordering');
     requestBody.custom_speeds=values;
   }
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
async function nativePost(path,body){
 const r=await fetch('/cxm/api/v1/native/'+path,{
   method:'POST',credentials:'same-origin',cache:'no-store',
   headers:{'Content-Type':'application/json','X-Requested-With':'CXM'},
   body:JSON.stringify(body)
 });
 const data=await r.json().catch(()=>({error:'Non-JSON native controller response'}));
 if(!r.ok)throw Error(data.error||'HTTP '+r.status);
 return data;
}
async function synchronizeNative(){
 if(requestBusy||current?.running||!current?.revision)return;
 requestBusy=true;chooseControls();
 try{
   await nativePost('sync',{expected_revision:current.revision});
   $('cxmNativeEmptyAck').checked=false;
   text('cxmNativeStatus','Dock XY synchronized. Inspect the physical EMPTY carriage, then tick confirmation.');
   lastError='';
 }catch(e){text('cxmNativeStatus','SYNC BLOCKED: '+e.message);}
 finally{requestBusy=false;await refresh();}
}
async function confirmNativeEmpty(){
 if(requestBusy||current?.running||!$('cxmNativeEmptyAck').checked)return;
 requestBusy=true;chooseControls();
 try{
   await nativePost('confirm-empty',{acknowledgement:'I_PHYSICALLY_INSPECTED_EMPTY_CARRIAGE'});
   $('cxmNativeEmptyAck').checked=false;
   text('cxmNativeStatus','Klipper confirmed EMPTY. Native controller ready for supervised movement.');
   lastError='';
 }catch(e){text('cxmNativeStatus','CONFIRM BLOCKED: '+e.message);}
 finally{requestBusy=false;await refresh();}
}
async function recoverNativeEmpty(){
 if(requestBusy||!$('cxmNativeEmptyAck').checked||current?.sensor!=='RELEASED')return;
 requestBusy=true;chooseControls();
 try{
   await nativePost('recover-empty',{acknowledgement:'I_INSPECTED_ALL_DOCKS_AND_CONFIRMED_PHYSICALLY_EMPTY'});
   $('cxmNativeEmptyAck').checked=false;
   text('cxmNativeStatus','Inspected EMPTY recovery complete. Recheck all dock seating and live status.');
   lastError='';
 }catch(e){text('cxmNativeStatus','RECOVERY BLOCKED: '+e.message);}
 finally{requestBusy=false;await refresh();}
}
async function setCarriageState(){
 if(requestBusy||!current||current.running)return;
 const value=$('cxmCarriageIdentity').value;
 if(value===''||!(/^-?(?:0|[1-9][0-9]*)$/.test(value))){
   lastError='Select EMPTY or the actual fitted tool number first.';
   text('cxmMultiStatus',lastError);return;
 }
 const tool=Number(value);
 if(!Number.isInteger(tool)||tool<-1||tool>=current.candidates.length){
   lastError='Invalid fitted tool number';text('cxmMultiStatus',lastError);return;
 }
 requestBusy=true;chooseControls();
 $('cxmDeclareCarriage').disabled=true;
 text('cxmNativeStatus','Checking declared carriage and preparing Z clearance automatically…');
 try{
   const result=await nativePost('initialize',{expected_revision:current.revision,carriage_tool:tool});
   if(!result.ready)throw Error('Klipper did not verify carriage state');
   lastError='';
 }catch(e){
   lastError='CARRIAGE NOT READY: '+e.message;
 }finally{
   requestBusy=false;
   $('cxmDeclareCarriage').disabled=false;
   await refresh();
   if(lastError)text('cxmMultiStatus',lastError);
 }
}
$('cxmDeclareCarriage').addEventListener('click',setCarriageState);
$('cxmSpeedSimple').addEventListener('change',()=>{
 $('cxmMultiAck').checked=false;
 $('cxmCustomSpeedFields').hidden=selectedProfile()!=='custom';
 if(['sprint','race','boost','custom'].includes(selectedProfile())){
   $('cxmMultiRepeats').value='1';
 }
 chooseControls();
});
for(const id of ['cxmCustomTravel','cxmCustomApproach','cxmCustomLatch']){
 $(id).addEventListener('input',chooseControls);
}
$('cxmCustomSpeedFields').hidden=selectedProfile()!=='custom';
$('cxmNativeRecover').addEventListener('click',recoverNativeEmpty);
$('cxmNativeEmptyAck').addEventListener('change',chooseControls);
$('cxmNativeSync').addEventListener('click',synchronizeNative);
$('cxmNativeConfirm').addEventListener('click',confirmNativeEmpty);
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
 for(const id of ['cxmMultiFastTransfer','cxmMultiPerformance','cxmMultiSprint','cxmMultiRace','cxmMultiBoost']){
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
$('cxmMultiBoost').addEventListener('change',()=>{
 if($('cxmMultiBoost').checked)clearOtherSpeedModes('cxmMultiBoost');
 $('cxmMultiAck').checked=false;chooseControls();
 if(!current?.running)text('cxmMultiStatus',$('cxmMultiBoost').checked
   ?'STAGE 3 BOOST selected: 600 clear / 120 guided / 40 latch mm/s REQUESTED. High-load trial only after Race passed; one supervised T0/T1 pass.'
   :'Boost disabled · choose a physically tested lower-speed profile.');
});
$('cxmMultiRapid').addEventListener('change',()=>{
 if($('cxmMultiRapid').checked)$('cxmMultiStream').checked=false;
 $('cxmMultiAck').checked=false;
 chooseControls();
 if(!current?.running)text('cxmMultiStatus',$('cxmMultiRapid').checked
   ?'RAPID KLIPPER selected · requires installed CXM_FAST_VERIFY macro and Klipper restart; approve only after inspection.'
   :'ORIGINAL MECHANICAL TEST selected · proven commissioning sequence.');
});
$('cxmMultiStream').addEventListener('change',()=>{
 if($('cxmMultiStream').checked){
  $('cxmMultiRapid').checked=false;
  // Stream is a one-cycle supervised physical test, never repetitions.
  $('cxmMultiRepeats').value='1';
 }
 $('cxmMultiAck').checked=false;chooseControls();
 if(!current?.running)text('cxmMultiStatus',$('cxmMultiStream').checked
   ?'UNINTERRUPTED STREAM: 2–3 tools, one continuous native Klipper script. No Stop-after-pair; PHYSICAL EMERGENCY STOP ONLY. Inspect every dock and approve.'
   :'Original Stop-after-current-tool behaviour available in Rapid or Standard.');
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