/* CXM Lineux integration: supervised command, provisional result, no AutoSave.
   This is deliberately separate from existing offline CoreXY math review.
*/
(()=>{
'use strict';
const el=id=>document.getElementById(id);
if(!el('cxmLineuxPreflight'))return;
const api='/cxm/api/v1/lineux';
let state=null,knownState=null,result=null,tool=null,busy=false;
function feedback(message,kind='pending'){
  const e=el('cxmLineuxResult');e.textContent=message;e.dataset.testState=kind;
}
function selected(){return Number(el('cxmDockTool')?.value);}
function controls(){
  const matching=result && Number.isInteger(tool) && selected()===tool;
  el('cxmLineuxStart').disabled=busy || !state?.ready || !state?.known_verified ||
    !el('cxmLineuxAck').checked;
  el('cxmLineuxKnownStart').disabled=busy || !knownState?.ready || !el('cxmLineuxKnownAck').checked;
  el('cxmLineuxToDraft').disabled=busy || !matching ||
    el('cxmDockX')?.disabled!==false || el('cxmDockY')?.disabled!==false;
  el('cxmLineuxPreflight').disabled=busy;
}
async function call(path,body){
  const options={credentials:'same-origin',cache:'no-store'};
  if(body!==undefined){options.method='POST';options.headers={
    'Content-Type':'application/json','X-Requested-With':'CXM'};
    options.body=JSON.stringify(body);
  }
  const r=await fetch(api+path,options);
  const data=await r.json();
  if(!r.ok)throw Error(data.error || 'CXM service HTTP '+r.status);
  return data;
}
async function preflight(){
  if(busy)return;
  const n=selected();
  state=null;knownState=null;result=null;tool=null;
  el('cxmLineuxAck').checked=false;
  el('cxmLineuxKnownAck').checked=false;
  controls();
  el('cxmLineuxStatus').textContent='Checking hardware integration…';
  try{
    if(!Number.isInteger(n)||n<0||n>11)throw Error('Select a valid hotend');
    const [dock,known]=await Promise.all([
      call('/status?tool='+n+'&mode=dock'),
      call('/status?tool='+n+'&mode=known')
    ]);
    state=dock;knownState=known;
    el('cxmLineuxEngineBadge').textContent=dock.engine_present?'Lineux module registered':'Module unavailable';
    el('cxmLineuxMeasureBadge').textContent=dock.known_verified
      ? 'Known-position maths validated · dock provisional'
      : 'Known-position validation required';
    if(known.ready){
      const xy=known.status?.known_start_xy_mm||[];
      el('cxmLineuxKnownStatus').textContent='KNOWN TEST READY · X'+
        Number(xy[0]).toFixed(3)+' Y'+Number(xy[1]).toFixed(3)+
        ' Z'+Number(known.status.z_mm).toFixed(3);
    }else{
      el('cxmLineuxKnownStatus').textContent='KNOWN TEST NOT READY · '+known.blockers.join('; ');
    }
    if(dock.ready){
      el('cxmLineuxStatus').textContent='ENGINE READY · T'+n+' · dock confirmation required';
      feedback('Known-position check passed in this Klipper session. You may prepare a supervised dock measurement.');
    }else{
      el('cxmLineuxStatus').textContent='DOCK LOCKED · '+dock.blockers.join('; ');
      feedback('Dock measurement remains locked pending known-position verification and other readiness checks.');
    }
  }catch(e){
    el('cxmLineuxStatus').textContent='NOT READY · '+e.message;
    el('cxmLineuxKnownStatus').textContent='KNOWN TEST NOT READY · '+e.message;
    el('cxmLineuxEngineBadge').textContent='Status unknown';
    feedback('Could not confirm engine readiness. No motion is authorised.','bad');
  }
  controls();
}

async function checkKnownPosition(){
  if(busy || !knownState?.ready || !el('cxmLineuxKnownAck').checked) return;
  const n=selected();
  if(n!==knownState.tool)return;
  const xy=knownState.status?.known_start_xy_mm;
  if(!Array.isArray(xy)||xy.length!==2)return;
  if(!window.confirm('RUN KNOWN-POSITION LINEUX TEST?\n\n'+
    'Klipper currently reports X'+Number(xy[0]).toFixed(3)+
    ' / Y'+Number(xy[1]).toFixed(3)+' mm. These are the independently homed'+
    ' test coordinates, not dock coordinates.\n\n'+
    'The unchanged Lineux code will move +3 mm X, home Y and home Y/X again.'+
    ' Z must physically clear all obstructions.\n\n'+
    'MOTORS WILL MOVE. Do NOT manually move the carriage during this test.'))return;
  busy=true;controls();
  feedbackKnown('Executing unchanged Lineux measurement at known XY. Do not interrupt…');
  try{
    const snapshot=await fetch('/cxm/api/v1/config',{credentials:'same-origin',cache:'no-store'}).then(r=>r.json());
    if(!snapshot?.revision)throw Error('CXM settings revision missing');
    const r=await call('/known-check',{
      tool:n, expected_revision:snapshot.revision,
      acknowledgement:'I_CONFIRM_HOMED_KNOWN_XY_CLEAR_PATH'
    });
    const e=r.jog_corrected_error_mm;
    if(!e||!Number.isFinite(e.x)||!Number.isFinite(e.y))throw Error('Invalid known-check report');
    feedbackKnown(r.status+': known X'+r.known_start_xy_mm.x.toFixed(3)+
      ' / Y'+r.known_start_xy_mm.y.toFixed(3)+
      '; raw Lineux X'+r.lineux_raw_xy_mm.x.toFixed(3)+
      ' / Y'+r.lineux_raw_xy_mm.y.toFixed(3)+
      '; corrected errors X'+e.x.toFixed(3)+
      ' Y'+e.y.toFixed(3)+' mm. '+(r.passed
         ? 'PASS · no coordinates saved; now check dock readiness.'
         : 'FAIL · dock measurement remains locked.'),r.passed?'ok':'bad');
  }catch(err){
    feedbackKnown('KNOWN TEST REJECTED: '+err.message+
      '. Machine may have moved. Inspect it before another attempt.','bad');
  }finally{
    busy=false;
    await preflight();
    controls();
  }
}
function feedbackKnown(message,kind='pending'){
  const e=el('cxmLineuxKnownResult');
  e.textContent=message;
  e.dataset.testState=kind;
}
async function measure(){
  if(busy || !state?.ready || !state?.known_verified || !el('cxmLineuxAck').checked)return;
  const n=selected();
  if(n!==state.tool)return;
  if(!window.confirm('START LINEUX DOCK MEASUREMENT FOR T'+n+'?\n\n'+
    'You physically positioned the carriage at the intended dock datum, have confirmed at least 15 mm '+
    'Z clearance and an unobstructed complete Y/X homing path.\n\n'+
    'The unchanged Lineux engine will set a kinematic position, jog X, home Y, then home X. '+
    'CXM Homing V2.0 homes Y a second time when X is requested.\n\n'+
    'The motors WILL MOVE. Keep emergency stop accessible. No XY coordinates will be saved.'))return;
  busy=true;result=null;tool=null;controls();
  feedback('Executing Lineux calibration. Do not interfere with the printer…');
  try{
    const snapshot=await fetch('/cxm/api/v1/config', {credentials:'same-origin',cache:'no-store'}).then(r=>r.json());
    if(!snapshot?.revision)throw Error('CXM config revision unavailable');
    const answer=await call('/measure',{tool:n,expected_revision:snapshot.revision,
      acknowledgement:'I_CONFIRM_CLEAR_DOCK_PATH'});
    if(answer.status!=='PROVISIONAL_LINEUX_UNVERIFIED'||answer.tool!==n||answer.verified!==false)
      throw Error('Measurement response not provisional for selected tool');
    result=answer;tool=n;
    feedback('PROVISIONAL T'+n+': raw X '+answer.raw_xy_mm.x.toFixed(3)+' / Y '+
      answer.raw_xy_mm.y.toFixed(3)+' mm; separately adjusted X preview '+
      answer.adjusted_x_preview_mm.toFixed(3)+' mm. Not saved or verified.','pending');
    await preflightAfterMeasurement();
  }catch(e){
    result=null;tool=null;
    feedback('MEASUREMENT NOT ACCEPTED: '+e.message+
      '. The printer may have moved. Inspect it before another attempt.','bad');
  }finally{busy=false;controls();}
}
async function preflightAfterMeasurement(){
  // Do not clear a result by invoking preflight(); report only updated status.
  try{
    const current=await call('/status?tool='+selected());
    state=current;
    el('cxmLineuxStatus').textContent=current.ready?'ENGINE READY · new capture requires fresh acknowledgement':
      'CHECK MACHINE · '+current.blockers.join('; ');
  }catch{state=null;el('cxmLineuxStatus').textContent='Status unknown after movement';}
  el('cxmLineuxAck').checked=false;
}
async function copy(){
  if(!result||selected()!==tool||busy||el('cxmDockX').disabled||el('cxmDockY').disabled)return;
  const n=tool;
  try{
    const latest=await fetch('/cxm/api/v1/config',{credentials:'same-origin',cache:'no-store'}).then(r=>r.json());
    if(latest.revision!==result.expected_revision)throw Error('Saved settings revision changed');
    const adjust=el('cxmLineuxApplyAdjust').checked;
    const x=adjust?result.adjusted_x_preview_mm:result.raw_xy_mm.x;
    const y=result.raw_xy_mm.y;
    if(!Number.isFinite(x)||!Number.isFinite(y))throw Error('Measurement not finite');
    if(!window.confirm('Copy PROVISIONAL Lineux X='+x.toFixed(3)+', Y='+y.toFixed(3)+
       ' to T'+n+' dock DRAFT only?\n\n'+(adjust?'The separate X docking correction is included.':
       'No X docking correction is applied.')+
       '\n\nZ is unchanged. This does NOT save or verify the dock.'))return;
    window.dispatchEvent(new CustomEvent('cxm-dock-provisional-xy',
      {detail:{tool:n,x,y,source:'lineux-live'}}));
    feedback('T'+n+' provisional XY sent to dock draft. Review the values and enter Z separately.');
    result=null;tool=null;
  }catch(e){feedback('Copy blocked: '+e.message,'bad');}
  controls();
}
el('cxmLineuxPreflight').addEventListener('click',preflight);
el('cxmLineuxKnownStart').addEventListener('click',checkKnownPosition);
el('cxmLineuxKnownAck').addEventListener('change',controls);
el('cxmLineuxStart').addEventListener('click',measure);
el('cxmLineuxToDraft').addEventListener('click',copy);
el('cxmLineuxAck').addEventListener('change',controls);
el('cxmDockTool').addEventListener('change',preflight);
window.addEventListener('cxm-calibrate-tool',()=>setTimeout(preflight,0));
preflight();
})();