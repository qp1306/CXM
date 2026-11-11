/* CXM simple XY/Z relative-offset editors. Saving is disk-only; no motors. */
(()=>{
'use strict';
const $=id=>document.getElementById(id);
if(!$('cxmXYEditSave') || !$('cxmZEditSave'))return;
const modes={
 xy:{select:'cxmXYEditTool',fields:['cxmXYEditX','cxmXYEditY'],status:'cxmXYEditStatus',
     save:'cxmXYEditSave',reset:'cxmXYEditReset',axes:['x','y'],min:-20,max:20},
 z:{select:'cxmZEditTool',fields:['cxmZEditValue'],status:'cxmZEditStatus',
     save:'cxmZEditSave',reset:'cxmZEditReset',axes:['z'],min:-10,max:10}
};
let snapshot=null,busy=false;
let dirty={xy:false,z:false};
const pick={xy:0,z:0};
const say=(mode,message)=>{const e=$(modes[mode].status);if(e)e.textContent=message;};
function values(mode){
 const spec=modes[mode],out={};
 for(let i=0;i<spec.fields.length;i++){
   const raw=$(spec.fields[i]).value.trim(),val=Number(raw);
   if(raw===''||!Number.isFinite(val)||val<spec.min||val>spec.max)
     throw Error('Enter valid '+spec.axes[i].toUpperCase()+' value ('+spec.min+' to +'+spec.max+' mm).');
   out[spec.axes[i]]=val;
 }
 if(pick[mode]===0&&Object.values(out).some(v=>v!==0))
   throw Error('T0 is the zero reference. Its offsets cannot be changed.');
 return out;
}
function entry(mode){return snapshot?.config?.tools?.[pick[mode]];}
function editable(mode){
 return !!snapshot&&!snapshot.migration_required&&!busy&&pick[mode]>=0
     &&pick[mode]<snapshot.config.globals.tool_count&&
     entry(mode)?.maintenance_lockout!==true;
}
function changed(mode,data){return modes[mode].axes.some(axis=>data[axis]!==entry(mode)?.['offset_'+axis]);}
function enable(mode){
 const spec=modes[mode],active=editable(mode);
 for(const id of spec.fields)$(id).disabled=!active||(pick[mode]===0&&!changedReference(mode));
 $(spec.select).disabled=busy||!snapshot;
 let okay=false;
 if(active&&dirty[mode]){try{okay=changed(mode,values(mode));}catch{}}
 $(spec.save).disabled=!okay;
 $(spec.reset).disabled=busy||!snapshot;
}
function changedReference(mode){return modes[mode].axes.some(axis=>entry(mode)?.['offset_'+axis]!==0);}
function render(mode,refreshSelector=true){
 const spec=modes[mode];
 const count=snapshot?.config?.globals?.tool_count??0;
 if(!Number.isInteger(pick[mode])||pick[mode]>=count)pick[mode]=0;
 const select=$(spec.select);
 if(refreshSelector){
   select.replaceChildren();
   for(let n=0;n<count;n++){
     const opt=document.createElement('option');
     opt.value=String(n);opt.textContent='T'+n+(n===0?' · reference':'');
     select.appendChild(opt);
   }
 }
 select.value=String(pick[mode]);
 const tool=entry(mode);
 for(let i=0;i<spec.fields.length;i++){
   const v=tool?.['offset_'+spec.axes[i]];
   $(spec.fields[i]).value=typeof v==='number'&&Number.isFinite(v)?String(v):'';
 }
 dirty[mode]=false;
 enable(mode);
 if(!snapshot)say(mode,'Configuration unavailable. No changes made.');
 else if(snapshot.migration_required)say(mode,'Config migration required in Settings.');
 else if(tool?.maintenance_lockout)say(mode,'T'+pick[mode]+' is maintenance-locked.');
 else if(pick[mode]===0)say(mode,'T0 reference = 0.000 mm. No separate relative-offset calibration is required for T0.');
 else say(mode,'T'+pick[mode]+' saved '+mode.toUpperCase()+' values loaded. Enter measured offsets and Save; no motion occurs.');
}
async function getConfig(){
 const r=await fetch('/cxm/api/v1/config',{credentials:'same-origin',cache:'no-store'});
 const result=await r.json();
 if(!r.ok||!result?.config)throw Error(result.error||'Configuration unavailable');
 return result;
}
async function fetchConfig(force=false){
 if(busy)return;
 if(!force&&(dirty.xy||dirty.z)){
   if(!window.confirm('Discard unsaved offset changes and reload from disk?'))return;
 }
 try{
   snapshot=await getConfig();
   render('xy');render('z');
 }catch(e){
   snapshot=null;
   render('xy');render('z');
   say('xy',e.message);say('z',e.message);
 }
}
function modify(mode){
 dirty[mode]=true;
 enable(mode);
 try{
   const data=values(mode);
   say(mode,changed(mode,data)
     ? 'Valid '+mode.toUpperCase()+' draft ready to save.'
     : 'No change from the saved values.');
 }catch(e){say(mode,e.message);}
}
async function save(mode){
 if(!editable(mode)||!dirty[mode])return;
 const spec=modes[mode],n=pick[mode];
 let data;
 try{data=values(mode);if(!changed(mode,data))return;}
 catch(e){say(mode,e.message);return;}
 const label=spec.axes.map(axis=>axis.toUpperCase()+' '+data[axis].toFixed(3)).join(' / ');
 if(!window.confirm('Save T'+n+' '+mode.toUpperCase()+' offsets: '+label+
    ' mm?\n\nThis creates a backup but does not move the printer or change its active tool.'))return;
 busy=true;enable('xy');enable('z');
 say(mode,'Saving T'+n+' '+mode.toUpperCase()+' offsets…');
 try{
   const body={tool:n,axes:mode,values:data,expected_revision:snapshot.revision};
   const r=await fetch('/cxm/api/v1/offset',{method:'POST',credentials:'same-origin',
      headers:{'Content-Type':'application/json','X-Requested-With':'CXM'},
      body:JSON.stringify(body)});
   const result=await r.json();
   if(!r.ok||!result.saved)throw Error(result.error||'Server did not confirm save');
   const fresh=await getConfig();
   const stored=fresh.config.tools[n];
   if(!spec.axes.every(axis=>stored['offset_'+axis]===data[axis]))
     throw Error('Saved values did not match disk verification');
   snapshot=fresh;
   dirty[mode]=false;
   // Update the other editor's data only if it had no unsaved changes.
   render(mode);
   if(!dirty[mode==='xy'?'z':'xy'])render(mode==='xy'?'z':'xy');
   say(mode,'T'+n+' '+mode.toUpperCase()+' offsets SAVED · backup protected · not yet verified or active in Klipper.');
   window.dispatchEvent(new Event('cxm-dock-saved'));
 }catch(e){
   say(mode,'Save not verified: '+e.message+' · draft retained.');
 }finally{
   busy=false;enable('xy');enable('z');
 }
}
for(const [mode,spec] of Object.entries(modes)){
 $(spec.select).addEventListener('change',event=>{
   if(dirty[mode]&&!window.confirm('Discard unsaved '+mode.toUpperCase()+' changes?')){
     event.target.value=String(pick[mode]);return;
   }
   pick[mode]=Number(event.target.value);
   render(mode,false);
 });
 for(const id of spec.fields)$(id).addEventListener('input',()=>modify(mode));
 $(spec.save).addEventListener('click',()=>save(mode));
 $(spec.reset).addEventListener('click',()=>render(mode,false));
}
window.addEventListener('cxm-camera-offset-saved',()=>{if(!dirty.xy&&!dirty.z)fetchConfig(true);});
document.querySelector('[data-tab="offsets"]')?.addEventListener('click',()=>{if(!dirty.xy)fetchConfig(true);});
document.querySelector('[data-tab="z-calibration"]')?.addEventListener('click',()=>{if(!dirty.z)fetchConfig(true);});
$('cxmOpenDiagnostics')?.addEventListener('click',()=>{
 document.querySelector('[data-tab="tests"]')?.click();
});
window.addEventListener('cxm-dock-saved',()=>{if(!busy&&!dirty.xy&&!dirty.z)fetchConfig(true);});
fetchConfig(true);
})();