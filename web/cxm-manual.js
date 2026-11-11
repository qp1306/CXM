/* CXM motor-on dock alignment. Backend is sole motor/geometry authority. */
(()=>{
'use strict';
const byId=id=>document.getElementById(id);
function bindJogs(root,panel,selector,suffix=''){
if(!root)return;
const el=id=>byId(id+suffix);
const captureButton=el('cxmManualCapture');
const captureAck=el('cxmManualCaptureAck');
const api='/cxm/api/v1';
let busy=false,live=null,revision=null,tool=-1;
let refreshVersion=0, polling=false;
const pending=[];
let jogging=false;
function canJog(){
  return !byId('cxmNativeToolPanel')?.inert && live?.ready && tool===selected() && live.revision===revision &&
    el('cxmManualApproval').checked && !panel?.hidden && !document.hidden;
}
function clearQueue(){
  pending.length=0;
  controls();
}
function selected(){const value=selector.value;return value===''?-1:Number(value);}
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
  const allowed=!busy&&live?.ready&&tool===selected()&&!!live.revision&&revision===live.revision;
  for(const button of root.querySelectorAll('[data-manual-axis]'))button.disabled=!canJog()||(busy&&!jogging);
  el('cxmJogClear').disabled=pending.length===0;
  el('cxmJogQueue').textContent=jogging ? 'Jog in progress · '+pending.length+' queued' : '';
  if(captureButton)captureButton.disabled=!allowed;
  el('cxmManualRefresh').disabled=busy;
}
async function refresh(silent=false){
  if(busy||panel?.hidden||(silent&&polling))return;
  const version=++refreshVersion;
  const selectedTool=selected();
  if(selectedTool<0)return;
  polling=true;
  const previous=live,oldTool=tool,oldRevision=revision;
  try{
    const latest=await request('/manual/status?tool='+selectedTool);
    if(version!==refreshVersion||selectedTool!==selected())return;
    // An identity/config change revokes the previous operator approval.
    if((oldTool>=0&&selectedTool!==oldTool) ||
       (oldRevision&&oldRevision!==latest.revision) ||
       (previous&&previous.native_tool_identity!==latest.native_tool_identity)) {
      el('cxmManualApproval').checked=false;
      if(captureAck)captureAck.checked=false;
    }
    revision=latest.revision;tool=selectedTool;live=latest;
    if (!window.CXMDockPosition?.streaming()) {
      el('cxmManualX').textContent=live.xy.x.toFixed(3)+' mm';
      el('cxmManualY').textContent=live.xy.y.toFixed(3)+' mm';
      el('cxmManualZ').textContent=live.z.toFixed(2)+' mm';
    }
    el('cxmManualSensor').textContent=live.sensor;
    el('cxmManualReadiness').textContent='READY · T'+tool+' selected by operator · XYZ homed · motors on · hotend MOUNTED';
    if(!silent) say('READY: sensor confirms MOUNTED, not tool identity. Verify the mounted hotend is physically T'+tool+' before approving any jog.');
  }catch(e){
    if(version!==refreshVersion||selectedTool!==selected())return;
    live=null;
    el('cxmManualApproval').checked=false;
    if(captureAck)captureAck.checked=false;
    el('cxmManualReadiness').textContent='NOT READY · '+e.message;
    say('Jog/capture blocked: '+e.message+'. Inspect and refresh after restoring safe state.',true);
  }finally{if(version===refreshVersion){polling=false;controls();}}
}
async function jog(button){
  if(!canJog() || (busy&&!jogging))return;
  pending.push({button, tool, revision});
  if(jogging){controls();return;}
  ++refreshVersion;polling=false;busy=true;jogging=true;
  const changeControls=byId('cxmChangeControls');
  if(changeControls)changeControls.disabled=true;
  try{
    while(pending.length && canJog()){
      const step=pending.shift();
      if(step.tool!==selected() || step.revision!==revision)break;
      const axis=step.button.dataset.manualAxis;
      const distance=Number(step.button.dataset.distance);
      controls();
      step.button.classList.add('jog-active');
      const started=performance.now();
      try{
        say('Jogging '+axis.toUpperCase()+' '+distance+' mm …');
        const answer=await request('/manual/jog',{
          tool:step.tool,axis,distance,expected_revision:step.revision,
          acknowledgement:'I_APPROVE_SUPERVISED_MOTOR_ON_JOG'});
        if(answer.jogged!==true || answer.revision!==step.revision)
          throw Error('Jog or saved revision could not be verified');
        if(!live || selected()!==step.tool)break;
        live.xy=answer.position;
        if(Number.isFinite(answer.z))live.z=answer.z;
        if(!window.CXMDockPosition?.streaming()){
          el('cxmManualX').textContent=live.xy.x.toFixed(3)+' mm';
          el('cxmManualY').textContent=live.xy.y.toFixed(3)+' mm';
          el('cxmManualZ').textContent=live.z.toFixed(2)+' mm';
        }
        say(axis.toUpperCase()+' '+distance+' mm confirmed · '+Math.round(performance.now()-started)+' ms.');
      }finally{step.button.classList.remove('jog-active');}
    }
  }catch(e){
    live=null;
    el('cxmManualApproval').checked=false;
    say('Jog unconfirmed. Queue cleared. '+e.message+'. Inspect the carriage before retrying.',true);
  }finally{jogging=false;busy=false;if(changeControls)changeControls.disabled=false;clearQueue();}
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
   revision=check.revision;live=null;
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
captureButton?.addEventListener('click',capture);
el('cxmManualApproval').addEventListener('change',clearQueue);
el('cxmJogClear').addEventListener('click',clearQueue);
function leaveJogPanel(){
  if(document.hidden || panel?.hidden){
    el('cxmManualApproval').checked=false;
    clearQueue();
  }
}
document.addEventListener('visibilitychange',leaveJogPanel);
for(const event of ['pagehide','offline'])window.addEventListener(event,()=>{
  el('cxmManualApproval').checked=false;clearQueue();
});
if(panel)new MutationObserver(()=>{leaveJogPanel();if(!panel.hidden)refresh(true);}).observe(panel,{attributes:true,attributeFilter:['hidden']});
captureAck?.addEventListener('change',controls);
selector.addEventListener('change',()=>{
  pending.length=0;live=null;tool=-1;
  el('cxmManualApproval').checked=false;if(captureAck)captureAck.checked=false;
  controls();refresh();
});
window.addEventListener('cxm-dock-saved',()=>{live=null;refresh();});
window.addEventListener('cxm-config-migrated',()=>{live=null;refresh();});
// Read-only Klipper position/state refresh, not a movement command. Do not poll
// while a jog/capture is in flight; any failed preflight revokes approval.
setInterval(()=>{
  if(!busy && document.visibilityState!=='hidden' &&
     !panel?.hidden)
    refresh(true);
},1500);
setTimeout(()=>refresh(false),400);
}
const dock=byId('cxmManualDock');
bindJogs(dock,document.querySelector('[data-panel="calibration"]'),byId('cxmDockTool'));
const axisJog=document.querySelector('#cxmAxisJog');
if(axisJog){
  byId('cxmAxisJogRows').append(dock.querySelector('.dock-jog-scroll').cloneNode(true));
  bindJogs(axisJog,document.querySelector('[data-panel="offsets"]'),byId('cxmAxisTool'),'XY');
}
})();
