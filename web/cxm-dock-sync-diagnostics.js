/* Read-only Dock XY discrepancy report. No writes and no motion. */
(()=>{
 'use strict';
 const details=document.getElementById('cxmDockSyncDetails');
 const summary=document.getElementById('cxmDockSyncSummary');
 const evidence=document.getElementById('cxmDockSyncEvidence');
 const copy=document.getElementById('cxmDockSyncCopy');
 if(!details||!summary||!evidence||!copy)return;
 let report='',lastRefresh=0,running=false;
 async function refresh(){
  if(running||document.hidden||Date.now()-lastRefresh<2000)return;
  lastRefresh=Date.now();
  running=true;
  try{
   const reply=await fetch('/cxm/api/v1/native/dock-sync-status',
     {credentials:'same-origin',cache:'no-store'});
   const data=await reply.json();
   if(!reply.ok)throw Error(data.error||'Could not inspect native dock coordinates');
   const issues=(data.tools||[]).filter(t=>t.saved.accepted===true&&t.match!==true);
   const lines=[
    'Klipper geometry '+(data.native_ready?'READY':'not synchronized')+
      ' · tool '+String(data.native_tool)+' · fault '+String(data.native_fault),
    'Loaded transfer macro: '+String(data.loaded_transfer),
    ...data.tools.map(t=>{
     const fmt=n=>typeof n==='number'&&Number.isFinite(n)?n.toFixed(3):String(n??'not set');
     return 'T'+t.tool+' saved X'+fmt(t.saved.x)+' Y'+fmt(t.saved.y)+
       ' / Klipper X'+fmt(t.native.x)+' Y'+fmt(t.native.y)+
       ' · '+(t.match?'MATCH':'DIFFERENT')+
       ' · saved '+String(t.saved.accepted)+' / native '+String(t.native.accepted);
    })
   ];
   if(data.legacy_guard_excerpt)lines.push(
    'Loaded legacy release-point guard:',data.legacy_guard_excerpt);
   report=lines.join('\n');
   evidence.textContent=report;
   const old=data.loaded_transfer==='older_proven_release_guard';
   const problem=old||issues.length>0;
   summary.textContent=old?'Old native release-point check detected — inspect below':
      issues.length?'Saved Dock XY differs from native Klipper for '+issues.map(t=>'T'+t.tool).join(', '):
      'Saved Dock XY and Klipper native XY · '+data.tools.length+' hotends checked';
   if(problem)details.open=true;
  }catch(e){
   summary.textContent='Native XY comparison unavailable';
   evidence.textContent='Read-only diagnostic failed: '+e.message;
  }finally{running=false;}
 }
 copy.addEventListener('click',async()=>{
  try{
   await navigator.clipboard.writeText(report||evidence.textContent);
   copy.textContent='Copied';
  }catch(e){copy.textContent='Copy unavailable';}
 });
 document.querySelector('[data-tab="tools"]')?.addEventListener('click',()=>{lastRefresh=0;refresh();});
 document.addEventListener('visibilitychange',()=>{if(!document.hidden){lastRefresh=0;refresh();}});
 setInterval(refresh,4000);
 refresh();
})();