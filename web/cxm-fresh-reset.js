/* CXM full commissioning reset — safeguarded data reset, no printer motion. */
(()=>{
 'use strict';
 const $=id=>document.getElementById(id);
 if(!$('cxmCommissionResetPanel'))return;
 const base='/cxm/api/v1';
 const ack='I_CONFIRMED_EMPTY_CARRIAGE_AND_WANT_TO_ERASE_ALL_CXM_CALIBRATIONS';
 let saved=null,native=null,working=false;
 const say=(id,value)=>{const el=$(id);if(el)el.textContent=value;};
 async function get(path){
  const r=await fetch(base+path,{credentials:'same-origin',cache:'no-store'});
  const d=await r.json().catch(()=>({error:'Invalid CXM response'}));
  if(!r.ok)throw Error(d.error||'HTTP '+r.status);
  return d;
 }
 async function preflight(){
  if(working)return;
  try{
   const results=await Promise.all([get('/config'),get('/native/status')]);
   saved=results[0];native=results[1];
   const stationary=!native.running && native.sensor==='RELEASED';
   const valid=!!saved.revision&&!saved.migration_required&&stationary&&
    native.native_protocol===2;
   const canReset=valid&&!working;
   $('cxmFreshAck').disabled=!canReset;
   $('cxmFreshReset').disabled=!canReset||!$('cxmFreshAck').checked;
   say('cxmFreshStatus',
    !stationary?'Blocked: stop native tests, physically remove tool and verify sensor RELEASED':
    saved.migration_required?'Migrate CXM settings before commissioning reset':
    native.native_protocol!==2?'Native Klipper macros unavailable or old protocol':
    'Sensor RELEASED · test idle · saved revision available. Inspect the carriage and confirm to start fresh.');
  }catch(e){
   saved=null;native=null;
   $('cxmFreshAck').disabled=true;
   $('cxmFreshReset').disabled=true;
   say('cxmFreshStatus','Reset unavailable: '+e.message);
  }
 }
 async function reset(){
  if(working||!saved||!native||!$('cxmFreshAck').checked
    ||native.sensor!=='RELEASED'||native.running)return;
  const revision=saved.revision;
  if(!window.confirm('BACK UP & RESET ALL 12 CXM TOOL CALIBRATIONS?\n\nThis clears every saved dock position, XY/Z tool offset and verification flag, then starts from an uncalibrated T0. Existing data will be backed up. No printer motion will be commanded.\n\nAll hotends must be safely docked, carriage physically EMPTY.'))return;
  working=true;$('cxmFreshReset').disabled=true;$('cxmFreshAck').disabled=true;
  say('cxmFreshResult','Backing up current CXM data and invalidating old toolchange targets…');
  try{
   const r=await fetch(base+'/commissioning/reset',{
    method:'POST',credentials:'same-origin',cache:'no-store',
    headers:{'Content-Type':'application/json','X-Requested-With':'CXM'},
    body:JSON.stringify({expected_revision:revision,acknowledgement:ack})
   });
   const result=await r.json().catch(()=>({error:'Non-JSON reset response'}));
   if(!r.ok)throw Error(result.error||'HTTP '+r.status);
   if(result.reset_commissioning!==true||result.cleared_tools!==12
      ||result.selected_tool_count!==1||result.native_inhibited!==true
      ||result.physically_empty!==true||!result.backup){
    throw Error('Reset was not fully verified. Do not command any tool movement.');
   }
   const [confirmed,live]=await Promise.all([get('/config'),get('/native/status')]);
   if(confirmed.revision!==result.revision||confirmed.config.globals.tool_count!==1
      ||confirmed.config.tools.length!==12
      ||confirmed.config.tools.some(t=>t.dock_x!==null||t.dock_y!==null
       ||t.dock_reference_accepted||t.offset_xy_accepted||t.offset_z_accepted||t.commissioned)
      ||live.native_ready!==false||live.sensor!=='RELEASED'||live.running){
    throw Error('Post-reset readback mismatch. Inspect Klipper and saved configuration.');
   }
   saved=confirmed;native=live;
   $('cxmFreshAck').checked=false;
   say('cxmFreshResult','RESET VERIFIED. Old data backed up as '+result.backup+
      '. All 12 calibrations cleared; T0 selected; native automatic toolchanging inhibited. Start with Dock XY → T0.');
   window.dispatchEvent(new Event('cxm-config-migrated'));
   window.dispatchEvent(new CustomEvent('cxm-commissioning-reset',{detail:{backup:result.backup}}));
  }catch(e){
   say('cxmFreshResult','RESET STOPPED / UNVERIFIED: '+e.message+
      '. Do not use automatic toolchanges or assume old coordinates remain safe.');
  }finally{
   working=false;await preflight();
  }
 }
 $('cxmFreshAck').addEventListener('change',()=>{
  $('cxmFreshReset').disabled=working||!saved||!native||
   native.running||native.sensor!=='RELEASED'||!$('cxmFreshAck').checked;
 });
 $('cxmFreshReset').addEventListener('click',reset);
 document.querySelector('[data-tab="settings"]')?.addEventListener('click',preflight);
 window.addEventListener('cxm-commissioning-reset',()=>{$('cxmFreshAck').checked=false;});
 preflight();
})();
