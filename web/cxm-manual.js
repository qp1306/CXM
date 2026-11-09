/* CXM motor-on dock alignment. Backend is sole motor/geometry authority. */
(()=>{
'use strict';
const el=id=>document.getElementById(id);
const root=el('cxmManualDock');
if(!root)return;
const api='/cxm/api/v1';
let busy=false,live=null,config=null,tool=-1;
function selected(){return Number(el('cxmDockTool').value);}
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
  el('cxmManualCapture').disabled=!allowed||!el('cxmManualCaptureAck').checked;
  el('cxmManualRefresh').disabled=busy;
}
async function refresh(){
  if(busy)return;
  busy=true;controls();
  try{
    config=await request('/config');
    tool=selected();live=await request('/manual/status?tool='+tool);
    el('cxmManualX').textContent=live.xy.x.toFixed(3)+' mm';
    el('cxmManualY').textContent=live.xy.y.toFixed(3)+' mm';
    el('cxmManualZ').textContent=live.z.toFixed(2)+' mm';
    el('cxmManualSensor').textContent=live.sensor;
    el('cxmManualReadiness').textContent='READY · T'+tool+' · XYZ homed · all motors on · carriage empty';
    say('Ready to jog T'+tool+' using the selected step. The machine will physically move.');
  }catch(e){
    live=null;
    el('cxmManualReadiness').textContent='NOT READY · '+e.message;
    say('Jog/capture blocked: '+e.message,true);
  }finally{busy=false;controls();}
}
async function jog(button){
  if(busy||!live?.ready||!el('cxmManualApproval').checked)return;
  const axis=button.dataset.manualAxis,sign=Number(button.dataset.manualSign);
  const distance=sign*Number(el('cxmManualStep').value);
  busy=true;controls();
  say('Jogging '+axis.toUpperCase()+' '+distance+' mm …');
  try{
    const answer=await request('/manual/jog',{
      tool,axis,distance,expected_revision:live.revision,
      acknowledgement:'I_APPROVE_SUPERVISED_MOTOR_ON_JOG'});
    if(answer.jogged!==true)throw Error('Motor jog not verified');
    live.xy=answer.position;
    el('cxmManualX').textContent=live.xy.x.toFixed(3)+' mm';
    el('cxmManualY').textContent=live.xy.y.toFixed(3)+' mm';
    say('Position reached. Verify the physical fit before further movement.');
  }catch(e){
    live=null;
    el('cxmManualApproval').checked=false;
    say('JOG STOPPED/UNCERTAIN: '+e.message+'. Inspect machine and refresh before any further movement.',true);
  }finally{busy=false;controls();}
}
async function capture(){
  if(busy||!live?.ready||!el('cxmManualCaptureAck').checked)return;
  busy=true;controls();
  try{
    const result=await request('/manual/capture',{
      tool,expected_revision:live.revision,
      acknowledgement:'I_INSPECTED_DOCK_ALIGNMENT_WITH_MOTORS_ON'});
    if(!result.captured||result.tool!==selected()||result.expected_revision!==live.revision)
      throw Error('Capture tool/revision mismatch');
    window.dispatchEvent(new CustomEvent('cxm-dock-provisional-xy',{
      detail:{tool,x:result.xy.x,y:result.xy.y,source:'motor-on-capture'}}));
    el('cxmManualCaptureAck').checked=false;
    say('Captured T'+tool+' X'+result.xy.x.toFixed(3)+' Y'+result.xy.y.toFixed(3)+
      '. Review draft below, save, then verify one slow native pickup/dropoff.');
  }catch(e){say('Capture failed: '+e.message,true);}
  finally{busy=false;controls();}
}
root.querySelectorAll('[data-manual-axis]').forEach(b=>b.addEventListener('click',()=>jog(b)));
el('cxmManualRefresh').addEventListener('click',refresh);
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
setTimeout(refresh,400);
})();
