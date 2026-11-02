/* CXM V0.6.1 settings editor; API served from loopback Python through Nginx. */
(() => {
  'use strict';
  const endpoint = '/cxm/api/v1';
  let snapshot = null;
  let tool = 0;
  let saving = false;
  const root = document.getElementById('configEditor');
  if (!root) return;
  const badge = document.getElementById('saveStatus');
  const definitions = {
    global: [['tool_count', 'Configured tools', 1], ['safe_y', 'Safe Y position (mm)', 0.1],
             ['x_docking_adjust', 'X docking adjustment (mm)', 0.01]],
    tool: [['dock_x', 'Dock X (mm)', 0.001],
           ['dock_y', 'Dock Y (mm)', 0.001], ['dock_z', 'Dock Z (mm)', 0.001],
           ['offset_x', 'X offset (mm)', 0.001], ['offset_y', 'Y offset (mm)', 0.001],
           ['offset_z', 'Z offset (mm)', 0.001],
           ['approach_speed', 'Approach speed (mm/min)', 1],
           ['dock_speed', 'Dock speed (mm/min)', 1]]
  };
  const escape = val => String(val).replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
  function status(message, warning=false) {
    badge.textContent = message;
    badge.style.color = warning ? '#eeb48d' : '';
  }
  function fields(scope, data) {
    return definitions[scope].map(([key, label, step]) => {
      const v = data[key];
      const value = v == null ? '' : v;
      const input = typeof v === 'boolean' ?
        `<input data-cxm="${scope}" data-key="${key}" type="checkbox" ${v?'checked':''}>` :
        `<input data-cxm="${scope}" data-key="${key}" type="number" step="${step}" value="${escape(value)}" placeholder="Not calibrated" style="width:150px;padding:8px;border-radius:6px;background:#161b23;border:1px solid #465061;color:#ecf0f6">`;
      return `<label class="kv"><span>${escape(label)}</span>${input}</label>`;
    }).join('');
  }
  function lockoutControl(profile) {
    const locked=profile.maintenance_lockout===true;
    const readonly=snapshot.migration_required===true;
    return `<label class="cxm-lockout-panel ${locked?'is-locked':'is-unlocked'} ${readonly?'is-readonly':''}">
      <span class="cxm-lockout-content">
        <span class="cxm-lockout-eyebrow">SAFETY OVERRIDE · HOTEND T${tool}</span>
        <span class="cxm-lockout-title">MAINTENANCE LOCKOUT</span>
        <span class="cxm-lockout-status" id="cxmLockoutState">${locked?'LOCKED OUT — calibration blocked':'UNLOCKED — calibration permitted'}</span>
        <span class="cxm-lockout-description">Use when a hotend is faulty, removed or under maintenance. Unlocking does not mean READY; physical calibration and verification remain mandatory.</span>
        <span class="cxm-lockout-saved" id="cxmLockoutPersist">${readonly?'Migration required · read-only':'AutoSave · current state loaded from disk'}</span>
      </span>
      <span class="cxm-lockout-action">
        <span class="cxm-lockout-track">
          <input class="cxm-lockout-input" id="cxmMaintenanceLockout" type="checkbox" role="switch"
            data-cxm="tool" data-key="maintenance_lockout"
            aria-label="Maintenance lockout for hotend T${tool}"
            ${locked?'checked':''} ${readonly?'disabled':''}>
          <span class="cxm-lockout-thumb" aria-hidden="true"></span>
        </span>
        <span class="cxm-lockout-onoff">${locked?'ON':'OFF'}</span>
      </span>
    </label>`;
  }
  function toolCards() {
    if (window.CXMToolCards) window.CXMToolCards.render(snapshot);
    const countSelect=document.getElementById('cxmCountSelect');
    if(countSelect) {
      countSelect.disabled=!snapshot || saving || snapshot.migration_required===true;
      if(snapshot) countSelect.value=String(snapshot.config.globals.tool_count);
    }
    const hint=document.getElementById('cxmCountHint');
    if(hint) {
      if(!snapshot) hint.textContent='Saved tool count unavailable';
      else {
        const count=snapshot.config.globals.tool_count;
        const locked=Array.from({length:count},(_,n)=>n)
          .filter(n=>snapshot.config.tools[n]?.maintenance_lockout===true);
        hint.textContent=snapshot.migration_required?'Legacy config: explicit migration required before editing'
          : locked.length?locked.length+' maintenance lockout(s) · inspect in Settings'
          :'Selected tools are NOT READY until calibrated and verified';
      }
    }
  }
  async function getJSON(url) {
    const r=await fetch(url,{cache:'no-store',credentials:'same-origin'});
    const d=await r.json();
    if(!r.ok) throw new Error(d.error||`HTTP ${r.status}`);
    return d;
  }
  async function postJSON(path,payload) {
    const r=await fetch(endpoint+path,{method:'POST',credentials:'same-origin',
      headers:{'Content-Type':'application/json','X-Requested-With':'CXM'},body:JSON.stringify(payload)});
    const d=await r.json();
    if(!r.ok) throw new Error(d.error||`HTTP ${r.status}`);
    return d;
  }
  async function load() {
    if (saving) return;
    try {
      snapshot = await getJSON(endpoint+'/config');
      render(); toolCards();
      status('AutoSave ready · disk only');
    } catch(e) {
      snapshot=null;
      toolCards(); // Clear stale saved values if the config backend becomes unreachable.
      root.innerHTML=`<div class="notice error">Configuration backend not available: ${escape(e.message)}. Install CXM V0.2 backend once using the Python bootstrap in GitHub's README. No settings have been changed.</div>`;
      status('Config backend offline',true);
    }
  }
  function render() {
    const cfg=snapshot.config;
    const count=cfg.globals.tool_count;
    if (tool>=count || tool<0) tool=0;
    root.innerHTML=`<div class="panel" style="margin-top:16px">
      <div class="panel-heading"><h3>CXM_variables.cfg</h3><span class="panel-label">AutoSave · backups · rollback</span></div>
      <p class="muted">Every accepted field change is saved immediately. Values are on disk, <b>not yet active in Klipper</b>. Verification flags are protected from manual editing.</p>
      <div style="margin-top:20px"><h3>Global settings</h3>${fields('global',cfg.globals)}</div>
      <div style="margin-top:20px;display:flex;align-items:center;gap:14px"><h3 style="margin:0">Hotend settings</h3><select id="cxmToolChoice" style="padding:9px;border-radius:6px;background:#161b23;border:1px solid #465061;color:white">${cfg.tools.slice(0,count).map((profile,i)=>`<option value="${i}" ${tool===i?'selected':''}>T${i}${profile.maintenance_lockout===true?' · locked out':''}</option>`).join('')}</select></div>
      ${lockoutControl(cfg.tools[tool])}
      ${fields('tool',cfg.tools[tool])}
      <p class="helper" id="cxmReadiness">Readiness requires hardware verification.</p>
      <div class="cxm-migration-slot" id="cxmMigrateSlot"></div>
      <div class="buttons"><button id="cxmReload" class="btn">Refresh settings</button><button id="cxmHistory" class="btn">Backup history / rollback</button></div>
      <div id="cxmFeedback" class="helper">Revision: ${escape(snapshot.revision.slice(0,12))} · Saved on disk · Not active in Klipper</div>
      <div id="cxmBackups" hidden></div>
    </div>`;
    root.querySelector('#cxmToolChoice').addEventListener('change',e=>{tool=Number(e.target.value);render();});
    const readiness=window.CXMToolState?.classify(cfg.tools[tool],tool,count,{migrationRequired:snapshot.migration_required});
    root.querySelector('#cxmReadiness').textContent=
      'Readiness: '+(readiness?.label||'NOT READY')+' — '+(readiness?.reason||'Unverified')+
      '. Zero offsets are not proof of calibration.';
    if(snapshot.migration_required){
      const note=document.createElement('div');
      note.className='cxm-migration-notice';
      note.setAttribute('role','status');
      const heading=document.createElement('strong');
      heading.textContent='CONFIGURATION MIGRATION REQUIRED';
      const explanation=document.createElement('p');
      explanation.textContent='Legacy schema 1 is loaded read-only. The reviewed schema-2 migration preserves coordinates/speeds, backs up the original, and sets ALL verification flags to false. No motor movement or Klipper restart.';
      const button=document.createElement('button');
      button.id='cxmMigrate';button.className='btn';
      button.textContent='Back up and migrate configuration';
      button.addEventListener('click',migrate);
      note.append(heading,explanation,button);
      root.querySelector('#cxmMigrateSlot').append(note);
      root.querySelectorAll('[data-cxm]').forEach(input=>input.disabled=true);
    }
    window.CXMToolPicker?.sync(root.querySelector('#cxmToolChoice'),cfg);
    root.querySelector('#cxmReload').addEventListener('click',load);
    root.querySelector('#cxmHistory').addEventListener('click',showHistory);
    root.querySelectorAll('[data-cxm]').forEach(input=>input.addEventListener('change',()=>saveField(input)));
  }
  // Count selects a tool range; manual maintenance lockout is independent.
  async function saveToolCount(input) {
    const prior=snapshot?.config?.globals?.tool_count;
    const next=Number(input.value);
    if(!snapshot || saving || snapshot.migration_required || !Number.isInteger(next) || next<1 || next>12) {
      if(prior!=null)input.value=String(prior);
      return;
    }
    if(next===prior)return;
    saving=true;
    input.disabled=true;
    status('Saving hotend count…');
    try {
      const result=await postJSON('/setting',{tool:'global',key:'tool_count',value:next,expected_revision:snapshot.revision});
      if(!result.saved)throw new Error('The configuration service did not confirm the save.');
      const latest=await getJSON(endpoint+'/config');
      if(latest.config?.globals?.tool_count!==next)throw new Error('Saved count could not be verified.');
      snapshot=latest;
      render();toolCards();
      status('AutoSaved '+next+' selected tool slots · disk only');
    }catch(e) {
      status('Tool count not verified: '+e.message,true);
      window.alert('CXM could not verify the tool count: '+e.message);
      await loadAfterSave();
    }finally {
      saving=false;
      input.disabled=!snapshot;
      if(snapshot)input.value=String(snapshot.config.globals.tool_count);
    }
  }
  document.getElementById('cxmCountSelect')?.addEventListener('change',e=>saveToolCount(e.currentTarget));
  async function saveField(input) {
    if(!snapshot||saving||snapshot.migration_required)return;
    const key=input.dataset.key;
    const scope=input.dataset.cxm;
    const isBool=input.type==='checkbox';
    if(key==='maintenance_lockout' && isBool && !input.checked &&
       snapshot.config.tools[tool].maintenance_lockout===true){
      if(!window.confirm('Remove maintenance lockout from T'+tool+'?\\n\\nCalibration will be permitted, but the hotend will remain NOT READY until physical verification. Pickup and movement remain disabled.')){
        input.checked=true;
        status('Maintenance lockout unchanged · T'+tool+' remains locked out');
        return;
      }
    }
    const raw=input.value.trim();
    const value=isBool?input.checked:raw===''?null:Number(raw);
    if(!isBool && raw!=='' && !Number.isFinite(value)){
      status('Invalid numeric value',true);return;
    }
    saving=true;
    status(key==='maintenance_lockout'?'Saving T'+tool+' maintenance lockout…':'Saving…');
    const localFeedback=root.querySelector('#cxmLockoutPersist');
    if(key==='maintenance_lockout' && localFeedback)localFeedback.textContent='Saving to CXM_variables.cfg…';
    root.querySelectorAll('[data-cxm]').forEach(x=>x.disabled=true);
    try{
      const result=await postJSON('/setting',{tool:scope==='global'?'global':tool,key,value,expected_revision:snapshot.revision});
      status(result.saved?'Saved to disk · pending Klipper integration':'Save rejected',!result.saved);
      await loadAfterSave();
    }catch(e){
      status('Save failed: '+e.message,true);
      window.alert('CXM setting was not saved: '+e.message);
      await loadAfterSave();
    }finally{saving=false;}
  }
  async function migrate(){
    if(!snapshot || saving || !snapshot.migration_required)return;
    const question=['Migrate CXM_variables.cfg to schema 2?',
      'The original file will be backed up and all numeric calibration values preserved.',
      'Every verification flag will start FALSE. Legacy T6–T11 were disabled by default,',
      'so confirm their hardware separately before any future commissioning.',
      'This will not move the printer or restart Klipper.'].join('\n\n');
    if(!window.confirm(question))return;
    saving=true;status('Backing up and migrating…');
    try{
      const response=await postJSON('/migrate',{expected_revision:snapshot.revision});
      if(!response.saved)throw new Error('Migration not confirmed');
      const fresh=await getJSON(endpoint+'/config');
      if(fresh.migration_required || fresh.config?.schema!==2)
        throw new Error('Schema 2 could not be verified from disk');
      snapshot=fresh;render();toolCards();
      status('Schema 2 verified · backup preserved · all tools unverified');
    }catch(e){
      status('Migration not verified: '+e.message,true);
      window.alert('CXM migration not verified: '+e.message);
      await loadAfterSave();
    }finally{saving=false;}
  }
  async function loadAfterSave(){
    try{snapshot=await getJSON(endpoint+'/config');render();toolCards();}
    catch(e){status('Could not verify saved configuration: '+e.message,true);}
  }
  async function showHistory() {
    const panel=root.querySelector('#cxmBackups');
    panel.hidden=false;
    panel.textContent='Reading backup history…';
    try {
      const data=await getJSON(endpoint+'/history');
      panel.innerHTML=data.backups.length
       ? `<p class="muted">Select a prior snapshot to restore it. CXM will first back up the current values.</p><select id="cxmBackupSelect" style="max-width:100%;padding:8px;background:#161b23;color:white">${data.backups.map(name=>`<option value="${escape(name)}">${escape(name)}</option>`).join('')}</select><button id="cxmRollback" class="btn" style="margin:8px">Restore selected backup</button>`
       : '<p class="muted">No backups yet; one will be created with the first accepted edit.</p>';
      const btn=panel.querySelector('#cxmRollback');
      if(btn)btn.addEventListener('click',async()=>{
        if(saving)return;
        const name=panel.querySelector('#cxmBackupSelect').value;
        if(!confirm(`Restore ${name}? Current settings will be backed up first.`))return;
        saving=true;status('Restoring backup…');
        try{
          await postJSON('/rollback',{name,expected_revision:snapshot.revision});
          status('Backup restored to disk · not active in Klipper');
          await loadAfterSave();
        }catch(e){status('Rollback failed: '+e.message,true);window.alert('Rollback failed: '+e.message);}
        finally{saving=false;}
      });
    } catch(e) {panel.textContent='Cannot read backups: '+e.message;}
  }
  document.querySelector('[data-tab="settings"]')?.addEventListener('click',()=>{if(!saving)load();});
  window.addEventListener('cxm-dock-saved',()=>{if(!saving)load();});
  window.addEventListener('cxm-edit-tool', event => {
    const n=event.detail?.tool;
    if (!snapshot || !Number.isInteger(n) || n<0 || n>=snapshot.config.tools.length) return;
    tool=n;
    document.querySelector('[data-tab="settings"]')?.click();
    render();
    root.scrollIntoView({behavior:'smooth',block:'start'});
  });
  // Refresh displayed saved values after returning to Tools. Avoid overwriting
  // a currently edited Settings form or interrupting a disk write.
  document.querySelector('[data-tab="tools"]')?.addEventListener('click', () => {if(!saving)load();});
  document.addEventListener('visibilitychange', () => {
    if(document.visibilityState==='visible' && !saving && !document.querySelector('[data-panel="tools"]').hidden) load();
  });
  load();
})();
