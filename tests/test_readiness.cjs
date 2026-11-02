const test=require('node:test'),assert=require('node:assert/strict');
const {classify}=require('../web/cxm-tool-state.js');
const base={maintenance_lockout:false,dock_x:null,dock_y:null,dock_z:null,
  offset_x:0,offset_y:0,offset_z:0,offset_xy_accepted:false,offset_z_accepted:false,
  dock_verified:false,offset_xy_verified:false,offset_z_verified:false,
  pickup_verified:false,dropoff_verified:false,heater_verified:false,
  sensor_verified:false,reference_verified:false,commissioned:false};
const tool=x=>({...base,...x});
test('selection is distinct from calibration and manual lockout',()=>{
 assert.equal(classify(tool(),10,6).code,'NOT_SELECTED');
 assert.equal(classify(tool(),10,12).code,'NOT_CALIBRATED');
 assert.equal(classify(tool({maintenance_lockout:true}),10,12).code,'LOCKED_OUT');
 assert.equal(classify(null,1,12).code,'CONFIG_UNAVAILABLE');
});
test('saved coordinates alone never count as calibrated',()=>{
 const dock=tool({dock_x:200,dock_y:150,dock_z:280});
 assert.equal(classify(dock,2,12).code,'INCOMPLETE');
 assert.equal(classify({...dock,offset_xy_accepted:true,offset_z_accepted:true},2,12).code,'AWAITING_VERIFICATION');
});
test('zero offsets are not automatically accepted or verified',()=>{
 const dock=tool({dock_x:200,dock_y:150,dock_z:280,offset_x:0,offset_y:0,offset_z:0});
 assert.equal(classify(dock,0,12).code,'INCOMPLETE');
});
test('T0 needs explicit physical reference verification',()=>{
 const ready=tool({dock_x:200,dock_y:150,dock_z:280,
  offset_xy_accepted:true,offset_z_accepted:true,dock_verified:true,
  offset_xy_verified:true,offset_z_verified:true,pickup_verified:true,
  dropoff_verified:true,heater_verified:true,sensor_verified:true,commissioned:true});
 assert.equal(classify(ready,0,12,{readyForMotion:true,controlVerified:true}).code,'AWAITING_VERIFICATION');
 assert.equal(classify(ready,1,12,{readyForMotion:true,controlVerified:true}).code,'READY');
 assert.equal(classify({...ready,reference_verified:true},0,12,{readyForMotion:true,controlVerified:true}).code,'READY');
 assert.equal(classify(ready,1,12,{readyForMotion:false,controlVerified:false}).code,'PRINTER_OFFLINE');
 assert.equal(classify(ready,1,12,{readyForMotion:true,controlVerified:false}).code,'PRINTER_OFFLINE');
});
test('migration and lockout enforce fail closed behaviour',()=>{
 assert.equal(classify(tool(),10,12,{migrationRequired:true}).canCalibrate,false);
 assert.equal(classify(tool({maintenance_lockout:true}),10,12).canCalibrate,false);
 assert.equal(classify(tool(),10,12).canPickup,false);
});
