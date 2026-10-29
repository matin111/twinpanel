from __future__ import annotations

from .public_connection_mobile_sheet_v42 import refine_public_connection_mobile_sheet_v42
from .public_connection_v2ray_multilink_v43 import apply_v2ray_multilink_v43


apply_v2ray_multilink_v43()

_MARKER = "TWINPANEL_PUBLIC_CONNECT_V2RAY_ACTIONS_V41"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_V2RAY_ACTIONS_V41 */
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .v34-client-card{
  display:flex!important;
  visibility:visible!important;
  opacity:1!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .tp-v48-xray-profiles{
  display:grid!important;
  gap:9px!important;
  width:100%!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .tp-v48-xray-profile{
  display:grid!important;
  gap:8px!important;
  width:100%!important;
  padding:10px!important;
  border:1px solid var(--line)!important;
  border-radius:12px!important;
  background:var(--surface2)!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .tp-v48-profile-actions{
  display:grid!important;
  grid-template-columns:repeat(2,minmax(0,1fr))!important;
  gap:7px!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .tp-v48-profile-actions>a,
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .tp-v48-profile-actions>button{
  width:100%!important;
  min-height:40px!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .tp-v48-profile-actions .tp-v48-hiddify{
  border-color:var(--p)!important;
  background:var(--p)!important;
  color:#fff!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .tp-v48-profile-actions .copy-btn{
  color:var(--p)!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .v34-server-actions[data-v41-duplicate="1"],
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] [data-v41-retired-actions="1"]{
  display:none!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .v34-server-actions:not([data-v41-duplicate="1"]){
  display:grid!important;
  grid-template-columns:repeat(2,minmax(0,1fr))!important;
  gap:7px!important;
  margin-top:8px!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .v34-server-actions:not([data-v41-duplicate="1"])>a,
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .v34-server-actions:not([data-v41-duplicate="1"])>button{
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

  function profileRows(view){
    return [...view.querySelectorAll(':scope > .tp-v48-xray-profiles > .tp-v48-xray-profile')];
  }

  function retireDirectLegacyActions(view,row,profiles){
    view.querySelectorAll(
      ':scope > .action-row,'+
      ':scope > .v13-modern-action,'+
      ':scope > .v13-client-only,'+
      ':scope > .v31-canonical-actions'
    ).forEach(node=>{
      if(node===row||profiles.includes(node))return;
      node.dataset.v41RetiredActions='1';
      node.setAttribute('aria-hidden','true');
    });
  }

  function simplifyProfile(profile){
    profile.removeAttribute('data-v40-retired-actions');
    profile.removeAttribute('aria-hidden');
    profile.removeAttribute('hidden');
    profile.style.removeProperty('display');

    const actions=profile.querySelector('.tp-v48-profile-actions');
    if(!actions)return;

    const primary=actions.querySelector('.tp-v48-hiddify');
    const copy=actions.querySelector('.copy-btn[data-copy]');

    [...actions.children].forEach(node=>{
      if(node!==primary&&node!==copy)node.remove();
    });

    if(primary){
      primary.textContent='ارسال به Hiddify';
      primary.setAttribute('aria-label','ارسال این اتصال به Hiddify');
    }
    if(copy){
      copy.textContent='کپی کانفیگ';
      copy.setAttribute('aria-label','کپی کانفیگ این اتصال');
    }

    actions.dataset.v41ProfileActions='1';
  }

  function simplifyCanonicalFallback(view,row){
    if(!row)return;

    row.removeAttribute('data-v41-duplicate');
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
    retireDirectLegacyActions(view,row,[]);
  }

  function preserveClientDownload(panel){
    const card=panel.querySelector('.v34-client-card');
    if(!card)return;
    card.hidden=false;
    card.removeAttribute('aria-hidden');
    card.style.removeProperty('display');
    card.dataset.v41ClientDownload='1';
  }

  function simplifyServer(view){
    const row=canonicalRow(view);
    const profiles=profileRows(view);

    if(profiles.length){
      const wrapper=view.querySelector(':scope > .tp-v48-xray-profiles');
      if(wrapper){
        wrapper.removeAttribute('data-v40-retired-actions');
        wrapper.removeAttribute('aria-hidden');
        wrapper.removeAttribute('hidden');
        wrapper.style.removeProperty('display');
        wrapper.dataset.v41ProfileCount=String(profiles.length);
      }

      profiles.forEach(simplifyProfile);
      retireDirectLegacyActions(view,row,profiles);

      if(row){
        row.dataset.v41Duplicate='1';
        row.setAttribute('aria-hidden','true');
      }
      return;
    }

    simplifyCanonicalFallback(view,row);
  }

  function apply(){
    document.body.classList.add('v41-v2ray-two-actions');
    document.querySelectorAll('.protocol-panel').forEach(panel=>{
      if(panelKey(panel)!=='v2ray')return;
      panel.dataset.v41V2ray='1';
      preserveClientDownload(panel);
      panel.querySelectorAll('.server-view').forEach(simplifyServer);
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
    """Preserve every real Xray profile and keep exactly Hiddify + Copy Config per profile."""
    if _MARKER not in source:
        source = source.replace("</style>", _CSS + "\n</style>", 1)
        source = source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
    return refine_public_connection_mobile_sheet_v42(source)
