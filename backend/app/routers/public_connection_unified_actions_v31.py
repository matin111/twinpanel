from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_UNIFIED_ACTIONS_V31"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_UNIFIED_ACTIONS_V31 */

/*
 * V31 is the final beginner-facing action authority.
 * Older renderers remain as hidden data/action sources only; customers see one
 * device-aware client card and one compact semantic action row per server.
 */
body.v31-ready .tp-v15-client-note,
body.v31-ready .v13-action-copy,
body.v31-ready .action-copy,
body.v31-ready .v13-client-only,
body.v31-ready .server-view .v13-app,
body.v31-ready .mobile-send-btn,
body.v31-ready .v9-icon-btn.mobile,
body.v31-ready .tp-win-v2ray-note,
body.v31-ready [data-v31-hide="1"],
body.v31-ready [data-v31-legacy-actions="1"]{
  display:none!important;
}

body.v31-ready .v31-client-card{
  margin:10px 12px 12px;
  padding:11px 12px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  border:1px solid var(--line);
  border-radius:12px;
  background:var(--surface2);
}
body.v31-ready .v31-client-card>span{
  color:var(--muted);
  font-size:12px;
  font-weight:800;
}
body.v31-ready .v31-client-card>a{
  min-height:38px;
  padding:8px 12px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  border:1px solid var(--line);
  border-radius:10px;
  background:var(--surface);
  color:var(--text);
  font-size:12px;
  font-weight:900;
  text-decoration:none;
  white-space:nowrap;
}

body.v31-ready .v31-canonical-actions{
  width:100%;
  margin-top:8px;
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:8px;
}
body.v31-ready .v31-canonical-actions>a,
body.v31-ready .v31-canonical-actions>button{
  min-height:42px!important;
  padding:9px 11px!important;
  display:inline-flex!important;
  align-items:center!important;
  justify-content:center!important;
  border:1px solid var(--line)!important;
  border-radius:10px!important;
  background:var(--surface)!important;
  color:var(--text)!important;
  font:inherit!important;
  font-size:12px!important;
  font-weight:900!important;
  line-height:1.35!important;
  text-align:center!important;
  text-decoration:none!important;
  cursor:pointer!important;
}
body.v31-ready .v31-canonical-actions>.v31-primary{
  border-color:var(--p)!important;
  background:var(--p)!important;
  color:#fff!important;
}
body.v31-ready .v31-canonical-actions>.v31-copy{
  color:var(--p)!important;
}

/* V30 owns the subscription itself; V31 owns which client is shown. */
body.v31-ready .v30-subscription-card .v30-client-downloads{
  display:none!important;
}
body.v31-ready .v30-subscription-card .v30-subscription-actions{
  grid-template-columns:repeat(2,minmax(0,1fr))!important;
}

/* No tutorial/helper copy inside connection cards. */
body.v31-ready .protocol-panel .v13-modern-action>p,
body.v31-ready .protocol-panel .v13-modern-action>small,
body.v31-ready .protocol-panel .v13-client-only>span,
body.v31-ready .protocol-panel .tp-win-v2ray-note{
  display:none!important;
}

