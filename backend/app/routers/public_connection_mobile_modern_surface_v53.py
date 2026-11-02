from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_MOBILE_MODERN_SURFACE_V53"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_MOBILE_MODERN_SURFACE_V53 */
/* V51's category bar is mobile-only. If the viewport returns to desktop after
   mobile rendering, keep that transient bar hidden so desktop has one category row. */
body.v53-mobile-modern-clean .v51-mobile-categories,
body:not(.v53-mobile-modern-clean) .v51-mobile-categories{
  display:none!important;
}

@media(max-width:720px){
  body.v53-mobile-modern-clean .v51-mobile-categories{
    display:flex!important;
  }

  /* Modern protocols are URI/config driven. Raw generic Server/Username/Password
     fact cards are not valid customer-facing connection instructions for them. */
  body.v53-mobile-modern-clean .protocol-panel[data-v53-modern="1"] .server-view .facts,
  body.v53-mobile-modern-clean .protocol-panel[data-v53-modern="1"] .server-view > .facts,
  body.v53-mobile-modern-clean .protocol-panel[data-v53-modern="1"] .server-view .fact{
    display:none!important;
  }

  /* Keep actual client/config actions and the authoritative V52 Multi-Link. */
  body.v53-mobile-modern-clean .protocol-panel[data-v53-modern="1"] .v52-multi-card,
  body.v53-mobile-modern-clean .protocol-panel[data-v53-modern="1"] .action-buttons,
  body.v53-mobile-modern-clean .protocol-panel[data-v53-modern="1"] .v13-action-buttons,
  body.v53-mobile-modern-clean .protocol-panel[data-v53-modern="1"] .v13-client-only,
  body.v53-mobile-modern-clean .protocol-panel[data-v53-modern="1"] .v13-karing-inline,
  body.v53-mobile-modern-clean .protocol-panel[data-v53-modern="1"] .v13-karing-import{
    display:flex!important;
  }
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectMobileModernSurfaceV53">
(function(){
  const MODERN=new Set([
    'v2ray','hysteria2','tuic','anytls','naive','shadowtls','snell','mieru',
    'trusttunnel','amneziawg','sudoku'
  ]);
  const MOBILE='(max-width:720px)';
  let timer=null;

  function normalize(value){
    const key=String(value||'').trim().toLowerCase();
    if(key==='xray')return'v2ray';
    if(key==='naiveproxy')return'naive';
    return key;
  }

  function panelKey(panel){
    const direct=normalize(panel?.dataset?.v34Protocol||panel?.dataset?.modernProtocol||'');
    if(direct)return direct;
    const choice=[...document.querySelectorAll('.protocol-choice')]
      .find(item=>String(item.dataset.protocol||'')===String(panel?.id||''));
    return normalize(choice?.dataset?.protocolKey||choice?.dataset?.protocol||'');
  }

  function clearMobileCategories(){
    document.querySelectorAll('.v51-mobile-categories').forEach(node=>node.remove());
    document.querySelectorAll('.protocol-choice[data-v51-filtered]').forEach(choice=>{
      delete choice.dataset.v51Filtered;
    });
  }

  function apply(){
    if(!window.matchMedia(MOBILE).matches){
      clearMobileCategories();
      document.body.classList.remove('v53-mobile-modern-clean');
      delete document.body.dataset.tpMobileModernSurface;
      document.querySelectorAll('.protocol-panel[data-v53-modern="1"]').forEach(panel=>delete panel.dataset.v53Modern);
      return;
    }

    document.body.classList.add('v53-mobile-modern-clean');
    document.body.dataset.tpMobileModernSurface='v53';
    document.querySelectorAll('.protocol-panel').forEach(panel=>{
      const modern=MODERN.has(panelKey(panel));
      if(modern)panel.dataset.v53Modern='1';
      else delete panel.dataset.v53Modern;
    });
  }

  function schedule(){
    clearTimeout(timer);
    timer=window.setTimeout(apply,0);
  }

  apply();
  window.setTimeout(apply,120);
  window.setTimeout(apply,500);
  window.setTimeout(apply,1400);
  window.addEventListener('resize',schedule,{passive:true});
  window.addEventListener('pagehide',()=>clearTimeout(timer),{once:true});
})();
</script>
"""


def refine_public_connection_mobile_modern_surface_v53(source: str) -> str:
    """Clean modern mobile protocol sheets and remove transient mobile category UI on desktop."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
