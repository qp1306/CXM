const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const read=name=>fs.readFileSync(path.join(__dirname,'../web',name),'utf8');
const html=read('index.html');
const native=read('cxm-native-control.js');
const multi=read('cxm-multi.js');

test('native CXM Control Centre offers only the new toolchange controller',()=>{
 for(const id of ['cxmNativeToolPanel','cxmNativeSelectedTool','cxmNativeToolAck',
                  'cxmNativeSelect','cxmNativeUnload','cxmNativeSync',
                  'cxmNativeConfirm','cxmNativeRecover','cxmMultiStop']) {
   assert.match(html,new RegExp('id="'+id+'"'));
 }
 assert.match(html,/src="cxm-native-control\.js\?v=/);
 assert.match(html,/src="cxm-multi\.js\?v=1\.4\.0"/);
 assert.doesNotMatch(html,/src="cxm-t0-auto\.js/);
 assert.doesNotMatch(html,/src="cxm-tools\.js/);
});

test('single operator declaration replaces repetitive readiness checkbox flow',()=>{
 for(const id of ['cxmCarriageIdentity','cxmDeclareCarriage','cxmSpeedSimple']){
   assert.match(html,new RegExp('id="'+id+'"'));
 }
 assert.match(multi,/nativePost\('initialize'/);
 assert.match(multi,/carriage_tool:tool/);
 assert.match(multi,/\$\('cxmMultiStart'\)\.disabled=!ready;/);
 assert.match(native,/post\('simple-change'/);
 assert.match(native,/mounted_tool:mounted/);
});

test('high-speed profiles exposed with one-cycle limiter',()=>{
 for(const mode of ['sprint','race','boost']){
  assert.match(html,new RegExp('<option value="'+mode+'">'));
 }
 assert.match(multi,/\['sprint','race','boost','custom'\]\.includes\(selectedProfile\(\)\)/);
 assert.match(multi,/\$\('cxmMultiRepeats'\)\.value='1'/);
});

test('custom three-speed controls are present and used',()=>{
 for(const id of ['cxmCustomSpeedFields','cxmCustomTravel','cxmCustomApproach','cxmCustomLatch']){
   assert.match(html,new RegExp('id="'+id+'"'));
 }
 assert.match(html,/<option value="custom">/);
 assert.match(multi,/custom_speeds=values/);
 assert.match(multi,/function customSpeeds\(\)/);
});

test('custom speed limits increase without dropping native safety checks',()=>{
 const cfg=fs.readFileSync(path.join(__dirname,'../vendor/cxm/cxm_native_toolchange.cfg'),'utf8');
 assert.match(cfg,/travel > 1200 or approach < 1 or approach > 600 or latch < 1 or latch > 300/);
 assert.match(cfg,/G4 P30/);
 assert.match(cfg,/DURATION=0\.01/);
 assert.match(html,/id="cxmCustomTravel" min="10" max="1200"/);
 assert.match(html,/id="cxmCustomApproach" min="1" max="600"/);
 assert.match(html,/id="cxmCustomLatch" min="1" max="300"/);
});

test('selected hotend UI only requests named Klipper macros through native API',()=>{
 assert.match(native,/api\+'native\/status'/);
 assert.match(native,/post\('simple-change'/);
 assert.match(native,/expected_revision:state.revision/);
 assert.match(native,/cxmNativeToolAck/);
 assert.match(native,/current>=-1/);
 assert.doesNotMatch(native,/\/printer\/gcode\/script|\bG1 [XYZ]|\bG0 [XYZ]/);
});

test('multi-test UI preserves profile selection and stop-at-pair request',()=>{
 assert.match(multi,/function selectedMode\(\)\{return 'native';\}/);
 assert.match(multi,/requestBody\.execution_mode='native'/);
 assert.match(multi,/execution_mode==='stream'/); // historic status message fallback only
 assert.match(multi,/async function nativePost\(/);
 assert.match(multi,/STOP_AFTER_CURRENT_TOOL_PAIR/);
 assert.match(multi,/nativePost\('sync'/);
 assert.match(multi,/nativePost\('confirm-empty'/);
 assert.match(multi,/nativePost\('recover-empty'/);
 assert.match(multi,/current\?\.native_ready===true/);
 assert.match(multi,/selection\(\)\.length<=3/);
});
