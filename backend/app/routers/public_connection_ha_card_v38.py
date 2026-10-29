from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_HA_CARD_V38"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_HA_CARD_V38 */
body.v38-ready .v37-multi-card{display:none!important}
body.v38-ready .v38-ha-card{
  margin:12px;
  border:1px solid color-mix(in srgb,var(--p) 30%,var(--line));
  border-radius:16px;
  overflow:hidden;
  background:var(--surface2);
}
body.v38-ready .v38-ha-head{
  min-height:54px;
  padding:11px 14px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  border-bottom:1px solid var(--line);
}
body.v38-ready .v38-ha-title{
  display:flex;
  align-items:center;
  gap:9px;
  min-width:0;
  font-size:14px;
  font-weight:950;
}
body.v38-ready .v38-ha-shield{font-size:18px;line-height:1}
body.v38-ready .v38-ha-badge{
  padding:5px 10px;
  border:1px solid color-mix(in srgb,var(--p) 48%,var(--line));
  border-radius:999px;
  color:var(--p);
  font-size:11px;
  font-weight:900;
  white-space:nowrap;
}
body.v38-ready .v38-ha-row{
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
body.v38-ready .v38-ha-name{
  display:flex;
  align-items:center;
  gap:9px;
  min-width:0;
  font-weight:950;
}
body.v38-ready .v38-ha-name small{
  color:var(--muted);
  font-size:10px;
  font-weight:800;
}
body.v38-ready .v38-ha-actions{
  display:flex;
  align-items:center;
  gap:7px;
  flex:0 0 auto;
}
body.v38-ready .v38-ha-actions>a,
body.v38-ready .v38-ha-actions>button{
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
  text-decoration:none;
  cursor:pointer;
  white-space:nowrap;
}
body.v38-ready .v38-ha-actions .v38-primary{
  border-color:var(--p)!important;
  background:var(--p)!important;
  color:#fff!important;
}
body.v38-ready .v38-server-list-title{
  margin:13px 12px 6px;
  color:var(--muted);
  font-size:11px;
  font-weight:900;
}

@media(max-width:720px){
  body.v38-ready[data-tp-platform="android"] .v38-ha-card,
  body.v38-ready[data-tp-platform="ios"] .v38-ha-card{margin:10px}
  body.v38-ready[data-tp-platform="android"] .v38-ha-head,
  body.v38-ready[data-tp-platform="ios"] .v38-ha-head{min-height:50px;padding:9px 11px}
  body.v38-ready[data-tp-platform="android"] .v38-ha-row,
  body.v38-ready[data-tp-platform="ios"] .v38-ha-row{margin:10px;min-height:50px;padding:7px 8px 7px 10px}
  body.v38-ready[data-tp-platform="android"] .v38-ha-actions>a,
  body.v38-ready[data-tp-platform="android"] .v38-ha-actions>button,
  body.v38-ready[data-tp-platform="ios"] .v38-ha-actions>a,
  body.v38-ready[data-tp-platform="ios"] .v38-ha-actions>button{min-height:36px;padding:7px 9px;font-size:10px}

  /* Keep individual servers compact inside the selected protocol, like the
   * reference card: one server row plus its existing canonical actions. */
  body.v38-ready[data-tp-platform="android"] .protocol-panel.v36-open .server-views,
  body.v38-ready[data-tp-platform="ios"] .protocol-panel.v36-open .server-views{
    gap:7px!important;
    padding:8px 10px 12px!important;
  }
  body.v38-ready[data-tp-platform="android"] .protocol-panel.v36-open .server-view,
  body.v38-ready[data-tp-platform="ios"] .protocol-panel.v36-open .server-view{
    padding:9px!important;
    border-radius:11px!important;
  }
  body.v38-ready[data-tp-platform="android"] .protocol-panel.v36-open .server-view:before,
  body.v38-ready[data-tp-platform="ios"] .protocol-panel.v36-open .server-view:before{
    margin-bottom:6px!important;
  }
  body.v38-ready[data-tp-platform="android"] .protocol-panel.v36-open .v34-server-actions,
  body.v38-ready[data-tp-platform="ios"] .protocol-panel.v36-open .v34-server-actions{
    grid-template-columns:repeat(2,minmax(0,1fr))!important;
    gap:6px!important;
    margin-top:6px!important;
  }
  body.v38-ready[data-tp-platform="android"] .protocol-panel.v36-open .v34-server-actions>a,
  body.v38-ready[data-tp-platform="android"] .protocol-panel.v36-open .v34-server-actions>button,
  body.v38-ready[data-tp-platform="ios"] .protocol-panel.v36-open .v34-server-actions>a,
  body.v38-ready[data-tp-platform="ios"] .protocol-panel.v36-open .v34-server-actions>button{
    min-height:38px!important;
    padding:7px 8px!important;
    font-size:10px!important;
  }
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectHaCardV38">
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

  function clientName(panel){
    const label=text(panel.querySelector('.v34-client-card a'));
    return label.replace(/^دانلود\s+/,'').trim();
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
    clearTimeout(window.__tpV38Toast);
    window.__tpV38Toast=setTimeout(()=>toast.classList.remove('show'),1500);
  }

  function actionLink(label,href,primary){
    const node=document.createElement('a');node.textContent=label;node.href=href;
    if(primary)node.classList.add('v38-primary');
    if(/^https?:\/\//i.test(href)){node.target='_blank';node.rel='noopener noreferrer'}
    return node;
  }

  function actionButton(label,handler,primary){
    const node=document.createElement('button');node.type='button';node.textContent=label;
    if(primary)node.classList.add('v38-primary');node.addEventListener('click',handler);return node;
  }

  function build(panel){
    panel.querySelectorAll('.v38-ha-card,.v38-server-list-title').forEach(node=>node.remove());
    const key=panelKey(panel);if(!MULTI.has(key))return;
    const views=[...panel.querySelectorAll('.server-view')];
    if(!views.length)return;
    const url=multiUrl(key);if(!url)return;

    const card=document.createElement('section');card.className='v38-ha-card';
    const head=document.createElement('div');head.className='v38-ha-head';
    const title=document.createElement('div');title.className='v38-ha-title';
    const shield=document.createElement('span');shield.className='v38-ha-shield';shield.textContent='🛡️';
    const titleText=document.createElement('span');titleText.textContent='High Availability Config';
    const badge=document.createElement('span');badge.className='v38-ha-badge';badge.textContent=protocolTitle(panel,key);
    title.append(shield,titleText);head.append(title,badge);

    const row=document.createElement('div');row.className='v38-ha-row';
    const name=document.createElement('div');name.className='v38-ha-name';
    const globe=document.createElement('span');globe.textContent='🌐';
    const label=document.createElement('span');label.textContent='Multi Server';
    const count=document.createElement('small');count.textContent=views.length+' سرور';
    name.append(globe,label,count);

    const actions=document.createElement('div');actions.className='v38-ha-actions';
    const client=clientName(panel);const deep=importHref(key,client,url);
    if(BUNDLE.has(key)){
      actions.appendChild(actionLink('دانلود همه',url,true));
    }else if(deep){
      actions.appendChild(actionLink('افزودن همه',deep,true));
      actions.appendChild(actionButton('کپی لینک',async()=>notify(await copy(url)?'مولتی‌لینک کپی شد ✓':'کپی انجام نشد'),false));
    }else{
      actions.appendChild(actionButton('کپی مولتی‌لینک',async()=>notify(await copy(url)?'مولتی‌لینک کپی شد ✓':'کپی انجام نشد'),true));
    }
    row.append(name,actions);card.append(head,row);

    const clientCard=panel.querySelector('.v34-client-card');
    const panelHead=panel.querySelector('.panel-head');
    if(clientCard)clientCard.insertAdjacentElement('beforebegin',card);
    else panelHead?.insertAdjacentElement('afterend',card);

    const listTitle=document.createElement('div');listTitle.className='v38-server-list-title';listTitle.textContent='سرورهای تکی';
    const serverViews=panel.querySelector('.server-views');
    if(serverViews)serverViews.insertAdjacentElement('beforebegin',listTitle);
  }

  function apply(){
    document.body.classList.add('v38-ready');
    document.body.dataset.tpPublicHa='v38';
    document.querySelectorAll('.protocol-panel').forEach(build);
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,220);
  window.setTimeout(apply,700);
})();
</script>
"""


def refine_public_connection_ha_card_v38(source: str) -> str:
    """Render deterministic HA/Multi Server cards above canonical per-server actions."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
