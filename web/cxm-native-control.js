/* CXM native Klipper tool-control panel: macro commands only, no G-code motion. */
(()=>{
'use strict';
const $=id=>document.getElementById(id);
if(!$('cxmNativeToolPanel'))return;
const api='/cxm/api/v1/';
let state=null,busy=false,previousSensor=null,previousTool=null;
const text=(id,value)=>{$(id).textContent=value;};
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
function controls(){
 const target=Number($('cxmNativeSelectedTool').value);
 const approved=true;
 const eligible=state?.candidates?.some(t=>t.tool===target&&t.eligible);
 const ready=state?.native_ready===true&&state?.fault===0&&!state?.running;
 const current=state?.current_tool;
 const canPickup=ready&&eligible&&$('cxmNativeSelectedTool').value!==''&&Number.isInteger(target)&&current>=-1&&current!==target;
 const canUnload=ready&&Number.isInteger(current)&&current>=0;
 const canCalibrationRelease=canUnload&&state?.sensor==='PRESSED'&&
   state?.candidates?.some(t=>t.tool===current&&t.eligible);
 $('cxmNativeSelect').disabled=busy||!canPickup;
 $('cxmNativeUnload').disabled=busy||!canUnload;
 $('cxmCalibrationReleaseAck').disabled=busy||!canCalibrationRelease;
 $('cxmCalibrationRelease').disabled=busy||!canCalibrationRelease||!$('cxmCalibrationReleaseAck').checked;
 if(state) $('cxmCalibrationRelease').textContent=current>=0?'Release mounted T'+current+' from dock':'Release mounted hotend from dock';
 $('cxmNativeSelectedTool').disabled=busy||state?.running===true;
 $('cxmNativeToolAck').disabled=busy||!ready||(!canPickup&&!canUnload);
 text('cxmNativeSelect',current>=0&&current!==target?'Change to T'+target:'Pick up T'+(Number.isInteger(target)?target:'—'));
 if(!state)return;
 const label=current===-2?'UNKNOWN — inspect and confirm EMPTY':
   current===-1?'EMPTY':current>=0?'T'+current+' mounted':'UNKNOWN';
 text('cxmNativeToolStatus',
   (ready?'NATIVE READY':'NATIVE LOCKED')+' · carriage '+label+
   ' · sensor '+String(state.sensor||'unknown')+
   (state.running?' · cycle active':'')+
   (state.fault?' · FAULT / unknown motion outcome':'')+
   '. Tool identity is tracked in Klipper, not inferred from the sensor.');
}
async function refresh(){
 if(busy)return;
 try{
   const next=await read();
   if(previousSensor!==null&&(next.sensor!==previousSensor||next.current_tool!==previousTool))
     $('cxmNativeToolAck').checked=false;
     $('cxmCalibrationReleaseAck').checked=false;
   previousSensor=next.sensor;previousTool=next.current_tool;
   state=next;
   const select=$('cxmNativeSelectedTool');
   const old=select.value;
   select.replaceChildren();
   const blank=document.createElement('option');blank.value='';blank.textContent='Choose tool';
   select.append(blank);
   for(const t of next.candidates||[]){
     const option=document.createElement('option');
     option.value=String(t.tool);option.textContent='T'+t.tool+(t.eligible?'':' · not accepted');
     option.disabled=!t.eligible;
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
async function selectTool(tool){
 if(busy||!state)return;
 const revision=state.revision;
 busy=true;$('cxmNativeToolAck').checked=false;controls();
 text('cxmNativeToolStatus','Submitting CXM_SELECT_TOOL TOOL='+tool+' · supervise the physical machine.');
 try{
   await post('select',{
     tool,expected_revision:revision,
     acknowledgement:'I_CONFIRMED_SELECTED_HOTEND_IDENTITY_AND_FULL_XY_PATH_CLEAR'
   });
   text('cxmNativeToolStatus','Macro completed. Check physical seating before the next command.');
 }catch(e){
   text('cxmNativeToolStatus','TOOLCHANGE NOT CONFIRMED: '+e.message+
     '. Inspect the carriage and docks. Do not automatically repeat.');
 }finally{
   busy=false;
   await refresh();
 }
}
async function calibrationRelease(){
 if(busy||!state||!$('cxmCalibrationReleaseAck').checked)return;
 const tool=state.current_tool,revision=state.revision;
 if(!Number.isInteger(tool)||tool<0||state.sensor!=='PRESSED'||state.native_ready!==true||state.fault!==0)return;
 if(!window.confirm('RELEASE T'+tool+' FROM ENGAGED DOCK?\\n\\nThis MOVES the carriage along X/Y release waypoints. Confirm T'+tool+' is attached to BOTH carriage and dock, and you can physically stop the printer.'))return;
 busy=true;controls();
 text('cxmCalibrationReleaseStatus','Executing supervised dock-engaged release. WATCH THE PRINTER; do not retry automatically.');
 try{
   const result=await post('calibration-release',{
     tool,expected_revision:revision,
     acknowledgement:'I_VERIFIED_MOUNTED_TOOL_ENGAGED_IN_CORRECT_DOCK_AND_APPROVE_RELEASE'
   });
   text('cxmCalibrationReleaseStatus','Command returned: '+result.result+'. Inspect T'+tool+' seated in dock and carriage EMPTY (RELEASED).');
 }catch(e){
   text('cxmCalibrationReleaseStatus','RELEASE NOT VERIFIED: '+e.message+
     '. Stop; inspect carriage, dock, sensor and native state. Do not repeat blindly.');
 }finally{
   $('cxmCalibrationReleaseAck').checked=false;
   busy=false;
   await refresh();
 }
}
$('cxmCalibrationReleaseAck').addEventListener('change',controls);
$('cxmCalibrationRelease').addEventListener('click',calibrationRelease);
$('cxmNativeToolAck').addEventListener('change',controls);
$('cxmNativeSelectedTool').addEventListener('change',()=>{
 $('cxmNativeToolAck').checked=false;controls();
});
$('cxmNativeSelect').addEventListener('click',()=>{
 const t=Number($('cxmNativeSelectedTool').value);
 if($('cxmNativeSelectedTool').value!==''&&Number.isInteger(t))selectTool(t);
});
$('cxmNativeUnload').addEventListener('click',()=>selectTool(-1));
document.querySelector('[data-tab="tools"]')?.addEventListener('click',refresh);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
setInterval(()=>{if(!document.hidden)refresh();},2000);
refresh();
})();