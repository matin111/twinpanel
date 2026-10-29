from __future__ import annotations

from .public_connection_mobile_authority_v40 import refine_public_connection_mobile_authority_v40


_MARKER = "TWINPANEL_PUBLIC_CONNECT_MOBILE_SIMPLIFIED_V39"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_MOBILE_SIMPLIFIED_V39 */
@media(max-width:720px){
  body.v39-mobile-simple .protocols{
    display:grid!important;
    grid-template-columns:repeat(2,minmax(0,1fr))!important;
    gap:7px!important;
  }
  body.v39-mobile-simple .protocol-choice.v39-real-protocol{
    display:grid!important;
    visibility:visible!important;
    opacity:1!important;
  }

  body.v39-mobile-simple .protocol-panel[data-v39-v2ray="1"] [data-v39-retired="1"]{
    display:none!important;
  }
  body.v39-mobile-simple .protocol-panel[data-v39-v2ray="1"] .v34-client-card{
    display:flex!important;
  }
  body.v39-mobile-simple .protocol-panel[data-v39-v2ray="1"] .v34-server-actions{
    display:grid!important;
    grid-template-columns:repeat(2,minmax(0,1fr))!important;
    gap:7px!important;
    margin-top:7px!important;
  }
  body.v39-mobile-simple .protocol-panel[data-v39-v2ray="1"] .v34-server-actions>a,
  body.v39-mobile-simple .protocol-panel[data-v39-v2ray="1"] .v34-server-actions>button{
    width:100%!important;
    min-height:40px!important;
  }
}

@media(max-width:390px){
  body.v39-mobile-simple .protocols{
    grid-template-columns:repeat(2,minmax(0,1fr))!important;
  }
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectMobileSimplifiedV39">
(function(){
  const MOBILE='(max-width:720px)';

  function normalize(value){
    const key=String(value||'').trim().toLowerCase();
    if(key==='xray')return'v2ray';
    if(key==='naiveproxy')return'naive';
    if(key==='openconnect'||key==='ocserv'||key==='anyconnect')return'cisco';
    return key;
  }

  function realChoice(choice){
    return choice &&
      !choice.classList.contains('v13-pending') &&
      !choice.classList.contains('tp-v20-hidden-pending') &&
      choice.dataset.v31Hide!=='1';
  }

  function panelKey(panel){
    const direct=normalize(panel?.dataset?.v34Protocol||panel?.dataset?.modernProtocol||'');
    if(direct)return direct;
    const choice=[...document.querySelectorAll('.protocol-choice')]
      .find(item=>String(item.dataset.protocol||'')===String(panel?.id||''));
    return normalize(choice?.dataset?.protocolKey||'');
  }

  function restoreProtocolChoices(){
    const list=document.querySelector('.protocols');
    if(list){
      list.hidden=false;
      list.removeAttribute('aria-hidden');
      list.style.removeProperty('display');
    }
    document.querySelectorAll('.protocol-choice').forEach(choice=>{
      if(!realChoice(choice))return;
      choice.hidden=false;
      choice.removeAttribute('aria-hidden');
      choice.style.removeProperty('display');
      choice.classList.add('v39-real-protocol');
    });
  }

  function retireLegacyServerActions(view,row){
    [...view.children].forEach(node=>{
      if(node===row)return;
      node.dataset.v39Retired='1';
      node.setAttribute('aria-hidden','true');
    });
  }

  function simplifyRow(view){
    const row=view.querySelector(':scope > .v34-server-actions');
    if(!row)return;
    retireLegacyServerActions(view,row);

    const primary=row.querySelector('.v34-primary');
    const copy=row.querySelector('.v34-copy');
    [...row.children].forEach(node=>{
      if(node!==primary&&node!==copy)node.remove();
    });
    if(primary){
      primary.textContent='ارسال به Hiddify';
      primary.setAttribute('aria-label','ارسال کانفیگ به Hiddify');
    }
    if(copy){
      copy.textContent='کپی کانفیگ';
      copy.setAttribute('aria-label','کپی کانفیگ');
    }
  }

  function simplifyMulti(panel){
    const actions=panel.querySelector('.v38-all-actions');
    if(!actions)return;
    const primary=actions.querySelector('.v38-primary');
    const copy=actions.querySelector('.v38-copy');
    [...actions.children].forEach(node=>{
      if(node!==primary&&node!==copy)node.remove();
    });
    if(primary){
      primary.textContent='ارسال به Hiddify';
      primary.setAttribute('aria-label','ارسال همه سرورها به Hiddify');
    }
    if(copy){
      copy.textContent='کپی کانفیگ';
      copy.setAttribute('aria-label','کپی کانفیگ همه سرورها');
    }
  }

  function simplifyV2ray(){
    document.querySelectorAll('.protocol-panel').forEach(panel=>{
      if(panelKey(panel)!=='v2ray')return;
      panel.dataset.v39V2ray='1';
      panel.querySelectorAll('.server-view').forEach(simplifyRow);
      simplifyMulti(panel);
    });
  }

  function apply(){
    if(!window.matchMedia(MOBILE).matches)return;
    document.body.classList.add('v39-mobile-simple');
    document.body.dataset.tpMobileSimple='v39';
    restoreProtocolChoices();
    simplifyV2ray();
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,260);
  window.setTimeout(apply,850);
})();
</script>
"""


def refine_public_connection_mobile_simplified_v39(source: str) -> str:
    """Show every real mobile protocol and keep only the two canonical V2Ray actions."""
    if _MARKER not in source:
        source = source.replace("</style>", _CSS + "\n</style>", 1)
        source = source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
    return refine_public_connection_mobile_authority_v40(source)
