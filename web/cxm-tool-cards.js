/* CXM V0.6 — saved tool overview with safe readiness classification.
   No MCU or motion. All values shown are saved but not active in Klipper. */
(function(){
  'use strict';
  const format=v=>v==null?'—':Number(v).toFixed(3);
  const row=(name,value)=>'<div class="tool-row"><span>'+name+'</span><b>'+value+'</b></div>';
  const stateApi=typeof require==='function'?require('./cxm-tool-state.js'):window.CXMToolState;
  function card(tool,n,count,runtime={}) {
    const s=stateApi.classify(tool,n,count,runtime);
    const dock=tool?[tool.dock_x,tool.dock_y].map(format).join(' / '):'— / —';
    const offsets=tool?[tool.offset_x,tool.offset_y,tool.offset_z].map(format).join(' / '):'— / — / —';
    const label=s.code==='LOCKED_OUT'?'LOCKED OUT':s.code==='READY'?'READY':
      s.code==='CONFIG_UNAVAILABLE'?'CONFIG UNAVAILABLE':
      s.code==='PRINTER_OFFLINE'?'PRINTER OFFLINE':s.label;
    const canEdit=!!tool && s.selected && runtime.migrationRequired!==true;
    const edit=canEdit?'<button class="btn" data-cxm-edit="'+n+'">Settings</button>':
      '<button class="btn" disabled>Settings</button>';
    const calibrate=s.canCalibrate?
      '<button class="btn primary" data-cxm-calibrate="'+n+'">Dock XY</button>':
      '<button class="btn" disabled title="Calibration locked">Dock XY</button>';
    return {state:s.code,
      html:'<div class="tool-header"><strong class="cxm-tool-chip">T'+n+'</strong>'+
      '<span class="dock-label cxm-readiness-label">'+label+'</span></div>'+
      '<div class="tool-sub">Hotend '+n+(n===0?' · reference':'')+'</div>'+
      '<div class="cxm-tool-readiness-detail">'+s.reason+'</div>'+
      row('Dock XY (mm)',dock)+row('Tool offsets XYZ (mm)',offsets)+
      '<div class="tool-buttons">'+calibrate+edit+'</div>'};
  }
  function render(snapshot){
    if(typeof document==='undefined')return;
    const config=snapshot?.config;
    const count=Number.isInteger(config?.globals?.tool_count)?config.globals.tool_count:0;
    const tools=Array.isArray(config?.tools)?config.tools:[];
    const migrationRequired=snapshot?.migration_required===true;
    let shown=0,ready=0,locked=0,unready=0,calibrated=0;
    document.querySelectorAll('.tool-card').forEach((element,n)=>{
      const tool=tools[n];
      const visible=!!tool && n<count;
      element.hidden=!visible;
      if(!visible)return;
      shown++;
      const state=stateApi.classify(tool,n,count,{migrationRequired});
      if(state.code==='READY')ready++;
      else if(state.code==='LOCKED_OUT')locked++;
      else unready++;
      if(['AWAITING_VERIFICATION','PRINTER_OFFLINE','READY'].includes(state.code))calibrated++;
      const result=card(tool,n,count,{migrationRequired});
      element.dataset.profileState=result.state;
      element.classList?.toggle('cxm-needs-attention',state.code!=='READY');
      element.classList?.toggle('cxm-maintenance',state.code==='LOCKED_OUT');
      element.style?.setProperty('--tool-color',typeof window==='undefined'?'#b6c4d5':(window.CXMToolStyle?.color(n)||'#b6c4d5'));
      element.innerHTML=result.html;
      const edit=element.querySelector('[data-cxm-edit]');
      if(edit)edit.addEventListener('click',()=>{if(typeof window!=='undefined')
        window.dispatchEvent(new CustomEvent('cxm-edit-tool',{detail:{tool:n}}));});
      const calibrate=element.querySelector('[data-cxm-calibrate]');
      if(calibrate)calibrate.addEventListener('click',()=>{if(typeof window!=='undefined')
        window.dispatchEvent(new CustomEvent('cxm-calibrate-tool',{detail:{tool:n}}));});
    });
    const summary=document.getElementById('cxmToolSummary');
    if(summary)summary.textContent=config
      ? shown+' selected · '+calibrated+' calibration accepted · '+ready+' ready · '+unready+' not ready'+(locked?' · '+locked+' locked out':'')
      : 'Configuration unavailable';
    const stat=document.getElementById('cxmActiveTools');
    if(stat)stat.textContent=config
      ? ready+' READY / '+shown+' selected':'Unavailable';
    const banner=document.getElementById('cxmNoTools');
    if(banner)banner.hidden=!!config;
    const safe=document.getElementById('cxmSafeY');
    if(safe)safe.textContent='Safe Y: '+(config?format(config.globals.safe_y)+' mm':'—');
    const adjust=document.getElementById('cxmXAdjust');
    if(adjust)adjust.textContent='X docking adjust: '+(config?format(config.globals.x_docking_adjust)+' mm':'—');
  }
  const api={card,render,format};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  if(typeof window!=='undefined')window.CXMToolCards=api;
})();