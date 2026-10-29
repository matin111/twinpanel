from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_FORWARD_V34"


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

body.v34-ready .v34-multi-card,
body.v34-ready .v34-client-card{
  margin:12px;padding:13px;border:1px solid var(--line);border-radius:14px;background:var(--surface2)
}
body.v34-ready .v34-multi-card{
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

/* A narrow desktop browser stays desktop. Phone stacking requires Android/iOS. */
@media(max-width:720px){
  body.v34-ready[data-tp-platform="android"] .v34-multi-card,
  body.v34-ready[data-tp-platform="ios"] .v34-multi-card,
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
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectForwardV34">
(function(){
  const MULTI=new Set([
    'openvpn','wireguard','v2ray','hysteria2','tuic','anytls','naive',
    'shadowtls','snell','mieru','trusttunnel','amneziawg','sudoku'
  ]);
  const MODERN=new Set([
    'hysteria2','tuic','anytls','naive','shadowtls','snell','mieru',
    'trusttunnel','amneziawg','sudoku'
  ]);
  const MANUAL=new Set(['cisco','l2tp']);
  const NATIVE_FILES=new Set(['openvpn','wireguard','amneziawg']);
  const URI_RE=/^(?:vmess|vless|trojan|ss|hysteria2|hy2|tuic|anytls|naive|mieru|snell|sudoku|trusttunnel|wg|wireguard):\/\//i;
  const APP_RE=/^(?:karing|hiddify|trusttunnel|sudoku|sing-box|amneziawg):\/\//i;
  const text=el=>String(el?.textContent||'').trim();

  const CLIENTS={
    cisco:{key:'openconnect',name:'OpenConnect / Cisco'},
    openvpn:{key:'openvpn',name:'OpenVPN'},
    wireguard:{key:'wireguard',name:'WireGuard'},
    v2ray:{key:'hiddify',name:'Hiddify'},
    hysteria2:{key:'karing',name:'Karing'},
    tuic:{key:'karing',name:'Karing'},
    anytls:{key:'karing',name:'Karing'},
    naive:{key:'karing',name:'Karing'},
    shadowtls:{key:'karing',name:'Karing'},
    snell:{key:'hiddify',name:'Hiddify'},
    mieru:{key:'karing',name:'Karing'},
    trusttunnel:{key:'trusttunnel',name:'TrustTunnel'},
    amneziawg:{key:'amneziawg',name:'AmneziaWG'},
    sudoku:{key:'sudoku',name:'Sudoku'}
  };

  function normalize(value){
    const key=String(value||'').trim().toLowerCase();
    if(key==='xray')return'v2ray';
    if(key==='naiveproxy')return'naive';
    if(key==='openconnect'||key==='ocserv'||key==='anyconnect')return'cisco';
    return key;
  }

  function platform(){
    const current=String(document.body?.dataset?.tpPlatform||'').trim().toLowerCase();
    if(['windows','android','ios','macos','linux'].includes(current))return current;
    const uaData=navigator.userAgentData||null;
    const ua=String(navigator.userAgent||'');
    const nav=String((uaData&&uaData.platform)||navigator.platform||'');
    const all=(ua+' '+nav).toLowerCase();
    if(/android/i.test(ua))return'android';
    if(/iphone|ipad|ipod/i.test(ua))return'ios';
    if(/macintosh|mac os|macintel/i.test(all)&&Number(navigator.maxTouchPoints||0)>1)return'ios';
    if(/windows|win32|win64|winarm/i.test(all))return'windows';
    if(/macintosh|mac os|macintel/i.test(all))return'macos';
    if(/linux|x11|cros/i.test(all))return'linux';
    return'unknown';
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
    const client=CLIENTS[key]||null;
    if(!client)return null;
    return {
      key:client.key,
      name:client.name,
      href:'/v1/connect/app-download/'+encodeURIComponent(client.key)+'/'+encodeURIComponent(p)
    };
  }

  function directCandidates(view){
    return [...view.querySelectorAll(
      'a.tp-win-hiddify[href],a.v15-karing-inline[href],a.v13-karing-inline[href],'+
      'a.v13-open-uri[href],a.primary-btn[href],button.v13-karing-import,button.primary-btn[data-config-path]'
    )].filter(node=>{
      const href=String(node.getAttribute?.('href')||'');
      if(node.matches?.('.tp-v16-safe-download,.v13-secondary,.download-config'))return false;
      if(href.includes('/modern-config'))return false;
      return true;
    });
  }

  function directScore(node,client){
    const href=String(node.getAttribute?.('href')||'').toLowerCase();
    const label=text(node).toLowerCase();
    const name=String(client?.name||'').toLowerCase();
    let score=0;
    if(node.matches?.('.tp-win-hiddify,.v15-karing-inline,.v13-karing-inline'))score+=30;
    if(node.matches?.('.v13-open-uri'))score+=20;
    if(APP_RE.test(href))score+=15;
    if(URI_RE.test(href))score+=10;
    if(name.includes('hiddify')&&(href+label).includes('hiddify'))score+=100;
    if(name.includes('karing')&&(href+label).includes('karing'))score+=100;
    if(name.includes('trusttunnel')&&(href+label).includes('trusttunnel'))score+=100;
    if(name.includes('amnezia')&&(href+label).includes('amnezia'))score+=100;
    if(name.includes('sudoku')&&(href+label).includes('sudoku'))score+=100;
    return score;
  }

  function bestDirect(view,client){
    const rows=directCandidates(view);
    rows.sort((a,b)=>directScore(b,client)-directScore(a,client));
    return rows[0]||null;
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

  function absolute(href){try{return new URL(href,window.location.href).href}catch(_error){return href}}

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
    const app=link('دانلود مستقیم '+client.name,client.href,false);card.append(label,app);
    if(afterNode)afterNode.insertAdjacentElement('afterend',card);
    else panel.querySelector('.panel-head')?.insertAdjacentElement('afterend',card);
    return card;
  }

  function token(){
    const match=String(window.location.pathname||'').match(/^\/v1\/connect\/([^/]+)/);if(!match)return'';
    try{return decodeURIComponent(match[1])}catch(_error){return match[1]}
  }

  function multiUrl(protocol){
    const value=token();if(!value)return'';
    return window.location.origin+'/v1/connect/'+encodeURIComponent(value)+'/multi/'+encodeURIComponent(protocol);
  }
  function multiMetaUrl(protocol){return multiUrl(protocol)+'/meta'}

  async function multiMeta(protocol){
    try{
      const response=await fetch(multiMetaUrl(protocol),{cache:'no-store',headers:{Accept:'application/json'}});
      if(!response.ok)return null;return await response.json();
    }catch(_error){return null}
  }

  async function useAll(protocol,client){
    const url=multiUrl(protocol);if(!url)return;
    const meta=await multiMeta(protocol);
    if(!meta){notify('اطلاعات همه سرورها آماده نیست');return}
    if(meta.kind==='bundle'){window.location.href=url;return}
    if(client?.key==='hiddify'){
      window.location.href='hiddify://import/'+encodeURI(url)+'#TwinPanel-'+encodeURIComponent(protocol);return;
    }
    if(client?.key==='karing'){
      window.location.href='karing://install-config?url='+encodeURIComponent(url)+'&name='+encodeURIComponent('TwinPanel '+protocol);return;
    }
    notify(await copy(url)?'لینک همه سرورها کپی شد ✓':'کپی انجام نشد');
  }

  function buildMultiCard(panel,key,count,client){
    if(!MULTI.has(key))return null;
    const url=multiUrl(key);if(!url)return null;
    const card=document.createElement('section');card.className='v34-multi-card';
    const head=document.createElement('div');head.className='v34-head';
    head.innerHTML='<b>همه سرورها</b><span>'+count+' سرور</span>';
    const actions=document.createElement('div');actions.className='v34-actions';
    let primary='دریافت همه سرورها';
    if(client?.key==='hiddify'||client?.key==='karing')primary='افزودن همه به '+client.name;
    else if(NATIVE_FILES.has(key))primary='دانلود همه کانفیگ‌ها';
    actions.appendChild(button(primary,()=>useAll(key,client),true,false));
    actions.appendChild(button('کپی لینک همه سرورها',async()=>{
      notify(await copy(url)?'لینک همه سرورها کپی شد ✓':'کپی انجام نشد');
    },false,true));
    card.append(head,actions);panel.querySelector('.panel-head')?.insertAdjacentElement('afterend',card);return card;
  }

  function hiddifyImportFromDownload(download){
    if(!download||download.tagName!=='A')return'';
    const href=String(download.getAttribute('href')||'').trim();if(!href)return'';
    return 'hiddify://import/'+encodeURI(absolute(href))+'#TwinPanel';
  }

  function buildServerActions(panel,view,key,client){
    view.querySelectorAll('.v34-server-actions').forEach(node=>node.remove());
    if(MANUAL.has(key))return;
    const row=document.createElement('div');row.className='v34-server-actions';
    const direct=bestDirect(view,client);const uri=uriFrom(view);const download=downloadCandidate(view);

    if(NATIVE_FILES.has(key)){
      const action=proxyClick(download,'دانلود کانفیگ',true);if(action)row.appendChild(action);
    }else if(key==='snell'&&client?.key==='hiddify'&&download){
      const importUri=hiddifyImportFromDownload(download);
      if(importUri)row.appendChild(link('اتصال به Hiddify',importUri,true));
      const file=proxyClick(download,'دانلود کانفیگ',false);if(file)row.appendChild(file);
    }else{
      if(direct){const action=proxyClick(direct,'اتصال به '+(client?.name||'برنامه'),true);if(action)row.appendChild(action)}
      if(uri){
        row.appendChild(button('کپی لینک اتصال',async()=>{
          notify(await copy(uri)?'لینک اتصال کپی شد ✓':'کپی انجام نشد');
        },false,true));
      }else if(download){
        const action=proxyClick(download,'دانلود کانفیگ',row.children.length===0);if(action)row.appendChild(action);
      }
    }
    while(row.children.length>2)row.lastElementChild?.remove();
    if(row.children.length)view.appendChild(row);
  }

  function buildPanel(panel){
    panel.querySelectorAll('.v34-multi-card,.v34-client-card').forEach(node=>node.remove());
    const key=panelKey(panel);if(!key)return;
    panel.dataset.v34Protocol=key;
    if(MODERN.has(key))panel.dataset.v34Modern='1';else delete panel.dataset.v34Modern;
    explicitFactLabels(panel);
    const client=clientFor(key);const views=[...panel.querySelectorAll('.server-view')];
    views.forEach((view,index)=>{
      view.dataset.v34ServerLabel=serverLabel(panel,view,index);buildServerActions(panel,view,key,client);
    });
    const multi=buildMultiCard(panel,key,views.length,client);buildClientCard(panel,client,multi);
  }

  function apply(){
    const p=platform();document.body.dataset.tpPlatform=p;document.documentElement.dataset.tpPlatform=p;
    document.body.classList.add('v34-ready');document.body.dataset.tpPublicPresentation='v34';
    document.querySelectorAll('.protocol-panel').forEach(buildPanel);
  }

  apply();window.setTimeout(apply,0);window.setTimeout(apply,180);window.setTimeout(apply,650);
})();
</script>
"""


def refine_public_connection_forward_v34(source: str) -> str:
    """Build one device-aware beginner presentation from canonical existing actions."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    source = source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
    return source
