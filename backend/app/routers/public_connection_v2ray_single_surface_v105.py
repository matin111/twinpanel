from __future__ import annotations

"""One canonical V2Ray server list on the public Connection page.

V54's asynchronous /sub/meta server groups and V67's legacy rows both used to
compete with newer V80 visual overrides. Their race caused one of three
different layouts to appear after refresh. The old DOM remains available as a
read-only data/action source but is never a visible presentation for V2Ray.

No changes to VPN profiles, endpoints, share links or other protocol panels.
"""

_MARKER = "TWINPANEL_PUBLIC_V2RAY_SINGLE_SURFACE_V105"

_CSS = r"""
/* TWINPANEL_PUBLIC_V2RAY_SINGLE_SURFACE_V105 */
/* Hide competing V2Ray presentations even before the async metadata resolves. */
html body.tp80-connection .protocol-panel[data-v54-v2ray="1"] > .v54-v2ray-groups,
html body.tp80-connection .protocol-panel[data-v54-v2ray="1"] > .ref67-list,
html body.tp80-connection .protocol-panel[data-v54-v2ray="1"] > .ref67-tabs,
html body.tp80-connection .protocol-panel[data-v54-v2ray="1"] > .tp74-country-bar,
html body.tp80-connection .protocol-panel[data-v54-v2ray="1"] > .tp92-v2-country-bar,
html body.tp80-connection .protocol-panel[data-v54-v2ray="1"] > .tp80-country-bar,
html body.tp80-connection .protocol-panel[data-v54-v2ray="1"] > .tp93-country-bar,
html body.tp80-connection .protocol-panel[data-v54-v2ray="1"] > .server-views,
html body.tp80-connection .protocol-panel[data-v54-v2ray="1"] > .v57-v2ray-server-tabs,
html body.tp80-connection .protocol-panel.tp105-v2ray > .v54-v2ray-groups,
html body.tp80-connection .protocol-panel.tp105-v2ray > .ref67-list,
html body.tp80-connection .protocol-panel.tp105-v2ray > .ref67-tabs,
html body.tp80-connection .protocol-panel.tp105-v2ray > .tp74-country-bar,
html body.tp80-connection .protocol-panel.tp105-v2ray > .tp92-v2-country-bar,
html body.tp80-connection .protocol-panel.tp105-v2ray > .tp80-country-bar,
html body.tp80-connection .protocol-panel.tp105-v2ray > .tp93-country-bar,
html body.tp80-connection .protocol-panel.tp105-v2ray > .server-views,
html body.tp80-connection .protocol-panel.tp105-v2ray > .v57-v2ray-server-tabs {
  display:none!important;
}

/* Same compact left-copy/right-flag rows as the customer's third reference. */
html body.tp80-connection .protocol-panel.tp105-v2ray > .tp105-v2ray-shell {
  display:block!important;
  order:4!important;
  margin:9px 16px 13px!important;
  padding:0!important;
  border:0!important;
  background:transparent!important;
  width:auto!important;
  align-self:stretch!important;
  min-width:0!important;
}
html body.tp80-connection .tp105-v2ray-filter {
  display:flex!important;
  direction:ltr!important;
  justify-content:flex-start!important;
  flex-wrap:wrap!important;
  gap:7px!important;
  margin:0 0 10px!important;
}
html body.tp80-connection .tp105-v2ray-filter button {
  display:inline-flex!important;
  direction:ltr!important;
  gap:6px!important;
  align-items:center!important;
  padding:7px 11px!important;
  min-height:35px!important;
  border-radius:9px!important;
  border:1px solid var(--tp-brand-stroke,#344563)!important;
  color:var(--tp-brand-text,#eef2ff)!important;
  background:var(--tp-brand-raised,#1b2843)!important;
  font:800 11px Tahoma,Arial,sans-serif!important;
  cursor:pointer!important;
  box-shadow:none!important;
}
html body.tp80-connection .tp105-v2ray-filter button.active {
  color:#fff!important;
  background:linear-gradient(120deg,var(--p,#2563eb),var(--s,#0891b2))!important;
  border-color:var(--p,#2563eb)!important;
}
html body.tp80-connection .tp105-v2ray-filter img,
html body.tp80-connection .tp105-v2ray-name img {
  display:block!important;width:23px!important;height:17px!important;
  object-fit:cover!important;border-radius:3px!important;
  flex:0 0 23px!important;
}
html body.tp80-connection .tp105-v2ray-list {
  display:block!important;
  border:1px solid var(--tp-brand-stroke,#344563)!important;
  border-radius:14px!important;
  overflow:hidden!important;
  min-width:0!important;
  background:var(--tp-brand-card,#101b33)!important;
}
html body.tp80-connection .tp105-v2ray-row {
  display:flex!important;
  align-items:center!important;
  justify-content:space-between!important;
  direction:ltr!important;
  min-height:60px!important;
  padding:10px 14px!important;
  gap:10px!important;
  border:0!important;
  border-bottom:1px solid var(--tp-brand-stroke,#344563)!important;
  background:var(--tp-brand-card,#101b33)!important;
}
html body.tp80-connection .tp105-v2ray-row:last-child {border-bottom:0!important}
html body.tp80-connection .tp105-v2ray-row[hidden] {display:none!important}
html body.tp80-connection .tp105-v2ray-name {
  display:inline-flex!important;align-items:center!important;
  justify-content:flex-end!important;gap:9px!important;
  direction:ltr!important;white-space:nowrap!important;
  color:var(--tp-brand-text,#fff)!important;
  font:850 12px Tahoma,Arial,sans-serif!important;
  min-width:0!important;
}
html body.tp80-connection .tp105-v2ray-copy {
  display:inline-flex!important;
  align-items:center!important;
  justify-content:center!important;
  gap:5px!important;
  direction:rtl!important;
  white-space:nowrap!important;
  padding:8px 11px!important;
  min-width:90px!important;
  min-height:34px!important;
  border-radius:9px!important;
  border:1px solid var(--tp-brand-stroke,#3b5274)!important;
  background:var(--tp-brand-raised,#202d47)!important;
  color:var(--tp-brand-text,#f5f8ff)!important;
  font:850 11px Tahoma,Arial,sans-serif!important;
  cursor:pointer!important;
  box-shadow:none!important;
}
html body.tp80-connection .tp105-v2ray-copy:disabled {opacity:.5!important;cursor:not-allowed!important}
html body.tp80-connection .tp105-v2ray-empty {
  padding:20px 15px!important;
  text-align:center!important;
  color:var(--tp-brand-muted,#a6adc0)!important;
  font:750 12px Tahoma,Arial,sans-serif!important;
}
@media(max-width:720px){
 html body.tp80-connection .protocol-panel.tp105-v2ray > .tp105-v2ray-shell {
   margin:8px!important;
 }
 html body.tp80-connection .tp105-v2ray-row {
   min-height:55px!important;padding:8px 10px!important;
 }
 html body.tp80-connection .tp105-v2ray-copy {
   min-width:75px!important;font-size:10px!important;
   padding:7px!important;
 }
 html body.tp80-connection .tp105-v2ray-name {
   gap:6px!important;font-size:11px!important;
 }
}
"""

