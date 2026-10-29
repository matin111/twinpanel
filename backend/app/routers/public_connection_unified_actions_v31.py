from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_UNIFIED_ACTIONS_V31"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_UNIFIED_ACTIONS_V31 */

/* V31 is presentation-only: one action vocabulary for every protocol. */
body.v31-ready .tp-v15-client-note,
body.v31-ready .v13-action-copy,
body.v31-ready .action-copy,
body.v31-ready .v13-client-only,
body.v31-ready .server-view .v13-app,
body.v31-ready [data-v31-hide="1"]{
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

body.v31-ready .protocol-panel .v13-action-buttons,
body.v31-ready .protocol-panel .action-buttons,
body.v31-ready .protocol-panel .tp-v48-profile-actions{
  width:100%!important;
  display:grid!important;
  grid-template-columns:repeat(2,minmax(0,1fr))!important;
  gap:8px!important;
}

body.v31-ready .protocol-panel .v13-action-buttons>a,
body.v31-ready .protocol-panel .v13-action-buttons>button,
body.v31-ready .protocol-panel .action-buttons>a,
body.v31-ready .protocol-panel .action-buttons>button,
body.v31-ready .protocol-panel .tp-v48-profile-actions>a,
body.v31-ready .protocol-panel .tp-v48-profile-actions>button{
  min-height:42px!important;
  padding:9px 11px!important;
  display:inline-flex!important;
  align-items:center!important;
  justify-content:center!important;
  border-radius:10px!important;
  font-size:12px!important;
  font-weight:900!important;
  line-height:1.35!important;
  text-align:center!important;
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
  }
  body.v31-ready .protocol-panel .v13-action-buttons,
  body.v31-ready .protocol-panel .action-buttons,
  body.v31-ready .protocol-panel .tp-v48-profile-actions{
    grid-template-columns:1fr!important;
  }
  body.v31-ready .v31-client-card{
    align-items:stretch;
    flex-direction:column;
  }
  body.v31-ready .v31-client-card>a{
    width:100%;
  }
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectUnifiedActionsV31">
(function(){
  const URI_RE=/^(?:vmess|vless|trojan|ss|hysteria2|hy2|tuic|anytls|naive|mieru|snell|sudoku|trusttunnel|wg|wireguard):\/\//i;
  const text=el=>String(el?.textContent||'').trim();

  function platform(){
    return String(document.body?.dataset?.tpPlatform||'unknown').trim().toLowerCase();
  }

  function valueFromTarget(id){
    const el=document.getElementById(String(id||''));
    if(!el)return'';
    return String('value' in el?el.value:el.textContent||'').trim();
  }

  function isUri(value){
    return URI_RE.test(String(value||'').trim());
  }

  function actionPayload(node){
    if(node?.dataset?.copy)return String(node.dataset.copy||'').trim();
    if(node?.dataset?.tpCopyTarget)return valueFromTarget(node.dataset.tpCopyTarget);
    return'';
  }

  function hide(node){
    if(node)node.dataset.v31Hide='1';
  }

  function normalizeServerAction(node){
    if(!node)return;

    if(node.matches('.v15-karing-inline,.v13-karing-import,.v13-karing-inline,.tp-v15-karing-classic')){
      node.textContent='اتصال به Karing';
      // V15 used this hidden target to copy raw config before app launch.
      // V31 keeps the action simple: launch the app only, with no raw-config copy toast.
      node.removeAttribute('data-tp-copy-target');
      return;
    }

    if(node.matches('.v13-open-uri')){
      node.textContent='باز کردن در برنامه';
      return;
    }

    if(node.matches('.v15-standard-link')){
      node.textContent='کپی لینک';
      return;
    }

    if(node.matches('.tp-v15-copy-config,.tp-v15-classic-copy')){
      const payload=actionPayload(node);
      if(isUri(payload))node.textContent='کپی لینک';
      else hide(node); // Raw config copy is intentionally not a beginner-facing action.
      return;
    }

    if(node.matches('.v13-secondary,.download-config,.tp-v16-safe-download')){
      node.textContent='دانلود کانفیگ';
      return;
    }

    if(node.matches('.copy-btn[data-copy]')){
      const payload=actionPayload(node);
      if(isUri(payload))node.textContent='کپی لینک';
      return;
    }
  }

  function dedupeActions(container){
    if(!container)return;
    const seen=new Set();
    [...container.querySelectorAll('a[href],button')].forEach(node=>{
      if(node.dataset.v31Hide==='1')return;
      let key='';
      if(node.tagName==='A')key='href:'+String(node.getAttribute('href')||'');
      else if(node.dataset.tpCopyTarget)key='copy-target:'+String(node.dataset.tpCopyTarget||'');
      else if(node.dataset.copy)key='copy:'+String(node.dataset.copy||'');
      else if(node.dataset.configPath)key='config:'+String(node.dataset.configPath||'');
      if(!key||key.endsWith(':'))return;
      if(seen.has(key))hide(node);
      else seen.add(key);
    });
  }

  function appName(link){
    return text(link).replace(/^دانلود\s+/,'').trim()||'برنامه اتصال';
  }

  function currentClientLink(panel){
    const links=[...panel.querySelectorAll('.v13-app[data-v13-platform]')];
    if(!links.length)return null;
    const p=platform();
    if(p!=='unknown'){
      const exact=links.find(link=>String(link.dataset.v13Platform||'').toLowerCase()===p);
      if(exact)return exact;
    }
    return links[0];
  }

  function protocolClientCard(panel){
    if(panel.querySelector('.v30-subscription-card'))return; // V30 already owns client downloads here.
    if(panel.querySelector('.v31-client-card'))return;
    const source=currentClientLink(panel);
    if(!source)return;

    const card=document.createElement('div');
    card.className='v31-client-card';
    const label=document.createElement('span');
    label.textContent='برنامه اتصال';
    const link=document.createElement('a');
    link.href=source.getAttribute('href')||'#';
    link.target='_blank';
    link.rel='noopener noreferrer';
    link.textContent='دانلود '+appName(source);
    card.append(label,link);

    const head=panel.querySelector('.panel-head');
    if(head)head.insertAdjacentElement('afterend',card);
    else panel.insertAdjacentElement('afterbegin',card);
  }

  function normalizePanel(panel){
    // Build the one protocol-level client download before hiding old per-server client rows.
    protocolClientCard(panel);

    panel.querySelectorAll('.v13-action-buttons a,.v13-action-buttons button,.action-buttons a,.action-buttons button,.tp-v48-profile-actions a,.tp-v48-profile-actions button')
      .forEach(normalizeServerAction);

    panel.querySelectorAll('.v13-action-buttons,.action-buttons,.tp-v48-profile-actions')
      .forEach(dedupeActions);

    // App downloads belong to the protocol, never to every country/server row.
    panel.querySelectorAll('.v13-app,.v13-client-only')
      .forEach(hide);
  }

  function apply(){
    document.body.classList.add('v31-ready');
    document.body.dataset.tpUnifiedActions='v31';
    document.querySelectorAll('.protocol-panel.v24-canonical-panel,.protocol-panel[data-modern-protocol]')
      .forEach(normalizePanel);
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,180);
  window.setTimeout(apply,500);
})();
</script>
"""


def refine_public_connection_unified_actions_v31(source: str) -> str:
    """Unify beginner-facing Public Connect actions without changing delivery data."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
