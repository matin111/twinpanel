from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_CANONICAL_PRESENTATION_V24"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_CANONICAL_PRESENTATION_V24 */
@media(max-width:720px){
  /* Canonical protocol panels/server views are the only mobile data authority. */
  body.v24-ready .v9-mobile-stack,
  body.v24-ready .v17-mobile-stack,
  body.v24-ready .protocol-toolbar,
  body.v24-ready .protocols,
  body.v24-ready .multi-link-card,
  body.v24-ready .smart-card{
    display:none!important;
  }

  body.v24-ready .protocol-panel{
    display:none!important;
  }

  body.v24-ready .protocol-panel.v24-canonical-panel{
    display:block!important;
    margin:12px 0 0;
    overflow:hidden;
    border:1px solid var(--line);
    border-radius:16px;
    background:var(--surface);
    box-shadow:0 8px 24px rgba(0,0,0,.07);
  }

  body.v24-ready .protocol-panel.v24-live-online{
    border-color:color-mix(in srgb,var(--ok) 72%,var(--line));
    box-shadow:
      0 0 0 1px color-mix(in srgb,var(--ok) 18%,transparent),
      0 8px 24px rgba(0,0,0,.07);
  }

  body.v24-ready .protocol-panel.v24-live-online .panel-head h3{
    color:var(--ok);
  }

  body.v24-ready .protocol-panel.v24-live-online .panel-head:after{
    content:'آنلاین';
    min-height:30px;
    padding:0 10px;
    display:inline-flex;
    align-items:center;
    justify-content:center;
    border:1px solid color-mix(in srgb,var(--ok) 44%,var(--line));
    border-radius:999px;
    background:color-mix(in srgb,var(--ok) 9%,var(--surface));
    color:var(--ok);
    font-size:12px;
    font-weight:900;
    white-space:nowrap;
  }

  body.v24-ready .section-head p,
  body.v24-ready .section-head small,
  body.v24-ready .apps-head,
  body.v24-ready .platform-title,
  body.v24-ready .app-card small,
  body.v24-ready .protocol-panel .panel-head>div:first-child>span,
  body.v24-ready .protocol-panel .action-copy,
  body.v24-ready .protocol-panel .v13-action-copy,
  body.v24-ready .protocol-panel .v13-client-only>span,
  body.v24-ready .protocol-panel .v13-native-client,
  body.v24-ready .protocol-panel .v13-pending-body,
  body.v24-ready .protocol-panel .v13-pending-apps{
    display:none!important;
  }

  body.v24-ready .protocol-panel .panel-head{
    min-height:58px;
    padding:12px 14px;
    gap:10px;
  }

  body.v24-ready .protocol-panel .panel-head h3{
    margin:0;
    font-size:16px!important;
    line-height:1.45;
  }

  body.v24-ready .protocol-panel .server-tabs{
    display:none!important;
  }

  body.v24-ready .protocol-panel .server-views{
    display:flex!important;
    flex-direction:column;
    gap:10px;
    padding:10px!important;
  }

  body.v24-ready .protocol-panel .server-view{
    display:block!important;
    position:relative;
    margin:0!important;
    padding:44px 10px 10px!important;
    border:1px solid var(--line);
    border-radius:13px;
    background:var(--surface2);
  }

  body.v24-ready .protocol-panel .server-view:before{
    content:attr(data-v24-server-label);
    position:absolute;
    top:10px;
    right:10px;
    left:10px;
    min-height:26px;
    display:flex;
    align-items:center;
    color:var(--text);
    font-size:13px;
    font-weight:900;
    line-height:1.4;
    pointer-events:none;
  }

  body.v24-ready .protocol-panel .server-view>.facts{
    display:grid!important;
  }

  body.v24-ready .protocol-panel .fact small,
  body.v24-ready .protocol-panel .fact span{
    font-size:12px!important;
    line-height:1.7!important;
  }

  body.v24-ready .protocol-panel .fact strong{
    font-size:13px!important;
    line-height:1.65!important;
  }

  body.v24-ready .protocol-panel .action-row,
  body.v24-ready .protocol-panel .v13-modern-action,
  body.v24-ready .protocol-panel .v13-client-only{
    margin:8px 0!important;
    padding:10px!important;
    gap:9px!important;
    border-radius:11px!important;
  }

  body.v24-ready .protocol-panel .action-buttons,
  body.v24-ready .protocol-panel .v13-action-buttons,
  body.v24-ready .protocol-panel .v13-client-only>div{
    width:100%;
    display:flex;
    flex-wrap:wrap;
    gap:8px!important;
  }

  body.v24-ready .protocol-panel .copy-btn,
  body.v24-ready .protocol-panel .primary-btn,
  body.v24-ready .protocol-panel .download-config,
  body.v24-ready .protocol-panel .v13-secondary,
  body.v24-ready .protocol-panel .v13-app,
  body.v24-ready .protocol-panel button,
  body.v24-ready .protocol-panel a{
    min-height:40px;
    padding:9px 12px!important;
    align-items:center;
    justify-content:center;
    border-radius:10px;
    font-size:12px!important;
    line-height:1.4;
  }

  body.v24-ready .apps{
    margin-top:12px;
  }

  body.v24-ready .platforms{
    padding:10px!important;
  }

  body.v24-ready .app-grid{
    display:grid!important;
    grid-template-columns:repeat(2,minmax(0,1fr));
    gap:8px!important;
    overflow:visible!important;
  }

  body.v24-ready .app-card{
    min-height:48px!important;
    padding:9px 10px!important;
    display:flex!important;
    align-items:center!important;
    gap:8px!important;
    border-radius:11px!important;
  }

  body.v24-ready .app-card b{
    font-size:12px!important;
    line-height:1.4!important;
  }

  /* Device detection changes app visibility only; connection facts/actions stay canonical. */
  body[data-tp-platform="android"].v24-ready .v13-app:not([data-v13-platform="android"]),
  body[data-tp-platform="ios"].v24-ready .v13-app:not([data-v13-platform="ios"]),
  body[data-tp-platform="windows"].v24-ready .v13-app:not([data-v13-platform="windows"]),
  body[data-tp-platform="macos"].v24-ready .v13-app:not([data-v13-platform="macos"]),
  body[data-tp-platform="linux"].v24-ready .v13-app:not([data-v13-platform="linux"]){
    display:none!important;
  }

  body[data-tp-platform="android"].v24-ready .v13-app[data-v13-platform="android"],
  body[data-tp-platform="ios"].v24-ready .v13-app[data-v13-platform="ios"],
  body[data-tp-platform="windows"].v24-ready .v13-app[data-v13-platform="windows"],
  body[data-tp-platform="macos"].v24-ready .v13-app[data-v13-platform="macos"],
  body[data-tp-platform="linux"].v24-ready .v13-app[data-v13-platform="linux"],
  body[data-tp-platform="unknown"].v24-ready .v13-app{
    display:inline-flex!important;
  }

  body.v24-ready .v13-pending-panel,
  body.v24-ready .protocol-panel.v24-empty{
    display:none!important;
  }
}

