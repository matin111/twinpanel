from __future__ import annotations

# One presentation-only node identity for all public Connection protocol panels.
# Keep original nodes, config handlers, metadata and links untouched.
_MARKER = "TWINPANEL_PUBLIC_CONNECT_UNIFIED_NODE_IDENTITY_V76"

_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_UNIFIED_NODE_IDENTITY_V76 */
body.tp76-unified .tp76-label{display:inline-flex!important;align-items:center!important;gap:7px!important;direction:ltr!important;white-space:nowrap!important}
body.tp76-unified .tp76-flag{display:inline-flex!important;width:25px!important;height:19px!important;min-width:25px!important;flex:0 0 25px!important;overflow:hidden!important;border-radius:4px!important;vertical-align:middle!important;box-shadow:0 1px 5px #0007!important}
body.tp76-unified .tp76-flag svg,body.tp76-unified .tp76-flag img{display:block!important;width:100%!important;height:100%!important;object-fit:cover!important}
body.tp76-unified .tp76-node-text{font:850 11px system-ui,Arial,sans-serif!important;color:inherit!important;direction:ltr!important;white-space:nowrap!important}
body.tp76-unified .server-tab .tp76-label,
body.tp76-unified .ref67-chip .tp76-label,
body.tp76-unified .tp74-country-chip .tp76-label{gap:6px!important}
body.tp76-unified .ref67-row-name .tp76-label{font-size:13px!important}
body.tp76-unified .v54-v2ray-server-head .tp76-label{font-size:13px!important}
@media(max-width:720px){
 body.tp76-unified .tp76-flag{width:23px!important;height:17px!important;min-width:23px!important;flex-basis:23px!important}
 body.tp76-unified .tp76-node-text{font-size:10px!important}
}
"""

_SCRIPT = r"""
<script id="twinpanelPublicConnectUnifiedNodeIdentityV76">
(function(){
 'use strict';
 if(!/^\/v1\/connect\/[^/]+\/?$/.test(location.pathname))return;
 document.body.classList.add('tp76-unified');
 const ns='http://www.w3.org/2000/svg';
 const valid=code=>/^[A-Z]{2}$/.test(code);
 function codeFrom(text){
   const raw=String(text||'');
   const flagged=Array.from(raw.match(/[\u{1F1E6}-\u{1F1FF}]{2}/u)?.[0]||'');
   if(flagged.length===2)return flagged.map(c=>String.fromCharCode(c.codePointAt(0)-127397)).join('');
   const coded=raw.match(/(?:^|[^A-Za-z])([A-Z]{2})(?=\s|[-·•:]|\d|$)/);
   return coded?.[1]||'';
 }
 function identity(raw,codeHint,idHint){
   const rawText=String(raw||'').trim();
   const code=String(codeHint||'').toUpperCase()||codeFrom(rawText);
   const explicit=String(idHint??'').trim();
   // Accept a node number only when clearly present; never assign array index as node identity.
   const number=explicit||rawText.match(/(?:^|[-·•\s])(?:#)?(\d{1,9})\s*$/)?.[1]||'';
   if(!valid(code)||!number)return null;
   return {code,id:number};
 }
 function flagSvg(code){
   if(code==='DE')return '<path fill="#111" d="M0 0h32v8H0z"/><path fill="#dd172c" d="M0 8h32v8H0z"/><path fill="#ffce00" d="M0 16h32v8H0z"/>';
   if(code==='TR')return '<path fill="#e30a17" d="M0 0h32v24H0z"/><circle cx="13" cy="12" r="7" fill="#fff"/><circle cx="15" cy="12" r="5.5" fill="#e30a17"/><path fill="#fff" d="m20 7 1.1 3.4h3.6l-2.9 2.1 1.1 3.3-2.9-2.1-2.9 2.1 1.1-3.3-2.9-2.1h3.6z"/>';
   if(code==='US'){
     let value='<path fill="#fff" d="M0 0h32v24H0z"/>';
     for(let i=0;i<7;i++)value+='<rect fill="#b22234" x="0" y="'+(i*48/13)+'" width="32" height="'+(24/13)+'"/>';
     value+='<rect fill="#3c3b6e" width="13" height="13"/>';
     return value;
   }
   if(code==='FR')return '<path fill="#0055a4" d="M0 0h10.67v24H0z"/><path fill="#fff" d="M10.67 0h10.67v24H10.67z"/><path fill="#ef4135" d="M21.34 0H32v24H21.34z"/>';
   if(code==='NL')return '<path fill="#ae1c28" d="M0 0h32v8H0z"/><path fill="#fff" d="M0 8h32v8H0z"/><path fill="#21468b" d="M0 16h32v8H0z"/>';
   return '';
 }
 function makeLabel(node){
   const label=document.createElement('span');label.className='tp76-label';
   label.setAttribute('dir','ltr');
   const flag=document.createElement('span');flag.className='tp76-flag';
   flag.setAttribute('role','img');flag.setAttribute('aria-label',node.code+' flag');
   const drawing=flagSvg(node.code);
   if(drawing){const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 32 24');svg.innerHTML=drawing;flag.append(svg)}
   else{
     const img=document.createElement('img');img.alt=node.code;img.loading='lazy';
     img.src='https://flagcdn.com/w40/'+node.code.toLowerCase()+'.png';
     img.addEventListener('error',()=>{flag.textContent=node.code;img.remove()});
     flag.append(img);
   }
   const name=document.createElement('span');name.className='tp76-node-text';
   name.textContent=node.code+' '+node.id;
   label.append(flag,name);return label;
 }
 function show(container,node,keepOther){
   if(!container||!node)return;
   const signature=node.code+':'+node.id;
   if(container.dataset.tp76Identity===signature && container.querySelector(':scope > .tp76-label'))return;
   // Only replace the identity text, never the server row or existing buttons/listeners.
   if(keepOther){const old=container.querySelector('.tp76-label');if(old)old.remove();
     container.prepend(makeLabel(node));
   }else container.replaceChildren(makeLabel(node));
   container.dataset.tp76Identity=signature;
 }
 function applyPanel(panel){
   const tabs=[...panel.querySelectorAll('.server-tab[data-server]')];
   const nodes=tabs.map(tab=>{
     const span=tab.querySelector(':scope > span')||tab;
     const src=span.dataset.tp76Source||span.textContent||'';
     if(!span.dataset.tp76Source)span.dataset.tp76Source=src;
     const node=identity(src,tab.dataset.countryCode||'',tab.dataset.nodeId||'');
     if(node)show(span,node,false);
     return {tab,node};
   });
   // Original tab's data-server is the authoritative link to the correct config view.
   const entries=new Map(nodes.filter(x=>x.node).map(x=>[x.tab.dataset.server,x.node]));
   panel.querySelectorAll('.ref67-row').forEach((row,i)=>{
     const tab=nodes[i];
     const node=tab?.node;
     const target=row.querySelector('.ref67-row-name');
     if(!node||!target)return;
     const name=target.querySelector('b');
     if(name)show(name,node,false);
     const flag=target.querySelector('.ref67-flag');
     if(flag)flag.style.display='none';
   });
   const chips=[...panel.querySelectorAll('.ref67-tabs .ref67-chip')];
   chips.slice(1).forEach((chip,i)=>{if(nodes[i]?.node)show(chip,nodes[i].node,false)});
   // V54's V2Ray/ Xray lists are built from /sub/meta; preserve all 3 profiles per node.
   const cards=[...panel.querySelectorAll('.v54-v2ray-server')];
   cards.forEach(card=>{
     const head=card.querySelector('.v54-v2ray-server-head');
     const name=head?.querySelector('.tp74-node-name strong');
     const node=identity(name?.textContent||head?.textContent||'',
       card.dataset.countryCode,card.dataset.nodeId);
     if(!node||!head)return;
     const host=head.querySelector('.tp74-node-identity')||head;
     if(host===head)show(host,node,true);
     else {
       const oldFlag=host.querySelector('.tp74-flag');if(oldFlag)oldFlag.style.display='none';
       const title=host.querySelector('.tp74-node-name strong');
       if(title)show(title,node,false);
     }
   });
   const countryChips=[...panel.querySelectorAll('.tp74-country-chip[data-tp74-node]')];
   countryChips.forEach((chip,i)=>{
     const card=cards[i];if(!card)return;
     const node=identity(chip.textContent,card.dataset.countryCode,card.dataset.nodeId);
     if(node)show(chip,node,false);
   });
   // Native server-view remains linked to its tab via id; do not rewrite ids.
   entries.forEach((_node,serverId)=>{
     const view=[...panel.querySelectorAll('.server-view')].find(el=>el.id===serverId);
     if(view)view.dataset.tp76Mapped='1';
   });
 }
 function apply(){document.querySelectorAll('.protocol-panel').forEach(applyPanel)}
 apply();
 // Older scripts mount rows asynchronously. Reconcile without changing config or actions.
 let count=0;const timer=setInterval(()=>{apply();if(++count>=30)clearInterval(timer)},350);
})();
</script>
"""

def refine_public_connection_unified_node_identity_v76(source: str) -> str:
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + "\n<!-- " + _MARKER + " -->\n</body>", 1)
