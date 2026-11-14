/* Guided T0–T11 setup is never an automatic commissioning bypass. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const web=n=>fs.readFileSync(path.join(__dirname,'..','web',n),'utf8');
const ui=web('cxm-approved-v1.js'),settings=web('cxm-settings.js'),dock=web('cxm-dock.js'),index=web('index.html');
test('all 12 slots accessible for supervised setup, no direct motion',()=>{
 assert.match(ui,/for\(let n=0;n<12;n\+\+\)/);
 assert.match(ui,/if\(role==='tools'&&\(!opt\|\|opt\.disabled\)\)\{setupSlot\(n\);return;\}/);
 assert.match(ui,/if\(role==='dock'&&\(!opt\|\|!Number\.isInteger\(count\)\|\|n>=count\)\)\{setupSlot\(n\);return;\}/);
 assert.match(ui,/new CustomEvent\('cxm-calibrate-tool'/);
 assert.doesNotMatch(ui,/\/printer\/gcode|SET_GCODE_OFFSET|CARTOGRAPHER_TOUCH_PROBE|method:\s*['"]POST|\bgit\s+reset/i);
});
test('count increase is delegated to version-checked existing autosave',()=>{
 assert.match(ui,/control\.dispatchEvent\(new Event\('change'/);
 assert.match(settings,/expected_revision:snapshot\.revision/);
 assert.match(settings,/latest\.config\?\.globals\?\.tool_count!==next/);
 assert.match(settings,/new CustomEvent\('cxm-tool-count-saved'/);
 assert.match(settings,/new CustomEvent\('cxm-tool-count-save-failed'/);
 assert.match(ui,/if\(event\.detail\?\.tool_count!==count\)/);
});
test('dock selection waits for new source snapshot instead of falling back to T0',()=>{
 assert.match(dock,/if \(snapshot && n < snapshot\.config\.globals\.tool_count && !dirty\) render\(\)/);
 assert.match(dock,/document\.querySelector\('\[data-tab="calibration"\]'\)\?\.click\(\)/);
});
test('no new path to auto-commission, never invent coordinates',()=>{
 assert.doesNotMatch(ui,/dock_reference_accepted\s*:\s*true|commissioned\s*:\s*true|SET_GCODE_VARIABLE|save_dock/);
 assert.match(ui,/Maintenance lockout · open Settings/);
 assert.match(index,/cxm-approved-v1\.js\?v=1\.4-compact/);
});
