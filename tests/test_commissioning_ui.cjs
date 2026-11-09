/* Manual dock alignment replaces deprecated MCU counter calculation. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
const tests=fs.readFileSync(path.join(__dirname,'../web/cxm-testing.js'),'utf8');
const manual=fs.readFileSync(path.join(__dirname,'../web/cxm-manual.js'),'utf8');
const dock=fs.readFileSync(path.join(__dirname,'../web/cxm-dock.js'),'utf8');

test('Testing diagnostics remain available without old MCU capture UI',()=>{
 assert.match(html,/data-panel="tests"/);
 for(const id of ['cxmTestRun','cxmTestBaseline','cxmTestCompare',
                   'cxmTestDownload','cxmTestHomed','cxmTestHoming',
                   'cxmTestThermistor','cxmTestRestartResult'])
  assert.match(html,new RegExp('id="'+id+'"'));
 assert.match(html,/cxm-testing\.js\?v=0\.9\.3/);
 assert.doesNotMatch(html,/cxm-test-math\.js|cxm-dock-review\.js|cxm-lineux\.js/);
 assert.doesNotMatch(html,/id="cxmTestXYReview"|id="cxmDockCaptureToDraft"/);
 assert.match(tests,/getJSON\('\/cxm\/api\/v1\/runtime'\)/);
 assert.match(tests,/getJSON\('\/cxm\/api\/v1\/config'\)/);
 assert.match(tests,/getJSON\('\/printer\/info'\)/);
});
test('dock Save uses one atomic server request, no browser capture/save split',()=>{
 assert.match(html,/id="cxmManualCapture" disabled>Save dock position/);
 assert.match(manual,/request\('\/manual\/save'/);
 assert.doesNotMatch(manual,/request\('\/manual\/capture'/);
 assert.doesNotMatch(manual,/request\('\/dock'/);
 assert.match(manual,/!saved\.saved\|\|!saved\.verified/);
 assert.match(manual,/actual\.dock_x!==saved\.xy\.x/);
 assert.match(manual,/cxm-dock-save-completed/);
 assert.match(dock,/cxm-dock-save-completed/);
 assert.doesNotMatch(manual,/CXМ_SELECT_TOOL/);
});
test('manual jog is approved per operator and restored to prior modal state by backend',()=>{
 const backend=fs.readFileSync(path.join(__dirname,'../server/cxm_manual.py'),'utf8');
 assert.match(manual,/I_APPROVE_SUPERVISED_MOTOR_ON_JOG/);
 assert.match(backend,/CXM_MANUAL_DOCK_JOG TOOL=/);
 assert.doesNotMatch(backend,/(SAVE_GCODE_STATE NAME=CXM_MANUAL_JOG|G1 [XY])/);
 const klipper=fs.readFileSync(path.join(__dirname,'../vendor/cxm/cxm_native_toolchange.cfg'),'utf8');
 assert.match(klipper,/\[gcode_macro CXM_MANUAL_DOCK_JOG\]/);
 assert.match(klipper,/SAVE_GCODE_STATE NAME=CXM_MANUAL_JOG/);
 assert.match(klipper,/RESTORE_GCODE_STATE NAME=CXM_MANUAL_JOG MOVE=0/);
 assert.match(backend,/M400/);
 assert.match(backend,/stepper_z3/);
 assert.match(backend,/print_stats/);
 assert.match(backend,/PRESSED/);
 assert.doesNotMatch(backend,/SET_KINEMATIC_POSITION|DOCK_LOCATE_CALIBRATE/);
});

test('one T1 Save survives a slow status poll and verifies the selected dock',async()=>{
 const vm=require('node:vm');
 const nodes=new Map();
 function node(id){
   if(!nodes.has(id))nodes.set(id,{style:{},value:'',handlers:{},
     querySelectorAll:()=>[],addEventListener(type,fn){this.handlers[type]=fn;}});
   return nodes.get(id);
 }
 node('cxmDockTool').value='1';
 let interval,initial,release,hold=false;
 const posts=[],events=[],xy={x:251.00625,y:65.73125};
 const config={revision:'first',config:{tools:[{},{}]}};
 const live={revision:'first',ready:true,xy,z:25,sensor:'PRESSED'};
 vm.runInNewContext(manual,{
   document:{getElementById:node,querySelector:()=>null},
   window:{addEventListener(){},dispatchEvent:e=>events.push(e)},
   CustomEvent:class{constructor(type,{detail}){this.type=type;this.detail=detail;}},
   setInterval:fn=>{interval=fn;},setTimeout:fn=>{initial=fn;},
   async fetch(path,opts){
     let data=config;
     if(path.endsWith('status?tool=1'))data=live;
     if(hold){hold=false;await new Promise(r=>{release=r;});}
     if(opts.method==='POST'){
       assert.ok(path.endsWith('/manual/save'));
       posts.push(JSON.parse(opts.body));
       config.config.tools[1]={dock_x:xy.x,dock_y:xy.y,dock_reference_accepted:true};
       data={saved:true,verified:true,tool:1,xy,backup:'before.cfg'};
     }
     return {ok:true,json:async()=>data};
   }
 });
 await initial();
 hold=true;interval();
 assert.equal(node('cxmManualCapture').disabled,false);
 const save=node('cxmManualCapture').handlers.click();
 await node('cxmManualCapture').handlers.click();
 await save;
 release();
 await new Promise(r=>setImmediate(r));
 assert.deepEqual(posts.map(p=>[p.tool,p.expected_revision]),[[1,'first']]);
 assert.equal(events[0].detail.tool,1);
 assert.match(node('cxmManualFeedback').textContent,/SAVED T1.*251.00625.*65.73125/);
});
