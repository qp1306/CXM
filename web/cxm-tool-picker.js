/* CXM V0.6 — accessible coloured tool picker for Dock, Axiscope and Settings.
   Native HTML <option> cannot be styled consistently in Safari.
   Keep the original <select> as source of truth and keyboard fallback.
*/
(function(){
  'use strict';
  const colour=n=>window.CXMToolStyle?.color(n)||'#b6c4d5';
  function sync(select,config){
    if(!select||!config)return;
    let widget=select.nextElementSibling;
    if(!widget?.classList?.contains('cxm-tool-picker')){
      widget=document.createElement('div');
      widget.className='cxm-tool-picker';
      const toggle=document.createElement('button');
      toggle.type='button'; toggle.className='cxm-picker-trigger';
      toggle.setAttribute('aria-haspopup','listbox');toggle.setAttribute('aria-expanded','false');
      const menu=document.createElement('div');
      menu.className='cxm-picker-menu'; menu.setAttribute('role','listbox');
      menu.hidden=true;widget.append(toggle,menu);
      select.insertAdjacentElement('afterend',widget);
      toggle.addEventListener('click',()=>{
        if(select.disabled)return;
        const opening=menu.hidden;
        document.querySelectorAll('.cxm-picker-menu').forEach(x=>{x.hidden=true;});
        document.querySelectorAll('.cxm-picker-trigger').forEach(x=>x.setAttribute('aria-expanded','false'));
        menu.hidden=!opening;toggle.setAttribute('aria-expanded',String(opening));
        if(opening)menu.querySelector('[aria-selected="true"]')?.focus();
      });
      toggle.addEventListener('keydown',event=>{
        if(event.key==='ArrowDown'||event.key==='Enter'||event.key===' '){
          event.preventDefault();if(menu.hidden)toggle.click();
        }
      });
      menu.addEventListener('keydown',event=>{
        const buttons=[...menu.querySelectorAll('[role="option"]')];
        const idx=buttons.indexOf(document.activeElement);
        if(event.key==='Escape'){event.preventDefault();menu.hidden=true;toggle.setAttribute('aria-expanded','false');toggle.focus();}
        if(event.key==='ArrowDown'||event.key==='ArrowUp'){
          event.preventDefault();buttons[(idx+(event.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length]?.focus();
        }
      });
    }
    select.classList.add('cxm-native-tool-select');
    const toggle=widget.querySelector('.cxm-picker-trigger'),menu=widget.querySelector('.cxm-picker-menu');
    menu.replaceChildren();
    const items=[...select.options];
    const selected=Number(select.value);
    for(const item of items){
      const n=Number(item.value);
      if(!Number.isInteger(n)||n<0||n>=12)continue;
      const tool=config.tools[n];
      const s=window.CXMToolState?.classify(tool,n,config.globals.tool_count,{});
      const option=document.createElement('button');
      option.type='button';option.className='cxm-picker-option';
      option.setAttribute('role','option');
      option.setAttribute('aria-selected',String(n===selected));
      option.style.setProperty('--tool-color',colour(n));
      const dot=document.createElement('span');dot.className='cxm-picker-dot';
      const name=document.createElement('strong');name.textContent='T'+n+(n===0?' · reference':'');
      const status=document.createElement('small');status.textContent=s?.label||'UNVERIFIED';
      option.append(dot,name,status);
      option.addEventListener('click',()=>{
        select.value=String(n);
        menu.hidden=true;toggle.setAttribute('aria-expanded','false');
        select.dispatchEvent(new Event('change',{bubbles:true}));
        toggle.focus();
      });
      menu.append(option);
    }
    toggle.disabled=select.disabled||!menu.children.length;
    toggle.style.setProperty('--tool-color',colour(selected));
    toggle.replaceChildren();
    const dot=document.createElement('span');dot.className='cxm-picker-dot';
    const name=document.createElement('strong');name.textContent='T'+selected+(selected===0?' · reference':'');
    const note=document.createElement('small');
    note.textContent=window.CXMToolState?.classify(config.tools[selected],selected,config.globals.tool_count,{})?.label||'NOT READY';
    toggle.append(dot,name,note);
  }
  if(typeof document!=='undefined'){
    document.addEventListener('pointerdown',event=>{
      for(const widget of document.querySelectorAll('.cxm-tool-picker')){
        if(widget.contains(event.target))continue;
        const menu=widget.querySelector('.cxm-picker-menu');
        if(menu)menu.hidden=true;
        widget.querySelector('.cxm-picker-trigger')?.setAttribute('aria-expanded','false');
      }
    });
  }
  if(typeof window!=='undefined')window.CXMToolPicker={sync};
})();
