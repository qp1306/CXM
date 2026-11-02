/* CXM V0.6 — single authoritative, pure tool-readiness policy.
   Colour is identity; readiness is a separately validated state.
   WARNING: Never infer verification from a zero offset or saved XYZ.
*/
(function () {
  'use strict';
  const FLAGS=['dock_verified','offset_xy_verified','offset_z_verified',
    'pickup_verified','dropoff_verified','heater_verified','sensor_verified',
    'commissioned'];
  function classify(tool, number, count, runtime={}) {
    const selected=Number.isInteger(number) && number>=0 && number<count;
    const base={selected, canCalibrate:false, canPickup:false, missing:[], reason:''};
    if(!selected) return {...base,code:'NOT_SELECTED',label:'NOT SELECTED'};
    if(!tool) return {...base,code:'CONFIG_UNAVAILABLE',label:'CONFIGURATION UNAVAILABLE'};
    if(tool.maintenance_lockout===true) {
      return {...base,code:'LOCKED_OUT',label:'LOCKED OUT',
        reason:'Maintenance lockout enabled; inspect in Settings'};
    }
    const allowCal=runtime.migrationRequired!==true;
    const dockFields=['dock_x','dock_y','dock_z'];
    const dockSaved=dockFields.every(k=>typeof tool[k]==='number' && Number.isFinite(tool[k]));
    const anyDock=dockFields.some(k=>typeof tool[k]==='number' && Number.isFinite(tool[k]));
    const acceptedXY=tool.offset_xy_accepted===true;
    const acceptedZ=tool.offset_z_accepted===true;
    if(!dockSaved && !anyDock && !acceptedXY && !acceptedZ) {
      return {...base,code:'NOT_CALIBRATED',label:'NOT CALIBRATED',
        reason:'Dock XYZ and tool offsets require calibration',
        missing:['Dock XYZ','XY offsets','Z offset'], canCalibrate:allowCal};
    }
    if(!dockSaved || !acceptedXY || !acceptedZ) {
      const missing=[];
      if(!dockSaved)missing.push('Dock XYZ');
      if(!acceptedXY)missing.push('XY offset acceptance');
      if(!acceptedZ)missing.push('Z offset acceptance');
      return {...base,code:'INCOMPLETE',label:'CALIBRATION INCOMPLETE',
        reason:'Missing: '+missing.join(', '),missing,canCalibrate:allowCal};
    }
    const missing=FLAGS.filter(k=>tool[k]!==true);
    if(number===0 && tool.reference_verified!==true)missing.push('reference_verified');
    if(missing.length) return {...base,code:'AWAITING_VERIFICATION',
      label:'AWAITING VERIFICATION',reason:'Physical verification outstanding',
      missing,canCalibrate:allowCal};
    if(runtime.readyForMotion!==true || runtime.controlVerified!==true) {
      return {...base,code:'PRINTER_OFFLINE',label:'PRINTER OFFLINE',
        reason:'Klipper, homing and CXM motion controls not verified',canCalibrate:allowCal};
    }
    return {...base,code:'READY',label:'READY',
      reason:'Calibrated, verified and operational',canCalibrate:true,
      canPickup:runtime.pickupEnabled===true};
  }
  const labels=Object.freeze({
    NOT_SELECTED:'Not selected', CONFIG_UNAVAILABLE:'Configuration unavailable',
    LOCKED_OUT:'Locked out', NOT_CALIBRATED:'Not calibrated',
    INCOMPLETE:'Calibration incomplete',
    AWAITING_VERIFICATION:'Awaiting verification',
    PRINTER_OFFLINE:'Printer offline', READY:'Ready'
  });
  const api=Object.freeze({classify,labels});
  if(typeof module!=='undefined' && module.exports)module.exports=api;
  if(typeof window!=='undefined')window.CXMToolState=api;
})();
