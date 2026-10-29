from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_HA_MULTISERVER_V39"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_HA_MULTISERVER_V39 */
body.v39-ready .v37-multi-card,
body.v39-ready .v38-all-card{display:none!important}

body.v39-ready .v39-ha-card{
  margin:12px;
  border:1px solid color-mix(in srgb,var(--p) 34%,var(--line));
  border-radius:16px;
  overflow:hidden;
  background:var(--surface2);
}
body.v39-ready .v39-ha-head{
  min-height:56px;
  padding:11px 14px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  border-bottom:1px solid var(--line);
}
body.v39-ready .v39-ha-title{
  display:flex;
  align-items:center;
  gap:9px;
  min-width:0;
  font-size:14px;
  font-weight:950;
}
body.v39-ready .v39-ha-shield{font-size:18px;line-height:1}
body.v39-ready .v39-ha-badge{
  padding:5px 10px;
  border:1px solid color-mix(in srgb,var(--p) 48%,var(--line));
  border-radius:999px;
  color:var(--p);
  font-size:11px;
  font-weight:900;
  white-space:nowrap;
}
body.v39-ready .v39-ha-row{
  margin:12px;
  min-height:58px;
  padding:8px 10px 8px 13px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  border:1px solid var(--line);
  border-radius:14px;
  background:var(--surface);
}
body.v39-ready .v39-ha-name{
  display:flex;
  align-items:center;
  gap:9px;
  min-width:0;
  font-weight:950;
}
body.v39-ready .v39-ha-name small{
  color:var(--muted);
  font-size:10px;
  font-weight:800;
}
body.v39-ready .v39-ha-actions{
  display:flex;
  align-items:center;
  gap:7px;
  flex:0 0 auto;
}
body.v39-ready .v39-ha-actions>a,
body.v39-ready .v39-ha-actions>button{
  min-height:40px;
  padding:8px 11px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  border:1px solid var(--line);
  border-radius:11px;
  background:var(--surface2);
  color:var(--text);
  font:inherit;
  font-size:11px;
  font-weight:900;
  text-decoration:none;
  cursor:pointer;
  white-space:nowrap;
}
body.v39-ready .v39-ha-actions .v39-primary{
  border-color:var(--p)!important;
  background:var(--p)!important;
  color:#fff!important;
}

