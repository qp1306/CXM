/* CXM Lineux integration: supervised command, provisional result, no AutoSave.
   This is deliberately separate from existing offline CoreXY math review.
*/
(()=>{
'use strict';
const el=id=>document.getElementById(id);
if(!el('cxmLineuxPreflight'))return;
const api='/cxm/api/v1/lineux';
let state=null,result=null,tool=null,busy=false;
function feedback(message,kind='pending'){
  const e=el('cxmLineuxResult');e.textContent=message;e.dataset.testState=kind;
}
function selected(){return Number(el('cxmDockTool')?.value);}
function controls(){
  const matching=result && Number.isInteger(tool) && selected()===tool;
  el('cxmLineuxStart').disabled=busy || !state?.ready || !el('cxmLineuxAck').checked;
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
  state=null;result=null;tool=null;
  el('cxmLineuxAck').checked=false;
  controls();
  el('cxmLineuxStatus').textContent='Checking hardware integration…';
  try{
    if(!Number.isInteger(n)||n<0||n>11)throw Error('Select a valid hotend');
    state=await call('/status?tool='+n);
    if(state.ready){
      el('cxmLineuxStatus').textContent='ENGINE READY · T'+n+' · confirmation required';
      feedback('The Lineux engine is installed and Klipper reports idle. Confirm physical clearance. '+
        'The script will home Y, then X (which re-homes Y under CXM V2.0).');
    }else{
      el('cxmLineuxStatus').textContent='NOT READY · '+state.blockers.join('; ');
      feedback('Measurement locked. No motion has occurred. Complete the one-time Lineux setup and review the blockers.');
    }
  }catch(e){
    el('cxmLineuxStatus').textContent='NOT READY · '+e.message;
    feedback('Could not confirm engine readiness. No motion is authorised.','bad');
  }
  controls();
}
async function measure(){
  if(busy || !state?.ready || !el('cxmLineuxAck').checked)return;
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
el('cxmLineuxStart').addEventListener('click',measure);
el('cxmLineuxToDraft').addEventListener('click',copy);
el('cxmLineuxAck').addEventListener('change',controls);
el('cxmDockTool').addEventListener('change',preflight);
window.addEventListener('cxm-calibrate-tool',()=>setTimeout(preflight,0));
preflight();
})();