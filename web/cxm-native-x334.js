/* Tools: one-time repair of stale native X bounds / obsolete T1 release datum. */
(()=>{
'use strict';
const root=document.getElementById('cxmNativeX334Fix');
if(!root)return;
const msg=document.getElementById('cxmNativeX334Message');
const button=document.getElementById('cxmNativeX334Apply');
const source='/cxm/api/v1/native/x334/';
let info=null,busy=false;
function say(text){msg.textContent=text;}
function controls(){
  const correction=info&&info.file_state==='needs_apply';
  const restart=info&&info.file_state==='installed'&&
    (info.loaded_guard==='x325'||info.loaded_release_guard==='obsolete_t1');
  root.hidden=!busy&&!correction&&!restart;
  button.disabled=busy||(!correction&&!restart);
  button.hidden=false;
  button.textContent=restart?'Restart Klipper to activate dock correction':
     'Fix obsolete dock check & restart Klipper';
}
async function request(url,body){
 const options={cache:'no-store',credentials:'same-origin'};
 if(body){options.method='POST';options.headers={'Content-Type':'application/json',
  'X-Requested-With':'CXM'};options.body=JSON.stringify(body);}
 const response=await fetch(url,options);
 const data=await response.json().catch(()=>({error:'Unexpected CXM response'}));
 if(!response.ok)throw Error(data.error||'CXM request rejected');
 return data;
}
async function status(){
 if(busy)return;
 try{
  info=await request(source+'status');
  controls();
  if(info.file_state==='needs_apply'&&info.patch_mode==='t1_only')say(
    'Old T1 X264.70/Y65.60 check detected in the installed macro. The one-time correction will remove only those two obsolete lines and keep all other settings.');
  else if(info.file_state==='needs_apply')say(
    'Installed native macro still has an obsolete staging check, X limit, or T1 release datum. '+
    'This one-time correction backs up the file, enables automatic Y+ staging for Dock Batch, and restarts Klipper. Saved dock XY and pickup/dropoff movements stay unchanged.');
  else if(info.loaded_release_guard==='obsolete_t1'||info.loaded_guard==='x325')say(
    'Corrected file is saved, but Klipper still has the older macro loaded. Restart Klipper to activate it.');
 }catch(e){
  info=null;root.hidden=false;button.disabled=true;
  say('X334 check unavailable: '+e.message);
 }
}
async function apply(){
 if(busy||!info)return;
 const patchNeeded=info.file_state==='needs_apply';
 if(!patchNeeded&&info.loaded_guard!=='x325'&&
    info.loaded_release_guard!=='obsolete_t1')return;
 busy=true;root.hidden=false;controls();
 let patched=false;
 try{
  if(patchNeeded){
   const done=await request(source+'apply',{sha256:info.sha256});
   if(done.patched!==true&&done.already_installed!==true)
     throw Error('Installed config did not confirm X334 patch');
   patched=true;
  }
  say('Dock macro correction ready. Restarting Klipper…');
  // Restart is essential: Klipper keeps its old macro source in RAM until restart.
  const restart=await request('/cxm/api/v1/native/restart',{});
  if(restart.restart_requested!==true)throw Error('Klipper restart was not confirmed');
  info=null;
  say('Klipper restart requested. Home XYZ, then confirm the old T1 check is gone before any toolchange. Saved coordinates are unchanged.');
  button.disabled=true;
  button.hidden=true;
 }catch(e){
  say((patched?'Dock correction saved; Klipper restart not confirmed: ':
       'Native dock correction refused: ')+e.message+
       (patched?'. Restart Klipper once from Mainsail, then home XYZ.':''));
  info=null;
  button.disabled=true;
 }finally{
  busy=false;
  // Preserve explicit success/error message; avoid accidental second apply.
 }
}
button.addEventListener('click',apply);
document.querySelector('[data-tab="tools"]')?.addEventListener('click',status);
document.querySelector('[data-tab="dock-batch"]')?.addEventListener('click',status);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)status();});
status();
})();