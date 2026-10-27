from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_CANONICAL_PRESENTATION_V24"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_CANONICAL_PRESENTATION_V24 */
@media(max-width:720px){
  /* Presentation only: canonical protocol panels/server views remain the sole data authority. */
  body.v24-ready .v9-mobile-stack,
  body.v24-ready .v17-mobile-stack{
    display:none!important;
  }

  body.v24-ready .protocol-toolbar,
  body.v24-ready .protocols{
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

  body.v24-ready .protocol-panel .panel-head{
    min-height:58px;
    padding:12px 14px;
    gap:10px;
  }

  body.v24-ready .protocol-panel .panel-head span,
  body.v24-ready .protocol-panel .panel-head small{
    font-size:12px!important;
    line-height:1.6;
  }

  body.v24-ready .protocol-panel .panel-head h3{
    margin-top:3px;
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
  body.v24-ready .protocol-panel .fact span,
  body.v24-ready .protocol-panel .action-copy small,
  body.v24-ready .protocol-panel .v13-action-copy small,
  body.v24-ready .protocol-panel .v13-client-only>span,
  body.v24-ready .protocol-panel .v13-native-client{
    font-size:12px!important;
    line-height:1.7!important;
  }

  body.v24-ready .protocol-panel .fact strong,
  body.v24-ready .protocol-panel .action-copy b,
  body.v24-ready .protocol-panel .v13-action-copy b{
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
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectCanonicalPresentationV24">
(function(){
  const MOBILE='(max-width:720px)';
  let liveObserver=null;
  let resizeTimer=null;

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

  function syncApps(){
    const platform=String(document.body.dataset.tpPlatform||'unknown').toLowerCase();
    document.querySelectorAll('.v13-app[data-v13-platform]').forEach(link=>{
      const target=String(link.dataset.v13Platform||'').toLowerCase();
      link.style.display=(platform==='unknown'||target===platform)?'inline-flex':'none';
    });
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

    syncApps();
    bindLive();
    body.classList.add('v24-ready');
    body.dataset.tpDevicePresentation='v24';
  }

  function deactivateMobile(){
    liveObserver?.disconnect();
    liveObserver=null;
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
  window.addEventListener('resize',schedule,{passive:true});
  window.addEventListener('pagehide',()=>liveObserver?.disconnect(),{once:true});
})();
</script>
"""


def refine_public_connection_canonical_presentation_v24(source: str) -> str:
    """Present one canonical connection dataset with device-specific layout/apps only."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
