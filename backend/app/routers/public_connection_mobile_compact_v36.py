from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_MOBILE_COMPACT_V36"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_MOBILE_COMPACT_V36 */
/* Smart Connect is retired on every platform. */
.smart-card{display:none!important}

@media(max-width:720px){
  /* Phone presentation is device-gated. Narrow desktop remains desktop. */
  body.v24-ready.v36-mobile-compact[data-tp-platform="android"] .protocols,
  body.v24-ready.v36-mobile-compact[data-tp-platform="ios"] .protocols,
  body.v36-mobile-compact[data-tp-platform="android"] .protocols,
  body.v36-mobile-compact[data-tp-platform="ios"] .protocols{
    display:grid!important;
    grid-template-columns:repeat(2,minmax(0,1fr))!important;
    gap:7px!important;
    overflow:visible!important;
    padding:0!important;
  }

  body.v36-mobile-compact[data-tp-platform="android"] .protocol-choice,
  body.v36-mobile-compact[data-tp-platform="ios"] .protocol-choice{
    width:100%!important;
    min-height:62px!important;
  }

  /* All protocol details start collapsed. Only the user-selected protocol opens. */
  body.v24-ready.v36-mobile-compact[data-tp-platform="android"] .protocol-panel,
  body.v24-ready.v36-mobile-compact[data-tp-platform="ios"] .protocol-panel,
  body.v36-mobile-compact[data-tp-platform="android"] .protocol-panel,
  body.v36-mobile-compact[data-tp-platform="ios"] .protocol-panel{
    display:none!important;
    margin-top:8px!important;
  }

  body.v24-ready.v36-mobile-compact[data-tp-platform="android"] .protocol-panel.v36-open,
  body.v24-ready.v36-mobile-compact[data-tp-platform="ios"] .protocol-panel.v36-open,
  body.v36-mobile-compact[data-tp-platform="android"] .protocol-panel.v36-open,
  body.v36-mobile-compact[data-tp-platform="ios"] .protocol-panel.v36-open{
    display:block!important;
  }

  body.v36-mobile-compact[data-tp-platform="android"] .server-tabs,
  body.v36-mobile-compact[data-tp-platform="ios"] .server-tabs{
    display:none!important;
  }

  body.v36-mobile-compact[data-tp-platform="android"] .server-views,
  body.v36-mobile-compact[data-tp-platform="ios"] .server-views{
    display:grid!important;
    grid-template-columns:1fr!important;
    gap:8px!important;
    padding:8px!important;
  }

  body.v36-mobile-compact[data-tp-platform="android"] .server-view,
  body.v36-mobile-compact[data-tp-platform="ios"] .server-view{
    display:block!important;
    margin:0!important;
  }

  /* V34's nested long-list fold is intentionally retired: protocol tap is the fold. */
  body.v36-mobile-compact[data-tp-platform="android"] .v34-mobile-servers,
  body.v36-mobile-compact[data-tp-platform="ios"] .v34-mobile-servers,
  body.v36-mobile-compact[data-tp-platform="android"] .v34-single-label,
  body.v36-mobile-compact[data-tp-platform="ios"] .v34-single-label{
    display:none!important;
  }
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectMobileCompactV36">
(function(){
  const PHONE=new Set(['android','ios']);
  const MOBILE='(max-width:720px)';
  const body=document.body;
  let initialized=false;
  let resizeTimer=null;

  function platform(){
    return String(body?.dataset?.tpPlatform||document.documentElement?.dataset?.tpPlatform||'unknown')
      .trim().toLowerCase();
  }

  function isPhone(){
    return PHONE.has(platform())&&window.matchMedia(MOBILE).matches;
  }

  function removeSmartConnect(){
    document.querySelectorAll('.smart-card').forEach(node=>node.remove());
    document.querySelectorAll('button,a').forEach(node=>{
      if(String(node.textContent||'').trim()!=='اتصال هوشمند')return;
      const smart=node.closest('.smart-card');
      if(smart)smart.remove();
      else node.remove();
    });
  }

  function unwrapV34ServerFolds(){
    document.querySelectorAll('.v34-mobile-servers[data-v34-server-fold="1"]').forEach(fold=>{
      const views=[...fold.children].find(node=>node.classList?.contains('server-views'))||null;
      if(views)fold.insertAdjacentElement('beforebegin',views);
      fold.remove();
    });
    document.querySelectorAll('.v34-single-label').forEach(node=>node.remove());
  }

  function panelFor(choice){
    const id=String(choice?.dataset?.protocol||'').trim();
    return id?document.getElementById(id):null;
  }

  function closeAll(){
    document.querySelectorAll('.protocol-choice').forEach(choice=>choice.classList.remove('active'));
    document.querySelectorAll('.protocol-panel').forEach(panel=>{
      panel.classList.remove('active','v36-open');
      panel.setAttribute('aria-hidden','true');
    });
  }

  function bindChoice(choice){
    if(choice.dataset.v36Bound==='1')return;
    choice.dataset.v36Bound='1';
    choice.setAttribute('aria-expanded','false');
    choice.addEventListener('click',event=>{
      if(!isPhone())return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const panel=panelFor(choice);
      if(!panel)return;
      const wasOpen=panel.classList.contains('v36-open');
      closeAll();
      document.querySelectorAll('.protocol-choice[data-v36-bound="1"]').forEach(node=>node.setAttribute('aria-expanded','false'));
      if(wasOpen)return;
      choice.classList.add('active');
      choice.setAttribute('aria-expanded','true');
      panel.classList.add('active','v36-open');
      panel.setAttribute('aria-hidden','false');
    },true);
  }

  function apply(){
    removeSmartConnect();
    if(!isPhone()){
      body.classList.remove('v36-mobile-compact');
      return;
    }

    body.classList.add('v36-mobile-compact');
    body.dataset.tpMobileCompact='v36';
    unwrapV34ServerFolds();

    const choices=[...document.querySelectorAll('.protocol-choice')];
    choices.forEach(bindChoice);

    if(!initialized){
      closeAll();
      choices.forEach(choice=>choice.setAttribute('aria-expanded','false'));
      initialized=true;
    }
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,180);

  window.addEventListener('resize',()=>{
    clearTimeout(resizeTimer);
    resizeTimer=window.setTimeout(apply,160);
  },{passive:true});

  window.addEventListener('pagehide',()=>clearTimeout(resizeTimer),{once:true});
})();
</script>
"""


def refine_public_connection_mobile_compact_v36(source: str) -> str:
    """Retire Smart Connect and make phone protocol cards the only server-list accordion."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
