/* CXM T0 commissioning: supervised XY-only motions, hardware-gated. */
(()=>{
'use strict';
const byId=id=>document.getElementById(id);
if(!byId('cxmT0TestPanel'))return;
let state=null,busy=false,choice='';
const base='/cxm/api/v1/t0';
const selected=()=>Number(byId('cxmDockTool')?.value);
const set=(id,msg)=>{const e=byId(id);if(e)e.textContent=msg;};
function values(){
  const dx=Number(byId('cxmT0Shift').value),dy=Number(byId('cxmT0Dodge').value);
  if(!Number.isFinite(dx)||!Number.isFinite(dy)||dx< -8||dx> -1||dy<5||dy>25)
    throw Error('Enter a lateral X shift from −8 to −1 mm and a Y dodge from 5 to 25 mm.');
  return {shift_x:dx,dodge_y:dy};
}
function path(){
  if(!state?.ready || selected()!==0)return 'T0 motion preview unavailable until printer safety checks pass.';
  const x=state.saved_xy_mm.x,y=state.saved_xy_mm.y,safe=state.safe_y_mm;
  try{
    const {shift_x:dx,dodge_y:dy}=values();
    if(y+dy+20>safe||x+dx<5||x+dx>330)throw Error('Dock shift/dodge conflicts with Safe Y or axis limits.');
    return 'Staging: X'+x.toFixed(3)+' / Y'+safe.toFixed(3)+' mm\n'+
      'PICKUP: Y'+(y+dy).toFixed(3)+' → X'+(x+dx).toFixed(3)+
      ' → Y'+y.toFixed(3)+' → X'+x.toFixed(3)+' → Y'+safe.toFixed(3)+'\n'+
      'DROPOFF: Y'+y.toFixed(3)+' → X'+(x+dx).toFixed(3)+
      ' → Y'+(y+dy).toFixed(3)+' → X'+x.toFixed(3)+' → Y'+safe.toFixed(3)+
      '\nNo Z moves. Dock coordinates are unadjusted.';
  }catch(e){return 'PATH BLOCKED · '+e.message;}
}
function valid(){try{values();return !path().startsWith('PATH BLOCKED');}catch{return false;}}
function controls(){
  const ready=!busy&&selected()===0&&state?.ready&&valid();
  const calibrated=state?.sensor_calibrated===true;
  const staged=state?.stage==='staged';
  byId('cxmT0Stage').disabled=!ready;
  byId('cxmT0Pickup').disabled=!ready||!calibrated||!staged||
    ![null,'staged','dropoff'].includes(state.last_action);
  byId('cxmT0Dropoff').disabled=!ready||!calibrated||!staged||state.last_action!=='pickup';
  byId('cxmT0Refresh').disabled=busy;
  byId('cxmT0Sensor').disabled=busy||selected()!==0||!state?.ready;
  byId('cxmT0RecordEmpty').disabled=busy||!choice||selected()!==0||!state?.ready;
  byId('cxmT0RecordMounted').disabled=busy||!choice||selected()!==0||!state?.ready;
}
async function request(path,body){
  const init={credentials:'same-origin',cache:'no-store'};
  if(body!==undefined){
    init.method='POST';
    init.headers={'Content-Type':'application/json','X-Requested-With':'CXM'};
    init.body=JSON.stringify(body);
  }
  const r=await fetch(base+path,init);
  const j=await r.json();
  if(!r.ok)throw Error(j.error||'HTTP '+r.status);
  return j;
}
async function revision(){
  const r=await fetch('/cxm/api/v1/config',{credentials:'same-origin',cache:'no-store'});
  if(!r.ok)throw Error('Configuration unavailable');
  return (await r.json()).revision;
}
async function refresh(){
  if(busy)return;
  try{
    state=await request('/status');
    if(selected()!==0){set('cxmT0Status','T0 only — select T0 in Dock Calibration.');}
    else if(state.ready){
      set('cxmT0Status','T0 X'+state.saved_xy_mm.x.toFixed(3)+
        ' Y'+state.saved_xy_mm.y.toFixed(3)+' · Safe Y'+state.safe_y_mm.toFixed(3)+
        ' · '+(state.stage==='staged'?'At staging':'Home and prepare for staging')+
        ' · powered XYZ / Klipper idle.');
    }else{
      set('cxmT0Status','BLOCKED · '+state.blockers.join('; '));
    }
    const options=state.sensor_candidates||[];
    const menu=byId('cxmT0Sensor');
    const desired=state.sensor||choice;
    menu.replaceChildren(new Option('Select carriage switch',''));
    options.forEach(o=>menu.add(new Option(o,o)));
    choice=options.includes(desired)?desired:'';
    menu.value=choice;
    const samples=state.sensor_samples||{};
    const mode=state.sensor_calibrated?'PASS · both physical states differ':
      'Not yet commissioned · record EMPTY and MOUNTED with physically different sensor states';
    set('cxmT0SensorStatus',mode+' · Live: '+
      options.map(n=>n+'='+String(state.sensor_states?.[n])).join(' | '));
    set('cxmT0Plan',path());
    controls();
  }catch(e){
    state=null;
    set('cxmT0Status','T0 status unavailable: '+e.message);
    set('cxmT0Plan','Movement is locked.');
    controls();
  }
}
async function record(condition){
  if(busy||!state?.ready||!choice||selected()!==0)return;
  const prompt=condition==='empty'?
    'Is the hotend physically REMOVED from the carriage, and the switch in its EMPTY state?':
    'Is hotend T0 physically MOUNTED on the carriage, and the switch actuated by actual seating?';
  if(!window.confirm(prompt+'\n\nRecord this live Klipper switch state for T0 only?'))return;
  busy=true;controls();
  try{
    const r=await request('/sensor',{expected_revision:await revision(),name:choice,
      condition,acknowledgement:'I_CHECKED_THE_PHYSICAL_T0_SENSOR'});
    set('cxmT0Result','Recorded '+condition.toUpperCase()+': '+String(r.value)+
      (r.both_states_distinct?' · sensor states differ':' · other state still required'));
  }catch(e){set('cxmT0Result','Sensor calibration blocked: '+e.message);}
  finally{busy=false;await refresh();}
}
async function move(kind){
  if(busy||!state?.ready||selected()!==0||!valid())return;
  const wp=path();
  if(wp.startsWith('PATH BLOCKED'))return;
  const n=kind==='stage'?'Approach T0 staging point':kind==='pickup'?'PICK UP T0':'DROP OFF T0';
  const confirmText=n+'?\n\n'+wp+'\n\n'+
    'The printer WILL MOVE at slow test speed. Have emergency stop available. '+
    'Confirm the full path is physically clear, hotend and carriage are in the correct initial state, '+
    'and that you can observe every movement. Never run unattended.';
  if(!window.confirm(confirmText))return;
  busy=true;controls();
  set('cxmT0Result',kind.toUpperCase()+' MOVEMENT IN PROGRESS · monitor the real printer.');
  try{
    const v=values(),r=await request('/motion',{
      expected_revision:await revision(),kind,
      shift_x:v.shift_x,dodge_y:v.dodge_y,
      acknowledgement:'I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH'
    });
    set('cxmT0Result',r.status+' · at X'+r.position_mm[0].toFixed(3)+
      '/Y'+r.position_mm[1].toFixed(3)+
      '. Visually inspect coupling. '+(r.sensor_confirmed?'Switch transition confirmed.':'No pickup attempted.'));
  }catch(e){
    set('cxmT0Result','TEST BLOCKED / FAILED: '+e.message+
      '. Inspect carriage and dock before making any further movement.');
  }finally{
    busy=false;
    await refresh();
  }
}
byId('cxmT0Refresh').addEventListener('click',refresh);
byId('cxmT0Stage').addEventListener('click',()=>move('stage'));
byId('cxmT0Pickup').addEventListener('click',()=>move('pickup'));
byId('cxmT0Dropoff').addEventListener('click',()=>move('dropoff'));
byId('cxmT0Sensor').addEventListener('change',e=>{choice=e.target.value;controls();});
byId('cxmT0RecordEmpty').addEventListener('click',()=>record('empty'));
byId('cxmT0RecordMounted').addEventListener('click',()=>record('mounted'));
['cxmT0Shift','cxmT0Dodge'].forEach(id=>byId(id).addEventListener('input',()=>{
  set('cxmT0Plan',path());controls();
}));
byId('cxmDockTool')?.addEventListener('change',refresh);
window.addEventListener('cxm-dock-saved',refresh);
document.querySelector('[data-tab="calibration"]')?.addEventListener('click',refresh);
refresh();
})();