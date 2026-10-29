from __future__ import annotations

from .public_connection_mobile_sheet_v42 import refine_public_connection_mobile_sheet_v42


_MARKER = "TWINPANEL_PUBLIC_CONNECT_V2RAY_ACTIONS_V41"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_V2RAY_ACTIONS_V41 */
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .v34-server-actions{
  display:grid!important;
  grid-template-columns:repeat(2,minmax(0,1fr))!important;
  gap:7px!important;
  margin-top:8px!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .v34-server-actions>a,
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .v34-server-actions>button{
  width:100%!important;
  min-height:40px!important;
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectV2rayActionsV41">
(function(){
  let timer=null;

  function normalize(value){
    const key=String(value||'').trim().toLowerCase();
    if(key==='xray')return'v2ray';
    return key;
  }

  function panelKey(panel){
    const direct=normalize(panel?.dataset?.v34Protocol||panel?.dataset?.modernProtocol||'');
    if(direct)return direct;
    const choice=[...document.querySelectorAll('.protocol-choice')]
      .find(item=>String(item.dataset.protocol||'')===String(panel?.id||''));
    return normalize(choice?.dataset?.protocolKey||choice?.dataset?.protocol||panel?.id||'');
  }

  function canonicalRow(view){
    return view.querySelector(':scope > .v34-server-actions');
  }

  function purgeLegacyInteractiveBlocks(view,row){
    [...view.children].forEach(child=>{
      if(child===row)return;
      const interactive=child.matches?.('a,button')||Boolean(child.querySelector?.('a,button'));
      if(interactive)child.remove();
    });

    view.querySelectorAll('a,button').forEach(node=>{
      if(row.contains(node))return;
      node.remove();
    });
  }

  function enforceTwoActions(view){
    const row=canonicalRow(view);
    if(!row)return;

    purgeLegacyInteractiveBlocks(view,row);
    row.removeAttribute('aria-hidden');
    row.removeAttribute('hidden');
    row.style.removeProperty('display');

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

    row.dataset.v41Canonical='1';
  }

  function apply(){
    document.body.classList.add('v41-v2ray-two-actions');
    document.querySelectorAll('.protocol-panel').forEach(panel=>{
      if(panelKey(panel)!=='v2ray')return;
      panel.dataset.v41V2ray='1';
      panel.querySelectorAll('.server-view').forEach(enforceTwoActions);
    });
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,250);
  window.setTimeout(apply,850);
  window.setTimeout(apply,1600);
  window.addEventListener('resize',()=>{
    clearTimeout(timer);
    timer=window.setTimeout(apply,220);
  },{passive:true});
  window.addEventListener('pagehide',()=>clearTimeout(timer),{once:true});
})();
</script>
"""


def refine_public_connection_v2ray_actions_v41(source: str) -> str:
    """Keep exactly Send to Hiddify + Copy Config for V2Ray server cards."""
    if _MARKER not in source:
        source = source.replace("</style>", _CSS + "\n</style>", 1)
        source = source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
    return refine_public_connection_mobile_sheet_v42(source)
