from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_MOBILE_COMPACT_V36"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_MOBILE_COMPACT_V36 */
/* Smart Connect is retired on every platform. */
.smart-card{display:none!important}

@media(max-width:720px){
  /* Responsive mobile presentation is viewport-owned so browser/mobile preview
   * and real phones share exactly the same accordion behaviour. */
  body.v36-mobile-compact .protocols{
    display:grid!important;
    grid-template-columns:repeat(2,minmax(0,1fr))!important;
    gap:7px!important;
    overflow:visible!important;
    padding:0!important;
  }

  body.v36-mobile-compact .protocol-choice{
    width:100%!important;
    min-height:62px!important;
  }

  /* All protocol details start collapsed. Only the selected protocol opens. */
  body.v36-mobile-compact .protocol-panel{
    display:none!important;
    margin-top:8px!important;
  }

  body.v36-mobile-compact .protocol-panel.v36-open{
    display:block!important;
  }

  body.v36-mobile-compact .server-tabs{
    display:none!important;
  }

  body.v36-mobile-compact .server-views{
    display:grid!important;
    grid-template-columns:1fr!important;
    gap:8px!important;
    padding:8px!important;
  }

  body.v36-mobile-compact .server-view{
    display:block!important;
    margin:0!important;
  }

  /* Protocol tap is the only fold; retire V34's nested server-list fold. */
  body.v36-mobile-compact .v34-mobile-servers,
  body.v36-mobile-compact .v34-single-label{
    display:none!important;
  }
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectMobileCompactV36">
(function(){
  const MOBILE='(max-width:720px)';
  const body=document.body;
  let compactInitialized=false;
  let resizeTimer=null;

  function isCompact(){
    return window.matchMedia(MOBILE).matches;
  }

  function removeSmartConnect(){
    document.querySelectorAll('.smart-card,.smart-empty').forEach(node=>node.remove());
    document.querySelectorAll('.section-head').forEach(node=>{
      const heading=String(node.querySelector('h2')?.textContent||'').trim();
      if(heading==='اتصال هوشمند')node.remove();
    });
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
    document.querySelectorAll('.protocol-choice').forEach(choice=>{
      choice.classList.remove('active');
      choice.setAttribute('aria-expanded','false');
    });
    document.querySelectorAll('.protocol-panel').forEach(panel=>{
      panel.classList.remove('active','v36-open');
      panel.setAttribute('aria-hidden','true');
    });
  }

  function restoreDesktop(){
    body.classList.remove('v36-mobile-compact');
    delete body.dataset.tpMobileCompact;
    const panels=[...document.querySelectorAll('.protocol-panel')];
    if(!panels.some(panel=>panel.classList.contains('active'))){
      const firstChoice=document.querySelector('.protocol-choice');
      const firstPanel=panelFor(firstChoice);
      if(firstChoice&&firstPanel){
        firstChoice.classList.add('active');
        firstChoice.setAttribute('aria-expanded','true');
        firstPanel.classList.add('active');
        firstPanel.classList.remove('v36-open');
        firstPanel.setAttribute('aria-hidden','false');
      }
    }
    compactInitialized=false;
  }

  function bindChoice(choice){
    if(choice.dataset.v36Bound==='1')return;
    choice.dataset.v36Bound='1';
    choice.setAttribute('aria-expanded','false');
    choice.addEventListener('click',event=>{
      if(!isCompact())return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const panel=panelFor(choice);
      if(!panel)return;
      const wasOpen=panel.classList.contains('v36-open');
      closeAll();
      if(wasOpen)return;
      choice.classList.add('active');
      choice.setAttribute('aria-expanded','true');
      panel.classList.add('active','v36-open');
      panel.setAttribute('aria-hidden','false');
    },true);
  }

  function apply(){
    removeSmartConnect();
    if(!isCompact()){
      restoreDesktop();
      return;
    }

    body.classList.add('v36-mobile-compact');
    body.dataset.tpMobileCompact='v36';
    unwrapV34ServerFolds();

    const choices=[...document.querySelectorAll('.protocol-choice')];
    choices.forEach(bindChoice);

    if(!compactInitialized){
      closeAll();
      compactInitialized=true;
    }
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,180);
  window.setTimeout(apply,650);

  window.addEventListener('resize',()=>{
    clearTimeout(resizeTimer);
    resizeTimer=window.setTimeout(apply,160);
  },{passive:true});

  window.addEventListener('pagehide',()=>clearTimeout(resizeTimer),{once:true});
})();
</script>
"""


def refine_public_connection_mobile_compact_v36(source: str) -> str:
    """Retire Smart Connect and make the responsive mobile view a protocol accordion."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
