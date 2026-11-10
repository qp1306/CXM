/* CXM V0.6 Axiscope, palette, selector and no-motion regression tests */
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const read=p=>fs.readFileSync(path.join(__dirname,'../web/'+p),'utf8');
const html=read('index.html'),axis=read('cxm-axiscope.js'),cards=read('cxm-tool-cards.js');
const picker=read('cxm-tool-picker.js'),colors=require('../web/cxm-tool-style.js');
test('12 distinct stable tool colours and T0 reference',()=>{
 assert.equal(colors.palette.length,12);assert.equal(new Set(colors.palette).size,12);
 assert.equal(colors.color(0),'#B6C4D5');assert.equal(colors.color(10),'#B2DA75');
 assert.match(cards,/CXMToolStyle\?\.color\(n\)/);
 assert.match(axis,/n===0\?' REF'/);
});
test('Axiscope supports secure Moonraker camera discovery',()=>{
 assert.match(axis,/\/server\/webcams\/list/);
 assert.match(axis,/url\.origin!==origin/);
 assert.match(axis,/url\.username \|\| url\.password/);
 assert.match(axis,/cameraURL\(entry\.stream_url,window\.location\.origin\)/);
});
test('coloured custom picker works with native select fallback',()=>{
 assert.match(picker,/cxm-picker-option/);
 assert.match(picker,/CXMToolStyle\?\.color\(n\)/);
 assert.match(picker,/dispatchEvent\(new Event\('change',\{bubbles:true\}\)\)/);
 assert.match(picker,/role','option'/);
 assert.match(picker,/event\.key==='Escape'/);
 assert.match(picker,/ArrowDown/);
 assert.match(picker,/select\.classList\.add\('cxm-native-tool-select'\)/);
 assert.match(html,/\.cxm-picker-option\[/);
});
test('selected tools show readiness independently of manual maintenance lockout',()=>{
 assert.match(axis,/function selectedTools\(\)/);
 assert.match(axis,/\.filter\(x=>x\.n<config\.globals\.tool_count\)/);
 assert.match(axis,/CXMToolState\?\.classify\(p,n,config\.globals\.tool_count/);
 assert.match(axis,/window\.CXMToolPicker\?\.sync\(selector,config\)/);
 assert.match(axis,/state\.textContent=readiness\?\.label/);
 assert.match(html,/<th>Tool status<\/th>/);
 const dock=read('cxm-dock.js'),settings=read('cxm-settings.js');
 assert.match(dock,/\.filter\(p => p\.n < count\)/);
 assert.match(dock,/maintenance_lockout !== true/);
 assert.match(settings,/cfg\.tools\.slice\(0,count\)\.map/);
});
test('Tool XY always shows the camera and supervised jogs with the optical comparison',()=>{
 const panel=html.split('<section data-panel="offsets" hidden>')[1].split('</section>')[0];
 assert.doesNotMatch(panel,/<details|future hardware/);
 assert.match(panel,/id="cxmAxisJogRows"/);
 assert.match(panel,/id="cxmManualApprovalXY"/);
 assert.match(panel,/id="cxmJogClearXY"/);
 assert.doesNotMatch(panel,/id="cxmManualCaptureXY"/);
 assert.doesNotMatch(axis,/\/printer\/gcode\/script|G1\s+[XY]|SET_GCODE_OFFSET|postJSON\(/);
 assert.match(html,/id="cxmAxisFrame"/);
 assert.match(html,/id="cxmAxisTable"/);
});
