/* CXM motor-on dock alignment. Backend is sole motor/geometry authority. */
(()=>{
'use strict';
const el=id=>document.getElementById(id);
const root=el('cxmManualDock');
if(!root)return;
const api='/cxm/api/v1';
let busy=false,live=null,config=null,tool=-1;
let refreshVersion=0, polling=false;
function selected(){const value=el('cxmDockTool').value;return value===''?-1:Number(value);}
function say(message,bad=false){const n=el('cxmManualFeedback');n.textContent=message;n.style.color=bad?'#f4aaaa':'#bed9ec';}
async function request(path,body){
  const opts={credentials:'same-origin',cache:'no-store'};
  if(body){opts.method='POST';opts.headers={'Content-Type':'application/json','X-Requested-With':'CXM'};
    opts.body=JSON.stringify(body);}
  const response=await fetch(api+path,opts);
  const json=await response.json().catch(()=>({error:'Invalid JSON or gateway error'}));
  if(!response.ok)throw Error(json.error||'HTTP '+response.status);
  return json;
}
function controls(){
  const allowed=!busy&&live?.ready&&tool===selected()&&config?.revision===live?.revision;
  for(const button of root.querySelectorAll('[data-manual-axis]'))button.disabled=!allowed||!el('cxmManualApproval').checked;
  el('cxmManualCapture').disabled=!allowed;
  el('cxmManualRefresh').disabled=busy;
}
async function refresh(silent=false){
  if(busy||(silent&&polling))return;
  const version=++refreshVersion;
  const selectedTool=selected();
  polling=true;
  const previous=live,oldTool=tool,oldRevision=config?.revision;
  try{
    const latestConfig=await request('/config');
    if(version!==refreshVersion||selectedTool!==selected())return;
    const latest=await request('/manual/status?tool='+selectedTool);
    if(version!==refreshVersion||selectedTool!==selected())return;
    // An identity/config change revokes the previous operator approval.
    if((oldTool>=0&&selectedTool!==oldTool) ||
       (oldRevision&&oldRevision!==latestConfig.revision) ||
       (previous&&previous.native_tool_identity!==latest.native_tool_identity)) {
      el('cxmManualApproval').checked=false;
      el('cxmManualCaptureAck').checked=false;
    }
    config=latestConfig;tool=selectedTool;live=latest;
    el('cxmManualX').textContent=live.xy.x.toFixed(3)+' mm';
    el('cxmManualY').textContent=live.xy.y.toFixed(3)+' mm';
    el('cxmManualZ').textContent=live.z.toFixed(2)+' mm';
    el('cxmManualSensor').textContent=live.sensor;
    el('cxmManualReadiness').textContent='READY · T'+tool+' selected by operator · XYZ homed · motors on · hotend MOUNTED';
    if(!silent) say('READY: sensor confirms MOUNTED, not tool identity. Verify the mounted hotend is physically T'+tool+' before approving any jog.');
  }catch(e){
    if(version!==refreshVersion||selectedTool!==selected())return;
    live=null;
    el('cxmManualApproval').checked=false;
    el('cxmManualCaptureAck').checked=false;
    el('cxmManualReadiness').textContent='NOT READY · '+e.message;
    say('Jog/capture blocked: '+e.message+'. Inspect and refresh after restoring safe state.',true);
  }finally{if(version===refreshVersion){polling=false;controls();}}
}
async function jog(button){
  if(busy||!live?.ready||tool!==selected()||!el('cxmManualApproval').checked)return;
  const axis=button.dataset.manualAxis;
  const distance=Number(button.dataset.distance);
  ++refreshVersion;polling=false;busy=true;controls();
  say('Jogging '+axis.toUpperCase()+' '+distance+' mm …');
  try{
    const answer=await request('/manual/jog',{
      tool,axis,distance,expected_revision:live.revision,
      acknowledgement:'I_APPROVE_SUPERVISED_MOTOR_ON_JOG'});
    if(answer.jogged!==true)throw Error('Motor jog not verified');
    live.xy=answer.position;
    el('cxmManualX').textContent=live.xy.x.toFixed(3)+' mm';
    el('cxmManualY').textContent=live.xy.y.toFixed(3)+' mm';
    say('Commanded position updated. Inspect physical alignment before saving.');
  }catch(e){
    live=null;
    el('cxmManualApproval').checked=false;
    say('JOG STOPPED/UNCERTAIN: '+e.message+'. Inspect machine and refresh before any further movement.',true);
  }finally{busy=false;controls();}
}
async function capture(){
 if(busy||!live?.ready||tool!==selected())return;
 const target=tool;
 ++refreshVersion;polling=false;busy=true;controls();
 say('Saving T'+tool+' dock X/Y…');
 try{
   const saved=await request('/manual/save',{
     tool:target,expected_revision:live.revision,
     acknowledgement:'I_INSPECTED_DOCK_ALIGNMENT_WITH_MOTORS_ON'});
   if(!saved.saved||!saved.verified||saved.tool!==target)
     throw Error('Dock Save was not verified');
   const check=await request('/config');
   const actual=check.config.tools[target];
   if(!actual||actual.dock_x!==saved.xy.x||actual.dock_y!==saved.xy.y
      ||actual.dock_reference_accepted!==true)
     throw Error('Stored dock differs from captured position');
   config=check;live=null;
   window.dispatchEvent(new CustomEvent('cxm-dock-save-completed',{
     detail:{tool:target,x:actual.dock_x,y:actual.dock_y}}));
   say('SAVED T'+target+' — X'+actual.dock_x.toFixed(5)+
     ' Y'+actual.dock_y.toFixed(5)+' mm · '+(saved.backup?'backup created':'already saved')+
     '. Ready to calibrate another tool.');
 }catch(e){
   say('Save unconfirmed: '+e.message+'. Check the stored T'+target+' coordinates before retrying.',true);
 }finally{busy=false;controls();refresh(true);}
}
root.querySelectorAll('[data-manual-axis]').forEach(b=>b.addEventListener('click',()=>jog(b)));
el('cxmManualRefresh').addEventListener('click',()=>refresh(false));
el('cxmManualCapture').addEventListener('click',capture);
el('cxmManualApproval').addEventListener('change',controls);
el('cxmManualCaptureAck').addEventListener('change',controls);
el('cxmDockTool').addEventListener('change',()=>{
  live=null;tool=-1;
  el('cxmManualApproval').checked=false;el('cxmManualCaptureAck').checked=false;
  controls();refresh();
});
window.addEventListener('cxm-dock-saved',()=>{live=null;refresh();});
window.addEventListener('cxm-config-migrated',()=>{live=null;refresh();});
// Read-only Klipper position/state refresh, not a movement command. Do not poll
// while a jog/capture is in flight; any failed preflight revokes approval.
setInterval(()=>{
  if(!busy && document.visibilityState!=='hidden' &&
     !document.querySelector('[data-panel="calibration"]')?.hidden)
    refresh(true);
},1500);
setTimeout(()=>refresh(false),400);
})();
