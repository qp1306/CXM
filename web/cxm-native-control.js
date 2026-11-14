/* CXM native Klipper tool-control panel: macro commands only, no G-code motion. */
(()=>{
'use strict';
const $=id=>document.getElementById(id);
if(!$('cxmNativeToolPanel'))return;
const panel=$('cxmNativeToolPanel');
const offsets=document.querySelector('[data-panel="offsets"]');
function placeControls(){
 const slot=$(offsets.hidden?'cxmToolsChangeSlot':'cxmAxisChangeSlot');
 if(panel.parentElement!==slot)slot.append(panel);
 $('cxmCameraSession').hidden=offsets.hidden;
}
placeControls();
new MutationObserver(placeControls).observe(offsets,{attributes:true,attributeFilter:['hidden']});
function revokeJogApproval(){
 for(const id of ['cxmManualApproval','cxmManualApprovalXY']){
   const approval=$(id);
   if(approval){approval.checked=false;approval.dispatchEvent(new Event('change'));}
 }
}
panel.addEventListener('click',event=>{
 if(event.target.closest('#cxmDeclareCarriage'))revokeJogApproval();
},true);
const api='/cxm/api/v1/';
let state=null,busy=false,previousSensor=null,previousTool=null;
const text=(id,value)=>{$(id).textContent=value;if(id==='cxmChangeResult')$('cxmCameraResult').textContent=value;};
async function read(){
 const r=await fetch(api+'native/status',{credentials:'same-origin',cache:'no-store'});
 const obj=await r.json();
 if(!r.ok)throw Error(obj.error||'HTTP '+r.status);
 return obj;
}
async function post(action,body){
 const r=await fetch(api+'native/'+action,{
   method:'POST',credentials:'same-origin',cache:'no-store',
   headers:{'Content-Type':'application/json','X-Requested-With':'CXM'},
   body:JSON.stringify(body)
 });
 let obj;try{obj=await r.json();}catch{throw Error('Non-JSON native response; inspect carriage before retrying')}
 if(!r.ok)throw Error(obj.error||'HTTP '+r.status);
 return obj;
}
let progressToken=null;
let savedTools=new Set();
function cameraSteps({ref,ready,valid,current}){
 const token=ref?.[0]||0;
 if(progressToken!==token){
   progressToken=token;
   savedTools=new Set();
   try{
     const progress=JSON.parse(sessionStorage.getItem('cxmCameraProgress'));
     if(progress?.token===token)savedTools=new Set(progress.tools);
   }catch{}
 }
 const locked=busy||panel.inert||$('cxmChangeControls').disabled||!state||state.running;
 $('cxmCameraSession').disabled=!!locked;
 $('cxmCameraActions').disabled=!!locked;
 const row=$('cxmCameraTools');
 const candidates=state?.candidates||[];
 // Only calibrated, eligible docks are actionable; never show unavailable T-n as load buttons.
 const tools=candidates.filter(t=>t.eligible);
 for(const [i,t] of tools.entries()){
   let button=row.children[i];
   if(!button){
     button=document.createElement('button');button.type='button';button.className='btn';
     const name=document.createElement('span');name.className='cxm-camera-tool-name';
     const status=document.createElement('span');status.className='cxm-camera-tool-state';
     button.append(name,status);row.append(button);
   }
   const mounted=current===t.tool&&state.sensor==='PRESSED';
   const status=mounted?'Mounted':savedTools.has(t.tool)?'XY saved':t.tool===0?'Reference':'Load / align';
   button.dataset.tool=String(t.tool);
   button.setAttribute('aria-label','T'+t.tool+' · '+status);
   button.setAttribute('aria-current',String(mounted));
   button.children[0].textContent='T'+t.tool;
   button.children[1].textContent=status;
   button.disabled=!ref||!valid||mounted||(!token&&t.tool!==0)||(!!token&&!ready);
 }
 while(row.children.length>tools.length)row.lastElementChild.remove();
 const unavailable=candidates.length-tools.length;
 text('cxmCameraUnavailable',unavailable?unavailable+' selected hotend(s) hidden: dock not accepted, maintenance lockout or geometry unavailable. Configure and accept each dock before loading.':'');
 const canUnload=ready&&current>=0&&state.sensor==='PRESSED'&&candidates.some(t=>t.tool===current&&t.eligible);
 $('cxmCameraUnload').disabled=!canUnload;
 text('cxmCameraCarriageState',!valid?'Carriage state requires verification':
   current===-1?'Carriage EMPTY':current>=0?'Carriage: T'+current+' mounted':'Carriage identity UNKNOWN');
 const next=tools.find(t=>t.tool>0&&!savedTools.has(t.tool));
 const needsSave=token&&current>0&&!savedTools.has(current);
 text('cxmCameraNext',!ref?'Checking camera reference availability…':!valid?'Confirm the physically fitted hotend above.':
   !token?(current===0?'1 · Centre and focus T0, then press Set T0 camera reference.':'1 · Press T0 to load the reference hotend.'):
   needsSave?'3 · Centre T'+current+' on the crosshair, then select the next hotend to auto-save XY before changing.':
   next?'2 · Press T'+next.tool+' to change tools and return to the crosshair.':
   'Alignment complete for the available hotends. End the camera session when finished.');
 text('cxmCameraCapture',current>0?'Save T'+current+' XY':'Save centred hotend XY');
}
// Clear All is independent of a stopped/stuck native cycle. It NEVER sends
// motion commands; server and Klipper separately verify a physically EMPTY carriage.
const CLEAR_ALL_ACK='I_REMOVED_THE_HOTEND_FROM_THE_CARRIAGE_RETURNED_IT_TO_ITS_DOCK_AND_VERIFIED_EMPTY';
function clearAllControls(){
 const approve=$('cxmClearAllAck'),button=$('cxmClearAllButton'),info=$('cxmClearAllState');
 if(!approve||!button||!info)return;
 const released=state?.sensor==='RELEASED';
 const ready=state?.native_ready===true;
 const healthyTestActive=state?.running===true&&!state?.stop_requested&&state?.fault!==1;
 button.disabled=busy||!approve.checked||!released||!ready||panel.inert||healthyTestActive;
 info.textContent=!state?'Cannot verify live carriage state — Clear All disabled':
   !ready?'Native geometry is not synchronized. Restore saved geometry before recovery':
   healthyTestActive?'An active tool test is running. Press Stop and verify the printer is stationary first':
   !released?'Sensor '+String(state.sensor||'UNKNOWN')+' — remove hotend from carriage and return it to its dock first':
   'Sensor RELEASED · carriage appears EMPTY. Inspect all docks, confirm printer is stationary, then approve Clear All.';
}
function controls(){
 clearAllControls();
 const target=$('cxmNativeSelectedTool').value;
 const current=state?.current_tool;
 const declared=$('cxmCarriageIdentity').value;
 const mounted=state?.sensor==='RELEASED'?-1:
   (Number.isInteger(current)&&current>=0?current:(declared!==''?Number(declared):null));
 const valid=mounted!==null&&(state?.sensor===(mounted===-1?'RELEASED':'PRESSED'));
 const available=Array.isArray(state?.candidates)&&state.candidates.some(t=>t.tool===Number(target)&&t.eligible);
 $('cxmNativeSelect').disabled=busy||!valid||target===''||!available;
 $('cxmNativeUnload').disabled=busy||!valid||mounted===-1;
 $('cxmNativeSelectedTool').disabled=busy;
 $('cxmNativeToolAck').disabled=true;
 $('cxmNativeToolAck').checked=false;
 $('cxmCalibrationReleaseAck').disabled=true;
 $('cxmCalibrationRelease').disabled=true;
 const ref=state?.camera_reference;
 const active=!!ref?.[0];
 const ready=valid && state?.native_ready && !state?.fault && !state?.running && !busy;
 cameraSteps({ref,ready,valid,current});
 $('cxmCameraReference').disabled=!ready||current!==0||!ref;
 $('cxmCameraCapture').disabled=!ready||!active||!(current>0)||Number($('cxmAxisTool').value)!==current;
 $('cxmCameraEnd').disabled=busy||!active;
 text('cxmCameraDatum',active?'T0 reference · '+['X','Y','Z'].map((a,i)=>a+ref[i+1].toFixed(3)).join('  '):
   ref?'Load T0 and centre its nozzle on the crosshair.':'Camera reference unavailable. Check the installed Klipper macro.');
 if(!state)return;
 const label=state.sensor==='RELEASED'?'EMPTY (sensor confirmed)':
   current===-2?'UNKNOWN — select mounted hotend':
   current===-1?'Identity mismatch — inspect mounted hotend':
   current>=0?'T'+current+' mounted':'UNKNOWN';
 text('cxmNativeToolStatus',
   'Carriage '+label+' · sensor '+String(state.sensor||'unknown')+
   (state.fault?' · native sync required':'')+
   (offsets.hidden?'. LOAD and UNLOAD automatically set up saved geometry.':'.'));
}
async function clearAll(){
 if(busy||!state||state.sensor!=='RELEASED'||state.native_ready!==true
    ||!$('cxmClearAllAck')?.checked||panel.inert
    ||(state.running&&!state.stop_requested&&state.fault!==1))return;
 const revision=state.revision;
 busy=true;controls();
 text('cxmClearAllResult','Checking physical EMPTY and clearing CXM toolchange state…');
 try{
   const reply=await post('clear-all',{
     expected_revision:revision,acknowledgement:CLEAR_ALL_ACK});
   if(reply.cleared!==true||reply.current_tool!==-1||reply.sensor!=='RELEASED'
      ||reply.running!==false||reply.fault!==0||reply.state!=='idle'
      ||reply.profile!=='standard'||reply.camera_cleared!==true
      ||reply.test_session_cleared!==true){
     throw Error('Server did not verify a complete EMPTY reset');
   }
   const after=await read();
   if(after.revision!==revision||after.sensor!=='RELEASED'||after.running!==false
      ||after.current_tool!==-1||after.fault!==0||after.native_ready!==true
      ||after.state!=='idle'||after.tools?.length!==0
      ||after.travel_profile!=='standard'
      ||!Array.isArray(after.camera_reference)||after.camera_reference.length!==4
      ||after.camera_reference.some(v=>v!==0)){
     throw Error('Live CXM state changed after reset; inspect before continuing');
   }
   state=after;
   savedTools.clear();progressToken=null;
   try{sessionStorage.removeItem('cxmCameraProgress');}catch{}
   $('cxmCarriageIdentity').value='-1';
   $('cxmNativeSelectedTool').value='';
   text('cxmClearAllResult','CLEAR ALL VERIFIED · Toolchanger EMPTY, test idle, faults cleared. Saved calibration preserved. Existing macro reset acceleration to 4000 mm/s². Continue supervised Dock XY setup.');
   window.dispatchEvent(new Event('cxm-clear-all-complete'));
 }catch(e){
   text('cxmClearAllResult','CLEAR ALL REFUSED / UNVERIFIED: '+e.message+
     '. Do not attempt tool movement until physically inspected.');
 }finally{
   $('cxmClearAllAck').checked=false;
   busy=false;
   await refresh();
 }
}
async function refresh(){
 if(busy)return;
 try{
   const next=await read();
   if(previousSensor!==null&&(next.sensor!==previousSensor||next.current_tool!==previousTool))
     $('cxmNativeToolAck').checked=false;
     $('cxmCalibrationReleaseAck').checked=false;
   if(previousSensor!==null&&next.sensor!==previousSensor)
      $('cxmClearAllAck').checked=false;
    previousSensor=next.sensor;previousTool=next.current_tool;
   state=next;
   const select=$('cxmNativeSelectedTool');
   const old=select.value;
   select.replaceChildren();
   const blank=document.createElement('option');blank.value='';blank.textContent='Choose tool';
   select.append(blank);
   for(const t of next.candidates||[]){
     const option=document.createElement('option');
     option.value=String(t.tool);option.textContent='T'+t.tool+(t.eligible?' · available':t.xy?.x!=null&&t.xy?.y!=null?' · dock saved; review pickup':' · dock not saved');
     option.disabled=!t.eligible;
     option.dataset.savedDock=String(t.xy?.x!=null&&t.xy?.y!=null);
     option.dataset.reason=t.reason||'';
     option.title=t.reason||'';
     select.append(option);
   }
   select.value=old;
   if(select.value!==old)$('cxmNativeToolAck').checked=false;
   controls();
 }catch(e){
   state=null;
   $('cxmNativeToolAck').checked=false;
   $('cxmCalibrationReleaseAck').checked=false;
   controls();
   text('cxmNativeToolStatus','Native tool controls unavailable: '+e.message);
 }
}
// Save the currently mounted hotend before changing it. Never change tools if
// the capture failed or live state changed during the save.
async function autoSaveBeforeCameraChange(tool,mounted){
 if(offsets.hidden || tool===mounted || mounted<1 || !state?.camera_reference?.[0])return;
 const before=state;
 if(before.current_tool!==mounted || before.sensor!=='PRESSED' ||
    !before.native_ready || before.fault || before.running){
   throw Error('Cannot auto-save: mounted hotend state is not verified');
 }
 if(Number($('cxmAxisTool').value)!==mounted){
   throw Error('Cannot auto-save: alignment selection does not match mounted T'+mounted);
 }
 text('cxmChangeResult','Saving T'+mounted+' XY before changing hotends…');
 const reply=await post('camera',{action:'capture',token:before.camera_reference[0],
   tool:mounted,mounted_tool:mounted,expected_revision:before.revision});
 if(reply.saved!==true || !reply.offsets ||
    !Number.isFinite(reply.offsets.x) || !Number.isFinite(reply.offsets.y)){
   throw Error('T'+mounted+' XY save was not confirmed');
 }
 savedTools.add(mounted);
 try{sessionStorage.setItem('cxmCameraProgress',JSON.stringify({
   token:before.camera_reference[0],tools:[...savedTools]}));}catch{}
 window.dispatchEvent(new Event('cxm-camera-offset-saved'));
 // A save may change the config revision. Refresh rather than reuse stale data.
 const after=await read();
 if(after.current_tool!==mounted || after.sensor!=='PRESSED' ||
    !after.native_ready || after.fault || after.running ||
    after.camera_reference?.[0]!==before.camera_reference[0]){
   throw Error('Native state changed after T'+mounted+' save; inspect before moving');
 }
 state=after;
 text('cxmChangeResult','T'+mounted+' XY saved. Changing hotend…');
}
async function selectTool(tool){
 if(busy||!state)return;
 const current=state.current_tool;
 const mounted=state.sensor==='RELEASED'?-1:
   (Number.isInteger(current)&&current>=0?current:
    ($('cxmCarriageIdentity').value===''?null:Number($('cxmCarriageIdentity').value)));
 if(mounted===null){
   text('cxmNativeToolStatus','Choose the currently mounted hotend or EMPTY once, then press LOAD/UNLOAD.');
   return;
 }
 busy=true;panel.inert=true;revokeJogApproval();controls();
 text('cxmChangeResult',(tool===-1?'UNLOAD':'LOAD T'+tool)+' running…');
 try{
   // The current hotend must be captured before its removal. A failed save
   // aborts the change, leaving the mounted hotend available for correction.
   await autoSaveBeforeCameraChange(tool,mounted);
   const useReference=!offsets.hidden && !!state.camera_reference?.[0];
   const reply=useReference ? await post('camera',{action:'change',token:state.camera_reference[0],
     tool,mounted_tool:mounted,expected_revision:state.revision}) : await post('simple-change',{tool,mounted_tool:mounted,
     expected_revision:state.revision});
   if(!offsets.hidden && tool>=0 && reply.current_tool===tool){
     const selector=$('cxmAxisTool');
     selector.value=String(tool);
     if(selector.value===String(tool))selector.dispatchEvent(new Event('change'));
   }
   text('cxmChangeResult',reply.already_empty?'Already empty':
     reply.already_mounted?'Already mounted':useReference&&tool>=0?'T'+tool+' returned to T0 camera XYZ. Fine-jog to centre the nozzle.':'Toolchange completed. Check physical seating.');
 }catch(e){
   text('cxmChangeResult','Save or toolchange stopped: '+e.message+
     '. No further change command was sent after this error; check the actual carriage before retrying.');
 }finally{busy=false;panel.inert=false;await refresh();}
}
async function cameraAction(action){
 if(busy||panel.inert||$('cxmChangeControls').disabled||offsets.hidden||!state)return;
 const mounted=state.current_tool;
 const token=state.camera_reference?.[0];
 if(token===undefined)return;
 busy=true;panel.inert=true;revokeJogApproval();controls();
 try{
   const tool=action==='capture'?Number($('cxmAxisTool').value):mounted;
   const reply=await post('camera',{action,token,tool,mounted_tool:mounted,expected_revision:state.revision});
   if(action==='capture'){
     if(reply.saved!==true)throw Error('Offset save was not confirmed');
     savedTools.add(mounted);
     try{sessionStorage.setItem('cxmCameraProgress',JSON.stringify({token,tools:[...savedTools]}));}catch{}
     text('cxmChangeResult','Saved T'+mounted+' · X '+reply.offsets.x.toFixed(3)+' · Y '+reply.offsets.y.toFixed(3)+' mm relative to T0.');
     window.dispatchEvent(new Event('cxm-camera-offset-saved'));
   }else text('cxmChangeResult',action==='clear'?'Camera session ended.':'T0 reference captured. Press the next hotend above the jog controls.');
 }catch(e){text('cxmChangeResult','Camera action stopped · '+e.message);}
 finally{busy=false;panel.inert=false;await refresh();}
}
new MutationObserver(controls).observe($('cxmChangeControls'),{attributes:true,attributeFilter:['disabled']});
new MutationObserver(controls).observe(panel,{attributes:true,attributeFilter:['inert']});
$('cxmCameraTools').addEventListener('click',e=>{
 const button=e.target.closest('button[data-tool]');
 if(!button||button.disabled||offsets.hidden||panel.inert||$('cxmChangeControls').disabled)return;
 selectTool(Number(button.dataset.tool));
});
$('cxmCameraReference').addEventListener('click',()=>cameraAction('reference'));
$('cxmCameraCapture').addEventListener('click',()=>cameraAction('capture'));
$('cxmCameraEnd').addEventListener('click',()=>cameraAction('clear'));
$('cxmClearAllAck')?.addEventListener('change',clearAllControls);
$('cxmClearAllButton')?.addEventListener('click',clearAll);
$('cxmNativeSelectedTool').addEventListener('change',controls);
$('cxmCarriageIdentity').addEventListener('change',controls);
$('cxmNativeSelect').addEventListener('click',()=>{
 const value=$('cxmNativeSelectedTool').value;
 if(value!=='')selectTool(Number(value));
});
$('cxmNativeUnload').addEventListener('click',()=>selectTool(-1));
$('cxmCameraUnload').addEventListener('click',()=>{
 if(!$('cxmCameraUnload').disabled && !offsets.hidden)selectTool(-1);
});
document.querySelector('[data-tab="tools"]')?.addEventListener('click',refresh);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
setInterval(()=>{if(!document.hidden)refresh();},2000);
refresh();
})();
