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
let travelBusy=false,retreatAnchor=null,verifiedRoundtrip=null;
const travelRetreat=el('cxmDockRetreat100'),travelReturn=el('cxmDockReturn100'),travelStatus=el('cxmDockTravelStatus');
const travelSay=msg=>{if(travelStatus)travelStatus.textContent=msg;};
const close=(a,b)=>Math.abs(a-b)<=0.08;
function resetTravel(message){retreatAnchor=null;verifiedRoundtrip=null;if(travelStatus)travelSay(message);}
function canJog(){
  return !byId('cxmNativeToolPanel')?.inert && live?.ready && (suffix || live.jog_revision===2) && tool===selected() && live.revision===revision &&
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
  // Dock reference must be saved at the release point BEFORE testing travel.
  // Never allow capture while the carriage is known to be 100 mm away.
  if(captureButton)captureButton.disabled=!allowed||(!suffix&&!!retreatAnchor);
  el('cxmManualRefresh').disabled=busy;
  if(travelRetreat)travelRetreat.disabled=busy||!canJog()||!!retreatAnchor||pending.length>0;
  if(travelReturn)travelReturn.disabled=busy||!canJog()||!retreatAnchor||!live||
    !close(live.xy.x,retreatAnchor.x)||!close(live.xy.y,retreatAnchor.y+100)||
    tool!==retreatAnchor.tool||revision!==retreatAnchor.revision;
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
    if(retreatAnchor && (selectedTool!==retreatAnchor.tool || latest.revision!==retreatAnchor.revision ||
       latest.native_tool_identity!==retreatAnchor.identity || !close(latest.xy.x,retreatAnchor.x) ||
       !close(latest.xy.y,retreatAnchor.y+100)))resetTravel('Release-point reference invalidated. Realign and repeat the 100 mm test.');
    if(verifiedRoundtrip && (selectedTool!==verifiedRoundtrip.tool || latest.revision!==verifiedRoundtrip.revision ||
      latest.native_tool_identity!==verifiedRoundtrip.identity ||
      !close(latest.xy.x,verifiedRoundtrip.x)||!close(latest.xy.y,verifiedRoundtrip.y)))
      resetTravel('Dock moved after travel test. Repeat verification if needed.');
    revision=latest.revision;tool=selectedTool;live=latest;
    if (!window.CXMDockPosition?.streaming()) {
      el('cxmManualX').textContent=live.xy.x.toFixed(3)+' mm';
      el('cxmManualY').textContent=live.xy.y.toFixed(3)+' mm';
      el('cxmManualZ').textContent=live.z.toFixed(2)+' mm';
    }
    el('cxmManualSensor').textContent=live.sensor;
    if(!suffix){
      const newJog=Number(live.jog_revision)===2;
      const label=el('cxmDockJogSpeed');
      if(label)label.textContent=newJog?'50 mm/s · native verified':'Native jog update required';
      el('cxmManualReadiness').textContent=newJog?'Ready · T'+tool+' mounted':'Native macro update required · jog disabled';
    }else{
      el('cxmManualReadiness').textContent='READY · T'+tool+' mounted';
    }
    if(!silent) say('READY: sensor confirms MOUNTED, not tool identity. Verify the mounted hotend is physically T'+tool+' before approving any jog.');
  }catch(e){
    if(version!==refreshVersion||selectedTool!==selected())return;
    live=null;
    resetTravel('Travel verification invalidated: '+e.message);
    el('cxmManualApproval').checked=false;
    if(captureAck)captureAck.checked=false;
    el('cxmManualReadiness').textContent='NOT READY · '+e.message;
    if(!suffix && el('cxmDockJogSpeed'))el('cxmDockJogSpeed').textContent='Jog speed unavailable';
    say('Jog/capture blocked: '+e.message+'. Inspect and refresh after restoring safe state.',true);
  }finally{if(version===refreshVersion){polling=false;controls();}}
}
async function jog(button){
  if(travelBusy)return;
  if(!canJog() || (busy&&!jogging))return;
  resetTravel('Manual jog changed release-point verification. Repeat the 100 mm test.');
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
          acknowledgement:suffix==='XY'?'I_APPROVE_SUPERVISED_CAMERA_JOG':'I_APPROVE_SUPERVISED_MOTOR_ON_JOG'});
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
async function travel100(returning){
  if(suffix || !travelRetreat)return;
  if(travelBusy || busy || jogging || pending.length){
    travelSay('Movement already running. Complete or clear pending jogs first.');return;
  }
  if(!canJog()){
    travelSay('100 mm movement blocked. Select a mounted tool, home XYZ and enable jogging.');return;
  }
  const target=tool,rev=revision,identity=live.native_tool_identity;
  const start={...live.xy};
  if(returning){
    if(!retreatAnchor || retreatAnchor.tool!==target || retreatAnchor.revision!==rev ||
       retreatAnchor.identity!==identity || !close(start.x,retreatAnchor.x) ||
       !close(start.y,retreatAnchor.y+100)){
      travelSay('Return blocked: carriage is not at the verified +100 mm point. Inspect the position.');return;
    }
  }else{
    if(retreatAnchor || !live.limits?.y || start.y+100>live.limits.y[1] ||
       start.y<live.limits.y[0]){
      travelSay('No movement: full +100 mm Y would exceed machine travel, or a test is already active.');return;
    }
  }
  const goal=returning?retreatAnchor.y:start.y+100;
  // Enabling supervised jogging is the operator's movement approval. Avoid a
  // second browser confirm (whose cancellation previously left no diagnostics).
  // Every subsequent 10 mm increment still passes the native safety guards.
  ++refreshVersion;polling=false;busy=true;travelBusy=true;controls();
  const changeControls=byId('cxmChangeControls');
  if(changeControls)changeControls.disabled=true;
  try{
    for(let step=1;step<=10;step++){
      if(!canJog() || selected()!==target || revision!==rev || document.hidden)
        throw Error('Approval, selected tool, or page state changed');
      travelSay((returning?'Returning':'Retreating')+' · moving increment '+step+' of 10');
      const answer=await request('/manual/jog',{
        tool:target,axis:'y',distance:returning?-10:10,expected_revision:rev,
        acknowledgement:'I_APPROVE_SUPERVISED_MOTOR_ON_JOG'});
      if(answer.jogged!==true||answer.revision!==rev||!live||
         !close(answer.position.x,start.x)||
         !close(answer.position.y,start.y+(returning?-10:10)*step))
        throw Error('Position or saved revision not verified at increment '+step);
      live.xy=answer.position;
      if(!window.CXMDockPosition?.streaming()){
        el('cxmManualX').textContent=live.xy.x.toFixed(3)+' mm';
        el('cxmManualY').textContent=live.xy.y.toFixed(3)+' mm';
      }
    }
    const latest=await request('/manual/status?tool='+target);
    if(latest.revision!==rev||latest.native_tool_identity!==identity||
       latest.sensor!=='PRESSED'||!close(latest.xy.x,start.x)||!close(latest.xy.y,goal))
      throw Error('Final sensor or machine position did not match expected state');
    live=latest;
    if(returning){
      const verified={tool:target,revision:rev,identity,x:retreatAnchor.x,y:retreatAnchor.y};
      resetTravel('Return verified at the saved release point.');
      verifiedRoundtrip=verified;
    }else{
      retreatAnchor={tool:target,revision:rev,identity,x:start.x,y:start.y};
      travelSay('Retreat +100 mm verified. Check clearance, then press Return −100 mm Y.');
    }
  }catch(e){
    resetTravel('Travel incomplete or uncertain: '+e.message+'. Inspect carriage and realign before retrying.');
    live=null;el('cxmManualApproval').checked=false;
    say('100 mm travel unconfirmed. No further movements sent. '+e.message,true);
  }finally{
    busy=false;travelBusy=false;
    if(changeControls)changeControls.disabled=false;
    controls();refresh(true);
  }
}
async function capture(){
 if(busy||!live?.ready||tool!==selected())return;
 const target=tool;
 ++refreshVersion;polling=false;busy=true;controls();
 say('Saving T'+tool+' dock X/Y…');
 try{
   if(retreatAnchor)
     throw Error('Carriage is 100 mm from the release point. Return before saving.');
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
   resetTravel('Dock XY saved. You can now verify the 100 mm travel.');
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
travelRetreat?.addEventListener('click',()=>travel100(false));
travelReturn?.addEventListener('click',()=>travel100(true));
el('cxmManualRefresh').addEventListener('click',()=>refresh(false));
captureButton?.addEventListener('click',capture);
el('cxmManualApproval').addEventListener('change',()=>{clearQueue();resetTravel('Approval changed. Recheck release-point alignment.');controls();});
el('cxmJogClear').addEventListener('click',clearQueue);
function leaveJogPanel(){
  if(document.hidden || panel?.hidden){
    el('cxmManualApproval').checked=false;
    clearQueue();resetTravel('Page hidden. Travel verification cancelled.');
  }
}
document.addEventListener('visibilitychange',leaveJogPanel);
for(const event of ['pagehide','offline'])window.addEventListener(event,()=>{
  el('cxmManualApproval').checked=false;clearQueue();resetTravel('Connection changed. Travel verification cancelled.');
});
if(panel)new MutationObserver(()=>{leaveJogPanel();if(!panel.hidden)refresh(true);}).observe(panel,{attributes:true,attributeFilter:['hidden']});
captureAck?.addEventListener('change',controls);
selector.addEventListener('change',()=>{
  pending.length=0;live=null;tool=-1;resetTravel('Tool changed. Align and repeat travel verification.');
  el('cxmManualApproval').checked=false;if(captureAck)captureAck.checked=false;
  controls();refresh();
});
window.addEventListener('cxm-dock-saved',()=>{live=null;resetTravel('Dock save invalidated previous travel reference.');refresh();});
window.addEventListener('cxm-config-migrated',()=>{live=null;resetTravel('Configuration changed; repeat travel verification.');refresh();});
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
