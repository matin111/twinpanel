from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_MULTILINK_PERSISTENCE_V52"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_MULTILINK_PERSISTENCE_V52 */
body.v52-multilink-stable .v52-multi-card{
  margin:12px;
  padding:12px;
  border:1px solid color-mix(in srgb,var(--p) 34%,var(--line));
  border-radius:15px;
  background:linear-gradient(145deg,color-mix(in srgb,var(--p) 7%,var(--surface2)),var(--surface2));
}
body.v52-multilink-stable .v52-multi-card .v51-multi-head{
  display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px;
}
body.v52-multilink-stable .v52-multi-card .v51-multi-title{display:grid;gap:2px}
body.v52-multilink-stable .v52-multi-card .v51-multi-title b{font-size:14px;line-height:1.5}
body.v52-multilink-stable .v52-multi-card .v51-multi-title small,
body.v52-multilink-stable .v52-multi-card .v51-multi-count{color:var(--muted);font-size:10px;font-weight:800}
body.v52-multilink-stable .v52-multi-card .v51-multi-count{padding:4px 8px;border:1px solid var(--line);border-radius:999px;white-space:nowrap}
body.v52-multilink-stable .v52-multi-card .v51-multi-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
body.v52-multilink-stable .v52-multi-card .v51-multi-actions>a,
body.v52-multilink-stable .v52-multi-card .v51-multi-actions>button{
  min-height:42px;padding:9px 11px;display:inline-flex;align-items:center;justify-content:center;
  border:1px solid var(--line);border-radius:10px;background:var(--surface);color:var(--text);
  font:inherit;font-size:12px;font-weight:900;text-align:center;text-decoration:none;cursor:pointer;
}
body.v52-multilink-stable .v52-multi-card .v51-multi-actions .v51-primary{border-color:var(--p);background:var(--p);color:#fff}

/* Legacy/competing V2Ray and old subscription surfaces must never win after V52. */
body.v52-multilink-stable .v30-subscription-card,
body.v52-multilink-stable .v34-subscription-card,
body.v52-multilink-stable .v37-multi-card,
body.v52-multilink-stable .v38-all-card,
body.v52-multilink-stable .v49-v2ray-summary,
body.v52-multilink-stable .v49-v2ray-groups,
body.v52-multilink-stable [data-v44-v2ray-multi="1"]{
  display:none!important;
}

@media(max-width:720px){
  body.v52-multilink-stable .v52-multi-card{margin:10px;padding:11px}
  body.v52-multilink-stable .v52-multi-card .v51-multi-actions{grid-template-columns:1fr}
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectMultilinkPersistenceV52">
(function(){
  const MULTI=new Set([
    'openvpn','wireguard','v2ray','hysteria2','tuic','anytls','naive',
    'shadowtls','snell','socks5','mieru','trusttunnel','amneziawg','sudoku'
  ]);
  let observer=null;
  let cleanupTimer=null;

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

  function stableCard(panel){
    return panel?.querySelector(':scope > .v52-multi-card')||panel?.querySelector('.v52-multi-card')||null;
  }

  function promote(card){
    if(!card||!card.isConnected)return null;
    const panel=card.closest('.protocol-panel');if(!panel)return null;
    const protocol=normalize(card.dataset.v51Protocol||panelKey(panel));
    if(!MULTI.has(protocol))return null;

    const existing=stableCard(panel);
    if(existing&&existing!==card){
      card.remove();
      return existing;
    }

    card.classList.remove('v51-multi-card');
    card.classList.add('v52-multi-card');
    card.dataset.v52Protocol=protocol;
    card.dataset.v52Stable='1';
    panel.dataset.v52Multilink='1';
    return card;
  }

  function retireLegacy(panel){
    if(!panel)return;
    panel.querySelectorAll(
      '.v30-subscription-card,.v34-subscription-card,.v37-multi-card,.v38-all-card,'+
      '.v49-v2ray-summary,.v49-v2ray-groups,[data-v44-v2ray-multi="1"]'
    ).forEach(node=>node.remove());

    const protocol=panelKey(panel);
    if(protocol==='v2ray'){
      panel.querySelectorAll('.v51-single-title').forEach(title=>{
        if(!panel.querySelector('.server-views'))title.remove();
      });
    }
  }

  function reconcilePanel(panel){
    if(!panel)return;
    const protocol=panelKey(panel);if(!MULTI.has(protocol))return;

    const candidates=[...panel.querySelectorAll('.v51-multi-card')];
    const existing=stableCard(panel);
    if(existing){
      candidates.forEach(node=>node.remove());
    }else if(candidates.length){
      promote(candidates[0]);
      candidates.slice(1).forEach(node=>node.remove());
    }
    retireLegacy(panel);
  }

  function reconcileAll(){
    document.body.classList.add('v52-multilink-stable');
    document.body.dataset.tpMultilinkPersistence='v52';
    document.querySelectorAll('.protocol-panel').forEach(reconcilePanel);
  }

  function schedule(){
    clearTimeout(cleanupTimer);
    cleanupTimer=window.setTimeout(reconcileAll,0);
  }

  function observe(){
    if(observer)return;
    observer=new MutationObserver(records=>{
      let relevant=false;
      for(const record of records){
        for(const node of record.addedNodes||[]){
          if(!(node instanceof Element))continue;
          if(node.matches?.('.v51-multi-card,.v30-subscription-card,.v34-subscription-card,.v37-multi-card,.v38-all-card,[data-v44-v2ray-multi="1"]')||
             node.querySelector?.('.v51-multi-card,.v30-subscription-card,.v34-subscription-card,.v37-multi-card,.v38-all-card,[data-v44-v2ray-multi="1"]')){
            relevant=true;break;
          }
        }
        if(relevant)break;
      }
      if(relevant)schedule();
    });
    observer.observe(document.body,{childList:true,subtree:true});
  }

  reconcileAll();
  observe();
  window.setTimeout(reconcileAll,120);
  window.setTimeout(reconcileAll,420);
  window.setTimeout(reconcileAll,1250);
  window.setTimeout(reconcileAll,1800);
  window.addEventListener('resize',schedule,{passive:true});
  window.addEventListener('pagehide',()=>{
    observer?.disconnect();observer=null;clearTimeout(cleanupTimer);
  },{once:true});
})();
</script>
"""


def refine_public_connection_multilink_persistence_v52(source: str) -> str:
    """Promote V51 Multi-Link cards into persistent final DOM authority without refetching delivery data."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
