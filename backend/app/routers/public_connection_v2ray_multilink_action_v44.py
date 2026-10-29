from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_V2RAY_MULTILINK_ACTION_V44"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_V2RAY_MULTILINK_GROUPS_V49 */
.v49-v2ray-summary{margin-top:10px;display:flex;align-items:center;justify-content:space-between;gap:10px}
.v49-v2ray-count{font-size:12px;font-weight:800;color:var(--muted)}
.v49-v2ray-toggle{min-height:38px;padding:0 12px;border:1px solid var(--line);border-radius:12px;background:var(--surface2);color:var(--text);font:inherit;font-size:12px;font-weight:800;cursor:pointer}
.v49-v2ray-groups{display:none;margin-top:10px;gap:9px}
.v49-v2ray-groups.open{display:grid}
.v49-v2ray-server{border:1px solid var(--line);border-radius:15px;background:var(--surface2);overflow:hidden}
.v49-v2ray-server-head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 12px;font-size:12px;font-weight:900;color:var(--text)}
.v49-v2ray-server-count{flex:0 0 auto;padding:3px 8px;border:1px solid var(--line);border-radius:999px;color:var(--muted);font-size:10px}
.v49-v2ray-profiles{display:grid;gap:1px;background:var(--line)}
.v49-v2ray-profile{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:10px;padding:10px 12px;background:var(--surface)}
.v49-v2ray-profile-copy{min-width:0}
.v49-v2ray-profile-title{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;font-weight:850;color:var(--text)}
.v49-v2ray-profile-meta{display:block;margin-top:2px;font-size:10px;color:var(--muted)}
.v49-v2ray-profile-actions{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px}
.v49-v2ray-profile-actions button,.v49-v2ray-profile-actions a{min-height:34px;display:inline-flex;align-items:center;justify-content:center;padding:0 9px;border:1px solid var(--line);border-radius:10px;background:var(--surface2);color:var(--text);font:inherit;font-size:10px;font-weight:800;text-decoration:none;cursor:pointer}
.v49-v2ray-empty{padding:10px 12px;border:1px dashed var(--line);border-radius:12px;color:var(--muted);font-size:11px;text-align:center}
@media(max-width:720px){
  .v49-v2ray-summary{align-items:stretch;flex-direction:column}
  .v49-v2ray-toggle{width:100%}
  .v49-v2ray-profile{grid-template-columns:1fr}
  .v49-v2ray-profile-actions{justify-content:stretch}
  .v49-v2ray-profile-actions button,.v49-v2ray-profile-actions a{flex:1 1 auto}
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectV2rayMultilinkActionV44">
(function(){
  function token(){
    const match=String(window.location.pathname||'').match(/^\/v1\/connect\/([^/]+)/);
    if(!match)return'';
    try{return decodeURIComponent(match[1])}catch(_error){return match[1]}
  }

  function multiUrl(){
    const value=token();
    if(!value)return'';
    return window.location.origin+'/v1/connect/'+encodeURIComponent(value)+'/sub';
  }

  function metaUrl(){
    const value=token();
    if(!value)return'';
    return window.location.origin+'/v1/connect/'+encodeURIComponent(value)+'/sub/meta';
  }

  function hiddifyUrl(url){
    return 'hiddify://import/'+encodeURI(url)+'#TwinPanel-v2ray';
  }

  function directHiddifyUrl(uri,title){
    return 'hiddify://import/'+encodeURIComponent(String(uri||''))+'#'+encodeURIComponent(String(title||'TwinPanel-V2Ray'));
  }

  function fallbackCopy(value){
    const area=document.createElement('textarea');
    area.value=String(value||'');
    area.readOnly=true;
    area.style.position='fixed';
    area.style.left='-9999px';
    document.body.appendChild(area);
    area.focus();
    area.select();
    area.setSelectionRange(0,area.value.length);
    let ok=false;
    try{ok=document.execCommand('copy')}catch(_error){}
    area.remove();
    return ok;
  }

  async function copy(value){
    const raw=String(value||'').trim();
    if(!raw)return false;
    if(navigator.clipboard&&window.isSecureContext){
      try{await navigator.clipboard.writeText(raw);return true}catch(_error){}
    }
    return fallbackCopy(raw);
  }

  function notify(message){
    const toast=document.getElementById('toast');
    if(!toast)return;
    toast.textContent=message;
    toast.classList.add('show');
    clearTimeout(window.__tpV44Toast);
    window.__tpV44Toast=setTimeout(()=>toast.classList.remove('show'),1500);
  }

  function el(tag,className,text){
    const node=document.createElement(tag);
    if(className)node.className=className;
    if(text!==undefined)node.textContent=String(text);
    return node;
  }

  function profileRow(profile,index){
    const row=el('div','v49-v2ray-profile');
    const info=el('div','v49-v2ray-profile-copy');
    const title=String(profile?.title||profile?.id||('Config '+(index+1))).trim();
    info.appendChild(el('b','v49-v2ray-profile-title',title));
    const metadata=[profile?.transport,profile?.security].map(v=>String(v||'').trim()).filter(Boolean).join(' · ');
    info.appendChild(el('small','v49-v2ray-profile-meta',metadata||'V2Ray / Xray'));

    const actions=el('div','v49-v2ray-profile-actions');
    const copyButton=el('button','', 'کپی');
    copyButton.type='button';
    copyButton.addEventListener('click',async()=>notify(await copy(profile?.uri)?'کانفیگ کپی شد ✓':'کپی انجام نشد'));
    actions.appendChild(copyButton);

    if(String(profile?.uri||'').trim()){
      const send=el('a','', 'Hiddify');
      send.href=directHiddifyUrl(profile.uri,title);
      send.rel='noopener noreferrer';
      actions.appendChild(send);
    }
    row.append(info,actions);
    return row;
  }

  function serverCard(server,index){
    const card=el('section','v49-v2ray-server');
    const head=el('div','v49-v2ray-server-head');
    head.append(
      el('span','',String(server?.server||('Server '+(index+1)))),
      el('span','v49-v2ray-server-count',String(server?.profile_count||0)+' کانفیگ')
    );
    const profiles=el('div','v49-v2ray-profiles');
    const rows=Array.isArray(server?.profiles)?server.profiles:[];
    rows.forEach((profile,profileIndex)=>profiles.appendChild(profileRow(profile,profileIndex)));
    card.append(head,profiles);
    return card;
  }

  async function loadGroups(card){
    if(card.dataset.v49Loaded==='1'||card.dataset.v49Loading==='1')return;
    const url=metaUrl();
    if(!url)return;
    card.dataset.v49Loading='1';
    const count=card.querySelector('.v49-v2ray-count');
    const groups=card.querySelector('.v49-v2ray-groups');
    try{
      const response=await fetch(url,{cache:'no-store',headers:{Accept:'application/json'}});
      if(!response.ok)throw new Error('meta '+response.status);
      const payload=await response.json();
      const servers=Array.isArray(payload?.servers)?payload.servers:[];
      const serverCount=Number(payload?.server_count||servers.length||0);
      const profileCount=Number(payload?.profile_count||0);
      if(count)count.textContent=serverCount+' سرور · '+profileCount+' کانفیگ';
      if(groups){
        groups.replaceChildren();
        servers.forEach((server,index)=>groups.appendChild(serverCard(server,index)));
        if(!servers.length)groups.appendChild(el('div','v49-v2ray-empty','کانفیگ V2Ray آماده‌ای پیدا نشد'));
      }
      card.dataset.v49Loaded='1';
    }catch(_error){
      if(count)count.textContent='نمایش جزئیات در دسترس نیست';
    }finally{
      delete card.dataset.v49Loading;
    }
  }

  function ensureDetails(card){
    if(card.querySelector('.v49-v2ray-summary'))return;
    const summary=el('div','v49-v2ray-summary');
    const count=el('div','v49-v2ray-count','در حال دریافت کانفیگ‌ها…');
    const toggle=el('button','v49-v2ray-toggle','مشاهده کانفیگ‌ها');
    toggle.type='button';
    const groups=el('div','v49-v2ray-groups');
    toggle.addEventListener('click',async()=>{
      await loadGroups(card);
      const open=groups.classList.toggle('open');
      toggle.textContent=open?'بستن کانفیگ‌ها':'مشاهده کانفیگ‌ها';
      toggle.setAttribute('aria-expanded',open?'true':'false');
    });
    toggle.setAttribute('aria-expanded','false');
    summary.append(count,toggle);
    card.append(summary,groups);
    loadGroups(card);
  }

  function rewrite(){
    const url=multiUrl();
    if(!url)return;

    document.querySelectorAll('.v38-all-card[data-v38-protocol="v2ray"]').forEach(card=>{
      const actions=card.querySelector('.v38-all-actions');
      if(!actions)return;

      const send=document.createElement('a');
      send.className='v38-primary v44-v2ray-multi-hiddify';
      send.textContent='ارسال همه به Hiddify';
      send.href=hiddifyUrl(url);
      send.setAttribute('aria-label','ارسال همه کانفیگ‌های V2Ray به Hiddify');

      const copyButton=document.createElement('button');
      copyButton.type='button';
      copyButton.className='v38-copy v44-v2ray-multi-copy';
      copyButton.textContent='کپی لینک';
      copyButton.setAttribute('aria-label','کپی لینک مولتی V2Ray');
      copyButton.addEventListener('click',async()=>{
        notify(await copy(url)?'لینک مولتی V2Ray کپی شد ✓':'کپی انجام نشد');
      });

      actions.replaceChildren(send,copyButton);
      card.dataset.v44V2rayMulti='1';
      card.dataset.v44Endpoint='/sub';
      ensureDetails(card);
    });
  }

  rewrite();
  window.setTimeout(rewrite,0);
  window.setTimeout(rewrite,300);
  window.setTimeout(rewrite,950);
})();
</script>
"""


def refine_public_connection_v2ray_multilink_action_v44(source: str) -> str:
    """Wire V2Ray Multi-Link to all profiles and render grouped profile details."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace(
        "</body>",
        _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>",
        1,
    )
