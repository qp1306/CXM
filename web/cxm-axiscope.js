/* CXM V0.5 — Axiscope visual preparation. NO G-code, motion or offset writes. */
(() => {
  'use strict';
  const panel=document.querySelector('[data-panel="offsets"]');
  if(!panel)return;
  const el=id=>document.getElementById(id);
  const API='/server/webcams/list';
  let config=null;
  let tool=0;
  let webcams=[];
  let liveCamera=null;

  const colour=n=>window.CXMToolStyle?.color(n)||'#a9bacb';
  const format=n=>n==null?'—':(Number(n)>=0?'+':'')+Number(n).toFixed(3);
  const text=(id,value)=>{const node=el(id);if(node)node.textContent=String(value)};
  const escape=value=>String(value).replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

  // Only same-origin HTTP(S) paths can be embedded. Never forward user-owned
  // URLs or credentials to another host. External camera streams must first
  // be exposed through the existing Mainsail/Crowsnest reverse proxy.
  function cameraURL(raw, origin) {
    if(typeof raw!=='string' || !raw.trim() || raw.startsWith('//'))return null;
    try {
      const url=new URL(raw,origin+'/');
      if(url.origin!==origin || !/^https?:$/.test(url.protocol)
        || url.username || url.password)return null;
      return url.href;
    }catch{return null;}
  }
  function clearCamera(message) {
    liveCamera=null;
    const img=el('cxmAxisImage');
    img.removeAttribute('src');
    img.hidden=true;
    el('cxmAxisFrame').classList.remove('has-camera');
    text('cxmAxisCameraMessage',message);
    el('cxmAxisCameraMessage').hidden=false;
  }
  function selectCamera() {
    const idx=Number(el('cxmAxisCamera').value);
    const entry=webcams[idx];
    if(!entry){clearCamera('No camera selected. Configure an Axiscope camera in Mainsail first.');return;}
    const url=cameraURL(entry.stream_url,window.location.origin);
    if(!url) {
      clearCamera('Camera "'+entry.name+'" uses an external URL. Configure its stream behind the printer’s same-origin webcam proxy before viewing it here.');
      return;
    }
    if(entry.service && !['mjpegstreamer','mjpgstreamer','ustreamer','camera-streamer'].includes(entry.service)) {
      clearCamera('This camera service may not provide an MJPEG image stream. Configure an MJPEG stream in Mainsail.');
      return;
    }
    const img=el('cxmAxisImage');
    img.onerror=()=>clearCamera('Camera stream could not be displayed. Verify its Mainsail webcam URL and service.');
    img.onload=()=>text('cxmAxisCameraMessage','Camera stream displayed; reticle alignment is not calibrated.');
    img.src=url;
    img.hidden=false;
    liveCamera=entry.uid||entry.name;
    el('cxmAxisFrame').classList.add('has-camera');
    el('cxmAxisCameraMessage').hidden=true;
    text('cxmAxisOrientation','Camera flip/rotation: '+(entry.flip_horizontal?'H ':'')+(entry.flip_vertical?'V ':'')+(entry.rotation||0)+'° (verify optical orientation before measuring)');
  }
  async function loadCameras() {
    const select=el('cxmAxisCamera');
    const remembered=webcams[Number(select.value)]?.uid||null;
    select.disabled=true;
    clearCamera('Checking webcams configured in Moonraker…');
    try {
      const response=await fetch(API,{credentials:'same-origin',cache:'no-store'});
      const raw=await response.json();
      if(!response.ok)throw new Error(raw.error?.message||'HTTP '+response.status);
      webcams=(raw.result?.webcams||[]).filter(w=>w.enabled && typeof w.stream_url==='string');
      select.replaceChildren();
      const none=document.createElement('option');
      none.value='-1';none.textContent='Choose camera';
      select.append(none);
      webcams.forEach((cam,n)=>{
        const opt=document.createElement('option');
        opt.value=String(n);
        opt.textContent=cam.name||('Camera '+(n+1));
        select.append(opt);
      });
      if(!webcams.length) {
        select.value='-1';
        clearCamera('No enabled webcams found in Moonraker. Add an Axiscope camera in Mainsail Settings → Webcams.');
      }else {
        let idx=webcams.findIndex(w=>w.uid===remembered);
        if(idx<0)idx=webcams.findIndex(w=>/axiscope/i.test(w.name||''));
        if(idx<0)idx=0;
        select.value=String(idx);
        selectCamera();
      }
      select.disabled=!webcams.length;
      text('cxmAxisCameraCount',webcams.length+' camera'+(webcams.length===1?'':'s')+' configured');
    }catch(e) {
      webcams=[];
      select.replaceChildren();
      clearCamera('Moonraker webcam discovery unavailable: '+e.message);
      text('cxmAxisCameraCount','No camera connection');
    }
  }
  async function loadProfiles() {
    try {
      const response=await fetch('/cxm/api/v1/config',{credentials:'same-origin',cache:'no-store'});
      const data=await response.json();
      if(!response.ok)throw new Error(data.error||'HTTP '+response.status);
      config=data.config;
      render();
    }catch(e){
      config=null;
      render();
      text('cxmAxisFeedback','Saved profiles are unavailable: '+e.message);
    }
  }
  function activeTools() {
    if(!config)return[];
    return config.tools.map((profile,n)=>({profile,n})).filter(x=>x.n<config.globals.tool_count && x.profile.enabled===true);
  }
  function render(){
    const list=activeTools();
    const selector=el('cxmAxisTool');
    if(!list.some(x=>x.n===tool))tool=list[0]?.n??0;
    selector.replaceChildren();
    for(const item of list){
      const opt=document.createElement('option');
      opt.value=String(item.n);
      opt.textContent='T'+item.n+(item.n===0?' · reference':'');
      selector.append(opt);
    }
    selector.value=String(tool);
    selector.disabled=!list.length;
    selector.style.borderColor=colour(tool);
    text('cxmAxisToolStatus',list.length?'T'+tool+(tool===0?' · reference':' · selected'):'No active hotends');
    el('cxmAxisToolStatus').style.color=colour(tool);
    const profile=config?.tools?.[tool];
    text('cxmAxisSavedX',profile?format(profile.offset_x)+' mm':'—');
    text('cxmAxisSavedY',profile?format(profile.offset_y)+' mm':'—');
    const table=el('cxmAxisTable');
    table.replaceChildren();
    for(const {n,profile:p} of list){
      const tr=document.createElement('tr');
      if(n===tool)tr.className='selected';
      const name=document.createElement('td');
      const badge=document.createElement('span');
      badge.className='cxm-tool-chip';
      badge.textContent='T'+n+(n===0?' REF':'');
      badge.style.setProperty('--tool-color',colour(n));
      name.append(badge);
      const x=document.createElement('td'),y=document.createElement('td'),measured=document.createElement('td');
      x.textContent=format(p.offset_x);
      y.textContent=format(p.offset_y);
      measured.textContent='Not measured';
      tr.append(name,x,y,measured);table.append(tr);
    }
    text('cxmAxisFeedback',list.length
      ? 'Saved XY offsets shown for '+list.length+' hotend(s). Camera alignment and measured offsets are not yet available.'
      : 'No enabled tools. Set the count and enable a profile in Settings.');
  }
  el('cxmAxisRefreshCameras').addEventListener('click',loadCameras);
  el('cxmAxisCamera').addEventListener('change',selectCamera);
  el('cxmAxisTool').addEventListener('change',e=>{tool=Number(e.target.value);render();});
  el('cxmAxisZoom').addEventListener('input',e=>{
    const zoom=Number(e.target.value);
    const img=el('cxmAxisImage');
    img.style.transform='scale('+zoom.toFixed(2)+')';
    text('cxmAxisZoomLabel',Math.round(zoom*100)+'%');
  });
  el('cxmAxisReticle').addEventListener('change',e=>{
    el('cxmAxisFrame').classList.toggle('hide-reticle',!e.target.checked);
  });
  document.querySelector('[data-tab="offsets"]')?.addEventListener('click',()=>{
    loadProfiles();
    if(!webcams.length)loadCameras();
  });
  // Re-reading is safe: settings are read-only here and never cause printer moves.
  window.addEventListener('cxm-dock-saved',loadProfiles);
  loadProfiles();
})();
