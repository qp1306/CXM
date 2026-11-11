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
 if(!state)return;
 const label=state.sensor==='RELEASED'?'EMPTY (sensor confirmed)':
   current===-2?'UNKNOWN — select mounted hotend':
   current===-1?'Identity mismatch — inspect mounted hotend':
   current>=0?'T'+current+' mounted':'UNKNOWN';
 text('cxmNativeToolStatus',
   'Carriage '+label+' · sensor '+String(state.sensor||'unknown')+
   (state.fault?' · native sync required':'')+
   '. LOAD and UNLOAD automatically set up saved geometry.');
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
   const reply=await post('simple-change',{tool,mounted_tool:mounted,
     expected_revision:state.revision});
   if(!offsets.hidden && tool>=0 && reply.current_tool===tool){
     const selector=$('cxmAxisTool');
     selector.value=String(tool);
     if(selector.value===String(tool))selector.dispatchEvent(new Event('change'));
   }
   text('cxmChangeResult',reply.already_empty?'Already empty':
     reply.already_mounted?'Already mounted':'Toolchange completed. Check physical seating.');
 }catch(e){
   text('cxmChangeResult','Toolchange stopped: '+e.message+
     '. Inspect actual carriage position before retrying.');
 }finally{busy=false;panel.inert=false;await refresh();}
}
$('cxmNativeSelectedTool').addEventListener('change',controls);
$('cxmCarriageIdentity').addEventListener('change',controls);
$('cxmNativeSelect').addEventListener('click',()=>{
 const value=$('cxmNativeSelectedTool').value;
 if(value!=='')selectTool(Number(value));
});
$('cxmNativeUnload').addEventListener('click',()=>selectTool(-1));
document.querySelector('[data-tab="tools"]')?.addEventListener('click',refresh);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
setInterval(()=>{if(!document.hidden)refresh();},2000);
refresh();
})();
