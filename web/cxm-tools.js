/* CXM selected-hotend commissioning (T1–T11): never reuse T0 coordinates. */
(()=>{
'use strict';
const get=id=>document.getElementById(id);
const root=get('cxmToolAuto');
if(!root)return;
const base='/cxm/api/v1';
let live=null,busy=false,checking=false,lastSignal=null,lastSelected=null,requestId=0;
const selected=()=>Number(get('cxmDockTool')?.value);
const active=()=>Number.isInteger(selected())&&selected()>=1&&selected()<=11;
const say=(id,v)=>{get(id).textContent=v;};
function buttons(){
 const n=selected(),show=active();
 root.hidden=!show;
 const auto=live?.automatic;
 const canApprove=show&&!busy&&!checking&&live?.tool===n&&live?.ready===true&&
   auto?.enabled===true;
 const approval=get('cxmToolMotionAck');
 approval.disabled=!canApprove;
 if(!canApprove)approval.checked=false;
 const ready=canApprove&&approval.checked===true;
 const canConfirmMounted=show&&!busy&&!checking&&live?.tool===n&&
   auto?.can_confirm_mounted===true;
 get('cxmToolMountedRecovery').hidden=!canConfirmMounted;
 get('cxmToolConfirmMounted').disabled=!canConfirmMounted;
 get('cxmToolPickup').disabled=!ready||auto?.signal!=='RELEASED';
 get('cxmToolDropoff').disabled=!ready||auto?.signal!=='PRESSED'||auto?.mounted_tool!==n;
 get('cxmToolFaultBox').hidden=!show||!auto?.fault;
 get('cxmToolClearFault').disabled=busy||checking||!auto?.fault||auto?.signal!=='RELEASED';
 root.setAttribute('aria-busy',busy?'true':'false');
 if(show){
   say('cxmToolAutoTitle','T'+n+' · Pickup / Dropoff');
   say('cxmToolMotionLabel','Approve T'+n+' movement');
   say('cxmToolPickup','Pick up T'+n);
   say('cxmToolDropoff','Drop off T'+n);
 }
}
async function read(url){
 const r=await fetch(url,{credentials:'same-origin',cache:'no-store'});
 if(r.status===502||r.status===504)throw Error('Gateway '+r.status+' · movement result UNKNOWN. Inspect printer before repeating.');
 let d;try{d=await r.json();}catch{throw Error('Invalid CXM API response. Inspect printer before repeating.');}
 if(!r.ok)throw Error(d.error||'HTTP '+r.status);
 return d;
}
async function post(path,body){
 const r=await fetch(base+'/tools/'+path,{
   method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-Requested-With':'CXM'},
   body:JSON.stringify(body)});
 if(r.status===502||r.status===504)throw Error('Gateway '+r.status+' · command outcome UNKNOWN. Inspect before repeating.');
 let d;try{d=await r.json();}catch{throw Error('Invalid command response. Outcome UNKNOWN; inspect printer.');}
 if(!r.ok)throw Error(d.error||'HTTP '+r.status);
 return d;
}
async function refresh(){
 if(busy)return;
 const n=selected(),token=++requestId;
 if(n!==lastSelected){
   live=null;lastSignal=null;get('cxmToolMotionAck').checked=false;
   lastSelected=n;
 }
 buttons();
 if(!active())return;
 checking=true;
 // Keep the last useful readiness message visible during background polling.
 // Only show a loading message for a newly selected hotend.
 if(!live||live.tool!==n)
   say('cxmToolAutoStatus','Checking live T'+n+' readiness…');
 try{
   const result=await read(base+'/tools/status?tool='+n);
   if(selected()!==n||token!==requestId)return;
   if(result.tool!==n)throw Error('Backend reported the wrong hotend');
   if(lastSignal!==null && result.automatic?.signal!==lastSignal)
     get('cxmToolMotionAck').checked=false;
   live=result;
   lastSignal=result.automatic?.signal;
   if(result.ready!==true||result.automatic?.enabled!==true)
     get('cxmToolMotionAck').checked=false;
   const a=result.automatic||{};
   say('cxmToolAutoStatus',a.can_confirm_mounted===true
     ?'T'+n+' PRESENT · Tool identity not yet confirmed. Physically verify T'+n+' is mounted before first dropoff.'
     :!result.ready||!a.enabled
       ?'T'+n+' BLOCKED · '+(a.reason||result.blockers?.join('; ')||'Check carriage and printer.')
       :a.signal==='PRESSED'
         ?a.identity_source==='operator_confirmed'
           ?'T'+n+' mounted · identity confirmed by operator, not pickup test. Dropoff requires approval.'
           :'T'+n+' pickup verified by switch · Dropoff available after approval'
         :'Carriage EMPTY · T'+n+' pickup available after approval');
   say('cxmToolGeometry','T'+n+' CxChanger dock X'+(result.saved_xy_mm?.x?.toFixed(3)??'—')+
     ' Y'+(result.saved_xy_mm?.y?.toFixed(3)??'—')+' · Selected-tool geometry');
 }catch(e){
   if(selected()===n&&token===requestId){live=null;get('cxmToolMotionAck').checked=false;say('cxmToolAutoStatus','T'+n+' unavailable · '+e.message);}
 }finally{if(token===requestId){checking=false;buttons();}}
}
async function command(kind){
 const n=selected(),a=live?.automatic;
 if(!active()||busy||checking||live?.tool!==n||live?.ready!==true||
    !a?.enabled||!get('cxmToolMotionAck').checked)return;
 if(kind==='pickup' && a.signal!=='RELEASED')return;
 if(kind==='dropoff' && (a.signal!=='PRESSED'||a.mounted_tool!==n))return;
 get('cxmToolMotionAck').checked=false;
 busy=true;buttons();
 say('cxmToolAutoResult','T'+n+' '+kind+' started · supervise hotend and dock.');
 try{
   const config=await read(base+'/config');
   // Selection cannot change what tool this request targets.
   if(selected()!==n)throw Error('Tool selection changed during preflight; movement cancelled');
   const outcome=await post('auto',{tool:n,kind,expected_revision:config.revision,
     acknowledgement:'I_CONFIRMED_SELECTED_TOOL_XY_PATH_CLEAR_AND_WILL_SUPERVISE'});
   if(outcome.tool!==n || outcome.status!=='T'+n+'_'+kind.toUpperCase()+'_SENSOR_CONFIRMED')
     throw Error('Backend did not verify the selected tool');
   say('cxmToolAutoResult','T'+n+' '+kind+' · switch '+outcome.signal+
     ' confirmed. Inspect hotend seating before another movement.');
 }catch(e){
   say('cxmToolAutoResult','T'+n+' TEST BLOCKED / FAILED · '+e.message+
     ' · Inspect real carriage, tool and dock before retrying.');
 }finally{
   busy=false;await refresh();
 }
}
async function confirmMounted(){
 const n=selected(),auto=live?.automatic;
 if(!active()||busy||checking||live?.tool!==n||auto?.can_confirm_mounted!==true)return;
 const question='CONFIRM HOTEND T'+n+' ALREADY MOUNTED?\\n\\n'+
   'I have physically identified hotend T'+n+' on the carriage (NOT a different tool).\\n'+
   'T'+n+' dock is EMPTY, its locking mechanism is clear, and the full dropoff XY path is clear.\\n'+
   'Klipper XYZ are genuinely homed, XY has NOT been moved by hand since homing, and real Z clearance is safe.\\n\\n'+
   'This confirmation issues NO movement. A separate checkbox approval is required before Dropoff.';
 if(!window.confirm(question))return;
 get('cxmToolMotionAck').checked=false;
 busy=true;buttons();
 say('cxmToolAutoResult','Recording inspected T'+n+' mounted identity · no movement…');
 try{
   const cfg=await read(base+'/config');
   if(selected()!==n)throw Error('Selection changed; confirmation cancelled');
   const r=await post('confirm-mounted',{tool:n,expected_revision:cfg.revision,
     acknowledgement:'I_IDENTIFIED_SELECTED_HOTEND_MOUNTED_EMPTY_DOCK_HOMED_XY_NOT_HAND_MOVED'});
   if(r.tool!==n||r.status!=='T'+n+'_MOUNTED_OPERATOR_CONFIRMED_NO_MOVEMENT')
     throw Error('Backend could not confirm selected tool without movement');
   say('cxmToolAutoResult','T'+n+' operator-confirmed on carriage. NO MOTION. Review actual clearance, then approve Dropoff T'+n+'.');
 }catch(e){
   say('cxmToolAutoResult','T'+n+' mounted confirmation blocked · '+e.message);
 }finally{
   busy=false;await refresh();
 }
}
async function clearFault(){
 const n=selected();
 if(!active()||busy||checking||live?.tool!==n||!live.automatic?.fault||
    live.automatic?.signal!=='RELEASED')return;
 if(!window.confirm('Confirm T'+n+' and its dock have been physically inspected, the carriage is EMPTY and the switch is RELEASED. Clearing does not move the printer.'))return;
 busy=true;buttons();
 try{
   const cfg=await read(base+'/config');
   if(selected()!==n)throw Error('Tool selection changed; no action taken');
   await post('clear-fault',{tool:n,expected_revision:cfg.revision,
     acknowledgement:'I_INSPECTED_SELECTED_TOOL_AND_CONFIRMED_EMPTY_CARRIAGE'});
   say('cxmToolAutoResult','T'+n+' fault cleared · no motion.');
 }catch(e){say('cxmToolAutoResult','T'+n+' fault not cleared: '+e.message);}
 finally{busy=false;await refresh();}
}
get('cxmToolPickup').addEventListener('click',()=>command('pickup'));
get('cxmToolDropoff').addEventListener('click',()=>command('dropoff'));
get('cxmToolMotionAck').addEventListener('change',buttons);
get('cxmToolClearFault').addEventListener('click',clearFault);
get('cxmToolConfirmMounted').addEventListener('click',confirmMounted);
get('cxmDockTool')?.addEventListener('change',()=>{get('cxmToolMotionAck').checked=false;lastSelected=null;refresh();});
document.querySelector('[data-tab="calibration"]')?.addEventListener('click',refresh);
window.addEventListener('cxm-dock-saved',refresh);
window.addEventListener('cxm-config-migrated',refresh);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
setInterval(()=>{if(!document.hidden&&active()&&!busy)refresh();},3500);
buttons();refresh();
})();