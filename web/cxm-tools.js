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
 const sameTool=live?.tool===n;
 const auto=sameTool?live?.automatic:null;
 // Routine read-only polling is NOT a reason to revoke a physical approval.
 const canApprove=show&&!busy&&sameTool&&live.ready===true&&
   auto?.enabled===true;
 get('cxmToolMotionAck').disabled=!canApprove;
 if(!canApprove)get('cxmToolMotionAck').checked=false;
 const ready=canApprove&&get('cxmToolMotionAck').checked===true;
 get('cxmToolPickup').disabled=!ready||auto?.signal!=='RELEASED';
 get('cxmToolDropoff').disabled=!ready||auto?.signal!=='PRESSED'||
   !(auto?.mounted_tool===null||auto?.mounted_tool===n);
 const fault=auto?.fault;
 const canRecoverMounted=typeof fault==='string'&&
   fault.startsWith('T'+n+' pickup result uncertain:')&&auto?.signal==='PRESSED';
 const canRecoverEmpty=typeof fault==='string'&&auto?.signal==='RELEASED';
 get('cxmToolFaultBox').hidden=!show||!sameTool||!fault;
 get('cxmToolClearFault').disabled=busy||!sameTool||
   !(canRecoverMounted||canRecoverEmpty);
 if(show&&sameTool&&fault){
   say('cxmToolFaultHelp',canRecoverMounted
     ?'T'+n+' pickup verification failed but the carriage now reads FILAMENT PRESENT. Visually confirm T'+n+' is firmly mounted and its dock is empty. Clearing this specific pickup fault issues NO motion.'
     :canRecoverEmpty
       ?'The carriage reads FILAMENT ABSENT. Verify it is physically empty and inspect T'+n+' and its dock before clearing. NO movement.'
       :'Fault locked. The carriage is PRESENT and this is not a recoverable pickup fault; inspect the actual mounted tool and dock.');
   say('cxmToolClearFault',canRecoverMounted
     ?'Confirm T'+n+' mounted & clear pickup fault'
     :'Clear fault after inspection');
 }
 root.setAttribute('aria-busy',busy?'true':'false');
 if(show){
   say('cxmToolAutoTitle','T'+n+' · Pickup / Dropoff');
   say('cxmToolMotionLabel','Approve T'+n+' movement');
   say('cxmToolApprovalDetail',auto?.signal==='PRESSED'
     ?'I physically confirm T'+n+' is the mounted hotend, its dock is EMPTY, and the full dropoff XY path is clear.'
     :'I confirm the carriage is EMPTY, T'+n+' is in its dock, and the full pickup XY path is clear.');
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
 const n=selected();
 if(busy || (checking && n===lastSelected))return;
 const token=++requestId;
 if(n!==lastSelected){
   live=null;lastSignal=null;get('cxmToolMotionAck').checked=false;
   lastSelected=n;
 }
 buttons();
 if(!active())return;
 checking=true;
 // Preserve a meaningful blocked/ready status during background polling.
 // "Checking..." is shown only on first load or a changed tool selection.
 if(!live||live.tool!==n)say('cxmToolAutoStatus','Checking live T'+n+' readiness…');
 try{
   const result=await read(base+'/tools/status?tool='+n);
   if(selected()!==n||token!==requestId)return;
   if(result.tool!==n)throw Error('Backend reported the wrong hotend');
   // Revoke the acknowledgement only on a meaningful change, not a poll.
   const next=result.automatic||{};
   const previous=live?.tool===n ? live.automatic : null;
   if((lastSignal!==null && next.signal!==lastSignal) ||
      (previous && (next.mounted_tool!==previous.mounted_tool ||
                    next.identity_source!==previous.identity_source)))
     get('cxmToolMotionAck').checked=false;
   live=result;
   lastSignal=result.automatic?.signal;
   if(result.ready!==true||result.automatic?.enabled!==true)
     get('cxmToolMotionAck').checked=false;
   const a=result.automatic||{};
   say('cxmToolAutoStatus',!result.ready||!a.enabled
     ?'T'+n+' BLOCKED · '+(a.reason||result.blockers?.join('; ')||'Check carriage and printer.')
     :a.signal==='PRESSED'
       ?a.identity_source==='verified_pickup'
         ?'T'+n+' SELECTED · FILAMENT PRESENT (prior pickup confirmed). Approve dropoff.'
         :'T'+n+' SELECTED · FILAMENT PRESENT. Confirm it is physically T'+n+', then approve dropoff.'
       :'T'+n+' SELECTED · FILAMENT ABSENT. Approve pickup after checking T'+n+' is in its dock.');
   say('cxmToolGeometry','T'+n+' CxChanger dock X'+(result.saved_xy_mm?.x?.toFixed(3)??'—')+
     ' Y'+(result.saved_xy_mm?.y?.toFixed(3)??'—')+' · Selected-tool geometry');
 }catch(e){
   if(selected()===n&&token===requestId){live=null;get('cxmToolMotionAck').checked=false;say('cxmToolAutoStatus','T'+n+' unavailable · '+e.message);}
 }finally{if(token===requestId){checking=false;buttons();}}
}
async function command(kind){
 const n=selected(),a=live?.automatic;
 if(!active()||busy||live?.tool!==n||live?.ready!==true||
    !a?.enabled||!get('cxmToolMotionAck').checked)return;
 if(kind==='pickup' && a.signal!=='RELEASED')return;
 if(kind==='dropoff' && (a.signal!=='PRESSED'||
    !(a.mounted_tool===null||a.mounted_tool===n)))return;
 get('cxmToolMotionAck').checked=false;
 // Invalidate a concurrent background GET. Only the post-command refresh
 // may update the UI after motion has been requested.
 requestId++;
 checking=false;
 busy=true;buttons();
 say('cxmToolAutoResult','T'+n+' '+kind+' started · supervise hotend and dock.');
 try{
   const config=await read(base+'/config');
   // Selection cannot change what tool this request targets.
   if(selected()!==n)throw Error('Tool selection changed during preflight; movement cancelled');
   const outcome=await post('auto',{tool:n,kind,expected_revision:config.revision,
     acknowledgement:'I_CONFIRMED_SELECTED_HOTEND_IDENTITY_AND_FULL_XY_PATH_CLEAR'});
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
async function clearFault(){
 const n=selected();
 if(!active()||busy||live?.tool!==n||!live.automatic?.fault)return;
 const auto=live.automatic;
 const mounted=auto.signal==='PRESSED'&&
   auto.fault.startsWith('T'+n+' pickup result uncertain:');
 const empty=auto.signal==='RELEASED';
 if(!mounted&&!empty)return;
 const question=mounted
   ?'CONFIRM T'+n+' IS PHYSICALLY MOUNTED?\\n\\nInspect the coupling, T'+n+' locking mechanism and empty T'+n+' dock. The carriage switch now reports FILAMENT PRESENT. Confirm it is truly T'+n+' and secure.\\n\\nClear this failed-pickup fault WITHOUT MOVEMENT?'
   :'CONFIRM T'+n+' CARRIAGE IS PHYSICALLY EMPTY?\\n\\nInspect tool, dock and switch. FILAMENT ABSENT must match the actual empty carriage.\\n\\nClear fault WITHOUT MOVEMENT?';
 if(!window.confirm(question))return;
 requestId++;
 checking=false;
 busy=true;buttons();
 try{
   const cfg=await read(base+'/config');
   if(selected()!==n)throw Error('Tool selection changed; no action taken');
   await post('clear-fault',{tool:n,expected_revision:cfg.revision,
     acknowledgement:mounted
       ?'I_INSPECTED_SELECTED_TOOL_MOUNTED_AND_DOCK_EMPTY'
       :'I_INSPECTED_SELECTED_TOOL_AND_CONFIRMED_EMPTY_CARRIAGE'});
   say('cxmToolAutoResult','T'+n+' fault cleared · '+(mounted?'mounted T'+n+' inspected':'empty carriage inspected')+' · NO MOTION. Approve any subsequent operation separately.');
 }catch(e){say('cxmToolAutoResult','T'+n+' fault not cleared: '+e.message);}
 finally{busy=false;await refresh();}
}
get('cxmToolPickup').addEventListener('click',()=>command('pickup'));
get('cxmToolDropoff').addEventListener('click',()=>command('dropoff'));
get('cxmToolMotionAck').addEventListener('change',buttons);
get('cxmToolClearFault').addEventListener('click',clearFault);
get('cxmDockTool')?.addEventListener('change',()=>{get('cxmToolMotionAck').checked=false;lastSelected=null;refresh();});
document.querySelector('[data-tab="calibration"]')?.addEventListener('click',refresh);
window.addEventListener('cxm-dock-saved',refresh);
window.addEventListener('cxm-config-migrated',refresh);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
setInterval(()=>{if(!document.hidden&&active()&&!busy)refresh();},3500);
buttons();refresh();
})();