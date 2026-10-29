from __future__ import annotations

import json

from .public_connection_modern_delivery_v13 import CLIENTS as V13_CLIENTS


_MARKER = "TWINPANEL_PUBLIC_CONNECT_FORWARD_V34"


def _client_catalog() -> dict[str, dict[str, dict[str, str]]]:
    """Expose only the already-authoritative V13 client name/link mapping."""
    result: dict[str, dict[str, dict[str, str]]] = {}
    for protocol, rows in V13_CLIENTS.items():
        platform_rows: dict[str, dict[str, str]] = {}
        for platform, value in rows.items():
            if not isinstance(value, tuple) or len(value) != 2:
                continue
            name, url = value
            name = str(name or "").strip()
            url = str(url or "").strip()
            if name and url:
                platform_rows[str(platform)] = {"name": name, "url": url}
        if platform_rows:
            result[str(protocol)] = platform_rows
    return result


def _client_data_script() -> str:
    payload = json.dumps(_client_catalog(), ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")
    return (
        '<script id="twinpanelPublicConnectV34ClientData">'
        f"window.__TP_V34_CLIENTS__={payload};"
        "</script>"
    )


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_FORWARD_V34 */

/* V34 is the only customer-facing action authority. Older renderers remain
 * available only as canonical data/action sources. */
body.v34-ready .multi-link-card,
body.v34-ready .apps-head,
body.v34-ready .apps,
body.v34-ready .v9-apps-drawer,
body.v34-ready .v17-mobile-stack,
body.v34-ready .v9-mobile-stack,
body.v34-ready .v13-client-only,
body.v34-ready .v13-modern-action,
body.v34-ready .server-view>.action-row,
body.v34-ready .mobile-send-btn,
body.v34-ready .tp-win-v2ray-note,
body.v34-ready .tp-v15-client-note{display:none!important}

/* Modern protocols must never show V5's generic Server/User/Password fallback. */
body.v34-ready .protocol-panel[data-v34-modern="1"] .facts{display:none!important}

body.v34-ready .v34-subscription-card,
body.v34-ready .v34-client-card{
  margin:12px;padding:13px;border:1px solid var(--line);border-radius:14px;background:var(--surface2)
}
body.v34-ready .v34-subscription-card{
  border-color:color-mix(in srgb,var(--p) 34%,var(--line));
  background:linear-gradient(145deg,color-mix(in srgb,var(--p) 7%,var(--surface2)),var(--surface2))
}
body.v34-ready .v34-head,
body.v34-ready .v34-client-card{display:flex;align-items:center;justify-content:space-between;gap:10px}
body.v34-ready .v34-head{margin-bottom:10px}
body.v34-ready .v34-head b{font-size:14px;line-height:1.5}
body.v34-ready .v34-head span,
body.v34-ready .v34-client-label{color:var(--muted);font-size:11px;font-weight:800}
body.v34-ready .v34-actions,
body.v34-ready .v34-server-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
body.v34-ready .v34-server-actions{margin-top:10px}
body.v34-ready .v34-actions>a,
body.v34-ready .v34-actions>button,
body.v34-ready .v34-server-actions>a,
body.v34-ready .v34-server-actions>button,
body.v34-ready .v34-client-card>a{
  min-height:42px;padding:9px 12px;display:inline-flex;align-items:center;justify-content:center;
  border:1px solid var(--line);border-radius:10px;background:var(--surface);color:var(--text);
  font:inherit;font-size:12px;font-weight:900;line-height:1.4;text-align:center;text-decoration:none;cursor:pointer
}
body.v34-ready .v34-primary{border-color:var(--p)!important;background:var(--p)!important;color:#fff!important}
body.v34-ready .v34-copy{color:var(--p)!important}
body.v34-ready .v34-client-card>a{min-width:150px}
body.v34-ready .fact .copy-btn{min-height:34px;padding:6px 9px;font-size:11px}
body.v34-ready .v34-single-label{margin:12px 12px 6px;color:var(--muted);font-size:12px;font-weight:900}
body.v34-ready .v34-mobile-servers{margin:10px;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--surface2)}
body.v34-ready .v34-mobile-servers>summary{min-height:44px;padding:0 12px;display:flex;align-items:center;justify-content:space-between;font-size:12px;font-weight:900;cursor:pointer;list-style:none}
body.v34-ready .v34-mobile-servers>summary::-webkit-details-marker{display:none}
body.v34-ready .v34-mobile-servers>summary:after{content:'⌄';color:var(--muted);font-size:16px}
body.v34-ready .v34-mobile-servers[open]>summary:after{content:'⌃'}

/* A narrow desktop browser stays desktop. Phone stacking requires V11's
 * authoritative Android/iOS platform value, never viewport width alone. */
@media(max-width:720px){
  body.v34-ready[data-tp-platform="android"] .v34-subscription-card,
  body.v34-ready[data-tp-platform="ios"] .v34-subscription-card,
  body.v34-ready[data-tp-platform="android"] .v34-client-card,
  body.v34-ready[data-tp-platform="ios"] .v34-client-card{margin:10px;padding:11px}
  body.v34-ready[data-tp-platform="android"] .v34-client-card,
  body.v34-ready[data-tp-platform="ios"] .v34-client-card{align-items:stretch;flex-direction:column}
  body.v34-ready[data-tp-platform="android"] .v34-client-card>a,
  body.v34-ready[data-tp-platform="ios"] .v34-client-card>a{width:100%}
  body.v34-ready[data-tp-platform="android"] .v34-actions,
  body.v34-ready[data-tp-platform="ios"] .v34-actions,
  body.v34-ready[data-tp-platform="android"] .v34-server-actions,
  body.v34-ready[data-tp-platform="ios"] .v34-server-actions{grid-template-columns:1fr}
  body.v34-ready[data-tp-platform="android"] .server-tabs,
  body.v34-ready[data-tp-platform="ios"] .server-tabs{display:none!important}
  body.v34-ready[data-tp-platform="android"] .server-views,
  body.v34-ready[data-tp-platform="ios"] .server-views{display:grid!important;gap:9px!important;padding:10px!important}
  body.v34-ready[data-tp-platform="android"] .server-view,
  body.v34-ready[data-tp-platform="ios"] .server-view{
    display:block!important;margin:0!important;padding:11px!important;border:1px solid var(--line)!important;
    border-radius:12px!important;background:var(--surface2)!important
  }
  body.v34-ready[data-tp-platform="android"] .server-view:before,
  body.v34-ready[data-tp-platform="ios"] .server-view:before{
    content:attr(data-v34-server-label);display:block;margin-bottom:8px;color:var(--text);
    font-size:12px;font-weight:900;text-align:right
  }
  body.v34-ready[data-tp-platform="android"] .v34-single-label,
  body.v34-ready[data-tp-platform="ios"] .v34-single-label{margin:10px 10px 4px}
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectForwardV34">
(function(){
  const SUBSCRIPTIONS=new Set(['v2ray','hysteria2','tuic','anytls']);
  const MODERN=new Set([
    'hysteria2','tuic','anytls','naive','shadowtls','snell','mieru',
    'trusttunnel','amneziawg','sudoku'
  ]);
  const MANUAL=new Set(['cisco','l2tp']);
  const NATIVE_FILES=new Set(['openvpn','wireguard','amneziawg']);
  const URI_RE=/^(?:vmess|vless|trojan|ss|hysteria2|hy2|tuic|anytls|naive|mieru|snell|sudoku|trusttunnel|wg|wireguard):\/\//i;
  const CLIENTS=window.__TP_V34_CLIENTS__||{};
  try{delete window.__TP_V34_CLIENTS__}catch(_error){}
  const text=el=>String(el?.textContent||'').trim();

  function normalize(value){
    const key=String(value||'').trim().toLowerCase();
    if(key==='xray')return'v2ray';
    if(key==='naiveproxy')return'naive';
    if(key==='openconnect'||key==='ocserv'||key==='anyconnect')return'cisco';
    return key;
  }

  function platform(){
    const current=String(document.body?.dataset?.tpPlatform||document.documentElement?.dataset?.tpPlatform||'').trim().toLowerCase();
    return ['windows','android','ios','macos','linux','unknown'].includes(current)?current:'unknown';
  }

  function isPhone(){
    const value=platform();
    return value==='android'||value==='ios';
  }

  function panelKey(panel){
    const modern=normalize(panel?.dataset?.modernProtocol||'');
    if(modern)return modern;
    const choice=[...document.querySelectorAll('.protocol-choice')]
      .find(item=>String(item.dataset.protocol||'')===String(panel?.id||''));
    return normalize(choice?.dataset?.protocolKey||choice?.dataset?.protocol||'');
  }

  function serverLabel(panel,view,index){
    const tabs=[...panel.querySelectorAll('.server-tab')];
    const direct=tabs.find(tab=>String(tab.dataset.server||'')===String(view.id||''));
    return text(direct?.querySelector('span'))||text(direct)||text(tabs[index])||('Server '+(index+1));
  }

  function targetValue(id){
    const node=document.getElementById(String(id||''));
    return node?String('value' in node?node.value:node.textContent||'').trim():'';
  }

  function payload(node){
    if(!node)return'';
    if(node.dataset?.copy)return String(node.dataset.copy||'').trim();
    if(node.dataset?.tpCopyTarget)return targetValue(node.dataset.tpCopyTarget);
    if(node.dataset?.target)return targetValue(node.dataset.target);
    return'';
  }

  function uriFrom(view){
    for(const node of view.querySelectorAll('[data-copy],[data-tp-copy-target],a[href]')){
      const raw=payload(node)||String(node.getAttribute?.('href')||'').trim();
      if(URI_RE.test(raw))return raw;
    }
    return'';
  }

  function clientFor(key){
    const p=platform();
    if(p==='unknown'||key==='l2tp')return null;
    const row=CLIENTS?.[key]?.[p]||null;
    if(!row?.name||!row?.url)return null;
    return {name:String(row.name),href:String(row.url)};
  }

  function directCandidates(view){
    return [...view.querySelectorAll(
      'a.tp-win-hiddify[href],a.tp-v48-hiddify[href],a.v15-karing-inline[href],a.v13-karing-inline[href],'+
      'a.v13-open-uri[href],a.primary-btn[href],button.v13-karing-import,button.primary-btn[data-config-path]'
    )].filter(node=>{
      const href=String(node.getAttribute?.('href')||'');
      if(node.matches?.('.tp-v16-safe-download,.v13-secondary,.download-config'))return false;
      if(href.includes('/modern-config'))return false;
      return true;
    });
  }

  function directMatchesClient(node,client){
    if(!node||!client)return false;
    const href=String(node.getAttribute?.('href')||'').trim().toLowerCase();
    const label=text(node).toLowerCase();
    const name=String(client.name||'').toLowerCase();
    if(name.includes('hiddify'))return href.startsWith('hiddify:')||(href+label).includes('hiddify');
    if(name.includes('karing'))return href.startsWith('karing:')||(href+label).includes('karing');
    if(name.includes('trusttunnel'))return href.startsWith('trusttunnel:')||(href+label).includes('trusttunnel');
    if(name.includes('sudoku')||name.includes('sudodroid')||name.includes('anywhere proxy'))return href.startsWith('sudoku:')||(href+label).includes('sudoku');
    return false;
  }

  function bestDirect(view,client){
    return directCandidates(view).find(node=>directMatchesClient(node,client))||null;
  }

  function downloadCandidate(view){
    return view.querySelector(
      'a.tp-v16-safe-download[href],a.v13-secondary[href],a[href*="/modern-config"],button.download-config[data-target]'
    );
  }

  function notify(message){
    const toast=document.getElementById('toast');
    if(!toast)return;
    toast.textContent=message;toast.classList.add('show');
    clearTimeout(window.__tpV34Toast);
    window.__tpV34Toast=setTimeout(()=>toast.classList.remove('show'),1700);
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

  function button(label,handler,primary,copyClass){
    const node=document.createElement('button');node.type='button';node.textContent=label;
    if(primary)node.classList.add('v34-primary');if(copyClass)node.classList.add('v34-copy');
    node.addEventListener('click',handler);return node;
  }

  function link(label,href,primary){
    const node=document.createElement('a');node.textContent=label;node.href=href;
    if(primary)node.classList.add('v34-primary');
    if(/^https?:\/\//i.test(href)){node.target='_blank';node.rel='noopener noreferrer'}
    return node;
  }

  function proxyClick(source,label,primary){
    if(!source)return null;
    const href=String(source.getAttribute?.('href')||'').trim();
    if(source.tagName==='A'&&href)return link(label,href,primary);
    return button(label,()=>source.click(),primary,false);
  }

  function explicitFactLabels(panel){
    panel.querySelectorAll('.fact').forEach(fact=>{
      const label=text(fact.querySelector('small')).toLowerCase();
      const copyButton=fact.querySelector('.copy-btn');if(!copyButton)return;
      if(label.includes('username'))copyButton.textContent='کپی نام کاربری';
      else if(label.includes('password'))copyButton.textContent='کپی رمز عبور';
      else if(label.includes('secret'))copyButton.textContent='کپی Secret';
      else copyButton.textContent='کپی سرور';
    });
  }

  function buildClientCard(panel,client,afterNode){
    if(!client?.href)return null;
    const card=document.createElement('section');card.className='v34-client-card';
    const label=document.createElement('span');label.className='v34-client-label';label.textContent='برنامه اتصال';
    const app=link('دانلود '+client.name,client.href,false);card.append(label,app);
    if(afterNode)afterNode.insertAdjacentElement('afterend',card);
    else panel.querySelector('.panel-head')?.insertAdjacentElement('afterend',card);
    return card;
  }

  function token(){
    const match=String(window.location.pathname||'').match(/^\/v1\/connect\/([^/]+)/);if(!match)return'';
    try{return decodeURIComponent(match[1])}catch(_error){return match[1]}
  }

  function subscriptionUrl(protocol){
    const value=token();if(!value||!SUBSCRIPTIONS.has(protocol))return'';
    return window.location.origin+'/v1/connect/'+encodeURIComponent(value)+'/sub/'+encodeURIComponent(protocol);
  }

  async function subscriptionCount(protocol){
    const url=subscriptionUrl(protocol);if(!url)return 0;
    try{
      const response=await fetch(url,{cache:'no-store',headers:{Accept:'text/plain'}});
      if(!response.ok)return 0;
      const encoded=String(await response.text()).trim();if(!encoded)return 0;
      const decoded=atob(encoded.replace(/\s+/g,''));
      return decoded.split(/\r?\n/).map(row=>row.trim()).filter(Boolean).length;
    }catch(_error){return 0}
  }

  function useSubscription(protocol,client){
    const url=subscriptionUrl(protocol);if(!url)return;
    const name=String(client?.name||'').toLowerCase();
    if(name.includes('hiddify')){
      window.location.href='hiddify://import/'+encodeURI(url)+'#TwinPanel-'+encodeURIComponent(protocol);return;
    }
    if(name.includes('karing')){
      window.location.href='karing://install-config?url='+encodeURIComponent(url)+'&name='+encodeURIComponent('TwinPanel '+protocol);return;
    }
    copy(url).then(ok=>notify(ok?'لینک اشتراک کپی شد ✓':'کپی انجام نشد'));
  }

  function buildSubscriptionCard(panel,key,client){
    if(!SUBSCRIPTIONS.has(key))return null;
    const url=subscriptionUrl(key);if(!url)return null;
    const card=document.createElement('section');card.className='v34-subscription-card';card.hidden=true;
    const head=document.createElement('div');head.className='v34-head';
    head.innerHTML='<b>همه سرورها</b><span>در حال بررسی…</span>';
    const actions=document.createElement('div');actions.className='v34-actions';
    let primary='استفاده از لینک اشتراک';
    const name=String(client?.name||'');
    if(/hiddify|karing/i.test(name))primary='افزودن همه به '+name;
    actions.appendChild(button(primary,()=>useSubscription(key,client),true,false));
    actions.appendChild(button('کپی لینک اشتراک',async()=>{
      notify(await copy(url)?'لینک اشتراک کپی شد ✓':'کپی انجام نشد');
    },false,true));
    card.append(head,actions);panel.querySelector('.panel-head')?.insertAdjacentElement('afterend',card);
    subscriptionCount(key).then(count=>{
      if(count<=0){card.remove();return}
      const counter=head.querySelector('span');if(counter)counter.textContent=count+' سرور';
      card.hidden=false;
    });
    return card;
  }

  function buildServerActions(view,key,client){
    view.querySelectorAll('.v34-server-actions').forEach(node=>node.remove());
    if(MANUAL.has(key))return;
    const row=document.createElement('div');row.className='v34-server-actions';
    const direct=bestDirect(view,client);const uri=uriFrom(view);const download=downloadCandidate(view);

    if(NATIVE_FILES.has(key)){
      const action=proxyClick(download,'دانلود کانفیگ',true);if(action)row.appendChild(action);
    }else{
      if(direct){
        const action=proxyClick(direct,'اتصال به '+client.name,true);if(action)row.appendChild(action);
      }
      if(uri&&row.children.length<2){
        row.appendChild(button('کپی لینک اتصال',async()=>{
          notify(await copy(uri)?'لینک اتصال کپی شد ✓':'کپی انجام نشد');
        },false,true));
      }
      if(download&&row.children.length<2){
        const action=proxyClick(download,'دانلود کانفیگ',row.children.length===0);if(action)row.appendChild(action);
      }
    }
    while(row.children.length>2)row.lastElementChild?.remove();
    if(row.children.length)view.appendChild(row);
  }

  function cleanupPanel(panel){
    panel.querySelectorAll('.v34-subscription-card,.v34-client-card,.v34-single-label').forEach(node=>node.remove());
    const fold=panel.querySelector('.v34-mobile-servers[data-v34-server-fold="1"]');
    if(fold){
      const views=fold.querySelector(':scope > .server-views');
      if(views)fold.insertAdjacentElement('beforebegin',views);
      fold.remove();
    }
  }

  function organizeServerList(panel,views){
    const serverViews=panel.querySelector('.server-views');if(!serverViews)return;
    if(isPhone()&&views.length>3){
      const fold=document.createElement('details');fold.className='v34-mobile-servers';fold.dataset.v34ServerFold='1';
      const summary=document.createElement('summary');summary.textContent='سرورهای تکی';
      serverViews.insertAdjacentElement('beforebegin',fold);fold.append(summary,serverViews);return;
    }
    const label=document.createElement('div');label.className='v34-single-label';label.textContent='سرورهای تکی';
    const tabs=panel.querySelector('.server-tabs');
    (tabs||serverViews).insertAdjacentElement('beforebegin',label);
  }

  function buildPanel(panel){
    cleanupPanel(panel);
    const key=panelKey(panel);if(!key)return;
    panel.dataset.v34Protocol=key;
    if(MODERN.has(key))panel.dataset.v34Modern='1';else delete panel.dataset.v34Modern;
    explicitFactLabels(panel);
    const client=clientFor(key);const views=[...panel.querySelectorAll('.server-view')];
    views.forEach((view,index)=>{
      view.dataset.v34ServerLabel=serverLabel(panel,view,index);buildServerActions(view,key,client);
    });
    const subscription=buildSubscriptionCard(panel,key,client);
    buildClientCard(panel,client,subscription);
    organizeServerList(panel,views);
  }

  function apply(){
    const p=platform();
    document.body.dataset.tpPlatform=p;document.documentElement.dataset.tpPlatform=p;
    document.body.classList.add('v34-ready');document.body.dataset.tpPublicPresentation='v34';
    document.querySelectorAll('.protocol-panel').forEach(buildPanel);
  }

  apply();
})();
</script>
"""


def refine_public_connection_forward_v34(source: str) -> str:
    """Build one V11-device-aware presentation from canonical existing actions."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    source = source.replace(
        "</body>",
        _client_data_script() + "\n" + _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>",
        1,
    )
    return source
