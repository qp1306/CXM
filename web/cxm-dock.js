/* CXM V0.9.1 — dock editor, live preflight and provisional capture-to-draft handoff.
   No printer motion, endstop probing, heating or sensor commands. */
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
      .filter(p => p.n < count);
  };
  // Selection is decided by tool_count. Only explicit maintenance lockout,
  // pending migration or an unavailable config prevents editing provisional XYZ.
  const canEdit = () => !!snapshot && !snapshot.migration_required
    && selected < snapshot.config.globals.tool_count
    && snapshot.config.tools[selected]?.maintenance_lockout !== true;
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
  // Match the backend's dock coordinate bounds. Backend validation remains
  // authoritative; this only prevents invalid or incomplete UI submissions.
  const limits = {x:[-50,600],y:[-50,600],z:[-20,600]};
  function validDraft() {
    if (!snapshot || busy || !dirty || !canEdit()) return false;
    try {
      const xyz=readDraft();
      return axis.every(name=>xyz[name]>=limits[name][0] && xyz[name]<=limits[name][1])
        && axis.some(name=>xyz[name]!==current()['dock_'+name]);
    } catch { return false; }
  }
  function updateActions() {
    get('cxmDockAccept').disabled=!validDraft();
  }
  function markDraft() {
    if (!snapshot || busy || !canEdit()) return;
    dirty = true;
    updateActions();
    report(validDraft()
      ? 'Valid XYZ draft ready. Accept all three coordinates to AutoSave; no motion will occur.'
      : 'Enter complete X/Y/Z coordinates within X/Y −50…600 mm and Z −20…600 mm before saving.', !validDraft());
  }
  function fill() {
    const tool = current();
    for (const name of axis) {
      const el = get('cxmDock' + name.toUpperCase());
      el.value = tool?.['dock_'+name] == null ? '' : String(tool['dock_'+name]);
      el.disabled = !canEdit() || busy;
    }
    dirty = false;
    const hasValues = tool && axis.every(name => tool['dock_'+name] != null);
    get('cxmDockStatus').textContent = !tool ? 'No selected tool'
      : !canEdit() ? 'LOCKED / MIGRATION · read only'
      : hasValues ? 'Saved · unverified' : 'Dock not calibrated';
    get('cxmDockSummary').textContent = tool
      ? 'T'+selected+' saved dock XYZ: '+axis.map(name => nice(tool['dock_'+name])).join(' / ')+
        ' mm · source: CXM_variables.cfg · not active in Klipper'
      : 'No profile selected. Choose a tool from the configured count.';
    updateActions(); // Never enable Save for empty or unchanged coordinates.
  }
  function render() {
    const select = get('cxmDockTool');
    const options = snapshot ? configured(snapshot.config) : [];
    if (!options.some(x => x.n === selected)) selected = options[0]?.n ?? 0;
    select.replaceChildren();
    for (const option of options) {
      const node = document.createElement('option');
      node.value = String(option.n);
      const state=window.CXMToolState?.classify(option.tool,option.n,
        snapshot.config.globals.tool_count,{migrationRequired:snapshot.migration_required});
      node.textContent = 'T'+option.n+(option.n===0?' · reference':'')+
        ' · '+(state?.label||'NOT READY');
      select.append(node);
    }
    select.value = String(selected);
    select.disabled = busy || !options.length;
    select.style.borderColor=window.CXMToolStyle?.color(selected)||'#45576b';
    window.CXMToolPicker?.sync(select,snapshot.config);
    fill();
    if (!busy) report(!options.length
      ? 'No selected hotends. Configure the count in Tools.'
      : !canEdit()
      ? 'T'+selected+' has a maintenance lockout or requires configuration migration. Saved coordinates are read-only.'
      : 'T'+selected+' is selected but NOT READY. Draft XYZ may be saved; physical verification is still required.', !options.length || !canEdit());
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

  // Read-only Moonraker status is informational. Never use it to grant
  // motion, permit calibration acceptance, or mark a tool verified.
  function liveField(id, label, cls='live-pending') {
    const node=get(id);
    if (!node) return;
    node.textContent=label;
    node.classList.remove('live-ok','live-pending','live-error');
    node.classList.add(cls);
  }
  function resetLive(message) {
    liveField('cxmDockLiveKlipper','Unavailable','live-error');
    liveField('cxmDockLiveHoming','Unknown','live-error');
    liveField('cxmDockLiveState','Unknown','live-error');
    liveField('cxmDockLivePosition','Unavailable','live-error');
    liveField('cxmDockLiveHomingTest','Not verified','live-pending');
    get('cxmDockLiveUpdated').textContent=message;
  }
  async function moonrakerRead(path) {
    const res=await fetch(path,{credentials:'same-origin',cache:'no-store'});
    if (!res.ok) throw new Error('Moonraker HTTP '+res.status);
    const data=await res.json();
    if (data.error || !data.result || typeof data.result!=='object') {
      throw new Error('Moonraker did not return a valid status result');
    }
    return data.result;
  }
  async function updateLiveStatus() {
    try {
      const info=await moonrakerRead('/printer/info');
      if (info.state!=='ready') {
        resetLive('Klipper state: '+String(info.state||'unknown')+
          '. This is a read-only status; no calibration is authorised.');
        return;
      }
      const listed=await moonrakerRead('/printer/objects/list');
      const names=Array.isArray(listed.objects)?listed.objects:[];
      if (!names.includes('toolhead')) throw new Error('Klipper toolhead is unavailable');
      const queries=['toolhead'];
      if (names.includes('idle_timeout')) queries.push('idle_timeout');
      if (names.includes('print_stats')) queries.push('print_stats');
      const data=await moonrakerRead('/printer/objects/query?'+queries.join('&'));
      const st=data.status||{};
      const toolhead=st.toolhead;
      if (!toolhead || typeof toolhead!=='object') throw new Error('Missing toolhead status');
      const homed=typeof toolhead.homed_axes==='string'?toolhead.homed_axes:'';
      const xyz=['x','y','z'].every(axis=>homed.includes(axis));
      const idle=st.idle_timeout?.state;
      const print=st.print_stats?.state;
      const state=print && !['standby','complete','cancelled','error'].includes(print)
        ? 'Print: '+print
        : idle==='Ready'||idle==='Idle'
        ? idle+' (Klipper)'
        : idle ? idle+' (Klipper)' : 'Idle status unknown';
      const position=toolhead.position;
      const finiteXYZ=Array.isArray(position) && position.length>=3
        && position.slice(0,3).every(n=>typeof n==='number' && Number.isFinite(n));
      liveField('cxmDockLiveKlipper','Ready (reported)','live-ok');
      liveField('cxmDockLiveHoming',xyz?'XYZ homed (reported)':homed.toUpperCase()||'Not homed',
        xyz?'live-ok':'live-pending');
      liveField('cxmDockLiveState',state,
        (['Ready','Idle'].includes(idle) && (!print ||
          ['standby','complete','cancelled','error'].includes(print)))?'live-ok':'live-pending');
      liveField('cxmDockLivePosition',finiteXYZ
        ? position.slice(0,3).map(v=>v.toFixed(3)).join(' / ')+' mm'
        : 'Position unavailable',finiteXYZ?'live-ok':'live-pending');
      liveField('cxmDockLiveHomingTest',xyz
        ? 'XYZ reported homed · physical validation pending'
        : 'Not all axes reported homed · physical validation pending',
        'live-pending');
      get('cxmDockLiveUpdated').textContent=
        'Updated from Moonraker (read-only). XYZ is the CURRENT carriage position, NOT the dock location. '+
        'Klipper homing does not verify motor directions, endstops or safe docking clearance.';
    } catch (e) {
      resetLive('Moonraker live preflight unavailable: '+e.message+
        '. Saved dock drafts remain separate. No motion or verification is authorised.');
    }
  }

  async function load() {
    if (busy) return;
    if (dirty && !window.confirm('Discard unsaved dock XYZ draft and reload the saved coordinates?')) return;
    try {
      snapshot = await getJSON('/config');
      render();
    } catch (e) {
      snapshot = null;
      render();
      report('Configuration service unavailable: '+e.message+'. No coordinates have been changed.',true);
    } finally {
      // Always refresh live status, even when saved config is inaccessible.
      // Never alter motion/saving safety gates based on this report.
      await updateLiveStatus();
    }
  }
  async function accept() {
    if (!validDraft()) {
      report('Complete and validate all three XYZ coordinates before accepting.',true);
      return;
    }
    let xyz;
    try { xyz = readDraft(); }
    catch (e) { report(e.message,true); return; }
    if (!window.confirm('Accept provisional XYZ for T'+selected+'? All three coordinates will be saved together and backed up.\n\nThis does NOT verify a pickup or move the printer.')) return;
    busy = true;
    const save = get('cxmDockAccept');
    save.disabled = true;
    get('cxmDockTool').disabled = true;
    report('Validating and saving all three axes atomically…');
    let verified=false;
    try {
      const reply = await postJSON('/dock',{tool:selected,xyz,expected_revision:snapshot.revision});
      if (!reply.saved) throw new Error('The service did not confirm the save');
      const fresh = await getJSON('/config');
      const stored = fresh.config.tools[selected];
      if (!axis.every(name => stored['dock_'+name] === xyz[name]))
        throw new Error('Disk verification did not match the requested coordinates');
      snapshot = fresh;
      dirty = false;
      verified=true;
      window.dispatchEvent(new Event('cxm-dock-saved'));
    } catch (e) {
      report('Save not verified: '+e.message+'. Review the current values before retrying.',true);
      // Keep the draft on screen if an operation fails. Use Refresh to reconcile.
    } finally {
      busy = false;
      get('cxmDockTool').disabled = !snapshot || !configured(snapshot.config).length;
      if (verified) {
        fill(); // Re-enable inputs after the request and show the saved values.
        report('T'+selected+' dock XYZ saved and verified on disk · backup created if changed · NOT verified in Klipper.');
      } else {
        // On failure, retain the user's draft and make its inputs editable.
        for (const name of axis) get('cxmDock'+name.toUpperCase()).disabled=!canEdit();
        updateActions();
      }
    }
  }
  get('cxmDockRefresh').addEventListener('click',load);
  get('cxmDockTool').addEventListener('change',e => {
    if (busy) return;
    if (dirty && !window.confirm('Discard unsaved dock XYZ draft and switch hotends?')) {
      e.currentTarget.value=String(selected);
      return;
    }
    selected=Number(e.currentTarget.value);
    e.currentTarget.style.borderColor=window.CXMToolStyle?.color(selected)||'#45576b';
    fill();
    report(canEdit()
      ? 'T'+selected+' selected. Draft edits are local until accepted; hardware remains unverified.'
      : 'T'+selected+' is locked or requires migration; edit blocked.', !canEdit());
    window.CXMToolPicker?.sync(e.currentTarget,snapshot.config);
  });
  for (const name of axis) {
    const node=get('cxmDock'+name.toUpperCase());
    node.addEventListener('focus',()=>activeAxis=name);
    node.addEventListener('input',markDraft);
  }
  root.querySelectorAll('[data-dock-adjust]').forEach(btn=>btn.addEventListener('click',()=>{
    const input=get('cxmDock'+activeAxis.toUpperCase());
    if (!snapshot || busy || !canEdit()) return;
    if (input.value.trim()==='') { report('Enter a starting '+activeAxis.toUpperCase()+' coordinate before adjusting.',true); return; }
    const n=Number(input.value), step=Number(btn.dataset.dockAdjust);
    if (!Number.isFinite(n)||!Number.isFinite(step)) return;
    input.value=(Math.round((n+step)*1000000)/1000000).toFixed(3);
    markDraft();
  }));
  // The independent read-only dock reviewer may propose raw XY for this
  // selected tool. Draft only; never save, move, unlock or modify Z automatically.
  window.addEventListener('cxm-dock-provisional-xy',event=>{
    const proposal=event.detail||{},n=proposal.tool;
    if (proposal.source!=='manual-mcu-review'||!Number.isInteger(n)||n!==selected
        ||!Number.isFinite(proposal.x)||!Number.isFinite(proposal.y)
        ||proposal.x<0||proposal.x>limits.x[1]
        ||proposal.y<0||proposal.y>limits.y[1]) {
      report('Rejected provisional XY: tool or captured coordinates do not match the dock editor.',true);
      return;
    }
    if (busy||!canEdit()) {
      report('Dock XY draft rejected: selected tool is locked or configuration is unavailable.',true);
      return;
    }
    const xInput=get('cxmDockX'),yInput=get('cxmDockY');
    if (dirty && (xInput.value.trim()!==''||yInput.value.trim()!=='') &&
        !window.confirm('Replace the existing unsaved X/Y draft for T'+selected+
          '? The separately entered Z coordinate will remain untouched.')) return;
    xInput.value=Number(proposal.x).toFixed(5);
    yInput.value=Number(proposal.y).toFixed(5);
    markDraft();
    report('T'+selected+' provisional raw X/Y copied into draft. Z is unchanged. '+
      'No X docking adjustment applied; no AutoSave, physical verification or motion occurred.');
  });
  get('cxmDockAccept').addEventListener('click',accept);
  get('cxmDockReset').addEventListener('click',()=>{if(!busy){fill();report('Draft reset to the last saved coordinates.');}});
  get('cxmDockBackups').addEventListener('click',()=>{
    document.querySelector('[data-tab="settings"]')?.click();
    setTimeout(()=>get('cxmHistory')?.click(),250);
  });
  document.querySelector('[data-tab="calibration"]')?.addEventListener('click',()=>{
    if (!dirty) load(); // Preserve unsaved drafts when switching tabs.
  });
  window.addEventListener('cxm-calibrate-tool',event=>{
    const n=event.detail?.tool;
    if (!Number.isInteger(n)||n<0||n>=12) return;
    if (dirty && n!==selected && !window.confirm('Discard unsaved dock XYZ draft and switch hotends?')) return;
    if (n!==selected) { selected=n; dirty=false; }
    document.querySelector('[data-tab="calibration"]')?.click();
    if (snapshot && !dirty) render(); // Preserve same-tool unsaved draft.
  });
  load();
})();
