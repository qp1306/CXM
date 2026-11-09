/* CXM V0.9.1 — dock editor, live preflight and provisional capture-to-draft handoff.
   No printer motion, endstop probing, heating or sensor commands. */
(() => {
  'use strict';
  const root = document.querySelector('[data-panel="calibration"]');
  if (!root) return;
  const base = '/cxm/api/v1';
  const get = id => document.getElementById(id);
  const axis = ['x','y'];
  let snapshot = null, selected = 0, busy = false, dirty = false, activeAxis = 'x';
  let rawDraft=null; // Legacy MCU provenance remains schema-compatible, never used for manual captures.
  let migrationMessage='';

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
  // pending migration or an unavailable config prevents editing provisional XY.
  const canEdit = () => !!snapshot && !snapshot.migration_required
    && selected < snapshot.config.globals.tool_count
    && snapshot.config.tools[selected]?.maintenance_lockout !== true;
  function readDraft() {
    const xy = {};
    for (const name of axis) {
      const el = get('cxmDock' + name.toUpperCase());
      const v = el.value.trim();
      if (v === '' || !Number.isFinite(Number(v))) throw new Error('Enter a finite number for '+name.toUpperCase());
      xy[name] = Number(v);
    }
    return xy;
  }
  function current() { return snapshot?.config?.tools?.[selected]; }
  // Match the backend's dock coordinate bounds. Backend validation remains
  // authoritative; this only prevents invalid or incomplete UI submissions.
  const limits = {x:[-50,600],y:[-50,600]};
  function validDraft() {
    if (!snapshot || busy || !dirty || !canEdit()) return false;
    try {
      const xy=readDraft();
      return axis.every(name=>xy[name]>=limits[name][0] && xy[name]<=limits[name][1])
        && (axis.some(name=>xy[name]!==current()['dock_'+name]) ||
            current().dock_z != null || !current().dock_reference_accepted ||
            (rawDraft && axis.some(name=>rawDraft[name]!==current()['lineux_raw_'+name])));
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
      ? 'X/Y dock coordinates ready to save. No motion will occur.'
      : 'Enter valid X/Y coordinates within −50…600 mm before saving.', !validDraft());
  }
  function fill() {
    const tool = current();
    for (const name of axis) {
      const el = get('cxmDock' + name.toUpperCase());
      el.value = tool?.['dock_'+name] == null ? '' : String(tool['dock_'+name]);
      el.disabled = !canEdit() || busy;
    }
    dirty = false;rawDraft=null;
    const hasValues = tool && axis.every(name => tool['dock_'+name] != null);
    get('cxmDockStatus').textContent = !tool ? 'No selected tool'
      : !canEdit() ? 'LOCKED / MIGRATION · read only'
      : hasValues && tool.dock_reference_accepted ? 'CxChanger datum saved · unverified'
      : hasValues ? 'Old XY reference · recapture/reaccept required'
      : 'CxChanger datum not calibrated';
    get('cxmDockSummary').textContent = tool
      ? 'T'+selected+' CxChanger locking-hole XY: '+
        axis.map(name => nice(tool['dock_'+name])).join(' / ')+
        ' mm · ' +
        ' · '+(tool.dock_reference_accepted?'accepted for supervised testing':'NOT accepted')
      : 'No profile selected. Choose a tool from the configured count.';
    updateActions(); // Never enable Save for empty or unchanged coordinates.
  }
  function renderMigration(){
    const box=get('cxmDockMigration'),button=get('cxmDockMigrate');
    const pending=snapshot?.migration_required===true;
    box.hidden=!pending;
    button.disabled=!pending||busy;
    if(pending)get('cxmDockMigrationText').textContent=migrationMessage||
      'Saved coordinates stay in place. The current file is backed up, then upgraded to schema 3. '+
      'Old motion verification is cleared and must be tested again. No motors move and Klipper does not restart.';
  }
  function render() {
    renderMigration();
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
      : 'T'+selected+' selected. Dock XY may be saved; physical pickup remains unverified.', !options.length || !canEdit());
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

  async function migrate(){
    if(busy||!snapshot?.migration_required)return;
    if(!window.confirm(
      'BACK UP AND UPGRADE CXM CONFIGURATION TO SCHEMA 3?\n\n'+
      'This creates a backup of CXM_variables.cfg and retains saved XY coordinates, '+
      'tool offsets and selected tool count. Previous motion verification is reset.\n\n'+
      'No printer movement or Klipper restart. Continue?'))return;
    busy=true;renderMigration();
    const feedback=get('cxmDockMigrationText');
    migrationMessage='Checking saved revision and preparing backup…';
    feedback.textContent=migrationMessage;
    try{
      const before=await getJSON('/config');
      if(before.revision!==snapshot.revision)throw Error('Configuration changed. Refresh and review before upgrading.');
      if(!before.migration_required)throw Error('Configuration was already upgraded. Refresh the page.');
      if(before.config?.schema!==3)throw Error('Current backend cannot project schema 3. Update CXM backend first.');
      const tracked=['dock_x','dock_y','offset_x','offset_y','offset_z'];
      const values=before.config.tools.map(t=>tracked.map(k=>t[k]));
      const count=before.config.globals.tool_count;
      const reply=await postJSON('/migrate',{expected_revision:before.revision});
      if(!reply.saved||typeof reply.backup!=='string')throw Error('Backup and migration were not both confirmed by the service.');
      const [after,history]=await Promise.all([getJSON('/config'),getJSON('/history')]);
      if(after.migration_required||after.config?.schema!==3)throw Error('Schema 3 migration not verified.');
      if(!Array.isArray(history.backups)||!history.backups.includes(reply.backup))
        throw Error('Backup was not found in backup history.');
      if(after.config.globals.tool_count!==count||
         after.config.tools.some((t,n)=>tracked.some((k,i)=>t[k]!==values[n][i])))
        throw Error('Saved XY or offsets differ after migration; inspect backup history.');
      snapshot=after;dirty=false;rawDraft=null;migrationMessage='';
      render();
      report('Configuration upgraded to schema 3 with verified backup '+reply.backup+
        '. Saved XY retained; confirm the dock datum and independently test each movement.');
      window.dispatchEvent(new Event('cxm-config-migrated'));
    }catch(e){
      migrationMessage='Upgrade not verified: '+e.message+' No movement was commanded.';
      feedback.textContent=migrationMessage;
      report('Configuration upgrade: '+e.message,true);
      // A server-side commit may have succeeded before a later check failed.
      // Read disk again rather than repeating the migration on stale state.
      try{
        snapshot=await getJSON('/config');
        if(!snapshot.migration_required){render();report('Configuration upgraded on disk. Review backup history and saved values before movement.');}
      }catch{}
    }finally{
      busy=false;renderMigration();
      await updateLiveStatus();
    }
  }
  async function load() {
    if (busy) return;
    if (dirty && !window.confirm('Discard unsaved dock XY draft and reload the saved coordinates?')) return;
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
      report('Enter valid X/Y dock coordinates before accepting.',true);
      return;
    }
    let xy;
    try { xy = readDraft(); }
    catch (e) { report(e.message,true); return; }
    if (!window.confirm('Save provisional dock XY for T'+selected+'? A configuration backup will be created.\n\nThis does NOT verify pickup or move the printer.')) return;
    busy = true;
    const save = get('cxmDockAccept');
    save.disabled = true;
    get('cxmDockTool').disabled = true;
    report('Validating and saving dock X/Y atomically…');
    let verified=false;
    try {
      const reply = await postJSON('/dock',{tool:selected,xy,expected_revision:snapshot.revision,
        ...(rawDraft?{raw_xy:rawDraft}:{})});
      if (!reply.saved) throw new Error('The service did not confirm the save');
      const fresh = await getJSON('/config');
      const stored = fresh.config.tools[selected];
      if (!axis.every(name => stored['dock_'+name] === xy[name]) ||
          stored.dock_z !== null || stored.dock_reference_accepted!==true ||
          (rawDraft && !axis.every(name=>stored['lineux_raw_'+name]===rawDraft[name])))
        throw new Error('Disk verification did not match the requested coordinates');
      snapshot = fresh;
      dirty = false;rawDraft=null;
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
        report('T'+selected+' motor-on dock XY saved as provisional. '+
          'Now run ONE supervised pickup/dropoff to verify physical geometry.');
      } else {
        // On failure, retain the user's draft and make its inputs editable.
        for (const name of axis) get('cxmDock'+name.toUpperCase()).disabled=!canEdit();
        updateActions();
      }
    }
  }
  window.addEventListener('cxm-dock-save-completed',()=>load());
  get('cxmDockRefresh').addEventListener('click',load);
  get('cxmDockMigrate').addEventListener('click',migrate);
  get('cxmDockTool').addEventListener('change',e => {
    if (busy) return;
    if (dirty && !window.confirm('Discard unsaved dock XY draft and switch hotends?')) {
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
    node.addEventListener('input',()=>{rawDraft=null;markDraft();});
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
  // selected tool. Draft only; never save, move, or unlock the printer.
  window.addEventListener('cxm-dock-provisional-xy',event=>{
    const proposal=event.detail||{},n=proposal.tool;
    if (proposal.source!=='motor-on-capture'||!Number.isInteger(n)||n!==selected
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
          '? This will replace the current unsaved XY values.')) return;
    xInput.value=Number(proposal.x).toFixed(5);
    yInput.value=Number(proposal.y).toFixed(5);
    rawDraft=null;
    markDraft();
    report('T'+selected+' CxChanger docking-hole XY copied from Lineux measurement. '+
      (proposal.source==='manual-mcu-review'
        ? 'Manual review (no measurement provenance). '
        : 'Captured Lineux raw XY + current X/Y datum offsets. ')+
      'No AutoSave or physical verification occurred.');
  });
  get('cxmDockAccept').addEventListener('click',accept);
  get('cxmDockReset').addEventListener('click',()=>{if(!busy){fill();report('Draft reset to the last saved coordinates.');}});
  get('cxmDockBackups').addEventListener('click',()=>{
    document.querySelector('[data-tab="settings"]')?.click();
    setTimeout(()=>get('cxmHistory')?.click(),250);
  });
  window.addEventListener('cxm-config-migrated',()=>{if(!busy)load();});
  document.querySelector('[data-tab="calibration"]')?.addEventListener('click',()=>{
    if (!dirty) load(); // Preserve unsaved drafts when switching tabs.
  });
  window.addEventListener('cxm-calibrate-tool',event=>{
    const n=event.detail?.tool;
    if (!Number.isInteger(n)||n<0||n>=12) return;
    if (dirty && n!==selected && !window.confirm('Discard unsaved dock XY draft and switch hotends?')) return;
    if (n!==selected) { selected=n; dirty=false; }
    document.querySelector('[data-tab="calibration"]')?.click();
    if (snapshot && !dirty) render(); // Preserve same-tool unsaved draft.
  });
  load();
})();
