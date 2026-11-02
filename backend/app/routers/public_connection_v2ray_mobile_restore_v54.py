from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_V2RAY_MOBILE_RESTORE_V54"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_V2RAY_MOBILE_RESTORE_V54 */
body.v54-v2ray-restore .protocol-panel[data-v54-v2ray="1"] .server-tabs,
body.v54-v2ray-restore .protocol-panel[data-v54-v2ray="1"] .server-views,
body.v54-v2ray-restore .protocol-panel[data-v54-v2ray="1"] .v51-single-title{
  display:none!important;
}
body.v54-v2ray-restore .protocol-panel[data-v54-v2ray="1"].v54-configs-open .server-tabs{
  display:flex!important;
}
body.v54-v2ray-restore .protocol-panel[data-v54-v2ray="1"].v54-configs-open .server-views{
  display:grid!important;
}
body.v54-v2ray-restore .protocol-panel[data-v54-v2ray="1"].v54-configs-open .v51-single-title{
  display:block!important;
}
body.v54-v2ray-restore .v54-v2ray-config-toggle{
  width:calc(100% - 24px);min-height:42px;margin:0 12px 12px;padding:9px 12px;
  border:1px solid var(--line);border-radius:10px;background:var(--surface2);color:var(--text);
  font:inherit;font-size:12px;font-weight:900;cursor:pointer;
}
@media(max-width:720px){
  body.v54-v2ray-restore .protocol-choice[data-v54-v2ray-choice="1"]{
    display:grid!important;visibility:visible!important;opacity:1!important;
  }
  body.v54-v2ray-restore .protocol-panel[data-v54-v2ray="1"].v54-configs-open .server-tabs{
    display:none!important;
  }
  body.v54-v2ray-restore .protocol-panel[data-v54-v2ray="1"].v54-configs-open .server-views{
    display:grid!important;grid-template-columns:1fr!important;
  }
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectV2rayMobileRestoreV54">
(function(){
  let timer=null;

  function normalize(value){
    const key=String(value||'').trim().toLowerCase();
    return key==='xray'?'v2ray':key;
  }

  function choiceFor(panel){
    if(!panel?.id)return null;
    return [...document.querySelectorAll('.protocol-choice')]
      .find(choice=>String(choice.dataset.protocol||'')===String(panel.id))||null;
  }

  function panelKey(panel){
    const direct=normalize(panel?.dataset?.v34Protocol||panel?.dataset?.modernProtocol||'');
    if(direct)return direct;
    const choice=choiceFor(panel);
    return normalize(choice?.dataset?.protocolKey||choice?.dataset?.protocol||'');
  }

  function ensureToggle(panel){
    const views=panel.querySelector('.server-views');
    if(!views)return;
    let button=panel.querySelector(':scope > .v54-v2ray-config-toggle');
    if(!button){
      button=document.createElement('button');
      button.type='button';
      button.className='v54-v2ray-config-toggle';
      button.textContent='مشاهده اتصال‌های هر سرور';
      button.setAttribute('aria-expanded','false');
      button.addEventListener('click',()=>{
        const open=panel.classList.toggle('v54-configs-open');
        button.textContent=open?'بستن اتصال‌های هر سرور':'مشاهده اتصال‌های هر سرور';
        button.setAttribute('aria-expanded',open?'true':'false');
      });
      const anchor=panel.querySelector(':scope > .v52-multi-card,:scope > .v51-multi-card');
      if(anchor)anchor.insertAdjacentElement('afterend',button);
      else panel.querySelector('.panel-head')?.insertAdjacentElement('afterend',button);
    }
  }

  function apply(){
    document.body.classList.add('v54-v2ray-restore');
    document.querySelectorAll('.protocol-panel').forEach(panel=>{
      if(panelKey(panel)!=='v2ray')return;
      panel.dataset.v54V2ray='1';
      const choice=choiceFor(panel);
      if(choice){
        choice.dataset.v54V2rayChoice='1';
        choice.hidden=false;
        choice.removeAttribute('aria-hidden');
        choice.classList.add('v40-real-protocol');
        choice.dataset.v51Filtered='0';
      }
      if(panel.querySelector('.server-view')){
        panel.classList.add('v24-canonical-panel');
        panel.classList.remove('v24-empty');
      }
      ensureToggle(panel);
    });
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,180);
  window.setTimeout(apply,650);
  window.setTimeout(apply,1500);
  window.addEventListener('resize',()=>{
    clearTimeout(timer);timer=window.setTimeout(apply,180);
  },{passive:true});
})();
</script>
"""


_V41_REMOVE_OLD = "panel.querySelectorAll('.v38-server-list-title,.tp-v41-profile-toggle,.server-views').forEach(node=>node.remove());"
_V41_REMOVE_NEW = "panel.querySelectorAll('.v38-server-list-title,.tp-v41-profile-toggle').forEach(node=>node.remove());"
_V51_MULTI_OLD = "return window.location.origin+'/v1/connect/'+encodeURIComponent(value)+'/multi/'+encodeURIComponent(protocol);"
_V51_MULTI_NEW = "return window.location.origin+'/v1/connect/'+encodeURIComponent(value)+(protocol==='v2ray'?'/sub':'/multi/'+encodeURIComponent(protocol));"


def refine_public_connection_v2ray_mobile_restore_v54(source: str) -> str:
    """Restore V2Ray mobile visibility, preserve hidden per-server profiles, and use /sub for Multi-Link."""
    source = str(source or "")
    source = source.replace(_V41_REMOVE_OLD, _V41_REMOVE_NEW)
    source = source.replace(_V51_MULTI_OLD, _V51_MULTI_NEW)
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
