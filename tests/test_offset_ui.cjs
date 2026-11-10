/* Main-page simplicity and functional XY/Z offset editors */
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const web=name=>fs.readFileSync(path.join(__dirname,'../web',name),'utf8');
const html=web('index.html'),ui=web('cxm-offset-editor.js');
test('normal nav has only useful pages and diagnostics are accessible from Settings',()=>{
 for(const tab of ['tools','calibration','offsets','z-calibration','updates','settings'])
   assert.match(html,new RegExp('data-tab="'+tab+'"'));
 assert.match(html,/data-tab="tests" hidden/);
 assert.match(html,/id="cxmOpenDiagnostics"/);
 assert.match(ui,/\$\('cxmOpenDiagnostics'\)/);
});
test('XY and Z editors have active inputs, saving and clear failure feedback',()=>{
 for(const id of ['cxmXYEditTool','cxmXYEditX','cxmXYEditY','cxmXYEditSave','cxmXYEditStatus',
                   'cxmZEditTool','cxmZEditValue','cxmZEditSave','cxmZEditStatus'])
   assert.match(html,new RegExp('id="'+id+'"'));
 assert.match(html,/cxm-offset-editor\.js\?v=[\w.-]+/);
 assert.match(ui,/method:'POST'/);
 assert.match(ui,/\/cxm\/api\/v1\/offset/);
 assert.match(ui,/expected_revision:snapshot\.revision/);
 assert.match(ui,/stored\['offset_'\+axis\]===data\[axis\]/);
 assert.match(ui,/pick\[mode\]===0/);
 assert.doesNotMatch(ui,/\/printer\/gcode\/script|SET_GCODE_OFFSET|G1 X|G1 Z/);
});
test('high-density diagnostics are optional while baseline editors are visible',()=>{
 const xy=html.split('<section data-panel="offsets" hidden>')[1].split('</section>')[0];
 const z=html.split('<section data-panel="z-calibration" hidden>')[1].split('</section>')[0];
 assert.ok(xy.indexOf('<h3>Axiscope camera')<xy.indexOf('Save tool XY offset'));
 assert.ok(z.indexOf('Save tool Z offset')<z.indexOf('Advanced · Cartographer Touch'));
 assert.match(xy,/id="cxmAxisTool"/);
 assert.match(z,/id="cxmZTool"/);
 assert.match(html,/Advanced · Diagnostics and system information/);
 assert.match(html,/id="cxmT0Auto"/);
});
test('Settings has no duplicate docking or offset editor or obsolete dock Z',()=>{
 const s=web('cxm-settings.js');
 assert.doesNotMatch(s,/\['dock_z',/);
 assert.doesNotMatch(s,/\['offset_z',/);
 assert.doesNotMatch(s,/\['dock_x',/);
 assert.match(s,/\['approach_speed',/);
 assert.match(s,/maintenance_lockout/);
});
