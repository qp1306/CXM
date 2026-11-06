/* CXM V0.9.0 - pure offline CoreXY capture review. Never issues G-code or saves. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.CXMTestMath=api;
})(typeof window!=='undefined'?window:null,function(){
'use strict';
function finite(value,label) {
  if(value===''||value==null||!Number.isFinite(Number(value)))throw Error(label+' must be a finite number');
  return Number(value);
}
function parseMCU(raw){
  if(typeof raw!=='string'||raw.length>16000)throw Error('Provide one GET_POSITION MCU snapshot');
  const lines=raw.split(/\r?\n/).map(x=>x.trim()).filter(x=>/(?:^|\s)mcu:\s*stepper_x:/.test(x));
  if(lines.length!==1)throw Error('Each capture needs exactly one MCU motor-count line (found '+lines.length+')');
  const line=lines[0];
  const get=(name)=>{
    const matches=[...line.matchAll(new RegExp('(?:^|\\s)'+name+':(-?\\d+)(?=\\s|$)','g'))];
    if(matches.length!==1)throw Error('Missing/duplicated '+name+' MCU counter');
    return Number(matches[0][1]);
  };
  const pair=[get('stepper_x'),get('stepper_y')];
  if(pair.some(v=>!Number.isSafeInteger(v)))throw Error('MCU step counts are outside safe integer range');
  return pair;
}
function review(value){
  const step=finite(value.step_mm,'Calibration move mm');
  if(step<1||step>100)throw Error('Calibration distance must be 1-100 mm');
  const calX=[finite(value.xA,'X move motor A'),finite(value.xB,'X move motor B')];
  const calY=[finite(value.yA,'Y move motor A'),finite(value.yB,'Y move motor B')];
  const ax=calX[0]/step,bx=calX[1]/step,ay=calY[0]/step,by=calY[1]/step;
  const det=ax*by-ay*bx;
  const norm=Math.max(Math.abs(ax),Math.abs(ay),Math.abs(bx),Math.abs(by));
  if(norm<1||Math.abs(det)<1e-5*norm*norm)throw Error('CoreXY calibration matrix is invalid/singular');
  const start=parseMCU(value.start),afterY=parseMCU(value.afterY),afterX=parseMCU(value.afterX);
  const Y=[afterY[0]-start[0],afterY[1]-start[1]];
  const X=[afterX[0]-afterY[0],afterX[1]-afterY[1]];
  const xy=(d)=>[(by*d[0]-ay*d[1])/det,(-bx*d[0]+ax*d[1])/det];
  const yMove=xy(Y),xMove=xy(X);
  if(![...yMove,...xMove].every(Number.isFinite))throw Error('Non-finite travel');
  if(Math.abs(yMove[0])>0.15||Math.abs(xMove[1])>0.15)
    throw Error('Cross-axis travel exceeds 0.15 mm; reject measurement');
  if(yMove[1]<=0||xMove[0]<=0)throw Error('Captured motion contradicts positive-endstop homing');
  const endX=finite(value.endX,'X endstop'),endY=finite(value.endY,'Y endstop');
  if(endX<=0||endY<=0||endX>1000||endY>1000)throw Error('Invalid endstop location');
  const x=endX-xMove[0],y=endY-yMove[1];
  if(x<0||x>endX||y<0||y>endY)throw Error('Candidate dock XY is outside the verified machine envelope');
  const knownX=value.knownX===''||value.knownX==null?null:finite(value.knownX,'Known X');
  const knownY=value.knownY===''||value.knownY==null?null:finite(value.knownY,'Known Y');
  const errors=knownX===null||knownY===null?null:{x:Math.abs(x-knownX),y:Math.abs(y-knownY)};
  return {
    status:'PROVISIONAL_UNVERIFIED',save_permitted:false,active_in_klipper:false,
    raw_dock_xy_mm:{x,y},travel_mm:{x:xMove[0],y:yMove[1]},
    cross_axis_mm:{during_y_home_x:yMove[0],during_x_home_y:xMove[1]},
    calibrated_steps_per_mm:{ax,ay,bx,by},
    known_reference_errors_mm:errors,
    known_position_math_pass:errors===null?null:errors.x<=0.05&&errors.y<=0.05,
    warnings:[
      'Step counters cannot prove mechanical alignment, clearance or pickup.',
      'Mainsail homing override may introduce extra Z movements and homing retracts.',
      'Captured step deltas require independent physical validation before use for actual dock coordinates.',
      'X docking adjustment is separate and has NOT been applied.',
      'Nothing was moved, saved or applied to Klipper by this reviewer.'
    ]
  };
}
return {parseMCU,review};
});