@media(max-width:720px){
  body.v31-ready .v31-client-card{
    margin:8px 10px 10px;
    align-items:stretch;
    flex-direction:column;
  }
  body.v31-ready .v31-client-card>a{
    width:100%;
  }
  body.v31-ready .v31-canonical-actions{
    grid-template-columns:1fr!important;
  }
  body.v31-ready .v30-subscription-card .v30-subscription-actions{
    grid-template-columns:1fr!important;
  }
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectUnifiedActionsV31">
(function(){
  const URI_RE=/^(?:vmess|vless|trojan|ss|hysteria2|hy2|tuic|anytls|naive|mieru|snell|sudoku|trusttunnel|wg|wireguard):\/\//i;
  const APP_SCHEME_RE=/^(?:karing|hiddify|trusttunnel|sudoku|sing-box|amneziawg):\/\//i;
  const text=el=>String(el?.textContent||'').trim();

  function detectPlatform(){
    const current=String(document.body?.dataset?.tpPlatform||'').trim().toLowerCase();
    if(['windows','android','ios','macos','linux'].includes(current))return current;
    const uaData=navigator.userAgentData||null;
    const ua=String(navigator.userAgent||'');
    const navPlatform=String((uaData&&uaData.platform)||navigator.platform||'');
    const haystack=(ua+' '+navPlatform).toLowerCase();
    if(/android/i.test(ua))return'android';
    if(/iphone|ipad|ipod/i.test(ua))return'ios';
    if(/macintosh|mac os|macintel/i.test(haystack)&&Number(navigator.maxTouchPoints||0)>1)return'ios';
    if(/windows|win32|win64|winarm/i.test(haystack))return'windows';
    if(/macintosh|mac os|macintel/i.test(haystack))return'macos';
    if(/linux|x11|cros/i.test(haystack))return'linux';
    return'unknown';
  }

  function platform(){
    const value=detectPlatform();
    document.body.dataset.tpPlatform=value;
    document.documentElement.dataset.tpPlatform=value;
    return value;
  }

  function valueFromTarget(id){
    const el=document.getElementById(String(id||''));
    if(!el)return'';
    return String('value' in el?el.value:el.textContent||'').trim();
  }

  function actionPayload(node){
    if(node?.dataset?.copy)return String(node.dataset.copy||'').trim();
    if(node?.dataset?.tpCopyTarget)return valueFromTarget(node.dataset.tpCopyTarget);
    return'';
  }

  function isUri(value){
    return URI_RE.test(String(value||'').trim());
  }

  function fallbackCopy(value){
    const area=document.createElement('textarea');
    area.value=String(value||'');
    area.setAttribute('readonly','');
    area.style.position='fixed';
    area.style.left='-9999px';
    area.style.top='0';
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
    const target=String(value||'').trim();
    if(!target)return false;
    if(navigator.clipboard&&window.isSecureContext){
      try{await navigator.clipboard.writeText(target);return true}catch(_error){}
    }
    return fallbackCopy(target);
  }

  function notify(message){
    const toast=document.getElementById('toast');
    if(!toast)return;
    toast.textContent=message;
    toast.classList.add('show');
    clearTimeout(window.__tpV31Toast);
    window.__tpV31Toast=setTimeout(()=>toast.classList.remove('show'),1800);
  }

  function hide(node){
    if(node)node.dataset.v31Hide='1';
  }

  function appName(link){
    return text(link).replace(/^دانلود\s+/,'').trim()||'برنامه اتصال';
  }

  function currentClientLink(panel){
    const links=[...panel.querySelectorAll('.v13-app[data-v13-platform]')];
    if(!links.length)return null;
    const p=platform();
    if(p==='unknown')return null;
    return links.find(link=>String(link.dataset.v13Platform||'').toLowerCase()===p)||null;
  }

  function preferredClient(panel){
    const link=currentClientLink(panel);
    if(!link)return null;
    const name=appName(link);
    return {link,name,key:name.toLowerCase()};
  }

  function protocolClientCard(panel){
    const existing=panel.querySelector('.v31-client-card');
    const source=currentClientLink(panel);
    if(!source){
      existing?.remove();
      return;
    }

    const name=appName(source);
    const href=source.getAttribute('href')||'';
    if(existing){
      const link=existing.querySelector('a');
      if(link){
        link.href=href;
        link.textContent='دانلود '+name;
      }
      return;
    }

    const card=document.createElement('div');
    card.className='v31-client-card';
    const label=document.createElement('span');
    label.textContent='برنامه مناسب دستگاه شما';
    const link=document.createElement('a');
    link.href=href;
    link.target='_blank';
    link.rel='noopener noreferrer';
    link.textContent='دانلود '+name;
    card.append(label,link);

    const subscription=panel.querySelector('.v30-subscription-card');
    if(subscription)subscription.insertAdjacentElement('afterend',card);
    else{
      const head=panel.querySelector('.panel-head');
      if(head)head.insertAdjacentElement('afterend',card);
      else panel.insertAdjacentElement('afterbegin',card);
    }
  }

  function normalizeAppKey(value){
    return String(value||'').toLowerCase().replace(/[^a-z0-9]+/g,'');
  }

  function directScore(node,preferred){
    if(!node)return-1;
    const href=String(node.getAttribute?.('href')||'').trim();
    const label=text(node).toLowerCase();
    const key=normalizeAppKey((preferred&&preferred.key)||'');
    let score=0;
    if(node.matches?.('.tp-win-hiddify,.v15-karing-inline,.v13-karing-inline,.tp-v15-karing-classic'))score+=20;
    if(node.matches?.('.v13-open-uri'))score+=10;
    if(href&&APP_SCHEME_RE.test(href))score+=15;
    if(href&&isUri(href))score+=8;
    if(key){
      const haystack=normalizeAppKey(label+' '+href);
      if(key.includes('hiddify')&&haystack.includes('hiddify'))score+=100;
      else if(key.includes('karing')&&haystack.includes('karing'))score+=100;
      else if(key.includes('trusttunnel')&&haystack.includes('trusttunnel'))score+=100;
      else if(key.includes('amnezia')&&haystack.includes('amnezia'))score+=100;
      else if(key.includes('sudoku')&&haystack.includes('sudoku'))score+=100;
      else if(key.includes('singbox')&&haystack.includes('singbox'))score+=100;
    }
    return score;
  }

  function candidateControls(scope){
    return [...scope.querySelectorAll(
      '.v13-action-buttons a,.v13-action-buttons button,'+
      '.action-buttons a,.action-buttons button,'+
      '.tp-v48-profile-actions a,.tp-v48-profile-actions button'
    )].filter(node=>!node.closest('.v31-canonical-actions'));
  }

  function configHref(node){
    if(!node)return'';
    const href=String(node.getAttribute?.('href')||'').trim();
    if(href&&!/^(?:karing|hiddify):\/\//i.test(href)&&!isUri(href))return href;
    const target=String(node.dataset?.target||node.dataset?.configPath||'').trim();
    return target;
  }

  function cleanAnchor(href,label,primary){
    const link=document.createElement('a');
    link.href=href;
    link.textContent=label;
    if(primary)link.classList.add('v31-primary');
    if(/^https?:\/\//i.test(href)){
      link.target='_blank';
      link.rel='noopener noreferrer';
    }
    return link;
  }

  function cleanCopyButton(value){
    const button=document.createElement('button');
    button.type='button';
    button.className='v31-copy';
    button.textContent='کپی لینک اتصال';
    button.addEventListener('click',async()=>{
      notify(await copy(value)?'لینک اتصال کپی شد ✓':'کپی انجام نشد');
    });
    return button;
  }

  function cleanLegacyContainers(scope){
    scope.querySelectorAll('.v13-action-buttons,.action-buttons,.tp-v48-profile-actions')
      .forEach(container=>container.dataset.v31LegacyActions='1');
    scope.querySelectorAll('.mobile-send-btn,.v9-icon-btn.mobile,.tp-win-v2ray-note,.tp-v15-client-note')
      .forEach(hide);
  }

  function canonicalServerActions(panel,scope){
    scope.querySelectorAll('.v31-canonical-actions').forEach(node=>node.remove());
    const controls=candidateControls(scope);
    if(!controls.length)return;

    const preferred=preferredClient(panel);
    const directCandidates=controls.filter(node=>{
      if(node.matches('.v13-app,.v13-client-only *,.mobile-send-btn'))return false;
      const href=String(node.getAttribute?.('href')||'').trim();
      return Boolean(
        node.matches('.v15-karing-inline,.v13-karing-inline,.tp-v15-karing-classic,.tp-win-hiddify,.v13-open-uri')||
        APP_SCHEME_RE.test(href)||isUri(href)
      );
    });
    directCandidates.sort((a,b)=>directScore(b,preferred)-directScore(a,preferred));
    const direct=directCandidates[0]||null;

    let uri='';
    for(const node of controls){
      const payload=actionPayload(node);
      if(isUri(payload)){uri=payload;break;}
    }
    if(!uri&&direct){
      const href=String(direct.getAttribute?.('href')||'').trim();
      if(isUri(href))uri=href;
    }

    let download='';
    for(const node of controls){
      if(!node.matches('.v13-secondary,.download-config,.tp-v16-safe-download'))continue;
      const href=configHref(node);
      if(href){download=href;break;}
    }

    const row=document.createElement('div');
    row.className='v31-canonical-actions';

    if(direct){
      const href=String(direct.getAttribute?.('href')||'').trim();
      if(href){
        const name=(preferred&&preferred.name)||'برنامه';
        row.appendChild(cleanAnchor(href,'اتصال به '+name,true));
      }else{
        direct.textContent='اتصال به '+((preferred&&preferred.name)||'برنامه');
        direct.classList.add('v31-primary');
        direct.removeAttribute('data-tp-copy-target');
        row.appendChild(direct);
      }
    }

    if(uri){
      row.appendChild(cleanCopyButton(uri));
    }else if(download){
      row.appendChild(cleanAnchor(download,'دانلود کانفیگ',false));
    }

    cleanLegacyContainers(scope);
    if(row.children.length)scope.appendChild(row);
  }

  function serverScopes(panel){
    const views=[...panel.querySelectorAll('.server-view')];
    if(views.length)return views;
    const rows=[...panel.querySelectorAll('.action-row')].filter(row=>!row.closest('.server-view'));
    if(rows.length)return rows;
    const modern=[...panel.querySelectorAll('.v13-modern-action')];
    return modern;
  }

  function subscriptionUrl(card){
    const primary=card?.querySelector('.v30-karing-all[href]');
    if(!primary)return'';
    try{
      return String(new URL(primary.getAttribute('href')).searchParams.get('url')||'').trim();
    }catch(_error){return'';}
  }

  function normalizeSubscriptionCard(panel){
    const card=panel.querySelector('.v30-subscription-card');
    if(!card)return;
    card.querySelector('.v30-client-downloads')?.setAttribute('data-v31-hide','1');

    const preferred=preferredClient(panel);
    const primary=card.querySelector('.v30-karing-all[href]');
    const url=subscriptionUrl(card);
    if(!primary||!url||!preferred)return;

    const key=preferred.key;
    if(key.includes('hiddify')){
      primary.href='hiddify://import/'+encodeURI(url)+'#TwinPanel';
      primary.textContent='افزودن همه به Hiddify';
    }else if(key.includes('karing')){
      primary.textContent='افزودن همه به Karing';
    }
  }

  function primeSubscriptionPanels(){
    // V30 originally targeted V24's mobile-only marker. Marking the real
    // protocol panels here lets the already-shipped V30 subscription renderer
    // build the same canonical "all servers" card on desktop as well.
    document.querySelectorAll('.protocol-panel').forEach(panel=>{
      panel.classList.add('v24-canonical-panel');
    });
  }

  function normalizePanel(panel){
    protocolClientCard(panel);
    normalizeSubscriptionCard(panel);
    serverScopes(panel).forEach(scope=>canonicalServerActions(panel,scope));
    panel.querySelectorAll('.v13-app,.v13-client-only,.mobile-send-btn,.v9-icon-btn.mobile')
      .forEach(hide);
  }

  function apply(){
    platform();
    primeSubscriptionPanels();
    document.body.classList.add('v31-ready');
    document.body.dataset.tpUnifiedActions='v31';
    document.querySelectorAll('.protocol-panel').forEach(normalizePanel);
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,220);
  window.setTimeout(apply,560);
  window.addEventListener('resize',()=>window.setTimeout(apply,80),{passive:true});
})();
</script>
"""


def refine_public_connection_unified_actions_v31(source: str) -> str:
    """Expose one device-aware beginner action surface without changing delivery data."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
