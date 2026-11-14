/* CXM Updates page: guarded targeted native jog speed upgrade only. */
(()=>{
'use strict';
const page=document.querySelector('[data-panel="updates"]');
if(!page)return;
const host=page.querySelector('.cxma-stage[data-stage="3"] .cxma-inner')||page;
const box=document.createElement('section');
box.className='panel';
box.id='cxmJogUpgradeBox';
box.innerHTML=`
  <div class="panel-heading"><h3>Dock XY jog · 50 mm/s</h3><span class="panel-label">Native macro update</span></div>
  <p class="helper">Only the X/Y jog speed changes. Dock pickup and dropoff movements stay untouched.</p>
  <p class="helper" id="cxmJogUpgradeStatus" role="status" aria-live="polite">Checking installed Klipper macro…</p>
  <label class="cxm-capture-ack"><input id="cxmJogUpgradeAck" type="checkbox">
    <span class="cxm-approval-copy"><strong>Carriage EMPTY and printer idle</strong><small>Physically inspect carriage and docks before applying</small></span>
  </label>
  <div class="buttons">
    <button type="button" class="btn" id="cxmJogUpgradeRefresh">Check macro</button>
    <button type="button" class="btn primary" id="cxmJogUpgradeApply" disabled>Install 50 mm/s jog</button>
    <button type="button" class="btn" id="cxmJogUpgradeRestart" disabled>Restart Klipper to activate</button>
  </div>`;
host.append(box);
const $=id=>document.getElementById(id);
let current=null,busy=false,restartNeeded=false;
const say=msg=>{$('cxmJogUpgradeStatus').textContent=msg;};
function controls(){
 $('cxmJogUpgradeRefresh').disabled=busy;
 $('cxmJogUpgradeApply').disabled=busy||!current||current.file_state!=='needs_apply'||!$('cxmJogUpgradeAck').checked;
 $('cxmJogUpgradeRestart').disabled=busy||!restartNeeded;
}
async function json(url,body){
 const opts={credentials:'same-origin',cache:'no-store'};
 if(body){opts.method='POST';opts.headers={'Content-Type':'application/json','X-Requested-With':'CXM'};
  opts.body=JSON.stringify(body);}
 const r=await fetch(url,opts);
 const obj=await r.json().catch(()=>({error:'Invalid response'}));
 if(!r.ok)throw Error(obj.error||'HTTP '+r.status);
 return obj;
}
async function refresh(){
 if(busy)return;
 busy=true;controls();
 try{
  current=await json('/cxm/api/v1/update/jog/status');
  restartNeeded=current.restart_required===true;
  say(current.file_state==='needs_apply'?'Native jog upgrade ready to review and install.':
      restartNeeded?'File updated. Restart Klipper here to activate 50 mm/s.':
      current.file_state==='installed'&&Number(current.live_revision)===2?
      '50 mm/s active in Klipper.':'Macro status needs review.');
 }catch(e){current=null;restartNeeded=false;say('Cannot verify native macro: '+e.message);}
 finally{busy=false;controls();}
}
async function apply(){
 if(busy||!current||current.file_state!=='needs_apply'||!$('cxmJogUpgradeAck').checked)return;
 if(!window.confirm('Apply the backed-up 50 mm/s dock jog update? Printer must be idle and carriage physically EMPTY. No motion will be sent.'))return;
 const fingerprint=current.sha256;
 busy=true;controls();
 try{
  const result=await json('/cxm/api/v1/update/jog/apply',{
   sha256:fingerprint,acknowledgement:'I_INSPECTED_EMPTY_CARRIAGE_AND_STOPPED_ALL_TESTS'});
  if(result.installed!==true)throw Error('Installation readback not verified');
  current=null;restartNeeded=result.restart_required===true;
  say(restartNeeded?'Native jog updated with backup. Restart Klipper here to activate.':'Installed jog is already up to date.');
 }catch(e){current=null;restartNeeded=false;say('Installation blocked: '+e.message);}
 finally{busy=false;controls();}
}
async function restart(){
 if(busy||!restartNeeded)return;
 if(!window.confirm('Restart Klipper now? Tool state will be unknown and axes must be rehomed. No automatic movement will occur.'))return;
 busy=true;controls();
 try{
  const response=await fetch('/printer/restart',{method:'POST',credentials:'same-origin',cache:'no-store'});
  if(!response.ok)throw Error('Moonraker restart request failed (HTTP '+response.status+')');
  restartNeeded=false;current=null;
  $('cxmJogUpgradeAck').checked=false;
  say('Klipper restart requested. Wait for Ready, rehome XYZ, then refresh Dock XY.');
 }catch(e){say('Restart not confirmed: '+e.message);}
 finally{busy=false;controls();}
}
$('cxmJogUpgradeAck').addEventListener('change',controls);
$('cxmJogUpgradeRefresh').addEventListener('click',refresh);
$('cxmJogUpgradeApply').addEventListener('click',apply);
$('cxmJogUpgradeRestart').addEventListener('click',restart);
refresh();
})();