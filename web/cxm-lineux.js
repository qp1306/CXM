/* CXM Lineux integration: supervised command, provisional result, no AutoSave.
   This is deliberately separate from existing offline CoreXY math review.
*/
(()=>{
'use strict';
const el=id=>document.getElementById(id);
if(!el('cxmLineuxPreflight'))return;
const api='/cxm/api/v1/lineux';
let state=null,knownState=null,releaseState=null,homeState=null,result=null,tool=null,busy=false;
function feedback(message,kind='pending'){
  const e=el('cxmLineuxResult');e.textContent=message;e.dataset.testState=kind;
}
function selected(){return Number(el('cxmDockTool')?.value);}
function controls(){
  const matching=result && Number.isInteger(tool) && selected()===tool;
  // Do not show a green approval on an operation that the backend cannot authorise.
  for(const [id,ready] of [
    ['cxmLineuxHomeAck',homeState?.ready],
    ['cxmLineuxReleaseAck',releaseState?.ready],
    ['cxmLineuxAck',state?.ready],
    ['cxmLineuxKnownAck',knownState?.ready]
  ]){
    const input=el(id);
    input.disabled=busy||ready!==true;
    if(ready!==true)input.checked=false;
  }
  el('cxmLineuxHome').disabled=busy || !homeState?.ready || !el('cxmLineuxHomeAck').checked;
  el('cxmLineuxStart').disabled=busy || !state?.ready ||
    !el('cxmLineuxAck').checked;
  el('cxmLineuxReleaseXY').disabled=busy || !releaseState?.ready ||
    !el('cxmLineuxReleaseAck').checked;
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
  state=null;knownState=null;releaseState=null;homeState=null;result=null;tool=null;
  el('cxmLineuxAck').checked=false;
  el('cxmLineuxKnownAck').checked=false;
  el('cxmLineuxReleaseAck').checked=false;
  el('cxmLineuxHomeAck').checked=false;
  controls();
  el('cxmLineuxStatus').textContent='Checking hardware integration…';
  try{
    if(!Number.isInteger(n)||n<0||n>11)throw Error('Select a valid hotend');
    const [dock,known,release,home]=await Promise.all([
      call('/status?tool='+n+'&mode=dock'),
      call('/status?tool='+n+'&mode=known'),
      call('/status?tool='+n+'&mode=prepare'),
      call('/status?tool='+n+'&mode=home')
    ]);
    state=dock;knownState=known;releaseState=release;homeState=home;
    el('cxmLineuxEngineBadge').textContent=dock.engine_present?'Lineux module registered':'Module unavailable';
    el('cxmLineuxMeasureBadge').textContent='Live measurement · provisional until independently verified';
    el('cxmLineuxHomeStatus').textContent=home.ready
      ? 'Ready to home · confirm physical clearance.'
      : 'Homing unavailable: '+home.blockers.join('; ');
    el('cxmLineuxReleaseStatus').textContent=release.ready
      ? 'XYZ homed, Z >=20 mm, four Z motors powered. Release X/Y when physically safe.'
      : 'X/Y release unavailable: '+release.blockers.join('; ');
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
      feedback('Carriage manually aligned and motors correctly configured: ready to measure selected dock. Check physical clearance and confirm.');
    }else{
      el('cxmLineuxStatus').textContent='DOCK LOCKED · '+dock.blockers.join('; ');
      feedback('Not ready to measure: '+dock.blockers.join('; ')+'. Home, raise Z20, release X/Y and align your dock first.');
    }
  }catch(e){
    el('cxmLineuxStatus').textContent='NOT READY · '+e.message;
    el('cxmLineuxKnownStatus').textContent='Known-position diagnostic unavailable · '+e.message;
    el('cxmLineuxHomeStatus').textContent='Homing status unavailable · '+e.message;
    el('cxmLineuxReleaseStatus').textContent='X/Y release status unavailable · '+e.message;
    el('cxmLineuxEngineBadge').textContent='Status unknown';
    feedback('Could not confirm engine readiness. No motion is authorised.','bad');
  }
  controls();
}

// Query live Klipper release readiness after Home, without resetting the
// user's current page, selected hotend or other controls. Klipper can report
// idle_timeout='Printing' briefly after a completed G-code script.
let releaseRefreshBusy=false;
async function refreshReleaseReadiness({retryTransient=true}={}){
  if(releaseRefreshBusy)return;
  releaseRefreshBusy=true;
  const n=selected();
  releaseState=null;
  controls();
  el('cxmLineuxReleaseStatus').textContent='Checking X/Y release readiness…';
  try{
    for(let attempt=0;attempt<(retryTransient?10:1);attempt++){
      if(selected()!==n)return;
      let response;
      try{
        response=await call('/status?tool='+n+'&mode=prepare');
      }catch(err){
        if(attempt===(retryTransient?9:0)){
          el('cxmLineuxReleaseStatus').textContent=
            'Cannot refresh release readiness: '+err.message+
            '. Check printer & engine if this continues.';
          return;
        }
        await new Promise(resolve=>setTimeout(resolve,500));
        continue;
      }
      if(selected()!==n)return;
      releaseState=response;
      if(response.ready){
        el('cxmLineuxReleaseStatus').textContent=
          'XYZ homed, Z >=20 mm, all four Z motors powered. '+
          'Confirm physical support above, then release only X/Y.';
        return;
      }
      const reasons=response.blockers||[];
      if(reasons.length!==1 || reasons[0]!=='Klipper motion state not idle'){
        el('cxmLineuxReleaseStatus').textContent=
          'X/Y release unavailable: '+reasons.join('; ');
        return;
      }
      if(attempt===(retryTransient?9:0)){
        el('cxmLineuxReleaseStatus').textContent=
          'Waiting for Klipper to become idle. Recheck by ticking the release confirmation; no page reload required.';
        return;
      }
      el('cxmLineuxReleaseStatus').textContent=
        'Home finished · waiting for Klipper to become idle…';
      await new Promise(resolve=>setTimeout(resolve,500));
    }
  }finally{
    releaseRefreshBusy=false;
    controls();
  }
}

async function homeAndLift(){
  if(busy || !homeState?.ready || !el('cxmLineuxHomeAck').checked)return;
  const n=selected();
  if(n!==homeState.tool)return;

  el('cxmLineuxHomeAck').checked=false; // one fresh approval for every motion
  busy=true;controls();
  el('cxmLineuxHomeStatus').textContent='Homing and raising to Z20…';
  try{
    const snapshot=await fetch('/cxm/api/v1/config',
      {credentials:'same-origin',cache:'no-store'}).then(r=>r.json());
    if(!snapshot?.revision)throw Error('CXM configuration revision unavailable');
    const result=await call('/home',{tool:n,expected_revision:snapshot.revision,
      acknowledgement:'I_CONFIRM_CLEAR_G28_AND_Z20_PATH'});
    if(result.status!=='HOMED_Z20_CENTRE')throw Error('Printer readiness confirmation failed');
    // Home succeeded and coordinates/motor states were verified by the
    // backend. Do NOT run full preflight here: it clears acknowledgements and
    // can cache a temporary Klipper-not-idle state until the page reloads.
    // A new physical release acknowledgement is required after homing.
    el('cxmLineuxReleaseAck').checked=false;
    el('cxmLineuxHomeStatus').textContent=
      'HOMED · Z20 · X195/Y170. Checking Release X/Y automatically…';
    await refreshReleaseReadiness({retryTransient:true});
    el('cxmLineuxHomeStatus').textContent=
      'HOMED · Z20 · X195/Y170. Next: confirm physical support and release X/Y.';
  }catch(e){
    el('cxmLineuxHomeStatus').textContent='HOME NOT VERIFIED: '+e.message+
      '. Inspect the printer before repeating.';
  }finally{busy=false;controls();}
}

async function releaseXY(){
  if(busy || !releaseState?.ready || !el('cxmLineuxReleaseAck').checked)return;
  const n=selected();
  if(n!==releaseState.tool)return;

  el('cxmLineuxReleaseAck').checked=false; // do not reuse an old approval
  busy=true;controls();
  el('cxmLineuxReleaseStatus').textContent='Releasing X/Y only; Z motors stay powered…';
  try{
    const snapshot=await fetch('/cxm/api/v1/config',
      {credentials:'same-origin',cache:'no-store'}).then(r=>r.json());
    if(!snapshot?.revision)throw Error('CXM configuration revision unavailable');
    const r=await call('/release-xy',{tool:n,expected_revision:snapshot.revision,
      acknowledgement:'I_CONFIRM_Z_SUPPORTED_RELEASE_XY'});
    if(r.status!=='XY_RELEASED_Z_REMAINS_POWERED'||r.release_confirmed!==true)
      throw Error('Motor state confirmation failed');
    await preflightAfterRelease();
  }catch(e){
    el('cxmLineuxReleaseStatus').textContent='RELEASE NOT CONFIRMED: '+e.message+
      '. Inspect motors before manually moving the carriage.';
  }finally{
    busy=false;controls();
  }
}
async function preflightAfterRelease(){
  // Release endpoint already verified X/Y OFF and four Z motors ON.
  // Refresh dock readiness, but do not require a separate known-position test.
  releaseState=null;
  el('cxmLineuxReleaseAck').checked=false;
  el('cxmLineuxReleaseStatus').textContent='X/Y RELEASED · Z motors ON. '+
    'Hand-align carriage at T'+selected()+' dock; X/Y coordinates shown in Mainsail are stale.';
  try{
    let current=await call('/status?tool='+selected()+'&mode=dock');
    if(!current.ready && current.blockers.length===1 &&
      current.blockers[0]==='Klipper motion state not idle'){
      // The stepper command can briefly leave Klipper in transient "Printing".
      await new Promise(resolve=>setTimeout(resolve,1200));
      current=await call('/status?tool='+selected()+'&mode=dock');
    }
    state=current;
    el('cxmLineuxStatus').textContent=current.ready
      ? 'ENGINE READY · physically align your dock, then press Measure dock XY'
      : 'DOCK NOT READY · '+current.blockers.join('; ');
  }catch(err){
    state=null;
    el('cxmLineuxStatus').textContent='Dock readiness unavailable: '+err.message;
  }
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
    'This is NOT a dock measurement. Do not run after releasing X/Y or moving by hand. '+
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
    const e=r.known_position_error_mm;
    if(!e||!Number.isFinite(e.x)||!Number.isFinite(e.y))throw Error('Invalid known-check report');
    feedbackKnown(r.status+': known X'+r.known_start_xy_mm.x.toFixed(3)+
      ' / Y'+r.known_start_xy_mm.y.toFixed(3)+
      '; original Lineux X'+r.lineux_raw_xy_mm.x.toFixed(3)+
      ' / Y'+r.lineux_raw_xy_mm.y.toFixed(3)+
      '; position errors X'+e.x.toFixed(3)+
      ' Y'+e.y.toFixed(3)+' mm. No second X jog compensation. '+(r.passed
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
  if(busy || !state?.ready || !el('cxmLineuxAck').checked)return;
  const n=selected();
  if(n!==state.tool)return;

  el('cxmLineuxAck').checked=false; // new safety review for each measurement
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
    feedback('LINEUX MEASURED T'+n+': raw X'+answer.raw_xy_mm.x.toFixed(3)+
      ' Y'+answer.raw_xy_mm.y.toFixed(3)+
      ' · CxChanger datum X'+answer.adjusted_x_preview_mm.toFixed(3)+
      ' Y'+answer.adjusted_y_preview_mm.toFixed(3)+
      '. Review the large-hole / locking-screw alignment before saving.','pending');
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
    // Lineux only measures. CxChanger movement must use the explicit
    // locking-hole datum, with independently configured X/Y corrections.
    const x=result.adjusted_x_preview_mm;
    const y=result.adjusted_y_preview_mm;
    if(!Number.isFinite(x)||!Number.isFinite(y))throw Error('Measurement not finite');
    if(!window.confirm('Copy CxChanger T'+n+' docking-hole datum X'+
       x.toFixed(3)+' Y'+y.toFixed(3)+'?\\n\\n'+
       'Lineux measured X'+result.raw_xy_mm.x.toFixed(3)+
       ' Y'+result.raw_xy_mm.y.toFixed(3)+
       ' (X/Y corrections included).\\n'+
       'Check locking-screw alignment. This is a DRAFT, not physical verification.'))return;
    window.dispatchEvent(new CustomEvent('cxm-dock-provisional-xy',
      {detail:{tool:n,x,y,raw_xy:result.raw_xy_mm,source:'lineux-live'}}));
    feedback('T'+n+' provisional XY sent to dock draft. Review and save X/Y in Dock Calibration; nozzle Z offsets are separate.');
    result=null;tool=null;
  }catch(e){feedback('Copy blocked: '+e.message,'bad');}
  controls();
}
el('cxmLineuxPreflight').addEventListener('click',preflight);
el('cxmLineuxHome').addEventListener('click',homeAndLift);
el('cxmLineuxHomeAck').addEventListener('change',controls);
el('cxmLineuxReleaseXY').addEventListener('click',releaseXY);
el('cxmLineuxReleaseAck').addEventListener('change',async ()=>{
  controls();
  // Also handles someone homing via Mainsail: the live Klipper state is
  // rechecked when the operator confirms release clearance, without reload.
  if(el('cxmLineuxReleaseAck').checked && !busy)
    await refreshReleaseReadiness({retryTransient:true});
});
el('cxmLineuxKnownStart').addEventListener('click',checkKnownPosition);
el('cxmLineuxKnownAck').addEventListener('change',controls);
el('cxmLineuxStart').addEventListener('click',measure);
el('cxmLineuxToDraft').addEventListener('click',copy);
el('cxmLineuxAck').addEventListener('change',controls);
el('cxmDockTool').addEventListener('change',preflight);
window.addEventListener('cxm-config-migrated',preflight);
window.addEventListener('cxm-calibrate-tool',()=>setTimeout(preflight,0));
preflight();
})();