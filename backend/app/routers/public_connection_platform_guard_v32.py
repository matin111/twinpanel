from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_PLATFORM_GUARD_V32"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_PLATFORM_GUARD_V32 */

/* V31 hidden sources must stay hidden even when older mobile rules use a more
 * specific display:* !important selector. V32 is the final presentation guard.
 */
body.v32-ready [data-v31-hide="1"],
body.v32-ready [data-v31-legacy-actions="1"]{
  display:none!important;
}

/* The client selector is an action, not explanatory copy. */
body.v32-ready .v31-client-card>span{
  display:none!important;
}
body.v32-ready .v31-client-card{
  justify-content:flex-end;
}

/* A narrow desktop browser is still desktop. Only Android/iOS may receive the
 * one-column phone action layout. */
@media(max-width:720px){
  body.v32-ready[data-tp-platform="windows"] .v31-client-card,
  body.v32-ready[data-tp-platform="macos"] .v31-client-card,
  body.v32-ready[data-tp-platform="linux"] .v31-client-card{
    margin:10px 12px 12px!important;
    align-items:center!important;
    flex-direction:row!important;
  }
  body.v32-ready[data-tp-platform="windows"] .v31-client-card>a,
  body.v32-ready[data-tp-platform="macos"] .v31-client-card>a,
  body.v32-ready[data-tp-platform="linux"] .v31-client-card>a{
    width:auto!important;
  }
  body.v32-ready[data-tp-platform="windows"] .v31-canonical-actions,
  body.v32-ready[data-tp-platform="macos"] .v31-canonical-actions,
  body.v32-ready[data-tp-platform="linux"] .v31-canonical-actions,
  body.v32-ready[data-tp-platform="windows"] .v30-subscription-card .v30-subscription-actions,
  body.v32-ready[data-tp-platform="macos"] .v30-subscription-card .v30-subscription-actions,
  body.v32-ready[data-tp-platform="linux"] .v30-subscription-card .v30-subscription-actions{
    grid-template-columns:repeat(2,minmax(0,1fr))!important;
  }
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectPlatformGuardV32">
(function(){
  const DESKTOP=new Set(['windows','macos','linux']);
  let observer=null;
  let resizeTimer=null;
  let applyTimer=null;

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

  function hardHide(node){
    if(!node)return;
    node.style.setProperty('display','none','important');
    node.setAttribute('aria-hidden','true');
  }

  function enforceUnifiedAuthority(){
    document.querySelectorAll(
      '[data-v31-hide="1"],[data-v31-legacy-actions="1"],'+
      '.server-view .v13-app,.v13-client-only,.mobile-send-btn,'+
      '.v9-icon-btn.mobile,.tp-win-v2ray-note,.tp-v15-client-note'
    ).forEach(hardHide);

    document.querySelectorAll('.v31-client-card>span').forEach(node=>node.remove());
  }

  function unwrapMobileServerDetails(){
    document.querySelectorAll('details.v30-single-servers').forEach(details=>{
      const views=[...details.children].find(node=>node.classList?.contains('server-views'))||null;
      if(views)details.insertAdjacentElement('beforebegin',views);
      details.remove();
    });
  }

  function restoreDesktopPanel(panel){
    panel.classList.remove(
      'v24-canonical-panel','v24-empty','v24-live-online','v27-active-protocol'
    );
    delete panel.dataset.v24ServerCount;
    panel.querySelectorAll('.server-view').forEach(view=>{
      view.classList.remove('v27-active-server','v29-server-card');
      delete view.dataset.v24ServerLabel;
    });
  }

  function restoreDesktopPresentation(){
    const body=document.body;
    body.classList.remove('v24-ready','v27-mobile-ui');
    delete body.dataset.tpDevicePresentation;
    delete body.dataset.tpMobilePresentation;
    delete body.dataset.tpMobileRefine;
    delete body.dataset.tpCanonicalMobile;
    document.querySelectorAll('.v27-connect-nav,.v28-scroll-hint').forEach(node=>node.remove());
    document.querySelectorAll('.protocol-panel').forEach(restoreDesktopPanel);
    unwrapMobileServerDetails();
  }

  function apply(){
    const body=document.body;
    if(!body)return;
    const platform=detectPlatform();
    body.dataset.tpPlatform=platform;
    document.documentElement.dataset.tpPlatform=platform;
    body.classList.add('v32-ready');
    body.dataset.tpPlatformGuard='v32';

    if(DESKTOP.has(platform))restoreDesktopPresentation();
    enforceUnifiedAuthority();
  }

  function schedule(delay){
    clearTimeout(applyTimer);
    applyTimer=window.setTimeout(apply,delay);
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,260);
  window.setTimeout(apply,720);

  observer=new MutationObserver(()=>schedule(0));
  observer.observe(document.body,{
    childList:true,
    subtree:true,
    attributes:true,
    attributeFilter:['class','data-v31-hide','data-v31-legacy-actions']
  });

  window.addEventListener('resize',()=>{
    clearTimeout(resizeTimer);
    resizeTimer=window.setTimeout(apply,220);
  },{passive:true});

  window.addEventListener('pagehide',()=>{
    observer?.disconnect();
    clearTimeout(applyTimer);
    clearTimeout(resizeTimer);
  },{once:true});
})();
</script>
"""


def refine_public_connection_platform_guard_v32(source: str) -> str:
    """Keep phone presentation phone-only and enforce one action authority for every protocol."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
