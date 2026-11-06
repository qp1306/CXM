/* CXM T0: live sensor determines action, staging is part of the move. */
(()=>{
'use strict';
const get=id=>document.getElementById(id);
const root=get('cxmT0Auto');
if(!root)return;
const API='/cxm/api/v1/t0';
let live=null,busy=false,checking=false,lastError='';
const onlyT0=()=>get('cxmDockTool')?.value==='0';
function say(id,message){get(id).textContent=message;}
function updateButtons(){
  const auto=live?.automatic;
  const good=!busy&&onlyT0()&&live?.ready===true&&auto?.enabled===true;
  get('cxmT0AutoPickup').disabled=!good||auto?.signal!=='RELEASED';
  get('cxmT0AutoDropoff').disabled=!good||auto?.signal!=='PRESSED';
  get('cxmT0AutoFaultBox').hidden=!(auto?.fault);
  get('cxmT0AutoClearFault').disabled=busy||!auto?.fault;
  root.setAttribute('aria-busy',busy?'true':'false');
}
async function getJSON(url){
  const r=await fetch(url,{cache:'no-store',credentials:'same-origin'});
  const data=await r.json();
  if(!r.ok)throw Error(data.error||'HTTP '+r.status);
  return data;
}
async function send(path,data){
  const r=await fetch(API+path,{method:'POST',credentials:'same-origin',
    headers:{'Content-Type':'application/json','X-Requested-With':'CXM'},
    body:JSON.stringify(data)});
  const payload=await r.json();
  if(!r.ok)throw Error(payload.error||'HTTP '+r.status);
  return payload;
}
async function configRevision(){
  return (await getJSON('/cxm/api/v1/config')).revision;
}
async function refresh(){
  if(busy||checking)return;
  checking=true;
  try{
    live=await getJSON(API+'/status');
    if(!onlyT0()){
      say('cxmT0AutoStatus','Select T0 to use these controls.');
    }else if(!live.ready||!live.automatic?.enabled){
      say('cxmT0AutoStatus','Not available · '+
        (live.automatic?.reason||live.blockers?.join('; ')||'Check Klipper and carriage sensor.'));
    }else{
      const a=live.automatic;
      say('cxmT0AutoStatus',a.signal==='PRESSED'
        ? 'Carriage sensor: PRESSED · T0 detected on carriage · Dropoff available'
        : 'Carriage sensor: RELEASED · carriage empty · Pickup available');
    }
    say('cxmT0AutoGeometry',
      'T0 dock X'+(live.saved_xy_mm?.x?.toFixed(3)??'—')+
      ' Y'+(live.saved_xy_mm?.y?.toFixed(3)??'—')+
      ' · Unlock X −4.8 mm · Y dodge 14 mm · XY only');
    updateButtons();
  }catch(e){
    live=null;
    say('cxmT0AutoStatus','Live status unavailable · '+e.message);
    updateButtons();
  }finally{checking=false;}
}
async function command(kind){
  if(busy||checking||!onlyT0()||live?.ready!==true||live.automatic?.enabled!==true)return;
  const signal=kind==='pickup'?'RELEASED':'PRESSED';
  if(live.automatic.signal!==signal)return;
  const physical=kind==='pickup'
    ? 'Carriage is EMPTY and T0 is seated in its dock.'
    : 'T0 is fully attached and its dock is EMPTY.';
  if(!window.confirm('TEST T0 '+kind.toUpperCase()+'?\n\n'+
      'CXM will stage automatically at Safe Y, then run the known T0 XY path.\n'+
      'Confirm physically: '+physical+'\n'+
      'Confirm the full staging and toolchange paths are clear.\n'+
      'The test is supervised: keep emergency stop available.\n\n'+
      'Continue with the actual printer movement?'))return;
  busy=true;
  updateButtons();
  say('cxmT0AutoResult','T0 '+kind+' running · supervise the carriage and dock.');
  try{
    const result=await send('/auto',{expected_revision:await configRevision(),
      kind,acknowledgement:'I_CONFIRMED_T0_XY_PATH_CLEAR_AND_WILL_SUPERVISE'});
    lastError='';
    say('cxmT0AutoResult','T0 '+kind.toUpperCase()+' · switch transition confirmed ('+
      result.signal+'). Inspect the physical hotend seating.');
  }catch(e){
    lastError=e.message;
    say('cxmT0AutoResult','TEST BLOCKED / FAILED · '+e.message+
      ' · Do not repeat movement until the carriage and dock are inspected.');
  }finally{
    busy=false;
    await refresh();
    if(lastError) say('cxmT0AutoResult','TEST BLOCKED / FAILED · '+lastError+
      ' · Check T0 and dock before retrying.');
  }
}
async function clearFault(){
  if(busy||!live?.automatic?.fault)return;
  if(!window.confirm('Have you physically inspected the actual carriage, dock and tool after the failed movement?\n\nClearing the test fault DOES NOT move the printer.'))return;
  busy=true;
  updateButtons();
  try{
    const r=await send('/clear-fault',{expected_revision:await configRevision(),
      acknowledgement:'I_PHYSICALLY_INSPECTED_T0_AND_PATH_AFTER_TEST_FAILURE'});
    lastError='';
    say('cxmT0AutoResult',r.status+' · no motor movement.');
  }catch(e){
    say('cxmT0AutoResult','Cannot clear test fault · '+e.message);
  }finally{busy=false;await refresh();}
}
get('cxmT0AutoPickup').addEventListener('click',()=>command('pickup'));
get('cxmT0AutoDropoff').addEventListener('click',()=>command('dropoff'));
get('cxmT0AutoClearFault').addEventListener('click',clearFault);
get('cxmDockTool')?.addEventListener('change',refresh);
document.querySelector('[data-tab="calibration"]')?.addEventListener('click',refresh);
window.addEventListener('cxm-dock-saved',refresh);
document.addEventListener('visibilitychange',()=>{
  if(!document.hidden)refresh();
});
setInterval(()=>{if(!document.hidden&&onlyT0())refresh();},2500);
refresh();
})();
