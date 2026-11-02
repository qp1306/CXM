/* CXM V0.7.1 — read-only Z calibration preparation.
   One carriage extruder, interchangeable hotends; T0 is the Z reference.
   NO motors, NO nozzle contact, NO acceptance and NO configuration writes.
*/
(function () {
  'use strict';
  const ENDPOINT='/cxm/api/v1/config';
  const color=n=>typeof window==='undefined'?'#b6c4d5':(window.CXMToolStyle?.color(n)||'#b6c4d5');
  const fmt=v=>typeof v==='number' && Number.isFinite(v)
    ? (v>=0?'+':'')+v.toFixed(3)+' mm':'—';

  function zState(profile,n) {
    if (!profile) return {code:'UNAVAILABLE',label:'CONFIG UNAVAILABLE'};
    if (profile.maintenance_lockout===true)
      return {code:'LOCKED_OUT',label:'LOCKED OUT'};
    // T0 establishes a bed/nozzle datum; its stored relative 0 is NOT
    // evidence that this datum has ever been measured.
    if (n===0 && profile.reference_verified!==true)
      return {code:'T0_UNVERIFIED',label:'T0 REFERENCE NOT VERIFIED'};
    if (profile.offset_z_accepted!==true)
      return {code:'NOT_MEASURED',label:'NOT MEASURED'};
    if (profile.offset_z_verified!==true)
      return {code:'SAVED_UNVERIFIED',label:'SAVED · NOT VERIFIED'};
    return {code:'VERIFIED_RECORD',label:'VERIFICATION RECORDED'};
  }

  function rows(snapshot) {
    const config=snapshot?.config;
    const n=config?.globals?.tool_count;
    if (!Number.isInteger(n) || n<1 || n>12 ||
        !Array.isArray(config.tools) || config.tools.length<n) return [];
    return config.tools.slice(0,n).map((profile,index)=>({
      number:index, offset:fmt(profile.offset_z),
      state:zState(profile,index), profile
    }));
  }

  function render(snapshot, selected=0) {
    if(typeof document==='undefined') return;
    const byId=id=>document.getElementById(id);
    const list=rows(snapshot);
    const count=list.length;
    const current=list.find(item=>item.number===selected)||list[0]||null;
    const select=byId('cxmZTool');
    if(!select)return;
    select.replaceChildren();
    for(const item of list) {
      const option=document.createElement('option');
      option.value=String(item.number);
      option.textContent='T'+item.number+(item.number===0?' · reference':'')+
        ' · '+item.state.label;
      select.append(option);
    }
    if(current)select.value=String(current.number);
    select.disabled=!count;
    if(current)select.style.borderColor=color(current.number);
    if(count) window.CXMToolPicker?.sync(select,snapshot.config);
    const value=byId('cxmZSaved');
    value.textContent=current?.offset||'—';
    value.style.color=current?color(current.number):'#bec6d2';
    const status=byId('cxmZStatus');
    status.textContent=current?.state.label||'CONFIG UNAVAILABLE';
    status.dataset.state=current?.state.code||'UNAVAILABLE';
    byId('cxmZScope').textContent=count+' selected hotend(s) · T0 reference';
    byId('cxmZProgress').textContent=count
      ? list.filter(x=>x.state.code==='VERIFIED_RECORD').length+
        ' verification record(s) · no live measurement enabled'
      : 'No stored tool profiles available';
    const body=byId('cxmZTable');
    body.replaceChildren();
    for(const item of list) {
      const row=document.createElement('tr');
      if(current && current.number===item.number)row.classList.add('selected');
      const toolCell=document.createElement('td'),chip=document.createElement('span');
      chip.className='cxm-tool-chip';
      chip.style.setProperty('--tool-color',color(item.number));
      chip.textContent='T'+item.number+(item.number===0?' REF':'');
      toolCell.append(chip);
      const offset=document.createElement('td');
      offset.textContent=item.offset;
      const measured=document.createElement('td');
      measured.textContent='Not captured in CXM';
      const verification=document.createElement('td');
      verification.textContent=item.state.label;
      verification.className='cxm-z-state';
      verification.dataset.state=item.state.code;
      row.append(toolCell,offset,measured,verification);
      body.append(row);
    }
  }

  if(typeof document!=='undefined'){
    const panel=document.querySelector('[data-panel="z-calibration"]');
    if(panel){
      let snapshot=null,selected=0,loading=false;
      const status=document.getElementById('cxmZFeedback');
      async function load(){
        if(loading)return;
        loading=true;
        try{
          const resp=await fetch(ENDPOINT,{credentials:'same-origin',cache:'no-store'});
          const raw=await resp.json();
          if(!resp.ok || !raw.config)throw Error(raw.error||'Configuration unavailable');
          snapshot=raw;
          render(snapshot,selected);
          status.textContent=raw.migration_required?
            'Legacy config · migration required in Settings; no Z calibration can be accepted.':
            'Read-only saved profiles. Physical Z measurement has not been implemented.';
        }catch(err){
          snapshot=null;
          render(null,selected);
          status.textContent='Configuration unavailable: '+err.message+'. No calibration data changed.';
        }finally{loading=false;}
      }
      document.getElementById('cxmZTool').addEventListener('change',event=>{
        selected=Number(event.target.value);
        render(snapshot,selected);
      });
      panel.querySelector('#cxmZRefresh').addEventListener('click',load);
      document.querySelector('[data-tab="z-calibration"]')?.addEventListener('click',load);
      window.addEventListener('cxm-dock-saved',load);
      // Never POST or send G-code from this page.
      load();
    }
  }
  const api=Object.freeze({zState,rows,fmt});
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
})();
