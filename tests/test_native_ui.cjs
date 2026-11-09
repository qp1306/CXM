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
 assert.match(html,/src="cxm-multi\.js\?v=1\.0\.0"/);
 assert.doesNotMatch(html,/src="cxm-t0-auto\.js/);
 assert.doesNotMatch(html,/src="cxm-tools\.js/);
});

test('selected hotend UI only requests named Klipper macros through native API',()=>{
 assert.match(native,/api\+'native\/status'/);
 assert.match(native,/post\('select'/);
 assert.match(native,/I_CONFIRMED_SELECTED_HOTEND_IDENTITY_AND_FULL_XY_PATH_CLEAR/);
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
