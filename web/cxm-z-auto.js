/* CXM Tool Z v2 — ordered UI, explicit selected tools; backend owns every move. */
(()=>{
  'use strict';
  if(typeof document==='undefined')return;
  const root=document.getElementById('cxmZAutoPanel');if(!root)return;
  const el=id=>document.getElementById(id);
  const base='/cxm/api/v1/';
  let revision=null, config=null, native=null, preflight=null, status=null;
  let running=false, loading=false, toolBusy=false, preparing=false, referenceSet=false;
  let selected=[0], toolFeedback='', persistedWarning='';
  function toolLabel(t){return 'T'+t;}
  const toolsQuery=()=>selected.join(',');
  function stateChip(id,value,state){const e=el(id);if(!e)return;e.textContent=String(value);e.dataset.state=state||'warn';}
  function text(id,v){const e=el(id);if(e)e.textContent=String(v)}
  function errorText(e){return e?.message||String(e)}
  async function get(path){
    const r=await fetch(base+path,{credentials:'same-origin',cache:'no-store'});
    const j=await r.json();if(!r.ok)throw Error(j.error||'CXM service unavailable');return j;
  }
  async function post(path,data){
    const r=await fetch(base+path,{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-Requested-With':'CXM'},body:JSON.stringify(data)});
    const j=await r.json();if(!r.ok)throw Error(j.error||'Operation rejected');return j;
  }
  function toolCanMove(target){
    const needed=target===0?-1:0;
    const eligible=Array.isArray(native?.candidates)&&native.candidates.some(t=>t.tool===0&&t.eligible===true);
    return !preparing&&!toolBusy&&!running&&!loading&&!!el('cxmZAutoApprove').checked&&
      native?.native_ready===true&&!native.fault&&!native.running&&
      native.current_tool===needed&&native.sensor===(needed===-1?'RELEASED':'PRESSED')&&eligible;
  }
  function toolMessage(){
    if(toolFeedback)return toolFeedback;
    if(!native)return 'Native tool state unavailable.';
    if(native.running||running)return 'Tool test or Z calibration currently running.';
    if(!native.native_ready||native.fault)return 'Native toolchanger is not READY; use Prepare if carriage is physically EMPTY.';
    if(native.current_tool===-1&&native.sensor==='RELEASED')return 'Carriage EMPTY · T0 may be loaded manually.';
    if(native.current_tool===0&&native.sensor==='PRESSED')return 'T0 MOUNTED · unload after physical inspection.';
    return 'Carriage identity uncertain. Inspect the physical printer before commanding motion.';
  }
  function allowedTools(){
    const cfg=config?.config;
    const total=Number(cfg?.globals?.tool_count)||0;
    const tools=Array.isArray(cfg?.tools)?cfg.tools:[];
    return Array.from({length:Math.min(12,total)},(_,t)=>{
      const data=tools[t]||{};
      const accepted=data.dock_reference_accepted===true && !data.maintenance_lockout;
      // Tool-card selection uses the authoritative, live commissioning status.
      // Preflight is request-specific and can be temporarily null during a
      // selection refresh; it must gate Start, not erase selectable tools.
      const gate=Number(status?.max_commissioned_tool);
      const gated=status?.physical_enabled===true && Number.isInteger(gate) && gate>=t;
      const x=Number(data.dock_x),y=Number(data.dock_y);
      const xy=accepted&&Number.isFinite(x)&&Number.isFinite(y)?`X${x.toFixed(3)} / Y${y.toFixed(3)}`:'Dock not accepted';
      return {t,accepted,gated,xy,enabled:accepted&&gated};
    });
  }
  function drawToolChoices(){
    const grid=el('cxmZToolsGrid');if(!grid)return;
    grid.replaceChildren();
    const tools=allowedTools();
    if(!tools.length){grid.textContent='No configured tools available';return;}
    const valid=new Set(tools.filter(x=>x.enabled).map(x=>x.t));
    selected=selected.filter(t=>t===0||valid.has(t));
    if(!selected.includes(0))selected.unshift(0);
    selected.sort((a,b)=>a-b);
    for(const entry of tools){
      const t=entry.t;
      const choice=document.createElement('button');choice.type='button';choice.className='cxm-tool-choice';
      choice.setAttribute('aria-pressed',String(selected.includes(t)));
      const locked=t!==0&&!entry.enabled;
      choice.disabled=locked||running||toolBusy||preparing;
      if(locked)choice.title=entry.accepted?'Commissioning gate does not permit T'+t:'Dock not accepted or maintenance lockout';
      if(t===0)choice.title='T0 is the mandatory Z reference';
      const name=document.createElement('span');name.className='cxm-choice-name';
      const mark=document.createElement('span');mark.className='cxm-choice-mark';mark.textContent='✓';
      name.appendChild(mark);name.appendChild(document.createTextNode('T'+t));
      const info=document.createElement('span');info.className='cxm-choice-position';
      info.textContent=entry.xy+(locked&&entry.accepted?' · Locked':'');
      choice.appendChild(name);choice.appendChild(info);
      if(t!==0)choice.addEventListener('click',()=>{
        if(choice.disabled)return;
        selected=selected.includes(t)?selected.filter(k=>k!==t):[...selected,t].sort((a,b)=>a-b);
        persistedWarning='';preflight=null;
        drawToolChoices();refresh();
      });
      grid.appendChild(choice);
    }
    text('cxmZToolsSummary',selected.map(toolLabel).join(' + '));
    text('cxmZLiveTools',selected.map(toolLabel).join(', '));
    // Keep legacy hidden field compatible with scripts reading tool count; never use it for motion.
    const old=el('cxmZAutoCount');if(old)old.value=String(Math.max(...selected)+1);
    renderWorkflowSteps();
  }
  function renderStatus(){
    const ready=preflight?.ready===true;
    stateChip('cxmZLivePrinter',running?'Running':ready?'Ready':'Check',ready?'ok':'warn');
    const meshBlocked=(preflight?.blockers||[]).some(x=>/mesh/i.test(x));
    stateChip('cxmZLiveMesh',meshBlocked?'Active':'Clear',meshBlocked?'warn':'ok');
    const mounted=native?.current_tool;
    const sensor=native?.sensor;
    const identity=mounted===-1&&sensor==='RELEASED'?'EMPTY':mounted>=0&&sensor==='PRESSED'?'T'+mounted:'Unknown';
    stateChip('cxmZLiveCarriage',identity,identity==='Unknown'?'warn':'ok');
    stateChip('cxmZLiveRef',referenceSet?'Selected':'Not selected',referenceSet?'ok':'warn');
    text('cxmZRefHint',referenceSet?'T0 selected as zero; measured at the beginning of the run.':'T0 is measured first during calibration; this step does not move the printer.');
    if(!referenceSet)el('cxmZRefSet').textContent='Use T0 as reference';
    else el('cxmZRefSet').textContent='T0 reference selected ✓';
    text('cxmZAutoPreflight',ready?'Ready for supervised calibration':(preflight?.blockers||[]).join(' · ')||'Readiness not confirmed');
    renderWorkflowSteps();
  }
  // UI-only step indicator: labels reflect actual selection, preflight and run results.
  // Clicking a tile navigates; it never grants readiness or runs G-code.
  function renderWorkflowSteps(){
    const approved=!!el('cxmZAutoApprove')?.checked;
    const tools=allowedTools();
    const valid=new Set(tools.filter(t=>t.enabled).map(t=>t.t));
    const toolsSelected=referenceSet&&selected.includes(0)&&selected.length>0&&selected.every(t=>valid.has(t));
    const pass=preflight?.ready===true&&approved&&toolsSelected;
    const failed=status?.state==='stopped_error'||status?.state==='failed'||status?.state==='error';
    const latest=status?.result;
    const resultMatches=!!latest?.tools&&selected.length===Object.keys(latest.tools).length&&
      selected.every(t=>latest.tools['T'+t]?.passed===true);
    const completed=status?.state==='complete'&&latest?.passed===true&&resultMatches&&referenceSet;
    const stopped=failed&&referenceSet;
    const hasResults=!!latest?.tools&&Object.keys(latest.tools).length>0;
    const preparingState=preparing;
    const inRun=running||status?.running===true;
    let stages;
    if(!referenceSet){
      stages=['active','idle','idle','idle','idle'];
    }else if(!toolsSelected){
      stages=['complete','active','idle','idle','idle'];
    }else if(stopped){
      stages=['complete','complete',approved?'complete':'idle','error',hasResults?'active':'idle'];
    }else if(inRun){
      stages=['complete','complete','complete','active','idle'];
    }else if(completed){
      stages=['complete','complete','complete','complete','complete'];
    }else if(!pass){
      // Typical unhomed/unsynchronised states are normal preparation, not failure.
      const severe=(preflight?.blockers||[]).some(b=>/sensor disagrees|unsafe|fault|printing|paused|stop|unexpected tool/i.test(String(b)));
      stages=['complete','complete',preparingState?'active':severe?'error':'active','idle','idle'];
    }else{
      stages=['complete','complete','complete','active','idle'];
    }
    root.querySelectorAll('.cxm-flow-step[data-cxm-stage]').forEach(tile=>{
      const index=Number(tile.dataset.cxmStage)-1;
      const current=stages[index]||'idle';
      tile.dataset.state=current;
      if(current==='active')tile.setAttribute('aria-current','step');
      else tile.removeAttribute('aria-current');
      tile.setAttribute('aria-label','Step '+(index+1)+': '+(tile.querySelector('.cxm-step-title')?.textContent||'')+ ', '+(
        {active:'current step',complete:'verified',error:'needs attention',idle:'not yet complete'}[current]));
    });
  }
  root.querySelectorAll('.cxm-flow-step[data-target]').forEach(tile=>{
    tile.addEventListener('click',()=>{
      const target=el(tile.dataset.target);
      target?.scrollIntoView({behavior:'smooth',block:'center'});
    });
  });
  function renderResults(){
    const body=el('cxmZResultsTable');body.replaceChildren();
    const result=status?.result;
    if(!result?.tools||typeof result.tools!=='object'){
      const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=5;
      td.textContent=status?.error?'Stopped: '+status.error:'No measurements recorded yet.';
      tr.appendChild(td);body.appendChild(tr);
      text('cxmZResultMeta',el('cxmZAutoMode').value==='quick'
        ?'Quick: 3 Touch/tool · range ≤ 0.050 mm · redock not tested · no offsets applied'
        :'Full: 6 Touch/tool · range/drift ≤ 0.050 mm · no offsets applied');
      return;
    }
    const n=Object.keys(result.tools).sort((a,b)=>Number(a.slice(1))-Number(b.slice(1)));
    const format=v=>typeof v==='number'&&Number.isFinite(v)?v.toFixed(5)+' mm':'—';
    for(const t of n){
      const v=result.tools[t],tr=document.createElement('tr');
      function cell(v){const td=document.createElement('td');td.textContent=String(v);tr.appendChild(td);return td;}
      cell(t);
      const state=cell('');const tag=document.createElement('span');tag.className='cxm-tag'+(v.passed?'':' failed');tag.textContent=v.passed?'PASS':'FAIL';state.appendChild(tag);
      const ranges=[v.range_before_mm,v.range_after_mm].filter(Number.isFinite);
      cell(format(ranges.length?Math.max(...ranges):null));
      cell(v.redock_verified===false?'Not tested':format(v.redock_drift_mm));
      cell(t==='T0'?'Reference (0.00000 mm)':format(v.relative_to_t0_mm));
      body.appendChild(tr);
    }
    const verified=result.redock_verified===true;
    text('cxmZResultMeta',(result.passed?'Selected tools passed':'Measurement review required')+
      (verified?' · Full redock test':' · Quick Touch only · redock not tested')+
      ' · Provisional — no offsets saved or applied');
  }
  function buttons(){
    const approved=el('cxmZAutoApprove').checked;
    const busy=preparing||toolBusy||running;
    el('cxmZRefSet').disabled=busy;
    el('cxmZAutoMode').disabled=busy;
    el('cxmZAutoPrepare').disabled=busy||!revision||!approved||!referenceSet;
    el('cxmZAutoStart').disabled=busy||!preflight?.ready||!revision||!approved||!referenceSet;
    el('cxmZAutoStop').disabled=!running;
    el('cxmZAutoLoadT0').disabled=!toolCanMove(0);
    el('cxmZAutoUnloadT0').disabled=!toolCanMove(-1);
    text('cxmZAutoToolState',toolMessage());
    for(const btn of el('cxmZToolsGrid').querySelectorAll('button')){
      const t=Number(btn.textContent.match(/T(\d+)/)?.[1]);
      if(t!==0)btn.disabled=btn.disabled||busy;
    }
    renderWorkflowSteps();
  }
  async function refresh(){
    if(loading)return;loading=true;
    try{
      const p=await get('z-auto/status');status=p;running=!!p.running;
      const [cfg,pf,n]=await Promise.all([
        get('config'),get('z-auto/preflight?tools='+encodeURIComponent(toolsQuery())),
        get('native/status').catch(e=>({native_error:e.message}))]);
      config=cfg;revision=cfg.revision;preflight=pf;
      native=n.native_error?null:n;
      if(n.native_error&&!toolBusy)toolFeedback='Native state unavailable: '+n.native_error;
      text('cxmZAutoProgress',p.state+' — '+(p.step||p.error||'No run started')+(p.stop_requested?' (stop requested)':''));
      el('cxmZAutoReport').textContent=JSON.stringify({measurements:p.measurements,result:p.result,error:p.error},null,2);
      if(p.state==='stopped_error')el('cxmZAutoApprove').checked=false;
      drawToolChoices();renderStatus();renderResults();
    }catch(e){preflight=null;text('cxmZAutoPreflight','Readiness unavailable: '+errorText(e));renderStatus()}
    finally{loading=false;buttons();}
  }
  async function changeTool(tool){
    if(toolBusy||running||preparing||loading)return;
    toolBusy=true;toolFeedback='Checking live carriage state…';buttons();
    try{
      const [n,z,c]=await Promise.all([get('native/status'),get('z-auto/status'),get('config')]);native=n;
      if(z.running)throw Error('Z measurement running');
      if(!el('cxmZAutoApprove').checked)throw Error('Complete physical inspection approval');
      const prev=tool===0?-1:0;
      if(n.native_ready!==true||n.fault||n.running||n.current_tool!==prev||n.sensor!==(prev===-1?'RELEASED':'PRESSED'))
        throw Error('Carriage identity is not confirmed for this action');
      if(!n.candidates?.some(t=>t.tool===0&&t.eligible===true))throw Error('T0 dock not accepted or locked out');
      if(!c.revision||c.migration_required)throw Error('Invalid saved configuration revision');
      toolFeedback=(tool===0?'Loading':'Unloading')+' T0… supervise physical motion.';buttons();
      await post('native/simple-change',{tool,mounted_tool:prev,expected_revision:c.revision});
      native=await get('native/status');
      if(native.native_ready===true&&!native.fault&&!native.running&&native.current_tool===tool&&native.sensor===(tool===0?'PRESSED':'RELEASED'))
        toolFeedback=tool===0?'T0 loaded · sensor PRESSED.':'T0 unloaded · carriage EMPTY.';
      else toolFeedback='Toolchange returned but final state unverified; inspect before another command.';
    }catch(e){toolFeedback='Movement not confirmed: '+errorText(e)+'. Inspect before retrying.';}
    finally{toolBusy=false;await refresh();}
  }
  el('cxmZRefSet').addEventListener('click',()=>{
    if(running||preparing||toolBusy)return;
    referenceSet=true;selected=[0];preflight=null;
    text('cxmZRefHint','T0 selected as the reference. Select any other commissioned tools below.');
    drawToolChoices();buttons();refresh();
  });
  el('cxmZAutoApprove').addEventListener('change',buttons);
  el('cxmZAutoMode').addEventListener('change',renderResults);
  el('cxmZAutoLoadT0').addEventListener('click',()=>changeTool(0));
  el('cxmZAutoUnloadT0').addEventListener('click',()=>changeTool(-1));
  el('cxmZAutoRefresh').addEventListener('click',refresh);
  el('cxmZAutoPrepare').addEventListener('click',async()=>{
    if(preparing||toolBusy||running||!revision||!referenceSet||!el('cxmZAutoApprove').checked)return;
    preparing=true;buttons();
    text('cxmZAutoPrepareResult','Preparing: G28 only if unhomed, then geometry, EMPTY and mesh clear. Supervise any motion.');
    try{
      const cfg=await get('config');
      if(cfg.revision!==revision||cfg.migration_required)throw Error('Saved config changed; refresh');
      const result=await post('z-auto/prepare',{tools:selected,expected_revision:cfg.revision,
        acknowledgement:'I_INSPECTED_EMPTY_CARRIAGE_COLD_HARDWARE_AND_WILL_SUPERVISE_HOMING'});
      text('cxmZAutoPrepareResult','READY · '+result.events.join(' · '));toolFeedback='';
    }catch(e){text('cxmZAutoPrepareResult','STOPPED: '+errorText(e)+' · Inspect printer before retrying.');}
    finally{preparing=false;await refresh();}
  });
  el('cxmZAutoStart').addEventListener('click',async()=>{
    if(preparing||toolBusy||running||!preflight?.ready||!referenceSet||!el('cxmZAutoApprove').checked)return;
    el('cxmZAutoStart').disabled=true;
    try{
      const requestedMode=el('cxmZAutoMode').value;
      const res=await post('z-auto/start',{tools:selected,expected_revision:revision,mode:requestedMode,
        acknowledgement:'I_VERIFIED_COLD_NOZZLE_BED_LATCHES_DOCKS_AND_SUPERVISE_MOTION'});
      text('cxmZAutoProgress','Started '+(res.selected_tools||selected).map(toolLabel).join(', ')+
        (requestedMode==='quick'?' · Quick (3 Touch/tool)':' · Full redock (6 Touch/tool)')+
        ' · supervise full motion and Touch.');
    }catch(e){text('cxmZAutoProgress','START REFUSED: '+errorText(e));}
    finally{await refresh();}
  });
  el('cxmZAutoStop').addEventListener('click',async()=>{
    try{await post('z-auto/stop',{acknowledgement:'STOP_AFTER_CURRENT_COMMAND'});
      text('cxmZAutoProgress','Stop requested after current command. For immediate danger use emergency stop.');}
    catch(e){text('cxmZAutoProgress','Stop request: '+errorText(e));}
  });
  document.querySelector('[data-tab="z-calibration"]')?.addEventListener('click',refresh);
  window.addEventListener('focus',refresh);
  setInterval(()=>{if(!document.hidden&&running)refresh();},1500);
  refresh();
})();
