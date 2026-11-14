/* CXM approved 7-page redesign V1 — PRESENTATION ONLY.
 * Restyles and reorganizes EXISTING live controls. It never emits G-code,
 * writes configuration, changes interlocks or sends motion requests.
 * Step completion is derived from live readouts; navigation alone never passes a step.
 */
(()=>{
'use strict';
if(typeof document==='undefined')return;
const $=id=>document.getElementById(id);
const q=(sel,root=document)=>root.querySelector(sel);
const qa=(sel,root=document)=>Array.from(root.querySelectorAll(sel));
const SVG={
  tools:'<path d="M9 3h6l1 4H8z"/><path d="M10 7v5l-3 4v4h10v-4l-3-4V7"/><path d="M9 20h6"/>',
  dock:'<path d="M3 4h18v5H3z"/><path d="M6 9v9h12V9"/><path d="M9 18v3m6-3v3"/><path d="m9 13 3 3 3-3"/>',
  target:'<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><path d="M12 2v4m0 12v4M2 12h4m12 0h4"/>',
  printer:'<path d="M6 8V3h12v5M6 17H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 14h12v7H6zM17 11h2"/>',
  play:'<path d="m8 5 11 7-11 7V5z"/>',check:'<path d="m4 12 5 5L20 6"/>',
  results:'<path d="M3 20h18"/><path d="M6 17V9h4v8M12 17V4h4v13M18 17v-7h3v7"/>',
  layers:'<path d="m12 3 9 5-9 5-9-5 9-5zM3 12l9 5 9-5M3 16l9 5 9-5"/>',
  verify:'<path d="M12 22s9-4 9-10V5l-9-3-9 3v7c0 6 9 10 9 10z"/><path d="m8 12 3 3 5-6"/>',
  car:'<rect x="3" y="8" width="18" height="9" rx="2"/><path d="M7 8V5h10v3M7 17v3m10-3v3"/>',
  wrench:'<path d="M14 7a5 5 0 0 0 6.3 6.3l-3.1 3.1a2 2 0 0 1-2.8-2.8L17.5 1a7 7 0 0 0-9 8.9L2.7 15.7a3 3 0 0 0 4.2 4.2l5.8-5.8"/>',
  settings:'<path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z"/><path d="M4 12a8 8 0 0 1 .3-2.1L2 8l2-4 2.9 1.1A8 8 0 0 1 9 4l.5-3h5l.5 3a8 8 0 0 1 2.1 1.1L20 4l2 4-2.3 1.9A8 8 0 0 1 20 12c0 .7-.1 1.4-.3 2.1L22 16l-2 4-2.9-1.1A8 8 0 0 1 15 20l-.5 3h-5L9 20a8 8 0 0 1-2.1-1.1L4 20l-2-4 2.3-1.9A8 8 0 0 1 4 12z"/>',
  search:'<circle cx="10.5" cy="10.5" r="7"/><path d="m16 16 5 5"/>',
  download:'<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
  upload:'<path d="M12 17V4m-5 5 5-5 5 5M4 17v4h16v-4"/>',
  refresh:'<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 9a7 7 0 0 1 12-3l2 1M4 17l2 1a7 7 0 0 0 12-3"/>',
  edit:'<path d="m4 20 5-1 11-11a2 2 0 0 0-3-3L6 16l-2 4zM15 7l3 3"/>',
  save:'<path d="M4 3h14l3 3v15H3V3zM7 3v7h10V3M7 21v-8h10v8"/>',
  camera:'<path d="M4 7h4l2-3h5l2 3h3a2 2 0 0 1 2 2v10H2V9a2 2 0 0 1 2-2z"/><circle cx="12" cy="13" r="4"/>',
  move:'<path d="M12 2v20m0-20-4 4m4-4 4 4M12 22l-4-4m4 4 4-4M2 12h20m-20 0 4-4m-4 4 4 4m16-4-4-4m4 4-4 4"/>',
  stop:'<rect x="5" y="5" width="14" height="14" rx="2"/>',
  alert:'<path d="m12 2 10 18H2L12 2zM12 8v5m0 4v1"/>',
  history:'<circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/>',
  file:'<path d="M5 3h9l5 5v13H5zM14 3v5h5M8 13h8M8 17h6"/>',
  power:'<path d="M12 2v10M7 4a9 9 0 1 0 10 0"/>',
  checkcircle:'<circle cx="12" cy="12" r="9"/><path d="m7 12 3 3 7-7"/>',
  lock:'<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
  pulse:'<path d="M2 12h4l3-7 5 14 3-7h5"/>',
  checklist:'<path d="M5 3h14v19H5zM9 8h6M9 13h6M9 18h4"/><path d="m7 8 1 1 2-2m-3 6 1 1 2-2"/>',
  sliders:'<path d="M4 6h16M4 12h16M4 18h16M9 4v4m6 2v4m-5 2v4"/>',
  archive:'<rect x="3" y="4" width="18" height="4" rx="1"/><path d="M5 8v13h14V8M10 13h4"/>',
  link:'<path d="M9 15 15 9M7 8H5a4 4 0 0 0 0 8h5m4-8h5a4 4 0 0 1 0 8h-5"/>',
  cpu:'<rect x="5" y="5" width="14" height="14" rx="2"/><path d="M9 9h6v6H9zM9 1v4m6-4v4M9 19v4m6-4v4M1 9h4m-4 6h4m14-6h4m-4 6h4"/>'
};
const ico=(name,size=18)=>`<svg class="ic" viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.85" stroke-linecap="round" stroke-linejoin="round">${SVG[name]||SVG.verify}</svg>`;
const configs={
 tools:{title:'Hotend Control',sub:'Select and change a verified hotend',icon:'tools',steps:[['layers','Select Hotend'],['car','Confirm Carriage'],['upload','Load / Unload'],['verify','Verify Result']]},
 calibration:{title:'Dock XY Calibration',sub:'Supervised motor-on dock alignment',icon:'dock',steps:[['layers','Select Tool'],['printer','Check Printer'],['move','Align Dock'],['save','Save Dock XY'],['verify','Test'],['refresh','Reset']]},
 offsets:{title:'Tool XY Calibration',sub:'Camera-aligned nozzle offsets relative to T0',icon:'target',steps:[['target','Set T0 Reference'],['layers','Select Hotend'],['camera','Align Nozzle'],['save','Save Hotend'],['results','Review']]},
 'z-calibration':{title:'Tool Z Calibration',sub:'Cold commissioning · Z offsets not applied',icon:'tools',steps:[['target','T0 Reference'],['layers','Select Tools'],['printer','Prepare'],['play','Calibrate'],['results','Results']]},
 tests:{title:'Diagnostics',sub:'Read-only machine checks and troubleshooting',icon:'verify',steps:[['link','Connect'],['printer','Check Machine'],['save','Verify AutoSave'],['download','Export']]},
 updates:{title:'CXM Updates',sub:'Review and install verified source updates',icon:'download',steps:[['refresh','Check'],['verify','Review'],['download','Install']]},
 settings:{title:'Settings',sub:'Configure, AutoSave and verify',icon:'settings',steps:[['layers','Choose Area'],['settings','Edit'],['save','AutoSave'],['verify','Verify']]}
};
const stageEls={};
const liveCards={};
function node(tag,cls,html){const e=document.createElement(tag);if(cls)e.className=cls;if(html!==undefined)e.innerHTML=html;return e;}
function move(el,parent){if(el)parent.append(el);return el;}
function fromId(id,parent){return move($(id),parent);}
function wrapPart(stage,el){if(el)stage.querySelector('.cxma-inner').append(el);}
function card(n,name,desc=''){
 const e=node('section','panel cxma-stage');e.dataset.stage=String(n);
 e.innerHTML=`<div class="panel-head"><span class="step-num">${n}</span><div><h2>${name}</h2>${desc?`<p>${desc}</p>`:''}</div></div><div class="cxma-inner"></div>`;
 return e;
}
function safeLink(tab,text){const b=node('button','btn big',ico('layers')+text);b.type='button';b.addEventListener('click',()=>q(`.tab[data-tab="${tab}"]`)?.click());return b;}
function detail(title){const d=node('details','adv cxma-advanced');d.innerHTML=`<summary>${ico('settings',16)} ${title}</summary><div class="cxma-advanced-inner"></div>`;return d;}
function note(text){return node('p','cxma-note',text)}
function pill(text,kind='blue'){return node('span','pill '+kind,text)}
function stepBar(conf,page){const bar=node('nav','steps');bar.style.setProperty('--count',String(conf.steps.length));bar.setAttribute('aria-label',conf.title+' steps');
 conf.steps.forEach(([ic,label],i)=>{const b=node('button','step',`<span class="number">${i+1}</span>${ico(ic,20)}<span class="step-name">${label}</span>`);b.type='button';b.dataset.jump=String(i+1);b.dataset.state='idle';b.addEventListener('click',()=>{const target=stageEls[page]?.[i];if(target)target.scrollIntoView({behavior:'smooth',block:'center'});});bar.append(b)});return bar}
function badges(entries){const bar=node('div','statusstrip cxma-status');
 entries.forEach(([id,ic,label])=>{const item=node('div','status-item',`${ico(ic,19)}<strong>${label}</strong><span class="pill blue" data-live="${id}">Checking</span>`);bar.append(item)});
 return bar;}
function header(page,conf,area){const heading=node('div','page-heading cxma-heading',`<div class="heading-left"><span class="heading-icon">${ico(conf.icon,26)}</span><div><h1>${conf.title}</h1><p class="subheading">${conf.sub}</p></div></div>`);
 area.insertBefore(heading,area.firstChild);
 const original=q('.section-title',area);if(original){original.classList.add('cxma-original-title');original.hidden=true;}
 return heading;}
function make(page,entries){const area=q(`[data-panel="${page}"]`),conf=configs[page];if(!area||!conf)return;
 const legacy=node('div','cxma-legacy cxma-unused');const orig=[...area.children];orig.forEach(x=>legacy.append(x));
 // Keep the legacy subtree CONNECTED while reparenting controls by ID.
 // Detached nodes are invisible to document.getElementById().
 area.append(legacy);area.classList.add('cxma-page');header(page,conf,area);
 const bar=stepBar(conf,page);area.append(bar);const strip=badges(entries);area.append(strip);
 const stack=node('div','stack cxma-stack');area.append(stack);stageEls[page]=[];
 function stage(n,name,desc){const s=card(n,name,desc);stack.append(s);stageEls[page].push(s);return s;}
 return {area,legacy,stack,stage,bar,strip};
}
function populateBank(parent,role,selection){const bank=node('div','toolgrid cxma-toolbank');bank.dataset.bank=role;bank.dataset.selection=selection||'';parent.append(bank);liveCards[role]=bank;return bank;}
function showOriginalInAdvanced(advanced,els){const inner=q('.cxma-advanced-inner',advanced);els.filter(Boolean).forEach(x=>inner.append(x));}
function tools(){const p=make('tools',[['printer','printer','Klipper'],['car','car','Carriage'],['available','layers','Available'],['remaining','verify','Remaining']]);
 const stage=p.stage;
 const s1=stage(1,'Select hotend','Choose any T0–T11. Unaccepted tools go to supervised Dock XY setup; they cannot load yet.');
 populateBank(q('.cxma-inner',s1),'tools','cxmNativeSelectedTool');
 const setupHint=note('Select a hotend to load, or click an uncalibrated slot to set up its dock. No motion is sent by selecting a slot.');
 setupHint.id='cxmaToolSetupNotice';setupHint.setAttribute('role','status');setupHint.setAttribute('aria-live','polite');
 q('.cxma-inner',s1).append(setupHint);
 const count=q('.tool-count-control',p.legacy);if(count){const summary=node('div','cxma-inline-data');move(count,summary);q('.cxma-inner',s1).append(summary);const title=count.querySelector('label[for="cxmCountSelect"]');if(title)title.textContent='Enabled tool slots';}
 const s2=stage(2,'Confirm carriage','Confirm physical carriage identity before changing a hotend.');
 // The native controller MUST retain ownership of its entire panel, fieldset and
 // dynamically relocated slot: cxm-native-control.js moves this panel between
 // #cxmToolsChangeSlot and #cxmAxisChangeSlot on tab changes.
 fromId('cxmToolsChangeSlot',q('.cxma-inner',s2));
 const s3=stage(3,'Load or unload','Uses the same native disabled/inert and backend interlocks.');
 const r=node('div','row cxma-proxy-row');
 const load=node('button','btn big',ico('upload')+'Load selected hotend');load.type='button';load.dataset.proxy='cxmNativeSelect';
 const unload=node('button','btn outline',ico('download')+'Unload current hotend');unload.type='button';unload.dataset.proxy='cxmNativeUnload';
 r.append(load,unload);q('.cxma-inner',s3).append(r);
 // Keep recovery visible in the approved Tools workflow, independently of the
 // native motion fieldset (which may be disabled after a failed toolchange).
 fromId('cxmClearAllBox',q('.cxma-inner',s3));
 const s4=stage(4,'Verify result','Only the reported carriage sensor and controller state can confirm a change.');
 q('.cxma-inner',s4).append(node('p','cxma-real-status','Waiting for native tool status'));
 const adv=detail('Advanced · Detailed tool cards, speeds and repeated tests');p.stack.append(adv);
 showOriginalInAdvanced(adv,[$('toolGrid'),$('cxmNoTools'),q('.tool-overview-meta',p.legacy),q('.footer-note',p.legacy)]);
 p.area.append(p.legacy);p.legacy.classList.add('cxma-unused');
}
function dock(){const p=make('calibration',[['printer','printer','Klipper'],['homing','move','Homing'],['car','car','Carriage'],['dock','dock','Dock']]);
 const s1=p.stage(1,'Choose hotend','Choose a saved tool position for supervised setup.');
 populateBank(q('.cxma-inner',s1),'dock','cxmDockTool');
 const top=q('.dock-top',p.legacy);if(top){wrapPart(s1,top);top.classList.add('cxma-simple-panel')}
 const s3=p.stage(2,'Align dock','Jog to the release point. The controller checks printer readiness before every move.');
 // Keep the genuine motor-on jog controls and their existing listeners together;
 // move only the existing Save controls into the intended next step.
 const dockPanel=fromId('cxmManualDock',q('.cxma-inner',s3));
 const s4=p.stage(3,'Save dock XY','Save the live release-point coordinates.');
 const sections=dockPanel?qa(':scope > .cxm-step',dockPanel):[];
 if(sections.length>=2){
   const saveControls=sections[1];saveControls.classList.add('cxma-save-section');
   q('.cxma-inner',s4).append(saveControls);
   // The coordinate is recorded first. The independent +100/-100 travel
   // verification follows it on the same Dock XY page, not vice versa.
   const travel=$('cxmDockTravelCheck');
   if(travel)q('.cxma-inner',s4).append(travel);
   const oldHeading=q('.panel-heading',saveControls);if(oldHeading)oldHeading.hidden=true;
   const capture=$('cxmManualCapture');if(capture){capture.innerHTML=ico('save')+'Capture & save dock XY';capture.classList.add('big');}
 }
 const s5=p.stage(4,'Test pickup / dropoff','Run the existing native repeat test here.');
 const test=$('cxmMultiPanel');
 if(test){
   q('.cxma-inner',s5).append(test);
   const heading=q('.panel-heading h3',test);
   if(heading)heading.textContent='Native pickup / dropoff · repeatable reliability cycles';
 }

 const s6=p.stage(5,'Recovery / Reset','Clear faults or restart commissioning without changing pages.');
 const recovery=$('cxmClearAllBox');
 if(recovery)q('.cxma-inner',s6).append(recovery);
 const reset=$('cxmCommissionResetPanel');
 if(reset){
   const more=detail('Advanced · Reset ALL CXM calibrations');
   q('.cxma-advanced-inner',more).append(reset);
   q('.cxma-inner',s6).append(more);
 }
 const adv=detail('Advanced · Fine X adjustment and backups');p.stack.append(adv);
 showOriginalInAdvanced(adv,[$('cxmFineDock'),q('.dock-columns',p.legacy),q('.dock-bottom',p.legacy)]);
 p.area.append(p.legacy);p.legacy.classList.add('cxma-unused');
}
function offsets(){const p=make('offsets',[['camera','camera','Camera'],['target','target','T0 reference'],['car','car','Carriage'],['tool','layers','Tool']]);
 const s1=p.stage(1,'Set T0 camera reference','Centre T0 once, then store the common camera datum.');
 const r=node('div','row cxma-proxy-row');const reference=node('button','btn big',ico('target')+'Set T0 camera reference');reference.type='button';reference.dataset.proxy='cxmCameraReference';r.append(reference);q('.cxma-inner',s1).append(r);
 const s2=p.stage(2,'Select next hotend','Select a commissioned hotend; changing tools is supervised.');populateBank(q('.cxma-inner',s2),'xy','cxmAxisTool');
 const s3=p.stage(3,'Align nozzle to camera','Real Axiscope feed and supervised jog controls.');
 const s4=p.stage(4,'Save centred hotend','Save only the mounted, aligned tool.');
 const s5=p.stage(5,'Review and continue','Continue to the next accepted tool.');
 const grid=q('.axis-grid',p.legacy),work=q('.axis-workbench',p.legacy);
 if(work){
  const frame=$('cxmAxisFrame'),cameraSettings=q('.axis-camera-settings',work),jog=$('cxmAxisJog'),tool=$('cxmAxisTool')?.closest('.axis-row');
  const sessions=$('cxmCameraSession'),actions=$('cxmCameraActions'),next=$('cxmCameraNext'),res=$('cxmCameraResult');
  const row=node('div','cxma-cam-grid');q('.cxma-inner',s3).append(row);
  const cam=node('div','cxma-camera');row.append(cam);[frame,cameraSettings].forEach(x=>move(x,cam));
  const jogbox=node('div','cxma-jog');row.append(jogbox);[tool,jog].forEach(x=>move(x,jogbox));
  if(sessions)wrapPart(s2,sessions);fromId('cxmAxisChangeSlot',q('.cxma-inner',s2));if(actions)wrapPart(s4,actions);
  [next,res].forEach(x=>wrapPart(s5,x));
  const rest=detail('Advanced · Camera diagnostics and manual XY offsets');p.stack.append(rest);
  showOriginalInAdvanced(rest,[work,q('.axis-table-panel',grid),q('.cxm-simple-editor',grid)]);
 }
 p.area.append(p.legacy);p.legacy.classList.add('cxma-unused');
}
function z(){const area=q('[data-panel="z-calibration"]');if(!area)return;
 area.classList.add('cxma-page','cxma-z-native');
 // Keep entire proven Tool Z DOM and step-state logic untouched.
 const heading=q('.cxm-flow-topline',area);if(heading){heading.classList.add('cxma-z-title');const h=heading.querySelector('h2');if(h){h.innerHTML=`${ico('tools',23)} <span>Tool Z Calibration</span>`}}
 // No new buttons, no mirrored status state and no changes to the Tool Z backend.
}
function updates(){const p=make('updates',[['source','link','Source'],['repo','verify','Repository'],['installed','download','Installed'],['printer','printer','Printer']]);
 const a=p.stage(1,'Check for updates','Ask Moonraker for the latest CXM source version.');
 const ver=node('div','simplegrid cxma-version-grid');
 for(const [id,label] of [['installedVersion','Installed'],['remoteVersion','Available'],['repo','Repository']]){const metric=node('div','metric',`<span class="metric-label">${label}</span>`);fromId(id,metric);ver.append(metric)}
 const b=$('checkUpdates');if(b){b.innerHTML=ico('refresh')+'Check for updates';b.classList.add('big');wrapPart(a,b)}q('.cxma-inner',a).append(ver);
 const rev=p.stage(2,'Review release','Confirm source validity, changes and required reloads.');
 const info=node('div','statuspanel cxma-review');info.append(node('strong','cxma-review-title','Waiting for update check'));
 info.append(node('p','cxma-review-message','When an update is available, verify the change list and whether a web, service or Klipper reload is required.'));
 info.append(node('p','cxma-note','The interface cannot infer file changes from a version number. Unknown reload type must remain unverified.'));
 q('.cxma-inner',rev).append(info);
 const install=p.stage(3,'Install approved update','Available only when Moonraker authorises a valid idle update.');
 const bt=$('installUpdate');if(bt){bt.innerHTML=ico('download')+'Install CXM update';bt.classList.add('big');wrapPart(install,bt)}
 wrapPart(install,$('devModePanel'));q('.cxma-inner',install).append(note('A completed Git update is not proof that altered Klipper macros are loaded.'));
 const adv=detail('Advanced · Exact repository state, Moonraker activity and recovery');p.stack.append(adv);
 showOriginalInAdvanced(adv,[$('updateBadge'),$('channel'),$('updateState'),$('activityLog'),$('lastChecked'),q('.sidebar-panel',p.legacy)]);
 p.area.append(p.legacy);p.legacy.classList.add('cxma-unused');
}
function settings(){const p=make('settings',[['store','save','AutoSave'],['backup','archive','Backups'],['source','verify','Source']]);
 const s1=p.stage(1,'Choose settings area','Select the configuration area to edit.');
 const row=node('div','row cxma-settings-nav');
 ['Tool configuration','Dock geometry','Motion speeds','Connection & backups'].forEach((text,i)=>{
 const b=node('button',i?'btn outline':'btn big',ico(['layers','dock','move','settings'][i])+text);b.type='button';b.addEventListener('click',()=>{
   qa('.cxma-settings-nav button').forEach(x=>{x.classList.remove('big');x.classList.add('outline')});b.classList.remove('outline');b.classList.add('big');
   const editor=$('configEditor');if(!editor)return;
   if(i===2){const adv=q('details.cxm-advanced',editor);if(adv)adv.open=true;}
   if(i===3){const history=$('cxmHistory');if(history&&!history.disabled)history.click();}
   const target=i===0?$('cxmToolChoice'):i===1?q('[data-key="cxm_shift_x"]',editor):i===2?q('[data-key="approach_speed"]',editor):$('cxmHistory');
   (target||editor).scrollIntoView({behavior:'smooth',block:'center'});
 });row.append(b)});q('.cxma-inner',s1).append(row);
 // Full recommissioning is owned by Dock XY; do not move the live reset
 // widget back into Settings after Dock XY has mounted it.
 q('.cxma-inner',s1).append(note('Full commissioning reset and native fault recovery are on Dock XY, alongside its supervised calibration and reliability test.'));
 const s2=p.stage(2,'Edit tool configuration','Edit real CXM settings with the existing AutoSave controls.');fromId('configEditor',q('.cxma-inner',s2));
 const s3=p.stage(3,'AutoSave to disk','Only disk persistence is confirmed, not live Klipper macro activation.');
 q('.cxma-inner',s3).append(note('AutoSave is handled by the existing CXM settings editor. Changes to motion macros may need a separate reload.'));
 const s4=p.stage(4,'Verify changes','Check current stored revision without changing it.');
 const b=node('button','btn big',ico('verify')+'Check saved settings');b.type='button';const result=node('p','cxma-note','Not checked');result.id='cxma-setting-check';
 b.addEventListener('click',async()=>{b.disabled=true;result.dataset.verified='false';result.textContent='Checking saved settings…';try{
   const response=await fetch('/cxm/api/v1/config',{credentials:'same-origin',cache:'no-store'});if(!response.ok)throw Error('HTTP '+response.status);
   const data=await response.json();if(!data.config||!(typeof data.revision==='number'||(typeof data.revision==='string'&&data.revision.trim())))throw Error('No verified revision returned');
   result.textContent='Stored configuration confirmed · revision '+data.revision+' · read-only check';result.dataset.verified='true';
 }catch(e){result.textContent='Unable to verify saved configuration: '+e.message;result.dataset.verified='false';}finally{b.disabled=false;}});
 q('.cxma-inner',s4).append(b,result);
 const adv=detail('Advanced · Full configuration and diagnostics');p.stack.append(adv);showOriginalInAdvanced(adv,[q('.cxm-advanced',p.legacy)]);
 p.area.append(p.legacy);p.legacy.classList.add('cxma-unused');
}
function tests(){const p=make('tests',[['moon','link','Moonraker'],['klipper','printer','Klipper'],['store','save','Data store'],['motion','car','Motion']]);
 const s1=p.stage(1,'Connect to services','Read current Moonraker and CXM state.');const t=$('cxmTestRun');if(t){t.innerHTML=ico('refresh')+'Refresh diagnostics';t.classList.add('big');wrapPart(s1,t)}
 const s2=p.stage(2,'Check machine health','Display actual machine status and current readiness.');
 const origin=qa(':scope > .panel',p.legacy);if(origin[0])wrapPart(s2,origin[0]);
 const s3=p.stage(3,'Verify AutoSave without restarting Klipper','Capture a baseline, change a harmless setting, then compare.');if(origin[1])wrapPart(s3,origin[1]);
 const s4=p.stage(4,'Export diagnostics','Download the real read-only diagnostics report.');const exp=$('cxmTestDownload');if(exp){exp.innerHTML=ico('download')+'Export diagnostic JSON';exp.classList.add('big');wrapPart(s4,exp)}
 const adv=detail('Advanced · Historical commissioning warnings');p.stack.append(adv);showOriginalInAdvanced(adv,[q('.dock-warning',p.legacy),origin[2]]);
 p.area.append(p.legacy);p.legacy.classList.add('cxma-unused');
}
function applyIcons(){qa('.tab[data-tab]').forEach(t=>{const c=configs[t.dataset.tab];if(!c)return;if(t.dataset.tab==='tests')t.hidden=false;const text={tools:'Tools',calibration:'Dock XY',offsets:'Tool XY','z-calibration':'Tool Z',tests:'Diagnostics',updates:'Updates',settings:'Settings'}[t.dataset.tab];
 const dot=$('updateDot');if(dot&&t.dataset.tab==='updates'){t.replaceChildren();t.insertAdjacentHTML('afterbegin',ico(c.icon,16)+' '+text+' ');t.append(dot)}
 else t.innerHTML=ico(c.icon,16)+' '+text; t.setAttribute('aria-label',text)});
 const brand=q('.topbar .brand');if(brand){brand.classList.add('cxma-brand');const mark=q('.brand-mark',brand);if(mark)mark.innerHTML='<span class="cxma-mark" aria-hidden="true"></span>CXM';}
 const logo=q('.topbar .brand small');if(logo)logo.textContent='Control Centre';
}
function texts(){const x=id=>($(id)?.textContent||'').trim();return x}
function checkState(page){const x=texts();const state=[];const hom=x('homing'),klip=x('klipperStatus'),printer=x('printStatus');
 const okPrinter=/ready|standby|idle/i.test(printer)&&!/(print|pause|error|shutdown)/i.test(printer);
 const homed=/xyz|x.*y.*z|homed/i.test(hom)&&!(/not homed|unhomed/i.test(hom));
 const change=x('cxmNativeToolStatus'),dockStatus=x('cxmDockStatus'),native=x('cxmChangeResult');
 const carriage=/(carriage EMPTY.*sensor RELEASED|carriage T\d+ mounted.*sensor PRESSED)/i.test(change);
 const cameraRef=!!x('cxmCameraDatum')&&!/not set|unavailable|not verified|checking|awaiting/i.test(x('cxmCameraDatum'));
 const stageFn=(states,cur=0)=>states.map((s,i)=>s?'complete':i===cur?'active':'idle');
 switch(page){
 case 'tools':{
 const tgt=$('cxmNativeSelectedTool')?.value;
 state.push(tgt!==undefined&&tgt!=='',carriage,/verified|completed|success/i.test(native)&&!/failed|error/i.test(native),/sensor confirmed|carriage (EMPTY|T\d+ mounted)/i.test(change)&&carriage&&/verified|completed|success/i.test(native));break;}
 case 'calibration':{
 const selected=$('cxmDockTool')?.value||'';const mr=x('cxmManualReadiness'),feed=x('cxmManualFeedback');
 state.push(selected!=='',false,/saved|confirmed/i.test(feed)&&!/not saved|unsaved|error|failed/i.test(feed),false,false);break;}
 case 'offsets':{
 const ref=$('cxmCameraReference'),res=x('cxmCameraResult'),next=x('cxmCameraNext');
 state.push(cameraRef,!!$('cxmAxisTool')?.value,false,/saved/i.test(res)&&!/unsaved|cannot|error|failed/i.test(res),/complete/i.test(next));break;}
 case 'updates':{
 const valid=/up.to.date|no confirmed updates|ready|available|new update|update available/i.test(x('updateState'))&&!/dirty|invalid|blocked|failed|error/i.test(x('updateState'));
 state.push(valid,false,false);break;}
 case 'settings':{
 const saved=x('saveStatus');state.push(false,false,/autosaved|saved/i.test(saved)&&!/not saved|error/i.test(saved),q('#cxma-setting-check')?.dataset.verified==='true');break;}
 case 'tests':{
 state.push(/connected|ready/i.test(klip),/connected|ready/i.test(klip),/pass|verified|match/i.test(x('cxmTestRestartResult'))&& !/mismatch|error|failed/i.test(x('cxmTestRestartResult')),/export(ed)?/i.test(x('cxmTestLast')));break;}
 }
 return {states:state,okPrinter,homed,carriage,change,klip,printer,hom};
}
// A slot is not permission to move. Existing settings own count AutoSave and
// Dock XY owns physical calibration; this UI only delegates to those controls.
let pendingToolSetup=null;
function setupNotice(message){
 const target=$('cxmaToolSetupNotice');if(target)target.textContent=message;
}
function startDockSetup(n){
 window.dispatchEvent(new CustomEvent('cxm-calibrate-tool',{detail:{tool:n}}));
}
function setupSlot(n){
 if(!Number.isInteger(n)||n<0||n>=12||pendingToolSetup!==null)return;
 const control=$('cxmCountSelect');const count=Number(control?.value);
 if(!Number.isInteger(count)||count<1||count>12){setupNotice('Cannot verify enabled tool slots. Refresh configuration first.');return;}
 if(n<count){setupNotice('Opening T'+n+' Dock XY setup. Saved coordinates and motion remain protected.');startDockSetup(n);return;}
 if(!control||control.disabled){setupNotice('Settings are not ready to add T'+n+'. Check AutoSave and configuration state.');return;}
 const next=n+1;
 if(next>count+1&&!window.confirm('Enable tool slots T'+count+'–T'+n+'?\n\nThese slots will be UNCALIBRATED and cannot move automatically until their docks are physically verified.'))return;
 pendingToolSetup={n,count:next};
 setupNotice('AutoSaving tool slots through T'+n+'… No tool movement.');
 control.value=String(next);
 control.dispatchEvent(new Event('change',{bubbles:true}));
}
window.addEventListener('cxm-tool-count-saved',event=>{
 if(!pendingToolSetup)return;
 const {n,count}=pendingToolSetup;pendingToolSetup=null;
 if(event.detail?.tool_count!==count){setupNotice('Tool count differs from requested count. Refresh before calibrating.');return;}
 setupNotice('Tool slots through T'+n+' saved and verified. Opening T'+n+' Dock XY setup.');
 startDockSetup(n);
});
window.addEventListener('cxm-tool-count-save-failed',event=>{
 if(!pendingToolSetup)return;
 const n=pendingToolSetup.n;pendingToolSetup=null;
 setupNotice('T'+n+' was NOT added: '+String(event.detail?.error||'Save was not verified')+'. No docking action sent.');
});
function updateBank(bank,stats){
 const role=bank.dataset.bank,select=$(bank.dataset.selection),current=select?.value;
 const options=select?.options?Array.from(select.options):[];
 const option=n=>options.find(o=>o.value===String(n));
 // Camera selection is a NATIVE TOOLCHANGE, not a local choice of number.
 // Only the native camera controller's verified/eligible live buttons can be used.
 const nativeCamera=n=>qa('#cxmCameraTools button[data-tool]').find(b=>b.dataset.tool===String(n));
 if(bank.childElementCount!==12){bank.replaceChildren();for(let n=0;n<12;n++){
   const b=node('button','cxma-tool-choice',`<span class="toolname"><b>T${n}</b>${ico('layers',16)}</span><small></small>`);
   b.type='button';b.dataset.number=String(n);
   b.addEventListener('click',()=>{
     if(role==='xy'){
       const original=nativeCamera(n),panel=$('cxmNativeToolPanel');
       if(!original||original.disabled||panel?.inert||original.closest('[inert]')||original.closest('fieldset:disabled')||$('cxmChangeControls')?.disabled)return;
       original.click();return;
     }
     const sel=$(bank.dataset.selection),opt=sel&&Array.from(sel.options).find(x=>x.value===String(n));
     const count=Number($('cxmCountSelect')?.value);
     const dockOption=Array.from($('cxmDockTool')?.options||[]).find(x=>x.value===String(n));
     if(dockOption?.textContent?.includes('LOCKED OUT')){
       setupNotice('T'+n+' is in maintenance lockout. Inspect its lockout in Settings; no movement is permitted.');
       window.dispatchEvent(new CustomEvent('cxm-edit-tool',{detail:{tool:n}}));return;
     }
     if(role==='tools'&&(!opt||opt.disabled)){setupSlot(n);return;}
     if(role==='dock'&&(!opt||!Number.isInteger(count)||n>=count)){setupSlot(n);return;}
     if(!sel||!opt||opt.disabled)return;
     sel.value=String(n);sel.dispatchEvent(new Event('change',{bubbles:true}));updateAll();
   });bank.append(b)
 }}
 qa('button',bank).forEach((button,n)=>{
   const o=option(n),cam=role==='xy'?nativeCamera(n):null;
   const control=$('cxmCountSelect'),count=Number(control?.value);
   const countKnown=Number.isInteger(count)&&count>=1&&count<=12;
   const configured=countKnown&&n<count;
   const dockOption=Array.from($('cxmDockTool')?.options||[]).find(x=>x.value===String(n));
   const locked=configured&&!!dockOption?.textContent?.includes('LOCKED OUT');
   const nativeEligible=!!o&&!o.disabled;
   const setupReady=role!=='xy'&&countKnown&&pendingToolSetup===null&&
     !locked&&(configured||!!control&&!control.disabled);
   const cameraAvailable=!!cam&&!cam.disabled&&!cam.closest('fieldset:disabled')&&!cam.closest('[inert]')&&!$('cxmNativeToolPanel')?.inert&&!$('cxmChangeControls')?.disabled;
   const available=role==='xy'?cameraAvailable:role==='tools'?(nativeEligible||setupReady):(nativeEligible||setupReady);
   const selected=role==='xy'?cam?.getAttribute('aria-current')==='true':current===String(n);
   const hint=role==='xy'?(cam?cam.getAttribute('aria-label')||'Eligible camera tool':'Dock not accepted · Tool XY locked'):
     locked?'Maintenance lockout · open Settings':
     !configured?'Add slot · set up Dock XY':
     role==='dock'?'Select for supervised dock calibration':
     nativeEligible?'Dock accepted · select for load':'Set up dock XY · no automatic load';
   button.querySelector('small').textContent=hint;
   button.disabled=role==='xy'?!cameraAvailable:locked?!countKnown:!available;
   button.classList.toggle('selected',!!selected);
   button.classList.toggle('unready',!nativeEligible);
   button.classList.toggle('setup-needed',role!=='xy'&&!nativeEligible&&available&&!locked);
   button.setAttribute('aria-pressed',String(!!selected));
   button.title=hint;
 });
}
function setPill(el,txt,kind){if(!el)return;el.textContent=txt;el.className='pill '+kind}
function updateAll(){const x=texts();const printer=x('printStatus');const state=checkState('tools');
 const h=x('homing');const printerReady=/ready|idle|standby/i.test(printer)&&!/printing|paused|error/i.test(printer);
 const repo=x('updateState');
 const carousel=Object.entries(stageEls);
 for(const [name,stages] of carousel){
 const {states}=checkState(name);
 const err=/error|fault|failed|stopped_error/i.test(name==='tools'?x('cxmChangeResult'):name==='calibration'?x('cxmManualFeedback'):name==='offsets'?x('cxmCameraResult'):name==='updates'?repo:name==='tests'?x('cxmTestLast'):'');
 const steps=qa('.steps .step',q(`[data-panel="${name}"]`));let next=states.indexOf(false);if(next<0)next=states.length-1;
 steps.forEach((b,i)=>{let v=states[i]?'complete':i===next?'active':'idle';if(err&&i===next)v='error';b.classList.remove('idle','active','complete','error');b.classList.add(v);b.dataset.state=v;b.setAttribute('aria-label',`Step ${i+1}: ${configs[name].steps[i][1]} · ${v}`)});
 stages.forEach((c,i)=>{const v=steps[i]?.dataset.state||'idle';c.classList.toggle('done',v==='complete');c.classList.toggle('current',v==='active');c.classList.toggle('error',v==='error');});
 }
 const as=(page,key,t,kind)=>setPill(q(`[data-panel="${page}"] [data-live="${key}"]`),t,kind);
 for(const page of ['tools','calibration','updates'])as(page,'printer',printer||'Unknown',printerReady?'ok':'warn');
 as('tools','car',state.carriage?state.change.replace(/^Carriage\s+/,'').split(' · ')[0]:'Unknown',state.carriage?'ok':'warn');
 const toolsList=$('cxmNativeSelectedTool');const eligible=toolsList?Array.from(toolsList.options).filter(o=>o.value!==''&&!o.disabled).map(o=>'T'+o.value):[];
 as('tools','available',eligible.length?eligible.join(', '):'Not verified',eligible.length?'ok':'warn');
 as('tools','remaining','12 slots visible','blue');
 const realTool=q('[data-panel="tools"] .cxma-real-status');if(realTool)realTool.textContent=x('cxmChangeResult')||x('cxmNativeToolStatus')||'Waiting for native tool status';
 const dockSave=q('[data-panel="calibration"] [data-stage="3"] .cxma-real-status');if(dockSave)dockSave.textContent=x('cxmManualFeedback')||'Awaiting saved coordinates';

 as('calibration','homing',h||'Unknown',state.homed?'ok':'warn');as('calibration','car',state.carriage?'Verified':'Inspect',state.carriage?'ok':'warn');
 as('calibration','dock',$('cxmDockTool')?.selectedOptions?.[0]?.textContent||'Choose','blue');
 as('offsets','camera',/unavailable|configure|not/i.test(x('cxmAxisCameraMessage'))?'Unavailable':'Check feed','blue');
 as('offsets','target',x('cxmCameraDatum')?.slice(0,32)||'Not set','blue');as('offsets','car',x('cxmCameraCarriageState')||'Unknown','blue');as('offsets','tool','T'+($('cxmAxisTool')?.value||'—'),'blue');
 as('updates','source',x('repo')||'Unknown','blue');as('updates','repo',/dirty|invalid|blocked/i.test(repo)?'Blocked':'Check status',/dirty|invalid|blocked/i.test(repo)?'warn':'blue');
 as('updates','installed',x('installedVersion')||'—','blue');
 as('tests','moon',/connected/i.test(x('connection'))?'Connected':'Check','blue');as('tests','klipper',x('cxmTestKlipper')||'Checking','blue');as('tests','store',x('cxmTestStore')||'Checking','blue');as('tests','motion','Read-only','ok');
 as('settings','store',x('saveStatus')||'Checking','blue');as('settings','backup','CXM disk','blue');as('settings','source','CXM_variables.cfg','blue');
 for(const bank of Object.values(liveCards))updateBank(bank,state);
 const rev=q('.cxma-review');if(rev){
 const available=/available|outdated|new update/i.test(repo)&&!/no confirmed|not available|no update/i.test(repo);
 const upToDate=/up.to.date|no confirmed updates|current/i.test(repo);
 q('.cxma-review-title',rev).textContent=available?'Update available — review required':upToDate?'No newer CXM release available':repo||'Awaiting update check';
 q('.cxma-review-message',rev).textContent=available?'Check the release notes and exact file changes before installing. Do not assume the reload type from the version alone.':upToDate?'GitHub and the installed source are already at the same version. Nothing to install.':'Use Check for Updates to retrieve the current Moonraker result.';
 }
 for(const el of qa('button[data-proxy]')){const target=$(el.dataset.proxy);el.disabled=!target||target.disabled||!!target.closest('fieldset:disabled')||!!target.closest('[inert]');}
}
function proxies(){for(const b of qa('button[data-proxy]'))b.addEventListener('click',()=>{
 const target=$(b.dataset.proxy);if(target&&!target.disabled&&!target.closest('fieldset:disabled')&&!target.closest('[inert]'))target.click();
 });}
function mount(){if(document.body.classList.contains('cxm-approved-v1'))return;document.body.classList.add('cxm-approved-v1');
 const main=q('main');if(main)main.classList.add('cxma-shell');
 applyIcons();
 // Existing Tool Z keeps the tested five-arrow workflow unchanged.
 tools();dock();offsets();z();updates();settings();tests();proxies();
 // Visually remove previous generic ribbons. They never owned live state.
 qa('.cxm-workflow-ribbon').forEach(e=>e.remove());
 updateAll();setInterval(updateAll,1600);
 window.addEventListener('cxm-camera-offset-saved',updateAll);
}
try{mount()}catch(e){console.error('CXM approved visual layout refused to mount; original controls remain available',e);document.body.classList.remove('cxm-approved-v1');}
})();