_SCRIPT = r"""
<script id="twinpanelPublicV2raySingleSurfaceV105">
(function(){
 'use strict';
 if(!/^\/v1\/connect\/[^/]+\/?$/.test(location.pathname))return;
 document.documentElement.classList.add('tp105-v2ray-canonical');
 const states=new WeakMap();
 const validCode=code=>/^[A-Z]{2}$/.test(code);
 const unique=values=>[...new Set(values.filter(Boolean))];
 const button=(text,klass)=>{
   const el=document.createElement('button');
   el.type='button';el.className=klass||'';el.textContent=text;
   return el;
 };
 function countryImage(code){
   const image=document.createElement('img');
   image.alt=code;
   image.loading='lazy';
   image.src='https://flagcdn.com/w40/'+code.toLowerCase()+'.png';
   image.addEventListener('error',()=>{image.replaceWith(document.createTextNode(code))},{once:true});
   return image;
 }
 function resolvePanel(panel){
   if(panel.dataset.v54V2ray==='1')return true;
   const choice=[...document.querySelectorAll('.protocol-choice[data-protocol]')]
     .find(x=>x.dataset.protocol===panel.id);
   return String(choice?.dataset.protocolKey||'').trim().toLowerCase()==='v2ray';
 }
 function mount(panel){
   panel.classList.add('tp105-v2ray');
   let current=states.get(panel);
   if(current)return current;
   const shell=document.createElement('section');
   shell.className='tp105-v2ray-shell';
   shell.setAttribute('aria-label','سرورهای V2Ray / Xray');
   const filter=document.createElement('nav');
   filter.className='tp105-v2ray-filter';
   filter.setAttribute('aria-label','فیلتر کشور سرورها');
   const list=document.createElement('div');
   list.className='tp105-v2ray-list';
   const pending=document.createElement('div');
   pending.className='tp105-v2ray-empty';
   pending.textContent='در حال دریافت سرورهای V2Ray…';
   list.append(pending);
   shell.append(filter,list);
   panel.append(shell);
   current={shell,filter,list,selection:'ALL',signature:'',firstSeen:Date.now()};
   states.set(panel,current);
   return current;
 }
 function fromV54(panel){
   const cards=[...panel.querySelectorAll(':scope > .v54-v2ray-groups > .v54-v2ray-server')];
   const output=[];
   for(const card of cards){
     const uris=unique([...card.querySelectorAll('.v54-v2ray-profile[data-tp78-uri]')]
       .map(p=>String(p.dataset.tp78Uri||'').trim()));
     if(!uris.length)continue;
     const country=String(card.dataset.countryCode||'').trim().toUpperCase();
     const code=validCode(country)?country:'';
     const id=String(card.dataset.nodeId||card.dataset.serverIndex||'').trim();
     // Preserve the original server name from /sub/meta, not the older
     // V76 rewrite that turned every name into "TR 6" on some refreshes.
     const name=String(card.dataset.nodeName||'').trim()
       ||String(card.querySelector('.v54-v2ray-server-head > span:first-child')?.textContent||'').trim()
       ||id;
     output.push({key:'v54:'+id+':'+output.length,code,id,name,uris});
   }
   return output;
 }
 function fromReference(panel){
   // The /sub/meta request may be pending or unavailable. The V67 nodes
   // retain real copy handlers; keep the same canonical presentation.
   const original=[...panel.querySelectorAll(':scope > .ref67-list > .ref67-row')];
   const tabs=[...panel.querySelectorAll('.server-tab[data-server]')];
   const output=[];
   original.forEach((row,index)=>{
     const name=String(row.querySelector('.ref67-row-name')?.textContent||'').trim();
     const tab=tabs[index];
     const raw=String(tab?.dataset.countryCode||'').trim().toUpperCase();
     const code=validCode(raw)?raw:((name.match(/\b(TR|DE|US|GB|FI|NL|FR)\b/i)||[])[1]||'').toUpperCase();
     const id=String(tab?.dataset.nodeId||'').trim()||(name.match(/\d+\s*$/)||[])[0]||String(index+1);
     const actualCopy=row.querySelector('.ref67-row-actions button');
     if(!actualCopy) return;
     output.push({
       key:'legacy:'+id+':'+index,code:validCode(code)?code:'',id,
       name:id,uris:[],originalCopy:actualCopy,
     });
   });
   return output;
 }
 function toast(message){
   const el=document.getElementById('toast');
   if(!el)return;
   el.textContent=message;
   el.classList.add('show');
   window.setTimeout(()=>el.classList.remove('show'),1600);
 }
 async function copyLines(uris){
   const value=unique(uris).join('\n');
   if(!value)return false;
   try{
     if(navigator.clipboard&&window.isSecureContext){
       await navigator.clipboard.writeText(value);return true;
     }
   }catch(_error){}
   const area=document.createElement('textarea');
   area.value=value;area.style.position='fixed';area.style.left='-9999px';
   area.setAttribute('readonly','');document.body.append(area);
   area.select();
   let ok=false;try{ok=document.execCommand('copy')}catch(_error){}
   area.remove();return ok;
 }
 function render(panel,rows,mode){
   const view=mount(panel);
   // Never put customer URIs into HTML, dataset attributes or the URL.
   // This signature remains closure-local and only prevents redundant paint.
   const signature=mode+'|'+rows.map(r=>
     [r.key,r.code,r.name,r.uris.join('\n')].join(':')).join('|');
   if(signature===view.signature)return;
   view.signature=signature;
   const counts=new Map();
   rows.forEach(r=>{if(r.code)counts.set(r.code,(counts.get(r.code)||0)+1)});
   if(view.selection!=='ALL'&&!counts.has(view.selection))view.selection='ALL';
   const filter=document.createDocumentFragment();
   const all=button('همه',view.selection==='ALL'?'active':'');
   all.dataset.country='ALL';filter.append(all);
   counts.forEach((count,code)=>{
     const btn=button('',view.selection===code?'active':'');
     btn.dataset.country=code;
     btn.append(countryImage(code),document.createTextNode(
       ' '+code+(count>1?' ('+count+')':''),
     ));
     filter.append(btn);
   });
   const list=document.createDocumentFragment();
   rows.forEach(r=>{
     const row=document.createElement('div');
     row.className='tp105-v2ray-row';
     row.dataset.country=r.code;
     row.dataset.nodeId=r.id;
     row.hidden=view.selection!=='ALL'&&r.code!==view.selection;
     const copy=button('کپی کانفیگ‌ها','tp105-v2ray-copy');
     copy.setAttribute('aria-label','کپی کانفیگ‌های '+(r.name||r.id));
     copy.disabled=!r.uris.length&&!r.originalCopy;
     copy.addEventListener('click',async event=>{
       event.preventDefault();event.stopPropagation();
       if(r.uris.length){
         toast(await copyLines(r.uris)?'کانفیگ‌ها کپی شدند':'کپی انجام نشد');
       }else if(r.originalCopy){
         // Invoke the real legacy node-local copy action, never a fake URL.
         r.originalCopy.click();
       }
     });
     const title=document.createElement('span');
     title.className='tp105-v2ray-name';
     const name=document.createElement('b');
     name.textContent=(r.code||'—')+' • '+r.name;
     title.append(name);
     if(r.code)title.append(countryImage(r.code));
     row.append(copy,title);
     list.append(row);
   });
   view.filter.replaceChildren(filter);
   if(rows.length)view.list.replaceChildren(list);
   else {
     const note=document.createElement('div');
     note.className='tp105-v2ray-empty';
     note.textContent='هنوز کانفیگ V2Ray قابل دریافت نیست';
     view.list.replaceChildren(note);
   }
   view.filter.querySelectorAll('button[data-country]').forEach(btn=>{
     btn.addEventListener('click',()=>{
       view.selection=btn.dataset.country||'ALL';
       view.filter.querySelectorAll('button').forEach(other=>
         other.classList.toggle('active',other===btn));
       view.list.querySelectorAll('.tp105-v2ray-row').forEach(row=>{
         row.hidden=view.selection!=='ALL'&&row.dataset.country!==view.selection;
       });
     });
   });
 }
 function sync(){
   for(const panel of document.querySelectorAll('.protocol-panel')){
     if(!resolvePanel(panel))continue;
     const view=mount(panel);
     const real=fromV54(panel);
     if(real.length){render(panel,real,'meta');continue}
     const holder=panel.querySelector(':scope > .v54-v2ray-groups');
     const failed=!!holder?.querySelector('.v54-v2ray-empty');
     if(failed||Date.now()-view.firstSeen>2500){
       const legacy=fromReference(panel);
       if(legacy.length)render(panel,legacy,'fallback');
       else if(failed)render(panel,[],'unavailable');
     }
   }
 }
 sync();
 // V54 fetch is asynchronous and legacy overlays can rewrite tabs/heads after
 // the first paint. Watch only server-card mutations; never observe our own rows.
 const attached=new WeakSet();
 const attach=()=>{
   for(const panel of document.querySelectorAll('.protocol-panel')){
     if(!resolvePanel(panel))continue;
     const holder=panel.querySelector(':scope > .v54-v2ray-groups');
     if(!holder||attached.has(holder))continue;
     attached.add(holder);
     const watcher=new MutationObserver(records=>{
       if(records.some(rec=>[...rec.addedNodes].some(n=>
         n.nodeType===1&&(n.matches?.('.v54-v2ray-server,.v54-v2ray-empty')
           ||n.querySelector?.('.v54-v2ray-server,.v54-v2ray-empty'))
       )))sync();
     });
     watcher.observe(holder,{childList:true,subtree:true});
   }
 };
 attach();
 let ticks=0;
 const poll=window.setInterval(()=>{
   attach();sync();
   if(++ticks>=120)window.clearInterval(poll);
 },350);
})();
</script>
"""

def refine_public_connection_v2ray_single_surface_v105(source: str) -> str:
    """Apply after V80, so the third reference has sole display authority."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace(
        "</body>",
        _SCRIPT + "\n<!-- " + _MARKER + " -->\n</body>",
        1,
    )
