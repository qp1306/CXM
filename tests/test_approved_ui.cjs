/* CXM approved seven-page design — motion and commissioning invariants. */
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const web=n=>fs.readFileSync(path.join(__dirname,'..','web',n),'utf8');
const js=web('cxm-approved-v1.js'),css=web('cxm-approved-v1.css'),index=web('index.html'),z=web('cxm-z-auto.js');
test('approved theme is added after existing UI; all 7 original page tabs retained',()=>{
 assert.match(index,/cxm-approved-v1\.css\?v=1\.4-compact/);
 assert.match(index,/cxm-approved-v1\.js\?v=1\.4-compact/);
 for(const name of ['tools','calibration','offsets','z-calibration','tests','updates','settings'])
  assert.match(index,new RegExp(`data-panel="${name}"`));
});
test('approved layout never sends motion, changes backend or applies offsets',()=>{
 assert.doesNotMatch(js,/\/printer\/gcode|SET_GCODE_OFFSET|CARTOGRAPHER_TOUCH_PROBE|SAVE_CONFIG|method:\s*['"]POST|\bgit\s+(reset|clean|push)/i);
 assert.match(js,/PRESENTATION ONLY/);
 assert.match(js,/fetch\('\/cxm\/api\/v1\/config'/);
});
test('native tool motion and camera changes retain original guarded buttons',()=>{
 for(const id of ['cxmNativeToolPanel','cxmNativeSelect','cxmNativeUnload','cxmToolsChangeSlot','cxmAxisChangeSlot','cxmCameraTools','cxmManualDock','cxmManualCapture'])
  assert.match(index,new RegExp(`id="${id}"`));
 assert.match(js,/!target\.disabled/);
 assert.match(js,/target\.closest\('fieldset:disabled'\)/);
 assert.match(js,/target\.closest\('\[inert\]'\)/);
 assert.match(js,/original\.disabled\|\|panel\?\.inert/);
 assert.match(js,/original\.click\(\)/);
 assert.match(js,/cxmCameraTools button\[data-tool\]/);
});
test('12 Tool Z slots visible but tool enablement remains guarded',()=>{
 assert.match(z,/Array\.from\(\{length:12\}/);
 assert.match(z,/data\.dock_reference_accepted===true/);
 assert.match(z,/status\?\.physical_enabled===true/);
 assert.match(z,/return \{t,accepted,gated,xy,enabled:accepted&&gated\}/);
 assert.match(z,/choice\.disabled=locked\|\|running\|\|toolBusy\|\|preparing/);
});
test('all workflows have numbered steps, but only status feedback can verify',()=>{
 for(const name of ['tools','calibration','offsets','tests','updates','settings'])
  assert.match(js,new RegExp(`${name.replace(/[-/\\^$*+?.()|[\]{}]/g,'\\$&')}:\\{title:`));
 assert.match(js,/const \{states\}=checkState\(name\)/);
 assert.match(js,/b\.dataset\.state=v/);
 assert.match(js,/current===String\(n\)/);
 assert.match(js,/stageEls/);
});
test('style maintains minimal overflow and existing saved calibration UI',()=>{
 assert.match(css,/@media\(max-width:450px\)/);
 assert.match(css,/\.cxma-toolbank/);
 assert.match(css,/\.cxma-cam-grid/);
 assert.match(css,/label\.cxm-capture-ack\[hidden\]\{display:none!important\}/);
 assert.match(index,/id="cxmZResultsTable"/);
 assert.match(index,/id="cxmZAutoStart"/);
});
