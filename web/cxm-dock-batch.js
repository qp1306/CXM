/* Dock Batch: expose existing native Klipper repeat test, no motion rewrite.
   Custom speeds persist in this browser across reloads and Klipper restarts.
 */
(()=>{
'use strict';
const slot=document.getElementById('cxmDockBatchSlot');
const panel=document.getElementById('cxmMultiPanel');
if(!slot||!panel)return;
slot.append(panel);
panel.classList.add('cxm-dock-batch');
const $=id=>document.getElementById(id);
// Show the same native carriage declaration on Dock Batch WITHOUT duplicating
// its listener, control ID or backend command. The original remains in Tools.
const existingIdentity=$('cxmCarriageIdentity');
const existingConfirm=$('cxmDeclareCarriage');
if(existingIdentity&&existingConfirm){
 const carriage=document.createElement('section');
 carriage.id='cxmBatchCarriagePanel';
 carriage.className='cxm-batch-carriage';
 carriage.innerHTML='<h3>Currently fitted</h3>'+
   '<p>Choose EMPTY or the hotend physically mounted on the carriage.</p>'+
   '<div class="cxm-batch-carriage-row">'+
     '<select id="cxmBatchCarriageIdentity" aria-label="Currently fitted hotend"></select>'+
     '<button class="btn primary" type="button" id="cxmBatchConfirmCarriage">Confirm carriage state</button>'+
   '</div>'+
   '<p id="cxmBatchCarriageStatus" role="status" aria-live="polite"></p>';
 slot.prepend(carriage);
 const mirror=carriage.querySelector('#cxmBatchCarriageIdentity');
 const button=carriage.querySelector('#cxmBatchConfirmCarriage');
 const note=carriage.querySelector('#cxmBatchCarriageStatus');
 const updateMirror=()=>{
  const keep=mirror.value;
  const hadSelection=mirror.options.length>0 && keep!=='';
  const original=[...existingIdentity.options];
  if(original.length && (mirror.options.length!==original.length ||
     original.some((option,i)=>mirror.options[i]?.value!==option.value ||
                          mirror.options[i]?.textContent!==option.textContent))){
   mirror.replaceChildren(...original.map(o=>o.cloneNode(true)));
  }
  if(hadSelection&&original.some(o=>o.value===keep))mirror.value=keep;
  else mirror.value=existingIdentity.value;
  mirror.disabled=existingIdentity.disabled||existingConfirm.disabled;
  button.disabled=existingConfirm.disabled||existingIdentity.disabled;
 };
 button.addEventListener('click',()=>{
  if(button.disabled||mirror.value===''){
   note.textContent='Choose the actual fitted hotend or EMPTY first.';
   return;
  }
  const selected=mirror.value;
  existingIdentity.value=selected;
  existingIdentity.dispatchEvent(new Event('change',{bubbles:true}));
  if(existingIdentity.value!==selected){
   note.textContent='Could not select that carriage identity. Refresh the tool list.';
   return;
  }
  existingConfirm.click(); // Existing native handler; never a new motion path.
  note.textContent='Carriage confirmation sent through the existing native controller. See the Dock Batch status below.';
 });
 document.querySelector('[data-tab="dock-batch"]')?.addEventListener('click',updateMirror);
 existingIdentity.addEventListener('change',updateMirror);
 setInterval(updateMirror,1800);
 updateMirror();
}
const heading=panel.querySelector('.panel-heading h3');
if(heading)heading.textContent='Dock pickup / dropoff batch test';
const speed=$('cxmSpeedSimple');
const custom=$('cxmCustomSpeedFields');
const key='CXM_DOCK_BATCH_CUSTOM_SPEED_V1';
const fields=['cxmCustomTravel','cxmCustomApproach','cxmCustomLatch'];
if(!speed||!custom)return;
// Only two choices for this commissioning page; the native speed engine still
// supports its old presets, but they no longer clutter this simple UI.
for(const option of Array.from(speed.options)){
 if(option.value!=='standard'&&option.value!=='custom')option.remove();
}
if(speed.value!=='standard'&&speed.value!=='custom'){
 speed.value='standard';
 speed.dispatchEvent(new Event('change',{bubbles:true}));
}
const save=document.createElement('button');
save.id='cxmBatchSaveCustom';
save.type='button';save.className='btn primary';
save.textContent='Save Custom Speed';
const info=document.createElement('p');
info.id='cxmBatchSavedSpeed';
info.className='helper';
info.setAttribute('role','status');
info.setAttribute('aria-live','polite');
custom.append(save,info);
function entered(){
 const raw=fields.map(id=>$(id).value.trim());
 if(raw.some(v=>v===''))return null;
 const [travel,approach,latch]=raw.map(Number);
 if(![travel,approach,latch].every(Number.isFinite))return null;
 if(!(travel>=10&&travel<=1200&&approach>=1&&approach<=600&&
      latch>=1&&latch<=300&&travel>=approach&&approach>=latch))return null;
 return {travel,approach,latch};
}
function label(v){return v.travel+' / '+v.approach+' / '+v.latch+' mm/s (travel / approach / latch)';}
function saved(){
 try{
  const raw=window.localStorage?.getItem(key);
  if(!raw)return null;
  const v=JSON.parse(raw);
  if(!v||typeof v!=='object')return null;
  const values=[v.travel,v.approach,v.latch];
  if(!values.every(n=>typeof n==='number'&&Number.isFinite(n))||
     !(v.travel>=10&&v.travel<=1200&&v.approach>=1&&v.approach<=600&&
       v.latch>=1&&v.latch<=300&&v.travel>=v.approach&&v.approach>=v.latch))return null;
  return v;
 }catch{return null;}
}
const remembered=saved();
if(remembered){
 for(const [id,value] of fields.map((id,i)=>[id,[remembered.travel,remembered.approach,remembered.latch][i]])){
  $(id).value=String(value);
  $(id).dispatchEvent(new Event('input',{bubbles:true}));
 }
 info.textContent='Saved on this browser: '+label(remembered);
}else{
 info.textContent='Choose your travel, approach and latch speeds, then Save Custom Speed.';
}
save.addEventListener('click',()=>{
 const value=entered();
 if(!value){
  info.textContent='Enter valid speeds: travel 10–1200, approach 1–600, latch 1–300 mm/s; travel ≥ approach ≥ latch.';
  return;
 }
 try{
  if(!window.localStorage)throw Error('Browser storage unavailable');
  window.localStorage.setItem(key,JSON.stringify(value));
  info.textContent='Saved on this browser: '+label(value);
  speed.value='custom';
  speed.dispatchEvent(new Event('change',{bubbles:true}));
 }catch(e){
  info.textContent='Could not save in this browser: '+e.message;
 }
});
document.querySelector('[data-tab="dock-batch"]')?.addEventListener('click',()=>{
 $('cxmMultiRefresh')?.click();
});
// Standard and Custom are simply UI choices. No saved preset changes anything
// in Klipper until the user presses Start cycles in the existing controller.
})();