@media(max-width:430px){
  body.v24-ready .app-grid{
    grid-template-columns:1fr!important;
  }
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectCanonicalPresentationV24">
(function(){
  const MOBILE='(max-width:720px)';
  let liveObserver=null;
  let legacyObserver=null;
  let resizeTimer=null;

  const DIRECT_APPS={
    android:{
      'OpenVPN Connect':['OpenVPN Connect','https://play.google.com/store/apps/details?id=net.openvpn.openvpn'],
      'WireGuard':['WireGuard','https://download.wireguard.com/android-client/com.wireguard.android-1.0.20260315.apk'],
      'Hiddify':['Hiddify','https://github.com/hiddify/hiddify-app/releases/latest/download/Hiddify-Android-universal.apk'],
      'Karing':['Karing','https://github.com/KaringX/karing/releases/download/v1.2.25.2802/karing_1.2.25.2802_android_arm.apk'],
      'OpenConnect':['Cisco Secure Client','https://play.google.com/store/apps/details?id=com.cisco.anyconnect.vpn.android.avf'],
      'Cisco Secure Client':['Cisco Secure Client','https://play.google.com/store/apps/details?id=com.cisco.anyconnect.vpn.android.avf'],
      'sing-box':['sing-box','https://github.com/SagerNet/sing-box/releases/download/v1.14.4/SFA-1.14.4-arm64-v8a.apk'],
      'sing-box Desktop':['sing-box','https://github.com/SagerNet/sing-box/releases/download/v1.14.4/SFA-1.14.4-arm64-v8a.apk'],
      'AmneziaWG':['AmneziaWG','https://github.com/amnezia-vpn/amneziawg-android/releases/download/v3.1.20260814/AmneziaWG-3.1.202060814.apk'],
      'TrustTunnel':['TrustTunnel','https://play.google.com/store/apps/details?id=com.adguard.trusttunnel'],
      'TrustTunnel GUI':['TrustTunnel','https://play.google.com/store/apps/details?id=com.adguard.trusttunnel'],
      'Sudodroid':['Sudodroid','https://github.com/SUDOKU-ASCII/sudoku-android/releases/download/v0.3.3/sudodroid-v0.3.3-universal.apk']
    },
    ios:{
      'OpenVPN Connect':['OpenVPN Connect','https://apps.apple.com/us/app/openvpn-connect/id590379981'],
      'WireGuard':['WireGuard','https://apps.apple.com/us/app/wireguard/id1451685025'],
      'Hiddify':['Hiddify','https://github.com/hiddify/hiddify-app/releases/latest/download/Hiddify-iOS.ipa'],
      'Karing':['Karing','https://apps.apple.com/us/app/karing/id6472431552'],
      'OpenConnect':['Cisco Secure Client','https://apps.apple.com/us/app/cisco-secure-client/id1135064690'],
      'Cisco Secure Client':['Cisco Secure Client','https://apps.apple.com/us/app/cisco-secure-client/id1135064690'],
      'sing-box':['sing-box MT','https://apps.apple.com/us/app/sing-box-mt/id6785326793'],
      'sing-box Desktop':['sing-box MT','https://apps.apple.com/us/app/sing-box-mt/id6785326793'],
      'AmneziaWG':['AmneziaWG','https://apps.apple.com/app/amneziawg/id6478942365'],
      'TrustTunnel':['TrustTunnel','https://apps.apple.com/us/app/trusttunnel/id6755807890'],
      'TrustTunnel GUI':['TrustTunnel','https://apps.apple.com/us/app/trusttunnel/id6755807890'],
      'Anywhere Proxy':['Anywhere Proxy','https://apps.apple.com/us/app/anywhere-proxy/id6758235178']
    }
  };

  function text(el){return String(el?.textContent||'').trim()}

  function choiceFor(panel){
    if(!panel?.id)return null;
    return [...document.querySelectorAll('.protocol-choice')]
      .find(choice=>String(choice.dataset.protocol||'')===panel.id)||null;
  }

  function serverLabel(panel,index){
    const tabs=[...panel.querySelectorAll('.server-tab')];
    return text(tabs[index])||('سرور '+(index+1));
  }

  function syncLive(){
    document.querySelectorAll('.protocol-panel.v24-canonical-panel').forEach(panel=>{
      const choice=choiceFor(panel);
      panel.classList.toggle('v24-live-online',Boolean(choice?.classList.contains('live-online')));
    });
  }

  function bindLive(){
    liveObserver?.disconnect();
    const choices=[...document.querySelectorAll('.protocol-choice')];
    liveObserver=new MutationObserver(syncLive);
    choices.forEach(choice=>liveObserver.observe(choice,{attributes:true,attributeFilter:['class']}));
    syncLive();
  }

  function normalizeAppName(value){
    return String(value||'').replace(/^دانلود\s+/,'').trim();
  }

  function applyDirectApp(link,platform){
    const rows=DIRECT_APPS[platform]||{};
    const current=normalizeAppName(link.textContent);
    const target=rows[current];
    if(!target)return;
    link.textContent=target[0];
    link.href=target[1];
    link.target='_blank';
    link.rel='noopener noreferrer';
    link.dataset.v24DirectInstall='1';
  }

  function syncApps(){
    const platform=String(document.body.dataset.tpPlatform||'unknown').toLowerCase();
    document.querySelectorAll('.v13-app[data-v13-platform]').forEach(link=>{
      const target=String(link.dataset.v13Platform||'').toLowerCase();
      link.style.display=(platform==='unknown'||target===platform)?'inline-flex':'none';
      if(platform!=='unknown'&&target===platform)applyDirectApp(link,platform);
    });

    document.querySelectorAll('.platform-group[data-platform]').forEach(group=>{
      const target=String(group.dataset.platform||'').toLowerCase();
      group.style.display=(platform==='unknown'||target===platform)?'block':'none';
      if(platform==='unknown'||target!==platform)return;
      group.querySelectorAll('.app-card').forEach(card=>{
        const name=text(card.querySelector('b'));
        const mapped=(DIRECT_APPS[platform]||{})[name];
        if(!mapped)return;
        card.href=mapped[1];
        card.target='_blank';
        card.rel='noopener noreferrer';
        const title=card.querySelector('b');
        if(title)title.textContent=mapped[0];
        card.dataset.v24DirectInstall='1';
      });
    });
  }

  function retireLegacyMobile(){
    const body=document.body;
    body.classList.remove('v9-ready','v17-ready');
    document.querySelectorAll('.v9-mobile-stack,.v17-mobile-stack').forEach(node=>node.remove());
  }

  function bindLegacyGuard(){
    legacyObserver?.disconnect();
    legacyObserver=new MutationObserver(()=>{
      retireLegacyMobile();
      syncApps();
    });
    legacyObserver.observe(document.body,{attributes:true,attributeFilter:['class'],childList:true,subtree:true});
    retireLegacyMobile();
  }

  function activateMobile(){
    const body=document.body;
    document.querySelectorAll('.protocol-panel').forEach(panel=>{
      const views=[...panel.querySelectorAll('.server-view')];
      const hasRealServer=views.length>0;
      panel.classList.toggle('v24-canonical-panel',hasRealServer);
      panel.classList.toggle('v24-empty',!hasRealServer);
      if(!hasRealServer)return;

      panel.dataset.v24ServerCount=String(views.length);
      views.forEach((view,index)=>{
        view.dataset.v24ServerLabel=serverLabel(panel,index);
      });
    });

    body.classList.add('v24-ready');
    body.dataset.tpDevicePresentation='v24';
    syncApps();
    bindLive();
    bindLegacyGuard();
  }

  function deactivateMobile(){
    liveObserver?.disconnect();
    liveObserver=null;
    legacyObserver?.disconnect();
    legacyObserver=null;
    document.body.classList.remove('v24-ready');
    document.querySelectorAll('.protocol-panel').forEach(panel=>{
      panel.classList.remove('v24-canonical-panel','v24-empty','v24-live-online');
      delete panel.dataset.v24ServerCount;
      panel.querySelectorAll('.server-view').forEach(view=>delete view.dataset.v24ServerLabel);
    });
  }

  function apply(){
    if(window.matchMedia(MOBILE).matches)activateMobile();
    else deactivateMobile();
  }

  function schedule(){
    clearTimeout(resizeTimer);
    resizeTimer=window.setTimeout(apply,40);
  }

  window.setTimeout(apply,0);
  window.setTimeout(()=>{
    if(window.matchMedia(MOBILE).matches){
      retireLegacyMobile();
      syncApps();
    }
  },120);
  window.addEventListener('resize',schedule,{passive:true});
  window.addEventListener('pagehide',()=>{
    liveObserver?.disconnect();
    legacyObserver?.disconnect();
  },{once:true});
})();
</script>
"""


def refine_public_connection_canonical_presentation_v24(source: str) -> str:
    """Present one canonical connection dataset with a minimal device-specific mobile shell."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
