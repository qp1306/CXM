/* CXM Clear All must never mask an attached tool or bypass Klipper recovery. */
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const read=(kind,name)=>fs.readFileSync(path.join(__dirname,'..',kind,name),'utf8');
const html=read('web','index.html'),client=read('web','cxm-native-control.js'),approved=read('web','cxm-approved-v1.js');
const backend=read('server','cxm_native.py'),service=read('server','cxm_service.py'),macro=read('vendor/cxm','cxm_native_toolchange.cfg');
test('Clear All is visible after load/unload with explicit physical removal note',()=>{
 for(const id of ['cxmClearAllBox','cxmClearAllAck','cxmClearAllButton','cxmClearAllState','cxmClearAllResult'])
  assert.match(html,new RegExp('id="'+id+'"'));
 assert.match(html,/Remove the hotend from the carriage and return it to its dock/);
 assert.match(approved,/fromId\('cxmClearAllBox'/);
 assert.match(html,/cxm-native-control\.js\?v=clear-all1/);
});
test('client only posts guarded named recovery; never direct movement',()=>{
 assert.match(client,/post\('clear-all'/);
 assert.match(client,/state\.sensor!=='RELEASED'/);
 assert.match(client,/state\.native_ready!==true/);
 assert.match(client,/reply\.cleared!==true/);
 assert.match(client,/after\.current_tool!==-1/);
 assert.match(client,/after\.fault!==0/);
 assert.match(client,/after\.running!==false/);
 assert.doesNotMatch(client,/\/printer\/gcode\/script|\bG1 [XYZ]|\bG0 [XYZ]/);
});
test('backend requires acknowledgement, matching revision and released sensor',()=>{
 assert.match(service,/\/v1\/native\/clear-all/);
 assert.match(service,/native_clear_all\(self\.server\.store/);
 assert.match(backend,/def clear_all\(store, expected_revision, acknowledgement\):/);
 assert.match(backend,/if sensor != 'RELEASED':/);
 assert.match(backend,/saved\['revision'\] != expected_revision/);
 assert.match(backend,/MOVE_LOCK\.acquire\(blocking=False\)/);
 assert.match(backend,/CXM_RECOVER CONFIRM=EMPTY/);
 assert.match(backend,/after_test\.get\('running'\) != 0/);
 assert.match(backend,/after_test\.get\('stop'\) != 0/);
 assert.match(backend,/calibration_preserved': True/);
});
test('guarded recovery macro cancels test, verifies EMPTY and never makes XY moves',()=>{
 const m=macro.split('[gcode_macro CXM_RECOVER]')[1].split('[gcode_macro CXM_TEST_RESET]')[0];
 assert.match(m,/CONFIRM=EMPTY/);
 assert.match(m,/UPDATE_DELAYED_GCODE ID=CXM_NATIVE_TEST_STEP DURATION=0/);
 assert.match(m,/CXM_TEST_RESET/);
 assert.match(m,/CXM_FAST_VERIFY EXPECT=RELEASED/);
 assert.match(m,/VARIABLE=current_tool VALUE=-1/);
 assert.match(m,/VARIABLE=fault VALUE=0/);
 assert.doesNotMatch(m,/(?:^|\n)\s*G[01]\s/i);
});
test('live client gating blocks PRESSSED/UNKNOWN, allows approved EMPTY only',()=>{
 const start=client.indexOf('const CLEAR_ALL_ACK='),end=client.indexOf('function controls(){',start);
 assert.ok(start>0&&end>start);
 const make=(sensor,ready,approved,busy=false,inert=false)=>{
   const ack={checked:approved},button={disabled:false},info={textContent:''};
   const ids={cxmClearAllAck:ack,cxmClearAllButton:button,cxmClearAllState:info};
   const context={state:sensor===null?null:{sensor,native_ready:ready},busy,panel:{inert},$:id=>ids[id],String};
   vm.runInNewContext(client.slice(start,end)+'\nclearAllControls();',context);
   return {button,info};
 };
 assert.equal(make('PRESSED',true,true).button.disabled,true);
 assert.equal(make(null,true,true).button.disabled,true);
 assert.equal(make('RELEASED',false,true).button.disabled,true);
 assert.equal(make('RELEASED',true,false).button.disabled,true);
 assert.equal(make('RELEASED',true,true,true).button.disabled,true);
 assert.equal(make('RELEASED',true,true,false,true).button.disabled,true);
 assert.equal(make('RELEASED',true,true).button.disabled,false);
});
