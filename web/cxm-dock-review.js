/* CXM V0.9.1 — CoreXY capture review lives on Dock Calibration.
   Inputs are local calculations only. NEVER command motion or save XYZ here.
   Only an explicitly confirmed PROVISIONAL X/Y draft may be transferred to
   the existing safeguarded editor, never directly to the config service.
*/
(()=>{
'use strict';
const get=id=>document.getElementById(id);
if(!get('cxmTestXYReview'))return;
let mode='none', result=null, measuredTool=null;
const keys=['cxmTestStep','cxmTestXA','cxmTestXB','cxmTestYA','cxmTestYB',
            'cxmTestEndX','cxmTestEndY','cxmTestKnownX','cxmTestKnownY',
            'cxmTestStart','cxmTestAfterY','cxmTestAfterX'];
const value=id=>get(id).value.trim();
function data(){
  return {
    step_mm:value('cxmTestStep'),xA:value('cxmTestXA'),xB:value('cxmTestXB'),
    yA:value('cxmTestYA'),yB:value('cxmTestYB'),
    endX:value('cxmTestEndX'),endY:value('cxmTestEndY'),
    start:value('cxmTestStart'),afterY:value('cxmTestAfterY'),
    afterX:value('cxmTestAfterX'),knownX:value('cxmTestKnownX'),
    knownY:value('cxmTestKnownY')
  };
}
function status(message,kind='pending'){
  const el=get('cxmTestXYResult');
  el.textContent=message;
  el.dataset.testState=kind;
}
function reset(message){
  result=null;measuredTool=null;
  get('cxmDockCaptureToDraft').disabled=true;
  status(message);
}
function validCopy(){
  const n=Number(get('cxmDockTool')?.value);
  const r=result;
  return mode==='manual' && r && r.status==='PROVISIONAL_UNVERIFIED'
    && r.save_permitted===false && r.known_reference_errors_mm===null
    && Number.isInteger(measuredTool) && measuredTool===n
    && get('cxmDockCaptureAck').checked===true
    && Number.isFinite(r.raw_dock_xy_mm.x) && Number.isFinite(r.raw_dock_xy_mm.y)
    && r.raw_dock_xy_mm.x>=0 && r.raw_dock_xy_mm.x<=Number(value('cxmTestEndX'))
    && r.raw_dock_xy_mm.y>=0 && r.raw_dock_xy_mm.y<=Number(value('cxmTestEndY'))
    && get('cxmDockX')?.disabled===false && get('cxmDockY')?.disabled===false;
}
function refreshCopy(){get('cxmDockCaptureToDraft').disabled=!validCopy();}
function review(){
  result=null;measuredTool=null;
  try{
    const r=window.CXMTestMath.review(data());
    result=r;
    const selected=Number(get('cxmDockTool')?.value);
    measuredTool=Number.isInteger(selected)?selected:null;
    const errors=r.known_reference_errors_mm;
    const verdict=errors
      ? ', reference errors X='+errors.x.toFixed(5)+', Y='+errors.y.toFixed(5)
        +' mm · known-position math '+(r.known_position_math_pass?'PASS':'FAIL')
      : ' · unknown dock reference — must physically verify before use';
    const kind=errors&&r.known_position_math_pass?'ok':'pending';
    status('PROVISIONAL X='+r.raw_dock_xy_mm.x.toFixed(5)+' mm; Y='+
      r.raw_dock_xy_mm.y.toFixed(5)+' mm'+verdict+
      '. No movement or save. X docking adjust is NOT applied.',kind);
  }catch(e){
    status('REJECTED: '+e.message,'bad');
  }
  refreshCopy();
}
function loadKnown(){
  mode='example';get('cxmDockCaptureAck').checked=false;
  const vals={
    cxmTestStep:'5',cxmTestXA:'800',cxmTestXB:'800',
    cxmTestYA:'800',cxmTestYB:'-800',cxmTestEndX:'335',
    cxmTestEndY:'362',cxmTestKnownX:'295',cxmTestKnownY:'100',
    cxmTestStart:'mcu: stepper_x:4814 stepper_y:27252 stepper_z:1877',
    cxmTestAfterY:'mcu: stepper_x:46739 stepper_y:-14673 stepper_z:9877',
    cxmTestAfterX:'mcu: stepper_x:53139 stepper_y:-8273 stepper_z:17877'
  };
  for(const [id,v] of Object.entries(vals))get(id).value=v;
  review();
  status(get('cxmTestXYResult').textContent+
    ' REFERENCE EXAMPLE: copying these coordinates into T0 is blocked.');
}
function startCapture(){
  mode='manual';
  get('cxmDockCaptureAck').checked=false;
  for(const id of ['cxmTestStart','cxmTestAfterY','cxmTestAfterX',
                    'cxmTestKnownX','cxmTestKnownY'])get(id).value='';
  reset('New capture ready. Paste real step-count lines into the three boxes. '+
    'The path must have been independently verified; this screen never commands G28.');
}
function copyDraft(){
  if(!validCopy())return;
  const n=measuredTool,x=result.raw_dock_xy_mm.x,y=result.raw_dock_xy_mm.y;
  if(!window.confirm('Copy PROVISIONAL raw X/Y into the T'+n+' DRAFT only?\n\n'+
    'This does not save a calibration or enable movement. Dock Z must be established separately. '+
    'The global X docking adjustment will not be applied here.'))return;
  window.dispatchEvent(new CustomEvent('cxm-dock-provisional-xy',
    {detail:{tool:n,x,y,source:'manual-mcu-review'}}));
  status('Provisional X='+x.toFixed(5)+' / Y='+y.toFixed(5)+
    ' mm sent to the T'+n+' dock draft. Z must be entered separately; no save or motion occurred.');
  get('cxmDockCaptureAck').checked=false;
  refreshCopy();
}
get('cxmTestXYReview').addEventListener('click',review);
get('cxmTestLoadKnown').addEventListener('click',loadKnown);
get('cxmDockCaptureNew').addEventListener('click',startCapture);
get('cxmDockCaptureToDraft').addEventListener('click',copyDraft);
get('cxmDockCaptureAck').addEventListener('change',refreshCopy);
get('cxmDockTool').addEventListener('change',()=>reset('Changed tool. Review fresh real capture data for this tool.'));
for(const id of keys)get(id).addEventListener('input',()=>reset(
  mode==='example'?'Reference data modified. Choose Start new T0 capture for manual calibration.'
    :'Capture inputs changed. Recalculate before copying any candidate.'));
})();
