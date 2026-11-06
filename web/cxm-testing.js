/* CXM V0.9.1: Diagnostics and restart evidence only.
   CoreXY dock review is now exclusively on Dock Calibration. No G-code. */
(()=>{
'use strict';
const $=id=>document.getElementById(id);
if(!$('cxmTestRun'))return;
let baseline=null,latest=null;
async function getJSON(path) {
  const r=await fetch(path,{credentials:'same-origin',cache:'no-store'});
  if(!r.ok)throw Error(path+' returned HTTP '+r.status);
  const j=await r.json();
  if(j.error)throw Error(j.error.message||j.error);
  return j;
}
function show(id,value){const e=$(id);if(e)e.textContent=value;}
function state(id,label,category='pending') {
  const node=$(id);if(!node)return;
  node.textContent=label;
  node.dataset.testState=category;
}
async function capture(){
  // Gather independently. Missing objects do not turn failed checks green.
  const [run,config,info,listed]=await Promise.all([
    getJSON('/cxm/api/v1/runtime'),getJSON('/cxm/api/v1/config'),
    getJSON('/printer/info'),getJSON('/printer/objects/list')
  ]);
  const names=Array.isArray(listed.result?.objects)?listed.result.objects:[];
  const query=['toolhead','idle_timeout','configfile','extruder','print_stats']
    .filter(name=>names.includes(name));
  const st=query.length
    ? (await getJSON('/printer/objects/query?'+query.join('&'))).result?.status||{}
    : {};
  return {run,revision:config.revision,schema:config.config?.schema,
          migration:!!config.migration_required,info:info.result||{},st,names,
          timestamp:new Date().toISOString()};
}
function display(s){
  const homed=s.st.toolhead?.homed_axes||'';
  const idle=s.st.idle_timeout?.state||'Unavailable';
  const print=s.st.print_stats?.state||'Unavailable';
  const mode=(s.info.state||'unknown');
  state('cxmTestKlipper',mode==='ready'?'Ready (reported)':mode,mode==='ready'?'ok':'bad');
  state('cxmTestHomed',homed.includes('x')&&homed.includes('y')&&homed.includes('z')
    ? 'XYZ homed (reported)' : homed?homed.toUpperCase()+' only':'NOT HOMED',
    homed.includes('x')&&homed.includes('y')&&homed.includes('z')?'ok':'pending');
  state('cxmTestIdle',idle+' / '+print,['Idle','Ready'].includes(idle)&&
    ['standby','complete','cancelled','error','Unavailable'].includes(print)?'ok':'pending');
  const pos=s.st.toolhead?.position;
  show('cxmTestPosition',Array.isArray(pos)&&pos.length>=3
    ? pos.slice(0,3).map(x=>Number(x).toFixed(3)).join(' / ')+' mm'
    : 'No position available');
  state('cxmTestStore',s.migration?'Migration required':s.revision?'Disk revision '+s.revision.slice(0,12):'Unavailable',
     !s.migration&&s.revision?'ok':'bad');
  state('cxmTestProcess',s.run.available?'Identity available':'Unable to confirm identity',
    s.run.available?'ok':'bad');
  const temp=s.st.extruder?.temperature;
  if(typeof temp==='number'&&temp< -20)
    state('cxmTestThermistor','Thermistor unconnected / invalid ('+temp.toFixed(1)+'°C) — no heating','bad');
  else if(typeof temp==='number'&&temp<=0)
    state('cxmTestThermistor','Temperature implausible ('+temp.toFixed(1)+'°C) — inspect sensor','bad');
  else if(typeof temp==='number')
    state('cxmTestThermistor','Sensor reports '+temp.toFixed(1)+'°C (NOT validated)','pending');
  else state('cxmTestThermistor','No sensor reading — no heating','bad');
  // A configfile object reveals a risky override but cannot certify a safe one.
  const override=s.st.configfile?.config?.homing_override;
  const gcode=typeof override?.gcode==='string'?override.gcode:'';
  if(override && override.set_position_z!=null && /G1\s+Z10\b/i.test(gcode))
    state('cxmTestHoming','BLOCKED: forced Z=0 and repeated Z10 in G28','bad');
  else state('cxmTestHoming','Not independently cleared: review homing_override','pending');
  show('cxmTestLast','Last checked '+new Date(s.timestamp).toLocaleString()+
    ' · Read-only; no motors, heaters or settings changed');
}
async function refresh(){
  show('cxmTestLast','Reading live Moonraker and CXM…');
  try{latest=await capture();display(latest);}
  catch(e){
    latest=null;
    show('cxmTestLast','Live preflight failed: '+e.message+'. No test has been authorised.');
    for(const id of ['cxmTestKlipper','cxmTestHomed','cxmTestIdle','cxmTestStore',
      'cxmTestProcess','cxmTestHoming'])state(id,'Unavailable','bad');
  }
}
async function baselineNow(){
  try {
    baseline=await capture();
    if(!baseline.run.available || !baseline.revision)
      throw Error('No valid process identity and configuration revision — cannot prove continuity');
    display(baseline);
    state('cxmTestRestartResult',
      'Baseline saved in this browser tab. Edit one safe field in Settings, wait for AutoSave, then Compare.',
      'pending');
  }catch(e){baseline=null;state('cxmTestRestartResult','Baseline failed: '+e.message,'bad');}
}
async function compareNow(){
  if(!baseline){state('cxmTestRestartResult','Capture baseline first.','bad');return;}
  try {
    const after=await capture();latest=after;display(after);
    if(!after.run.available){
      state('cxmTestRestartResult','INCONCLUSIVE: Klipper process identity unavailable.','bad');return;
    }
    if(after.run.identity!==baseline.run.identity){
      state('cxmTestRestartResult','FAILED: Klipper process identity changed between snapshots.','bad');return;
    }
    if(after.revision===baseline.revision){
      state('cxmTestRestartResult','INCOMPLETE: Same Klipper process, but no CXM disk revision change. Change a safe Settings value and AutoSave first.','pending');
      return;
    }
    state('cxmTestRestartResult',
      'PASS: CXM saved revision changed while Klipper process identity stayed unchanged. NO Klipper process restart. Disk settings are NOT applied live.',
      'ok');
  }catch(e){state('cxmTestRestartResult','Comparison inconclusive: '+e.message,'bad');}
}
function download(){
  // Local-only diagnostic bundle for reproducible faultfinding; no credentials.
  const payload={format:'CXM_DIAGNOSTIC_V1',generated:new Date().toISOString(),
    safety:'READ_ONLY; no printer control',runtime:latest?
      {klipper_state:latest.info.state,homed_axes:latest.st.toolhead?.homed_axes,
       printer_state:latest.st.idle_timeout?.state,
       process_identity_available:latest.run.available,
       config_revision:latest.revision,
       saved_data_active_in_klipper:false}:null,
    note:'Dock step-count calculation is found exclusively on Dock Calibration.'};
  const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download='CXM-diagnostic-'+new Date().toISOString().slice(0,10)+'.json';
  document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);
}
$('cxmTestRun').addEventListener('click',refresh);
$('cxmTestBaseline').addEventListener('click',baselineNow);
$('cxmTestCompare').addEventListener('click',compareNow);
$('cxmTestDownload').addEventListener('click',download);
refresh();
})();
