from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_V2RAY_COUNTRY_CLICK_OPEN_V59"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_V2RAY_COUNTRY_CLICK_OPEN_V59 */
body.v54-v2ray-restore .protocol-panel[data-v54-v2ray="1"] > .server-views,
body.v54-v2ray-restore .protocol-panel[data-v54-v2ray="1"] > .v51-single-title,
body.v54-v2ray-restore .protocol-panel[data-v54-v2ray="1"] > .v57-v2ray-server-tabs{
  display:none!important;
}
body.v54-v2ray-restore .protocol-panel[data-v54-v2ray="1"] .protocol-panel-head .server-tabs{
  display:flex!important;
}
body.v54-v2ray-restore .protocol-panel[data-v54-v2ray="1"] .v54-v2ray-groups{
  display:block!important;margin:0 12px 14px;
}
body.v54-v2ray-restore .v54-v2ray-server{
  border:1px solid var(--line);border-radius:14px;background:var(--surface2);overflow:hidden;
}
body.v54-v2ray-restore .v54-v2ray-server-head{
  width:100%;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:11px 12px;
  border:0;background:transparent;font-size:12px;font-weight:900;color:var(--text);text-align:right;cursor:pointer;
}
body.v54-v2ray-restore .v54-v2ray-server-head span:last-child{
  color:var(--muted);font-size:10px;border:1px solid var(--line);border-radius:999px;padding:3px 8px;
}
body.v54-v2ray-restore .v54-v2ray-profiles{display:none!important;border-top:1px solid var(--line)}
body.v54-v2ray-restore .v54-v2ray-server.open > .v54-v2ray-profiles{display:grid!important}
body.v54-v2ray-restore .v54-v2ray-profile{
  display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:10px;padding:10px 12px;
  border-bottom:1px solid var(--line);background:var(--surface);
}
body.v54-v2ray-restore .v54-v2ray-profile:last-child{border-bottom:0}
body.v54-v2ray-restore .v54-v2ray-profile-info{min-width:0}
body.v54-v2ray-restore .v54-v2ray-profile-title{
  display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;font-weight:850;color:var(--text);
}
body.v54-v2ray-restore .v54-v2ray-profile-meta{display:block;margin-top:2px;font-size:10px;color:var(--muted)}
body.v54-v2ray-restore .v54-v2ray-profile-actions{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px}
body.v54-v2ray-restore .v54-v2ray-profile-actions button,
body.v54-v2ray-restore .v54-v2ray-profile-actions a{
  min-height:34px;display:inline-flex;align-items:center;justify-content:center;padding:0 9px;border:1px solid var(--line);
  border-radius:10px;background:var(--surface2);color:var(--text);font:inherit;font-size:10px;font-weight:800;text-decoration:none;cursor:pointer;
}
body.v54-v2ray-restore .v54-v2ray-empty{padding:12px;color:var(--muted);font-size:11px;text-align:center}
@media(max-width:720px){
  body.v54-v2ray-restore .protocol-choice[data-v54-v2ray-choice="1"]{display:grid!important;visibility:visible!important;opacity:1!important}
  body.v54-v2ray-restore .v54-v2ray-profile{grid-template-columns:1fr}
  body.v54-v2ray-restore .v54-v2ray-profile-actions{justify-content:stretch}
  body.v54-v2ray-restore .v54-v2ray-profile-actions button,
  body.v54-v2ray-restore .v54-v2ray-profile-actions a{flex:1 1 auto}
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectV2rayCountryClickOpenV59">
(function(){
  let timer=null;

  function normalize(value){
    const key=String(value||'').trim().toLowerCase();
    return key==='xray'?'v2ray':key;
  }

  function choiceFor(panel){
    if(!panel?.id)return null;
    return [...document.querySelectorAll('.protocol-choice')]
      .find(choice=>String(choice.dataset.protocol||'')===String(panel.id))||null;
  }

  function panelKey(panel){
    const direct=normalize(panel?.dataset?.v34Protocol||panel?.dataset?.modernProtocol||'');
    if(direct)return direct;
    const choice=choiceFor(panel);
    return normalize(choice?.dataset?.protocolKey||choice?.dataset?.protocol||'');
  }

  function token(){
    const match=String(window.location.pathname||'').match(/^\/v1\/connect\/([^/]+)/);
    if(!match)return'';
    try{return decodeURIComponent(match[1])}catch(_error){return match[1]}
  }

  function metaUrl(){
    const value=token();
    return value?window.location.origin+'/v1/connect/'+encodeURIComponent(value)+'/sub/meta':'';
  }

  function platform(){
    const explicit=String(document.body?.dataset?.tpPlatform||'').trim().toLowerCase();
    if(explicit)return explicit;
    const ua=String(navigator.userAgent||'');
    if(/android/i.test(ua))return'android';
    if(/iphone|ipad|ipod/i.test(ua))return'ios';
    return'windows';
  }

  function copy(value){
    const raw=String(value||'');
    if(!raw)return Promise.resolve(false);
    if(navigator.clipboard&&window.isSecureContext){
      return navigator.clipboard.writeText(raw).then(()=>true).catch(()=>fallbackCopy(raw));
    }
    return Promise.resolve(fallbackCopy(raw));
  }

  function fallbackCopy(value){
    const area=document.createElement('textarea');
    area.value=String(value||'');area.readOnly=true;area.style.position='fixed';area.style.left='-9999px';
    document.body.appendChild(area);area.select();let ok=false;
    try{ok=document.execCommand('copy')}catch(_error){}
    area.remove();return ok;
  }

  function notify(message){
    const toast=document.getElementById('toast');
    if(!toast)return;
    toast.textContent=message;toast.classList.add('show');
    clearTimeout(window.__tpV54Toast);window.__tpV54Toast=setTimeout(()=>toast.classList.remove('show'),1500);
  }

  function el(tag,className,text){
    const node=document.createElement(tag);
    if(className)node.className=className;
    if(text!==undefined)node.textContent=String(text);
    return node;
  }

  function serverLabel(server,index){
    const exact=String(server?.server||'').trim();
    return exact||('سرور '+(index+1));
  }

  function addProfileAction(actions,uri){
    const p=platform();
    if(p==='android'){
      const send=el('a','', 'ارسال به v2rayNG');
      send.href='v2rayng://install-config?url='+encodeURIComponent(uri);
      send.rel='noopener noreferrer';actions.appendChild(send);
    }else if(p==='ios'){
      const send=el('a','', 'ارسال به V2Box');
      send.href=uri;send.rel='noopener noreferrer';actions.appendChild(send);
    }
    const button=el('button','', 'کپی کانفیگ');
    button.type='button';
    button.addEventListener('click',async()=>notify(await copy(uri)?'کانفیگ کپی شد ✓':'کپی انجام نشد'));
    actions.appendChild(button);
  }

  function profileRow(profile,index){
    const row=el('div','v54-v2ray-profile');
    const info=el('div','v54-v2ray-profile-info');
    info.appendChild(el('b','v54-v2ray-profile-title','اتصال '+(index+1)));
    const details=[profile?.title,profile?.transport,profile?.security]
      .map(v=>String(v||'').trim()).filter(Boolean).join(' · ');
    info.appendChild(el('small','v54-v2ray-profile-meta',details||'V2Ray / Xray'));
    const actions=el('div','v54-v2ray-profile-actions');
    const uri=String(profile?.uri||'').trim();
    if(uri)addProfileAction(actions,uri);
    row.append(info,actions);return row;
  }

  function serverCard(server,index,openInitially){
    const profiles=Array.isArray(server?.profiles)?server.profiles:[];
    if(profiles.length!==3)return null;
    const card=el('section','v54-v2ray-server');
    const head=el('div','v54-v2ray-server-head');
    head.setAttribute('role','button');head.setAttribute('tabindex','0');head.setAttribute('aria-expanded',openInitially?'true':'false');
    head.append(el('span','',serverLabel(server,index)),el('span','', '۳ اتصال'));
    if(openInitially)card.classList.add('open');
    const toggle=()=>{
      const open=card.classList.toggle('open');
      head.setAttribute('aria-expanded',open?'true':'false');
    };
    head.addEventListener('click',toggle);
    head.addEventListener('keydown',event=>{
      if(event.key==='Enter'||event.key===' '){event.preventDefault();toggle()}
    });
    const body=el('div','v54-v2ray-profiles');
    profiles.forEach((profile,profileIndex)=>body.appendChild(profileRow(profile,profileIndex)));
    card.append(head,body);return card;
  }

  function renderSelected(tabs,holder,servers,selectedIndex,openProfiles){
    const index=Math.max(0,Math.min(selectedIndex,servers.length-1));
    [...tabs.querySelectorAll('.server-tab')].forEach((tab,tabIndex)=>{
      tab.classList.toggle('active',tabIndex===index);
      tab.setAttribute('aria-selected',tabIndex===index?'true':'false');
    });
    holder.replaceChildren();
    const card=serverCard(servers[index],index,Boolean(openProfiles));
    if(card)holder.appendChild(card);
  }

  function buildTabs(tabs,holder,servers){
    tabs.replaceChildren();
    servers.forEach((server,index)=>{
      const button=el('button','server-tab');
      button.type='button';button.setAttribute('role','tab');button.setAttribute('aria-selected','false');
      button.append(el('span','',serverLabel(server,index)),el('i',''));
      button.addEventListener('click',()=>renderSelected(tabs,holder,servers,index,true));
      tabs.appendChild(button);
    });
    renderSelected(tabs,holder,servers,0,false);
  }

  async function ensureGroups(panel){
    if(panel.dataset.v54GroupsLoaded==='1'||panel.dataset.v54GroupsLoading==='1')return;
    const anchor=panel.querySelector(':scope > .v52-multi-card,:scope > .v51-multi-card');
    const tabs=panel.querySelector(':scope > .protocol-panel-head .server-tabs');
    if(!anchor||!tabs)return;
    panel.querySelectorAll(':scope > .v57-v2ray-server-tabs').forEach(node=>node.remove());
    let holder=panel.querySelector(':scope > .v54-v2ray-groups');
    if(!holder){holder=el('div','v54-v2ray-groups');anchor.insertAdjacentElement('afterend',holder)}
    panel.dataset.v54GroupsLoading='1';
    try{
      const url=metaUrl();if(!url)throw new Error('no meta url');
      const response=await fetch(url,{cache:'no-store',headers:{Accept:'application/json'}});
      if(!response.ok)throw new Error('meta '+response.status);
      const payload=await response.json();
      const servers=(Array.isArray(payload?.servers)?payload.servers:[])
        .filter(server=>Array.isArray(server?.profiles)&&server.profiles.length===3);
      tabs.replaceChildren();holder.replaceChildren();
      if(!servers.length){holder.appendChild(el('div','v54-v2ray-empty','اتصال‌های V2Ray این سرورها هنوز آماده نشده‌اند'))}
      else buildTabs(tabs,holder,servers);
      panel.dataset.v54GroupsLoaded='1';
    }catch(_error){
      tabs.replaceChildren();
      holder.replaceChildren(el('div','v54-v2ray-empty','نمایش سرورها و اتصال‌های V2Ray در دسترس نیست'));
    }finally{delete panel.dataset.v54GroupsLoading}
  }

  function retireLegacyStandalone(){
    document.querySelectorAll('.multi-link-card').forEach(card=>{
      const text=String(card.textContent||'').toLowerCase();
      if(text.includes('v2ray')||text.includes('xray'))card.remove();
    });
  }

  function apply(){
    document.body.classList.add('v54-v2ray-restore');
    retireLegacyStandalone();
    document.querySelectorAll('.protocol-panel').forEach(panel=>{
      if(panelKey(panel)!=='v2ray')return;
      panel.dataset.v54V2ray='1';
      const choice=choiceFor(panel);
      if(choice){
        choice.dataset.v54V2rayChoice='1';choice.hidden=false;choice.removeAttribute('aria-hidden');
        choice.classList.add('v40-real-protocol');choice.dataset.v51Filtered='0';
      }
      if(panel.querySelector('.server-view')){
        panel.classList.add('v24-canonical-panel');panel.classList.remove('v24-empty');
      }
      panel.querySelectorAll(':scope > .v54-v2ray-config-toggle,:scope > .v57-v2ray-server-tabs').forEach(node=>node.remove());
      ensureGroups(panel);
    });
  }

  apply();window.setTimeout(apply,0);window.setTimeout(apply,180);window.setTimeout(apply,650);window.setTimeout(apply,1500);
  window.addEventListener('resize',()=>{clearTimeout(timer);timer=window.setTimeout(apply,180)},{passive:true});
})();
</script>
"""


_V41_REMOVE_OLD = "panel.querySelectorAll('.v38-server-list-title,.tp-v41-profile-toggle,.server-views').forEach(node=>node.remove());"
_V41_REMOVE_NEW = "panel.querySelectorAll('.v38-server-list-title,.tp-v41-profile-toggle').forEach(node=>node.remove());"
_V51_MULTI_OLD = "return window.location.origin+'/v1/connect/'+encodeURIComponent(value)+'/multi/'+encodeURIComponent(protocol);"
_V51_MULTI_NEW = "return window.location.origin+'/v1/connect/'+encodeURIComponent(value)+(protocol==='v2ray'?'/sub':'/multi/'+encodeURIComponent(protocol));"


def refine_public_connection_v2ray_mobile_restore_v54(source: str) -> str:
    """Keep V2Ray profiles collapsed initially, then open the selected country's three profiles on tab click."""
    source = str(source or "")
    source = source.replace(_V41_REMOVE_OLD, _V41_REMOVE_NEW)
    source = source.replace(_V51_MULTI_OLD, _V51_MULTI_NEW)
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + "\n</body>", 1)
