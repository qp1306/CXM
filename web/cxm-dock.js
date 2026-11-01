/* CXM V0.4 — dock coordinate editor; all movement and sensor actions absent. */
(() => {
  'use strict';
  const root = document.querySelector('[data-panel="calibration"]');
  if (!root) return;
  const base = '/cxm/api/v1';
  const get = id => document.getElementById(id);
  const axis = ['x','y','z'];
  let snapshot = null, selected = 0, busy = false, dirty = false, activeAxis = 'x';

  const report = (message, error = false) => {
    const el = get('cxmDockFeedback');
    if (el) { el.textContent = message; el.style.color = error ? '#f4aaaa' : '#afc6db'; }
  };
  const nice = value => value == null ? '—' : Number(value).toFixed(3);
  const configured = data => {
    const count = data.globals.tool_count;
    return data.tools.map((tool,n) => ({tool,n}))
      .filter(p => p.n < count && p.tool.enabled === true);
  };
  function readDraft() {
    const xyz = {};
    for (const name of axis) {
      const el = get('cxmDock' + name.toUpperCase());
      const v = el.value.trim();
      if (v === '' || !Number.isFinite(Number(v))) throw new Error('Enter a finite number for '+name.toUpperCase());
      xyz[name] = Number(v);
    }
    return xyz;
  }
  function current() { return snapshot?.config?.tools?.[selected]; }
  function markDraft() {
    if (!snapshot || busy) return;
    dirty = true;
    report('Draft edited. Not saved until you accept all three coordinates. No motion will occur.');
  }
  function fill() {
    const tool = current();
    for (const name of axis) {
      const el = get('cxmDock' + name.toUpperCase());
      el.value = tool?.['dock_'+name] == null ? '' : String(tool['dock_'+name]);
      el.disabled = !tool || busy;
    }
    dirty = false;
    const hasValues = tool && axis.every(name => tool['dock_'+name] != null);
    get('cxmDockStatus').textContent = !tool ? 'No active tool' : hasValues ? 'Saved · unverified' : 'Dock not calibrated';
    get('cxmDockSummary').textContent = tool
      ? 'T'+selected+' saved dock XYZ: '+axis.map(name => nice(tool['dock_'+name])).join(' / ')+
        ' mm · source: CXM_variables.cfg · not active in Klipper'
      : 'No enabled tool selected. Enable the tool in Settings to create a dock position.';
    get('cxmDockAccept').disabled = !tool || busy;
  }
  function render() {
    const select = get('cxmDockTool');
    const options = snapshot ? configured(snapshot.config) : [];
    if (!options.some(x => x.n === selected)) selected = options[0]?.n ?? 0;
    select.replaceChildren();
    for (const option of options) {
      const node = document.createElement('option');
      node.value = String(option.n);
      node.textContent = 'T'+option.n;
      select.append(node);
    }
    select.value = String(selected);
    select.disabled = busy || !options.length;
    fill();
    if (!busy) report(options.length
      ? 'Ready to edit T'+selected+'. Draft XYZ can be accepted together with one backup; hardware verification is not available.'
      : 'No enabled hotends in the configured tool count.', !options.length);
  }
  async function getJSON(path) {
    const response = await fetch(base+path,{credentials:'same-origin',cache:'no-store'});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error||'HTTP '+response.status);
    return data;
  }
  async function postJSON(path,body) {
    const response = await fetch(base+path,{method:'POST',credentials:'same-origin',
      headers:{'Content-Type':'application/json','X-Requested-With':'CXM'},body:JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error||'HTTP '+response.status);
    return data;
  }
  async function load() {
    if (busy) return;
    try {
      snapshot = await getJSON('/config');
      render();
    } catch (e) {
      snapshot = null;
      render();
      report('Configuration service unavailable: '+e.message+'. No coordinates have been changed.',true);
    }
  }
  async function accept() {
    if (!snapshot || busy || !current()) return;
    let xyz;
    try { xyz = readDraft(); }
    catch (e) { report(e.message,true); return; }
    if (!window.confirm('Accept provisional XYZ for T'+selected+'? All three coordinates will be saved together and backed up.\n\nThis does NOT verify a pickup or move the printer.')) return;
    busy = true;
    const save = get('cxmDockAccept');
    save.disabled = true;
    get('cxmDockTool').disabled = true;
    report('Validating and saving all three axes atomically…');
    try {
      const reply = await postJSON('/dock',{tool:selected,xyz,expected_revision:snapshot.revision});
      if (!reply.saved) throw new Error('The service did not confirm the save');
      const fresh = await getJSON('/config');
      const stored = fresh.config.tools[selected];
      if (!axis.every(name => stored['dock_'+name] === xyz[name]))
        throw new Error('Disk verification did not match the requested coordinates');
      snapshot = fresh;
      dirty = false;
      window.dispatchEvent(new Event('cxm-dock-saved'));
      report('T'+selected+' dock XYZ AutoSaved together · backup created if changed · not verified or active in Klipper.');
    } catch (e) {
      report('Save not verified: '+e.message+'. Review the current values before retrying.',true);
      // Keep the draft on screen if an operation fails. Use Refresh to reconcile.
    } finally {
      busy = false;
      get('cxmDockTool').disabled = false;
      save.disabled = !current();
    }
  }
  get('cxmDockRefresh').addEventListener('click',load);
  get('cxmDockTool').addEventListener('change',e => {
    if (busy) return;
    selected=Number(e.currentTarget.value);
    fill();
    report('T'+selected+' selected. All draft edits are local until accepted.');
  });
  for (const name of axis) {
    const node=get('cxmDock'+name.toUpperCase());
    node.addEventListener('focus',()=>activeAxis=name);
    node.addEventListener('input',markDraft);
  }
  root.querySelectorAll('[data-dock-adjust]').forEach(btn=>btn.addEventListener('click',()=>{
    const input=get('cxmDock'+activeAxis.toUpperCase());
    if (!snapshot || busy || !current()) return;
    if (input.value.trim()==='') { report('Enter a starting '+activeAxis.toUpperCase()+' coordinate before adjusting.',true); return; }
    const n=Number(input.value), step=Number(btn.dataset.dockAdjust);
    if (!Number.isFinite(n)||!Number.isFinite(step)) return;
    input.value=(Math.round((n+step)*1000000)/1000000).toFixed(3);
    markDraft();
  }));
  get('cxmDockAccept').addEventListener('click',accept);
  get('cxmDockReset').addEventListener('click',()=>{if(!busy){fill();report('Draft reset to the last saved coordinates.');}});
  get('cxmDockBackups').addEventListener('click',()=>{
    document.querySelector('[data-tab="settings"]')?.click();
    setTimeout(()=>get('cxmHistory')?.click(),250);
  });
  document.querySelector('[data-tab="calibration"]')?.addEventListener('click',load);
  window.addEventListener('cxm-calibrate-tool',event=>{
    const n=event.detail?.tool;
    if (!Number.isInteger(n)||n<0||n>=12) return;
    selected=n;
    document.querySelector('[data-tab="calibration"]')?.click();
  });
  load();
})();
