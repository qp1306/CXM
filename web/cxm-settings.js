/* CXM V0.3 settings editor; API served from loopback Python through Nginx. */
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
    tool: [['enabled', 'Enabled', null], ['dock_x', 'Dock X (mm)', 0.001],
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
  function toolCards() {
    if (window.CXMToolCards) window.CXMToolCards.render(snapshot);
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
    root.innerHTML=`<div class="panel" style="margin-top:16px">
      <div class="panel-heading"><h3>CXM_variables.cfg</h3><span class="panel-label">AutoSave · backups · rollback</span></div>
      <p class="muted">Every accepted field change is saved immediately. Values are persistent on disk, but are <b>not yet active in Klipper</b>. Dock coordinates are unverified until pickup testing is implemented.</p>
      <div style="margin-top:20px"><h3>Global settings</h3>${fields('global',cfg.globals)}</div>
      <div style="margin-top:20px;display:flex;align-items:center;gap:14px"><h3 style="margin:0">Hotend settings</h3><select id="cxmToolChoice" style="padding:9px;border-radius:6px;background:#161b23;border:1px solid #465061;color:white">${cfg.tools.map((_,i)=>`<option value="${i}" ${tool===i?'selected':''}>T${i}</option>`).join('')}</select></div>
      ${fields('tool',cfg.tools[tool])}
      <div class="buttons"><button id="cxmReload" class="btn">Refresh settings</button><button id="cxmHistory" class="btn">Backup history / rollback</button></div>
      <div id="cxmFeedback" class="helper">Revision: ${escape(snapshot.revision.slice(0,12))} · Saved on disk · Not active in Klipper</div>
      <div id="cxmBackups" hidden></div>
    </div>`;
    root.querySelector('#cxmToolChoice').addEventListener('change',e=>{tool=Number(e.target.value);render();});
    root.querySelector('#cxmReload').addEventListener('click',load);
    root.querySelector('#cxmHistory').addEventListener('click',showHistory);
    root.querySelectorAll('[data-cxm]').forEach(input=>input.addEventListener('change',()=>saveField(input)));
  }
  async function saveField(input) {
    if(!snapshot||saving)return;
    const key=input.dataset.key;
    const scope=input.dataset.cxm;
    const isBool=input.type==='checkbox';
    const raw=input.value.trim();
    const value=isBool?input.checked:raw===''?null:Number(raw);
    if(!isBool && raw!=='' && !Number.isFinite(value)){
      status('Invalid numeric value',true);return;
    }
    saving=true;
    status('Saving…');
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
