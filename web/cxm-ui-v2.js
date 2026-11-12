/* CXM visual-only progressive enhancement for ALL existing tabs. No API / motion. */
(()=>{
  'use strict';
  if(typeof document==='undefined')return;
  const patterns={
    tools:['Identify','Load / Unload','Verify','Test'],
    calibration:['Select dock','Align XY','Save position','Verify'],
    offsets:['Set T0 camera','Select hotend','Align XY','Save'],
    'z-calibration':[],  // Dedicated fully ordered Tool Z workflow in page source.
    tests:['Check','Capture','Verify'],
    updates:['Check','Review','Install'],
    settings:['Select','Adjust','Save']
  };
  for(const [name,labels] of Object.entries(patterns)){
    if(!labels.length)continue;
    const area=document.querySelector('section[data-panel="'+name+'"]');
    if(!area || area.querySelector('.cxm-workflow-ribbon'))continue;
    const ribbon=document.createElement('div');
    ribbon.className='cxm-workflow-ribbon';
    ribbon.setAttribute('aria-label',name+' workflow');
    for(let i=0;i<labels.length;i++){
      const chip=document.createElement('span');
      const num=document.createElement('b');num.textContent=String(i+1);
      chip.appendChild(num);chip.appendChild(document.createTextNode(labels[i]));
      ribbon.appendChild(chip);
    }
    const title=area.querySelector('.section-title');
    if(title)title.insertAdjacentElement('afterend',ribbon);
    else area.insertBefore(ribbon,area.firstChild);
  }
  document.documentElement.classList.add('cxm-ui-v2');
})();
