from __future__ import annotations

from .public_connection_mobile_simplified_v39 import (
    refine_public_connection_mobile_simplified_v39,
)


_MARKER = "TWINPANEL_PUBLIC_CONNECT_REFERENCE_LAYOUT_V38"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_REFERENCE_LAYOUT_V38 */
body.v38-reference .v37-multi-card{display:none!important}
body.v38-reference .v38-all-card{
  margin:12px;
  border:1px solid color-mix(in srgb,var(--p) 30%,var(--line));
  border-radius:16px;
  overflow:hidden;
  background:var(--surface2);
}
body.v38-reference .v38-all-head{
  min-height:54px;
  padding:11px 14px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  border-bottom:1px solid var(--line);
}
body.v38-reference .v38-ha-title{
  display:flex;
  align-items:center;
  gap:9px;
  min-width:0;
  font-size:14px;
  font-weight:950;
}
body.v38-reference .v38-ha-shield{font-size:18px;line-height:1}
body.v38-reference .v38-ha-badge{
  padding:5px 10px;
  border:1px solid color-mix(in srgb,var(--p) 48%,var(--line));
  border-radius:999px;
  color:var(--p);
  font-size:11px;
  font-weight:900;
  white-space:nowrap;
}
body.v38-reference .v38-multi-row{
  margin:12px;
  min-height:54px;
  padding:8px 10px 8px 13px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  border:1px solid var(--line);
  border-radius:14px;
  background:var(--surface);
}
body.v38-reference .v38-multi-name{
  display:flex;
  align-items:center;
  gap:9px;
  min-width:0;
  font-weight:950;
}
body.v38-reference .v38-multi-name small{
  color:var(--muted);
  font-size:10px;
  font-weight:800;
  white-space:nowrap;
}
body.v38-reference .v38-all-actions{
  display:flex;
  align-items:center;
  gap:7px;
  flex:0 0 auto;
}
body.v38-reference .v38-all-actions>a,
body.v38-reference .v38-all-actions>button{
  min-height:38px;
  padding:8px 11px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  border:1px solid var(--line);
  border-radius:10px;
  background:var(--surface2);
  color:var(--text);
  font:inherit;
  font-size:11px;
  font-weight:900;
  line-height:1.4;
  text-align:center;
  text-decoration:none;
  cursor:pointer;
  white-space:nowrap;
}
body.v38-reference .v38-primary{
  border-color:var(--p)!important;
  background:var(--p)!important;
  color:#fff!important;
}
body.v38-reference .v38-copy{color:var(--p)!important}
body.v38-reference .v38-server-list-title{
  margin:13px 12px 6px;
  color:var(--muted);
  font-size:11px;
  font-weight:900;
}
body.v38-reference .v38-sr-only{
  position:absolute!important;
  width:1px!important;
  height:1px!important;
  padding:0!important;
  margin:-1px!important;
  overflow:hidden!important;
  clip:rect(0,0,0,0)!important;
  white-space:nowrap!important;
  border:0!important;
}

