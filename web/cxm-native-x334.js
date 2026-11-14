/* Tools: correct only outdated native 325mm guards, then restart Klipper. */
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
  const restart=info&&info.file_state==='installed'&&info.loaded_guard==='x325';
  root.hidden=!busy&&!correction&&!restart;
  button.disabled=busy||(!correction&&!restart);
  button.textContent=restart?'Restart Klipper to load X334':
     'Apply X334 fix & restart Klipper';
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
  if(info.file_state==='needs_apply')say(
    'Saved native Klipper macros still contain the old X325 limit. One click will patch only those limits, back up the file and restart Klipper.');
  else if(info.loaded_guard==='x325')say(
    'Native file uses X334, but Klipper is still running the old X325 guard. Restart to activate it.');
 }catch(e){
  info=null;root.hidden=false;button.disabled=true;
  say('X334 check unavailable: '+e.message);
 }
}
async function apply(){
 if(busy||!info)return;
 const patchNeeded=info.file_state==='needs_apply';
 if(!patchNeeded&&info.loaded_guard!=='x325')return;
 busy=true;root.hidden=false;controls();
 let patched=false;
 try{
  if(patchNeeded){
   const done=await request(source+'apply',{sha256:info.sha256});
   if(done.patched!==true&&done.already_installed!==true)
     throw Error('Installed config did not confirm X334 patch');
   patched=true;
  }
  say('X334 config ready. Restarting Klipper…');
  // Restart is essential: Klipper keeps its old macro source in RAM until restart.
  const response=await fetch('/printer/restart',{method:'POST',
      credentials:'same-origin',cache:'no-store'});
  if(!response.ok)throw Error('Klipper restart request HTTP '+response.status);
  info=null;
  say('Klipper restart requested. Home XYZ, then try loading T0. Saved dock coordinates are unchanged.');
  button.disabled=true;
  button.hidden=true;
 }catch(e){
  say((patched?'X334 saved to disk; Klipper restart not confirmed: ':
       'Native X334 correction refused: ')+e.message+
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
document.addEventListener('visibilitychange',()=>{if(!document.hidden)status();});
status();
})();