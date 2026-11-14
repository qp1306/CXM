/* One-purpose Updates-page installer for EMPTY carriage dock verification macro. */
(()=>{
'use strict';
const page=document.querySelector('[data-panel="updates"]');if(!page)return;
const host=page.querySelector('.cxma-stage[data-stage="3"] .cxma-inner')||page;
const box=document.createElement('section');box.className='panel';box.id='cxmDockVerifyUpgradeBox';
box.innerHTML=
 '<div class="panel-heading"><h3>Locked dock · ABSENT verification</h3><span class="panel-label">Append-only Klipper macro</span></div>'+
 '<p class="helper">Adds an independent EMPTY-carriage test macro. Existing docking and mounted jogging remain untouched.</p>'+
 '<p class="helper" id="cxmDockVerifyUpgradeStatus" role="status">Checking installed macro…</p>'+
 '<label class="cxm-capture-ack"><input type="checkbox" id="cxmDockVerifyUpgradeAck">'+
 '<span class="cxm-approval-copy"><strong>Carriage EMPTY · printer idle · tests stopped</strong>'+
 '<small>Inspect the printer before installing a new Klipper macro</small></span></label>'+
 '<div class="buttons"><button class="btn" id="cxmDockVerifyUpgradeRefresh">Check macro</button>'+
 '<button class="btn primary" id="cxmDockVerifyUpgradeApply" disabled>Install locked-dock verification</button>'+
 '<button class="btn" id="cxmDockVerifyUpgradeRestart" disabled>Restart Klipper to activate</button></div>';
host.append(box);
const $=id=>document.getElementById(id);
let current=null,busy=false,restartNeeded=false;
const say=msg=>{$('cxmDockVerifyUpgradeStatus').textContent=msg;};
function controls(){
 $('cxmDockVerifyUpgradeRefresh').disabled=busy;
 $('cxmDockVerifyUpgradeApply').disabled=busy||!current||
  current.file_state!=='needs_apply'||!$('cxmDockVerifyUpgradeAck').checked;
 $('cxmDockVerifyUpgradeRestart').disabled=busy||!restartNeeded;
}
async function json(url,body){
 const opts={credentials:'same-origin',cache:'no-store'};
 if(body){opts.method='POST';opts.headers={'Content-Type':'application/json','X-Requested-With':'CXM'};
  opts.body=JSON.stringify(body);}
 const r=await fetch(url,opts),d=await r.json().catch(()=>({error:'Invalid response'}));
 if(!r.ok)throw Error(d.error||'HTTP '+r.status);return d;
}
async function refresh(){
 if(busy)return;busy=true;controls();
 try{
  current=await json('/cxm/api/v1/update/dock-verify/status');
  restartNeeded=current.restart_required===true;
  say(current.file_state==='needs_apply'?'Approved append-only macro ready for installation.':
    restartNeeded?'Installed with backup. Restart Klipper to activate.':
    current.file_state==='installed'&&current.live_version===1?
    'Locked-dock ABSENT verification active in Klipper.':'Macro status needs review.');
 }catch(e){current=null;restartNeeded=false;say('Macro check blocked: '+e.message);}
 finally{busy=false;controls();}
}
async function apply(){
 if(busy||!current||current.file_state!=='needs_apply'||!$('cxmDockVerifyUpgradeAck').checked)return;
 if(!window.confirm('Install the independent locked-dock Klipper macro with backup? Carriage must be EMPTY, printer idle. No motion will occur.'))return;
 busy=true;controls();
 try{
  const d=await json('/cxm/api/v1/update/dock-verify/apply',{
   sha256:current.sha256,acknowledgement:'I_INSPECTED_EMPTY_CARRIAGE_AND_STOPPED_ALL_TESTS'});
  if(!d.installed)throw Error('Installed macro readback failed');
  restartNeeded=d.restart_required===true;
  current=null;
  say('Macro backed up and installed. Restart Klipper deliberately to activate.');
 }catch(e){current=null;restartNeeded=false;say('Installation refused: '+e.message);}
 finally{busy=false;controls();}
}
async function restart(){
 if(busy||!restartNeeded)return;
 if(!window.confirm('Restart Klipper? XYZ must be rehomed before further movement.'))return;
 busy=true;controls();
 try{
  const r=await fetch('/printer/restart',{method:'POST',credentials:'same-origin',cache:'no-store'});
  if(!r.ok)throw Error('Restart request failed: HTTP '+r.status);
  restartNeeded=false;current=null;
  $('cxmDockVerifyUpgradeAck').checked=false;
  say('Klipper restart requested. Rehome XYZ and check live macro status.');
 }catch(e){say('Restart not confirmed: '+e.message);}
 finally{busy=false;controls();}
}
$('cxmDockVerifyUpgradeAck').addEventListener('change',controls);
$('cxmDockVerifyUpgradeRefresh').addEventListener('click',refresh);
$('cxmDockVerifyUpgradeApply').addEventListener('click',apply);
$('cxmDockVerifyUpgradeRestart').addEventListener('click',restart);
refresh();
})();