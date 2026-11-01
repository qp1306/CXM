/* CXM V0.3 — read-only overview of validated, disk-saved tool settings.
 * Works with no MCU. Never sends motion G-code or labels a saved dock as calibrated.
 */
(function () {
  'use strict';
  const format = v => v == null ? '—' : Number(v).toFixed(3);
  const speed = v => v == null ? '—' : String(Number(v).toFixed(0));
  const row = (name, value) => '<div class="tool-row"><span>' + name + '</span><b>' + value + '</b></div>';
  function card(tool, n, count) {
    const inRange = n < count;
    const present = !!tool && inRange && tool.enabled === true;
    const hasDock = present && [tool.dock_x,tool.dock_y,tool.dock_z].every(v => v != null);
    const label = !tool ? 'Config unavailable'
      : !inRange ? 'Outside tool count'
      : !present ? 'Disabled'
      : hasDock ? 'Saved · not verified' : 'Dock not calibrated';
    const state = !present ? 'inactive' : hasDock ? 'configured' : 'unconfigured';
    const dock = tool ? [tool.dock_x,tool.dock_y,tool.dock_z].map(format).join(' / ') : '— / — / —';
    const offsets = tool ? [tool.offset_x,tool.offset_y,tool.offset_z].map(format).join(' / ') : '— / — / —';
    const approach = tool ? speed(tool.approach_speed) + ' mm/min' : '—';
    const engage = tool ? speed(tool.dock_speed) + ' mm/min' : '—';
    const edit = tool ? '<button class="btn" data-cxm-edit="' + n + '" title="Edit saved settings without moving the printer">Edit</button>'
                      : '<button class="btn" disabled>Edit</button>';
    return {
      state,
      html: '<div class="tool-header"><strong>T' + n + '</strong><span class="dock-label">' + label + '</span></div>'
        + '<div class="tool-sub">Hotend ' + n + (n===0?' · reference':'') + '</div>'
        + row('Dock XYZ (mm)',dock)
        + row('Tool offsets XYZ (mm)',offsets)
        + row('Approach speed',approach)
        + row('Dock speed',engage)
        + row('Temperature','— (not connected)')
        + '<div class="tool-buttons"><button class="btn primary" disabled title="Pickup unavailable until verified CXM macros are installed">Pick up</button>'
        + edit
        + (present ? '<button class="btn" data-cxm-calibrate="' + n + '" title="Open dock coordinate editor">Calibrate</button>' : '<button class="btn" disabled title="Tool not enabled">Calibrate</button>') + '</div>'
    };
  }
  function render(snapshot) {
    if (typeof document==='undefined') return;
    const config=snapshot?.config;
    const cards=document.querySelectorAll('.tool-card');
    const count=Number.isInteger(config?.globals?.tool_count) ? config.globals.tool_count : 0;
    const tools=Array.isArray(config?.tools) ? config.tools : [];
    let enabled=0, savedDock=0;
    cards.forEach((element,n) => {
      const t=tools[n];
      // Hide any tool beyond the configured count or explicitly disabled.
      // All 12 profiles remain available via Settings for future expansion.
      const visible=!!t && n<count && t.enabled===true;
      element.hidden=!visible;
      if(visible) enabled++;
      if(visible && [t.dock_x,t.dock_y,t.dock_z].every(v=>v!=null)) savedDock++;
      if(!visible) return;
      const result=card(t,n,count);
      element.dataset.profileState=result.state;
      element.innerHTML=result.html;
      const edit=element.querySelector('[data-cxm-edit]');
      if(edit)edit.addEventListener('click',() => {
        if(typeof window!=='undefined')window.dispatchEvent(new CustomEvent('cxm-edit-tool',{detail:{tool:n}}));
      });
      const calibrate=element.querySelector('[data-cxm-calibrate]');
      if(calibrate)calibrate.addEventListener('click',() => {
        if(typeof window!=='undefined')window.dispatchEvent(new CustomEvent('cxm-calibrate-tool',{detail:{tool:n}}));
      });
    });
    const summary=document.getElementById('cxmToolSummary');
    if(summary)summary.textContent=config ?
      enabled+' shown / '+count+' configured · '+savedDock+' with saved dock XYZ'
      : 'Configuration unavailable';
    const toolsStat=document.getElementById('cxmActiveTools');
    if(toolsStat)toolsStat.textContent=config ? enabled+' active' : 'Unavailable';
    const noTools=document.getElementById('cxmNoTools');
    if(noTools)noTools.hidden=!(config && enabled===0);
    const safe=document.getElementById('cxmSafeY');
    if(safe)safe.textContent='Safe Y: '+(config ? format(config.globals.safe_y)+' mm' : '—');
    const adjust=document.getElementById('cxmXAdjust');
    if(adjust)adjust.textContent='X docking adjust: '+(config ? format(config.globals.x_docking_adjust)+' mm' : '—');
  }
  const api={card,render,format};
  if(typeof module!=='undefined' && module.exports) module.exports=api;
  if(typeof window!=='undefined')window.CXMToolCards=api;
})();