@media(max-width:720px){
  body.v39-ready .v39-ha-card{margin:10px}
  body.v39-ready .v39-ha-head{min-height:50px;padding:9px 11px}
  body.v39-ready .v39-ha-row{margin:10px;min-height:52px;padding:7px 8px 7px 10px}
  body.v39-ready .v39-ha-actions>a,
  body.v39-ready .v39-ha-actions>button{min-height:36px;padding:7px 9px;font-size:10px}

  /* The protocol card itself is the only disclosure on mobile. */
  body.v39-ready.v36-mobile-compact .protocol-panel{display:none!important}
  body.v39-ready.v36-mobile-compact .protocol-panel.v36-open{display:block!important}

  /* Client install is represented by the protocol/multi actions; remove the
   * standalone client block that made the selected protocol unnecessarily long. */
  body.v39-ready .protocol-panel.v36-open .v34-client-card{display:none!important}

  /* Compact the existing canonical per-server rows without changing actions. */
  body.v39-ready .protocol-panel.v36-open .server-views{
    gap:7px!important;
    padding:8px 10px 12px!important;
  }
  body.v39-ready .protocol-panel.v36-open .server-view{
    padding:9px!important;
    border-radius:11px!important;
  }
  body.v39-ready .protocol-panel.v36-open .server-view:before{
    margin-bottom:6px!important;
  }
  body.v39-ready .protocol-panel.v36-open .v34-server-actions{
    grid-template-columns:repeat(2,minmax(0,1fr))!important;
    gap:6px!important;
    margin-top:6px!important;
  }
  body.v39-ready .protocol-panel.v36-open .v34-server-actions>a,
  body.v39-ready .protocol-panel.v36-open .v34-server-actions>button{
    min-height:38px!important;
    padding:7px 8px!important;
    font-size:10px!important;
  }
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectHaMultiserverV39">
(function(){
  const MULTI=new Set([
    'openvpn','wireguard','v2ray','hysteria2','tuic','anytls','naive',
    'shadowtls','snell','mieru','trusttunnel','amneziawg','sudoku'
  ]);
  const BUNDLE=new Set(['openvpn','wireguard','amneziawg']);
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

  function token(){
    const match=String(window.location.pathname||'').match(/^\/v1\/connect\/([^/]+)/);
    if(!match)return'';
    try{return decodeURIComponent(match[1])}catch(_error){return match[1]}
  }

  function multiUrl(protocol){
    const value=token();
    if(!value||!MULTI.has(protocol))return'';
    return window.location.origin+'/v1/connect/'+encodeURIComponent(value)+'/multi/'+encodeURIComponent(protocol);
  }

  function protocolTitle(panel,key){
    return text(panel.querySelector('.panel-head h2,.panel-head h3,.panel-head'))||key;
  }

  function clientInfo(panel){
    const anchor=panel.querySelector('.v34-client-card a');
    const label=text(anchor).replace(/^دانلود\s+/,'').trim();
    return {name:label,href:String(anchor?.href||'').trim()};
  }

  function importHref(protocol,client,url){
    const name=String(client||'').toLowerCase();
    if(name.includes('hiddify'))return 'hiddify://import/'+encodeURI(url)+'#TwinPanel-'+encodeURIComponent(protocol);
    if(name.includes('karing'))return 'karing://install-config?url='+encodeURIComponent(url)+'&name='+encodeURIComponent('TwinPanel '+protocol);
    return'';
  }

  function fallbackCopy(value){
    const area=document.createElement('textarea');
    area.value=String(value||'');area.readOnly=true;area.style.position='fixed';area.style.left='-9999px';
    document.body.appendChild(area);area.focus();area.select();area.setSelectionRange(0,area.value.length);
    let ok=false;try{ok=document.execCommand('copy')}catch(_error){}area.remove();return ok;
  }

  async function copy(value){
    const raw=String(value||'').trim();if(!raw)return false;
    if(navigator.clipboard&&window.isSecureContext){try{await navigator.clipboard.writeText(raw);return true}catch(_error){}}
    return fallbackCopy(raw);
  }

  function notify(message){
    const toast=document.getElementById('toast');if(!toast)return;
    toast.textContent=message;toast.classList.add('show');
    clearTimeout(window.__tpV39Toast);
    window.__tpV39Toast=setTimeout(()=>toast.classList.remove('show'),1500);
  }

  function actionLink(label,href,primary){
    const node=document.createElement('a');node.textContent=label;node.href=href;
    if(primary)node.classList.add('v39-primary');
    if(/^https?:\/\//i.test(href)){node.target='_blank';node.rel='noopener noreferrer'}
    return node;
  }

  function actionButton(label,handler,primary){
    const node=document.createElement('button');node.type='button';node.textContent=label;
    if(primary)node.classList.add('v39-primary');node.addEventListener('click',handler);return node;
  }

  function build(panel){
    panel.querySelectorAll('.v39-ha-card').forEach(node=>node.remove());
    const key=panelKey(panel);if(!MULTI.has(key))return;
    const views=[...panel.querySelectorAll('.server-view')];
    if(!views.length)return;
    const url=multiUrl(key);if(!url)return;

    const card=document.createElement('section');card.className='v39-ha-card';
    const head=document.createElement('div');head.className='v39-ha-head';
    const title=document.createElement('div');title.className='v39-ha-title';
    const shield=document.createElement('span');shield.className='v39-ha-shield';shield.textContent='🛡️';
    const titleText=document.createElement('span');titleText.textContent='High Availability Config';
    const badge=document.createElement('span');badge.className='v39-ha-badge';badge.textContent=protocolTitle(panel,key);
    title.append(shield,titleText);head.append(title,badge);

    const row=document.createElement('div');row.className='v39-ha-row';
    const name=document.createElement('div');name.className='v39-ha-name';
    const globe=document.createElement('span');globe.textContent='🌐';
    const label=document.createElement('span');label.textContent='Multi Server';
    const count=document.createElement('small');count.textContent=views.length+' سرور';
    name.append(globe,label,count);

    const actions=document.createElement('div');actions.className='v39-ha-actions';
    const client=clientInfo(panel);const deep=importHref(key,client.name,url);
    if(BUNDLE.has(key)){
      actions.appendChild(actionLink('دانلود همه',url,true));
      if(client.href)actions.appendChild(actionLink('برنامه',client.href,false));
    }else if(deep){
      actions.appendChild(actionLink('افزودن همه',deep,true));
      actions.appendChild(actionButton('کپی لینک',async()=>notify(await copy(url)?'مولتی‌لینک کپی شد ✓':'کپی انجام نشد'),false));
    }else{
      actions.appendChild(actionButton('کپی مولتی‌لینک',async()=>notify(await copy(url)?'مولتی‌لینک کپی شد ✓':'کپی انجام نشد'),true));
    }
    row.append(name,actions);card.append(head,row);

    panel.querySelector('.panel-head')?.insertAdjacentElement('afterend',card);
  }

  function apply(){
    document.body.classList.add('v39-ready');
    document.body.dataset.tpPublicHa='v39';
    document.querySelectorAll('.v37-multi-card,.v38-all-card').forEach(node=>node.remove());
    document.querySelectorAll('.protocol-panel').forEach(build);
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,220);
  window.setTimeout(apply,700);
})();
</script>
"""


def refine_public_connection_ha_multiserver_v39(source: str) -> str:
    """Refine the reference layout into deterministic HA/Multi Server cards."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
