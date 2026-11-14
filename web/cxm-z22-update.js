/* Single CXM Dock XY calibration upgrade: sensor-free manual jog + guarded Z22. */
(()=>{
'use strict';
const panel=document.querySelector('[data-panel="updates"]');
if(!panel)return;
const old=document.getElementById('cxmDockVerifyUpgradeBox');
if(old)old.hidden=true;
const host=panel.querySelector('.cxma-stage[data-stage="3"] .cxma-inner')||panel;
const box=document.createElement('section');box.className='panel';box.id='cxmDockCalibrationUpgrade';
box.innerHTML=
 '<div class="panel-heading"><h3>Dock XY calibration</h3><span class="panel-label">One supervised macro update</span></div>'+
 '<p class="helper">Removes filament checks from manual Dock XY calibration and adds automatic Z22 on Enable jogging. Native pickup/dropoff stays unchanged.</p>'+
 '<p class="helper" id="cxmDockCalibrationUpdateState" role="status">Checking loaded Klipper calibration…</p>'+
 '<label class="cxm-capture-ack"><input type="checkbox" id="cxmDockCalibrationUpdateAck">'+
 '<span class="cxm-approval-copy"><strong>Printer idle · no toolchange running · carriage inspected</strong>'+
 '<small>Installation only. Klipper restart and homing required before motion.</small></span></label>'+
 '<div class="buttons">'+
 '<button type="button" class="btn" id="cxmDockCalibrationUpdateCheck">Check calibration</button>'+
 '<button type="button" class="btn primary" id="cxmDockCalibrationUpdateApply" disabled>Install calibration update</button>'+
 '<button type="button" class="btn" id="cxmDockCalibrationUpdateRestart" disabled>Restart Klipper to activate</button>'+
 '</div>';
host.append(box);
const $=id=>document.getElementById(id);
const state=$('cxmDockCalibrationUpdateState'),ack=$('cxmDockCalibrationUpdateAck');
let current=null,busy=false,restartRequired=false;
function show(msg){state.textContent=msg;}
function controls(){
 $('cxmDockCalibrationUpdateCheck').disabled=busy;
 $('cxmDockCalibrationUpdateApply').disabled=busy||!current||
   current.file_state!=='needs_apply'||!ack.checked;
 $('cxmDockCalibrationUpdateRestart').disabled=busy||!restartRequired;
}
async function request(path,body){
 const opts={credentials:'same-origin',cache:'no-store'};
 if(body){opts.method='POST';opts.headers={'Content-Type':'application/json','X-Requested-With':'CXM'};
  opts.body=JSON.stringify(body);}
 const r=await fetch(path,opts),d=await r.json().catch(()=>({error:'Invalid response'}));
 if(!r.ok)throw Error(d.error||'HTTP '+r.status);
 return d;
}
async function check(){
 if(busy)return;busy=true;controls();
 try{
  const d=await request('/cxm/api/v1/update/z22/status');
  current=d;
  restartRequired=d.restart_required===true;
  show(d.file_state==='needs_apply'?'One calibration macro update ready. Review, approve and install.':
   restartRequired?'Calibration files updated. Restart Klipper to activate.':
   d.file_state==='installed'&&d.live_version===1&&d.jog_calibration_revision===2?
    'Dock XY calibration ready · filament checks removed · Z22 automatic.':
    'Calibration not yet confirmed in live Klipper. Check macro status.');
 }catch(e){current=null;restartRequired=false;show('Calibration check refused: '+e.message);}
 finally{busy=false;controls();}
}
async function apply(){
 if(busy||!ack.checked||current?.file_state!=='needs_apply')return;
 busy=true;controls();
 try{
  const d=await request('/cxm/api/v1/update/z22/apply',{
    sha256:current.sha256,acknowledgement:'I_INSPECTED_EMPTY_CARRIAGE_AND_STOPPED_ALL_TESTS'});
  if(!d.installed)throw Error('Macro update readback not verified');
  current=null;restartRequired=d.restart_required===true;
  show('Calibration update backed up and installed. Restart Klipper to activate.');
 }catch(e){current=null;restartRequired=false;show('Installation refused: '+e.message);}
 finally{busy=false;controls();}
}
async function restart(){
 if(busy||!restartRequired)return;
 if(!window.confirm('Restart Klipper to activate calibration? XYZ must be rehomed.'))return;
 busy=true;controls();
 try{
  const r=await fetch('/printer/restart',{method:'POST',credentials:'same-origin',cache:'no-store'});
  if(!r.ok)throw Error('Restart request not accepted');
  restartRequired=false;current=null;ack.checked=false;
  show('Klipper restart requested. Home XYZ, then check calibration status.');
 }catch(e){show('Restart not confirmed: '+e.message);}
 finally{busy=false;controls();}
}
ack.addEventListener('change',controls);
$('cxmDockCalibrationUpdateCheck').addEventListener('click',check);
$('cxmDockCalibrationUpdateApply').addEventListener('click',apply);
$('cxmDockCalibrationUpdateRestart').addEventListener('click',restart);
check();
})();