@media(max-width:720px){
  body.v38-reference.v36-mobile-compact .protocol-panel{display:none!important}
  body.v38-reference.v36-mobile-compact .protocol-panel.v36-open{display:block!important}
  body.v38-reference .v38-all-card{margin:10px}
  body.v38-reference .v38-all-head{min-height:50px;padding:9px 11px}
  body.v38-reference .v38-multi-row{margin:10px;min-height:50px;padding:7px 8px 7px 10px}
  body.v38-reference .v38-all-actions>a,
  body.v38-reference .v38-all-actions>button{min-height:36px;padding:7px 9px;font-size:10px}

  body.v38-reference.v36-mobile-compact .protocol-panel.v36-open .server-views{
    gap:7px!important;
    padding:8px 10px 12px!important;
  }
  body.v38-reference.v36-mobile-compact .protocol-panel.v36-open .server-view{
    padding:9px!important;
    border-radius:11px!important;
  }
  body.v38-reference.v36-mobile-compact .protocol-panel.v36-open .server-view:before{
    margin-bottom:6px!important;
  }
  body.v38-reference.v36-mobile-compact .protocol-panel.v36-open .v34-server-actions{
    grid-template-columns:repeat(2,minmax(0,1fr))!important;
    gap:6px!important;
    margin-top:6px!important;
  }
  body.v38-reference.v36-mobile-compact .protocol-panel.v36-open .v34-server-actions>a,
  body.v38-reference.v36-mobile-compact .protocol-panel.v36-open .v34-server-actions>button{
    min-height:38px!important;
    padding:7px 8px!important;
    font-size:10px!important;
  }
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectReferenceLayoutV38">
(function(){
  const SUBSCRIPTIONS=new Set(['v2ray','hysteria2','tuic','anytls']);
  const MULTI=new Set([
    'openvpn','wireguard','v2ray','hysteria2','tuic','anytls','naive',
    'shadowtls','snell','mieru','trusttunnel','amneziawg','sudoku'
  ]);
  const NATIVE_BUNDLES=new Set(['openvpn','wireguard','amneziawg']);
  const text=node=>String(node?.textContent||'').trim();

  function normalize(value){
    const key=String(value||'').trim().toLowerCase();
    if(key==='xray')return'v2ray';
    if(key==='naiveproxy')return'naive';
    if(key==='openconnect'||key==='ocserv'||key==='anyconnect')return'cisco';
    return key;
  }

  function panelKey(panel){
    const direct=normalize(panel?.dataset?.v34Protocol||panel?.dataset?.modernProtocol||'');
    if(direct)return direct;
    const choice=[...document.querySelectorAll('.protocol-choice')]
      .find(item=>String(item.dataset.protocol||'')===String(panel?.id||''));
    return normalize(choice?.dataset?.protocolKey||choice?.dataset?.protocol||'');
  }

  function protocolTitle(panel,key){
    const heading=text(panel.querySelector('.panel-head h2,.panel-head h3,.panel-head'));
    return heading||key;
  }

  function token(){
    const match=String(window.location.pathname||'').match(/^\/v1\/connect\/([^/]+)/);
    if(!match)return'';
    try{return decodeURIComponent(match[1])}catch(_error){return match[1]}
  }

  function subscriptionUrl(protocol){
    const value=token();
    if(!value||!SUBSCRIPTIONS.has(protocol))return'';
    return window.location.origin+'/v1/connect/'+encodeURIComponent(value)+'/sub/'+encodeURIComponent(protocol);
  }

  function multiUrl(protocol){
    const value=token();
    if(!value||!MULTI.has(protocol))return'';
    return window.location.origin+'/v1/connect/'+encodeURIComponent(value)+'/multi/'+encodeURIComponent(protocol);
  }

  function fallbackCopy(value){
    const area=document.createElement('textarea');
    area.value=String(value||'');area.readOnly=true;area.style.position='fixed';area.style.left='-9999px';
    document.body.appendChild(area);area.focus();area.select();area.setSelectionRange(0,area.value.length);
    let ok=false;try{ok=document.execCommand('copy')}catch(_error){}area.remove();return ok;
  }

  async function copy(value){
    const raw=String(value||'').trim();if(!raw)return false;
    if(navigator.clipboard&&window.isSecureContext){
      try{await navigator.clipboard.writeText(raw);return true}catch(_error){}
    }
    return fallbackCopy(raw);
  }

  function notify(message){
    const toast=document.getElementById('toast');if(!toast)return;
    toast.textContent=message;toast.classList.add('show');
    clearTimeout(window.__tpV38Toast);
    window.__tpV38Toast=setTimeout(()=>toast.classList.remove('show'),1500);
  }

  function link(label,href,primary,ariaLabel){
    const node=document.createElement('a');node.textContent=label;node.href=href;
    if(primary)node.classList.add('v38-primary');
    if(ariaLabel)node.setAttribute('aria-label',ariaLabel);
    if(/^https?:\/\//i.test(href)){node.target='_blank';node.rel='noopener noreferrer'}
    return node;
  }

  function button(label,handler,primary,copyClass,ariaLabel){
    const node=document.createElement('button');node.type='button';node.textContent=label;
    if(primary)node.classList.add('v38-primary');
    if(copyClass)node.classList.add('v38-copy');
    if(ariaLabel)node.setAttribute('aria-label',ariaLabel);
    node.addEventListener('click',handler);
    return node;
  }

  function clientName(panel){
    const label=text(panel.querySelector('.v34-client-card a'));
    return label.replace(/^دانلود\s+/,'').trim();
  }

  function importHref(protocol,client,url){
    const name=String(client||'').toLowerCase();
    if(name.includes('hiddify')){
      return 'hiddify://import/'+encodeURI(url)+'#TwinPanel-'+encodeURIComponent(protocol);
    }
    if(name.includes('karing')){
      return 'karing://install-config?url='+encodeURIComponent(url)+'&name='+encodeURIComponent('TwinPanel '+protocol);
    }
    return'';
  }

  function serverCount(panel){
    return panel.querySelectorAll('.server-views .server-view').length;
  }

  function allCard(panel,protocol,url,count,kind){
    const card=document.createElement('section');card.className='v38-all-card';
    card.dataset.v38Protocol=protocol;

    const head=document.createElement('div');head.className='v38-all-head';
    const heading=document.createElement('div');heading.className='v38-ha-title';
    const shield=document.createElement('span');shield.className='v38-ha-shield';shield.textContent='🛡️';
    const headingText=document.createElement('span');headingText.textContent='High Availability Config';
    const title=document.createElement('span');title.className='v38-sr-only';title.textContent='همه سرورها';
    const badge=document.createElement('span');badge.className='v38-ha-badge';badge.textContent=protocolTitle(panel,protocol);
    heading.append(shield,headingText,title);head.append(heading,badge);

    const row=document.createElement('div');row.className='v38-multi-row';
    const name=document.createElement('div');name.className='v38-multi-name';
    const globe=document.createElement('span');globe.textContent='🌐';
    const label=document.createElement('span');label.textContent='Multi Server';
    const counter=document.createElement('small');counter.textContent=String(count)+' سرور';
    name.append(globe,label,counter);

    const actions=document.createElement('div');actions.className='v38-all-actions';
    const client=clientName(panel);
    const deep=importHref(protocol,client,url);
    const subscription=SUBSCRIPTIONS.has(protocol);
    const bundle=kind==='bundle'||NATIVE_BUNDLES.has(protocol);

    if(subscription&&deep){
      actions.appendChild(link('افزودن همه',deep,true,'افزودن همه به '+client));
      actions.appendChild(button('کپی لینک',async()=>{
        notify(await copy(url)?'لینک اشتراک کپی شد ✓':'کپی انجام نشد');
      },false,true,'کپی لینک اشتراک'));
    }else if(subscription){
      actions.appendChild(button('کپی لینک',async()=>{
        notify(await copy(url)?'لینک اشتراک کپی شد ✓':'کپی انجام نشد');
      },true,false,'کپی لینک اشتراک'));
    }else if(bundle){
      actions.appendChild(link('دانلود همه',url,true,'دانلود همه کانفیگ‌ها'));
      actions.appendChild(button('کپی لینک',async()=>{
        notify(await copy(url)?'لینک همه سرورها کپی شد ✓':'کپی انجام نشد');
      },false,true,'کپی لینک همه سرورها'));
    }else if(deep){
      actions.appendChild(link('افزودن همه',deep,true,'افزودن همه به '+client));
      actions.appendChild(button('کپی لینک',async()=>{
        notify(await copy(url)?'لینک همه سرورها کپی شد ✓':'کپی انجام نشد');
      },false,true,'کپی لینک همه سرورها'));
    }else{
      actions.appendChild(button('کپی مولتی‌لینک',async()=>{
        notify(await copy(url)?'لینک همه سرورها کپی شد ✓':'کپی انجام نشد');
      },true,false,'کپی لینک همه سرورها'));
    }

    row.append(name,actions);card.append(head,row);
    panel.querySelector('.panel-head')?.insertAdjacentElement('afterend',card);

    const serverViews=panel.querySelector('.server-views');
    if(serverViews&&!panel.querySelector('.v38-server-list-title')){
      const listTitle=document.createElement('div');
      listTitle.className='v38-server-list-title';listTitle.textContent='سرورهای تکی';
      serverViews.insertAdjacentElement('beforebegin',listTitle);
    }
    return card;
  }

  function build(panel){
    if(panel.dataset.v38Ready==='1')return;
    const protocol=panelKey(panel);if(!MULTI.has(protocol))return;

    panel.querySelectorAll('.v37-multi-card,.v38-all-card,.v38-server-list-title').forEach(node=>node.remove());

    const count=serverCount(panel);
    if(count<=0)return;

    const subscription=SUBSCRIPTIONS.has(protocol);
    const url=subscription?subscriptionUrl(protocol):multiUrl(protocol);
    if(!url)return;

    allCard(
      panel,
      protocol,
      url,
      count,
      subscription?'subscription':(NATIVE_BUNDLES.has(protocol)?'bundle':'multi')
    );
    panel.dataset.v38Ready='1';
  }

  function apply(){
    document.body.classList.add('v38-reference');
    document.body.dataset.tpPublicReference='v38';
    document.querySelectorAll('.v37-multi-card').forEach(node=>node.remove());
    document.querySelectorAll('.protocol-panel').forEach(build);
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,250);
  window.setTimeout(apply,800);
})();
</script>
"""


def refine_public_connection_reference_layout_v38(source: str) -> str:
    """Render the reference HA/Multi Server card, then apply V39 mobile refinement."""
    if _MARKER not in source:
        source = source.replace("</style>", _CSS + "\n</style>", 1)
        source = source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
    return refine_public_connection_mobile_simplified_v39(source)
