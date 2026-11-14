/* One-time on-printer activation of the T0–T11 native Dock Batch runner.
 * Never run a motion command from browser JavaScript. */
(()=>{
'use strict';
const section=document.getElementById('cxmBatchUpgrade');
if(!section)return;
const button=document.getElementById('cxmBatchUpgradeApply');
const message=document.getElementById('cxmBatchUpgradeMessage');
const api='/cxm/api/v1/';
let info=null,busy=false;
async function request(url,body){
 const args={credentials:'same-origin',cache:'no-store'};
 if(body!==undefined){
  args.method='POST';
  args.headers={'Content-Type':'application/json','X-Requested-With':'CXM'};
  args.body=JSON.stringify(body);
 }
 const reply=await fetch(api+url,args);
 const data=await reply.json().catch(()=>({error:'CXM backend response unavailable'}));
 if(!reply.ok)throw Error(data.error||'HTTP '+reply.status);
 return data;
}
function show(text){message.textContent=text;}
function controls(){
 const upgrade=info&&(info.file_state==='needs_apply'||info.loaded_revision!==2);
 section.hidden=!busy&&!upgrade;
 button.disabled=busy||!upgrade;
 button.textContent=info?.file_state==='installed'
   ?'Restart Klipper to activate 12-tool batch'
   :'Upgrade Dock Batch & restart Klipper';
}
async function refresh(){
 if(busy)return;
 try{
  info=await request('native/batch-upgrade/status');
  controls();
  if(info.file_state==='needs_apply')show(
    'Native Klipper is still running the 1–3-tool batch controller. One click will back up and upgrade only its test macros; saved dock XY, speeds and pickup/dropoff paths remain untouched.');
  else if(info.loaded_revision!==2)show(
    'The native batch upgrade is saved, but Klipper has not loaded revision 2. Restart Klipper once to activate all 12 tool choices.');
 }catch(e){
  info=null;section.hidden=false;button.disabled=true;
  show('Batch upgrade unavailable: '+e.message);
 }
}
async function apply(){
 if(busy||!info)return;
 busy=true;controls();
 let patched=false;
 try{
  if(info.file_state==='needs_apply'){
   const updated=await request('native/batch-upgrade/apply',{sha256:info.sha256});
   if(!updated.patched&&!updated.already_installed)throw Error('Native macro update not verified');
   patched=true;
  }
  show('12-tool batch macro saved. Restarting Klipper…');
  const restarted=await request('native/restart',{});
  if(restarted.restart_requested!==true)throw Error('Klipper restart not confirmed');
  show('Klipper restart requested. Home XYZ and confirm the carriage is physically EMPTY before running any Dock Batch cycles.');
  info=null;button.disabled=true;button.hidden=true;
 }catch(e){
  show((patched?'Batch macro saved, but restart not confirmed: ':'Batch macro upgrade refused: ')+e.message+
    (patched?' Restart Klipper once from Mainsail, then home XYZ.':''));
  button.disabled=true;
 }finally{busy=false;}
}
button.addEventListener('click',apply);
document.querySelector('[data-tab="dock-batch"]')?.addEventListener('click',refresh);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
refresh();
})();