from __future__ import annotations

from .public_connection_v2ray_multilink_action_v44 import (
    refine_public_connection_v2ray_multilink_action_v44,
)


_MARKER = "TWINPANEL_PUBLIC_CONNECT_MOBILE_SHEET_V42"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_MOBILE_SHEET_V42 */
@media(max-width:720px){
  body.v42-sheet-active{
    overflow:hidden!important;
  }

  body.v42-mobile-sheet .v42-sheet-backdrop{
    position:fixed!important;
    inset:0!important;
    z-index:2147483600!important;
    background:rgba(3,7,18,.62)!important;
    backdrop-filter:blur(2px)!important;
    -webkit-backdrop-filter:blur(2px)!important;
  }

  body.v42-mobile-sheet .protocol-panel.v42-sheet-open{
    display:block!important;
    position:fixed!important;
    z-index:2147483601!important;
    left:8px!important;
    right:8px!important;
    bottom:8px!important;
    top:auto!important;
    width:auto!important;
    max-width:none!important;
    max-height:min(82dvh,760px)!important;
    overflow:auto!important;
    overscroll-behavior:contain!important;
    margin:0!important;
    padding-top:0!important;
    border:1px solid var(--line)!important;
    border-radius:22px!important;
    background:var(--surface)!important;
    box-shadow:0 -18px 50px rgba(0,0,0,.28)!important;
  }

  body.v42-mobile-sheet .protocol-panel.v42-sheet-open .v42-sheet-toolbar{
    position:sticky!important;
    top:0!important;
    z-index:5!important;
    min-height:54px!important;
    display:flex!important;
    align-items:center!important;
    justify-content:space-between!important;
    gap:12px!important;
    padding:10px 12px!important;
    border-bottom:1px solid var(--line)!important;
    background:color-mix(in srgb,var(--surface) 94%,transparent)!important;
    backdrop-filter:blur(12px)!important;
    -webkit-backdrop-filter:blur(12px)!important;
  }

  body.v42-mobile-sheet .v42-sheet-title{
    min-width:0!important;
    font-size:15px!important;
    font-weight:900!important;
    color:var(--text)!important;
    white-space:nowrap!important;
    overflow:hidden!important;
    text-overflow:ellipsis!important;
  }

  body.v42-mobile-sheet .v42-sheet-close{
    flex:0 0 40px!important;
    width:40px!important;
    height:40px!important;
    min-height:40px!important;
    display:inline-flex!important;
    align-items:center!important;
    justify-content:center!important;
    border:1px solid var(--line)!important;
    border-radius:12px!important;
    background:var(--surface2)!important;
    color:var(--text)!important;
    font:inherit!important;
    font-size:22px!important;
    line-height:1!important;
    cursor:pointer!important;
  }

  body.v42-mobile-sheet .protocol-panel.v42-sheet-open .panel-head{
    display:none!important;
  }

  body.v42-mobile-sheet .protocol-panel.v42-sheet-open .server-tabs{
    display:none!important;
  }

  body.v42-mobile-sheet .protocol-panel.v42-sheet-open .server-views{
    display:grid!important;
    grid-template-columns:1fr!important;
    gap:9px!important;
    padding:10px!important;
  }

  body.v42-mobile-sheet .protocol-panel.v42-sheet-open .server-view{
    display:block!important;
    margin:0!important;
  }

  /* V41 removes the lower V2Ray server inventory. The fixed V42 sheet must
     therefore expose the surviving V38/V44 multi-link and client surfaces. */
  body.v42-mobile-sheet .protocol-panel.v42-sheet-open[data-v41-v2ray="1"] .v38-all-card[data-v38-protocol="v2ray"]{
    display:block!important;
    visibility:visible!important;
    opacity:1!important;
  }
  body.v42-mobile-sheet .protocol-panel.v42-sheet-open[data-v41-v2ray="1"] .v34-client-card{
    display:flex!important;
    visibility:visible!important;
    opacity:1!important;
  }
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectMobileSheetV42">
(function(){
  const MOBILE='(max-width:720px)';
  let activePanel=null;
  let activeChoice=null;
  let backdrop=null;

  function isMobile(){
    return window.matchMedia(MOBILE).matches;
  }

  function panelFor(choice){
    const id=String(choice?.dataset?.protocol||'').trim();
    return id?document.getElementById(id):null;
  }

  function titleFor(choice,panel){
    const direct=String(choice?.querySelector?.('b,strong')?.textContent||choice?.textContent||'').trim();
    if(direct)return direct.replace(/\s+/g,' ');
    return String(panel?.dataset?.v34Protocol||panel?.id||'سرورها').trim();
  }

  function hasSheetSurface(panel){
    if(!panel)return false;
    if(panel.querySelector('.server-view'))return true;
    const v2rayReady=panel.dataset.v41V2ray==='1'||panel.dataset.v41LowerConfigsRemoved==='1';
    if(!v2rayReady)return false;
    return Boolean(
      panel.querySelector('.v38-all-card[data-v38-protocol="v2ray"]') ||
      panel.querySelector('.v34-client-card')
    );
  }

  function ensureBackdrop(){
    if(backdrop?.isConnected)return backdrop;
    backdrop=document.createElement('div');
    backdrop.className='v42-sheet-backdrop';
    backdrop.setAttribute('aria-hidden','true');
    backdrop.addEventListener('click',closeSheet);
    document.body.appendChild(backdrop);
    return backdrop;
  }

  function ensureToolbar(panel,choice){
    let toolbar=panel.querySelector(':scope > .v42-sheet-toolbar');
    if(!toolbar){
      toolbar=document.createElement('div');
      toolbar.className='v42-sheet-toolbar';
      const title=document.createElement('div');
      title.className='v42-sheet-title';
      const close=document.createElement('button');
      close.type='button';
      close.className='v42-sheet-close';
      close.setAttribute('aria-label','بستن');
      close.textContent='×';
      close.addEventListener('click',closeSheet);
      toolbar.append(title,close);
      panel.prepend(toolbar);
    }
    const title=toolbar.querySelector('.v42-sheet-title');
    if(title)title.textContent=titleFor(choice,panel);
  }

  function closeAllMobileSurfaces(){
    document.querySelectorAll('.protocol-panel.active,.protocol-panel.v36-open,.protocol-panel.v42-sheet-open').forEach(panel=>{
      panel.classList.remove('v42-sheet-open','active','v36-open','v27-active-protocol');
      panel.setAttribute('aria-hidden','true');
    });
    document.querySelectorAll('.protocol-choice.active').forEach(choice=>{
      choice.classList.remove('active');
      choice.setAttribute('aria-expanded','false');
    });
  }

  function closeSheet(){
    closeAllMobileSurfaces();
    backdrop?.remove();
    backdrop=null;
    activePanel=null;
    activeChoice=null;
    document.body.classList.remove('v42-sheet-active');
  }

  function openSheet(choice,panel){
    closeSheet();
    ensureBackdrop();
    ensureToolbar(panel,choice);
    activeChoice=choice;
    activePanel=panel;
    choice.classList.add('active');
    choice.setAttribute('aria-expanded','true');
    panel.classList.add('active','v36-open','v42-sheet-open');
    panel.setAttribute('aria-hidden','false');
    document.body.classList.add('v42-sheet-active');
    panel.scrollTop=0;
  }

  function handleProtocolTap(event){
    if(!isMobile())return;
    const choice=event.target?.closest?.('.protocol-choice');
    if(!choice)return;
    const panel=panelFor(choice);
    if(!hasSheetSurface(panel))return;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    if(activePanel===panel){
      closeSheet();
      return;
    }
    openSheet(choice,panel);
  }

  function apply(){
    if(!isMobile()){
      closeSheet();
      document.body.classList.remove('v42-mobile-sheet');
      delete document.body.dataset.tpMobileSheet;
      return;
    }
    document.body.classList.add('v42-mobile-sheet');
    document.body.dataset.tpMobileSheet='v42';
  }

  document.addEventListener('click',handleProtocolTap,true);
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape'&&activePanel)closeSheet();
  });

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,350);
  window.addEventListener('resize',apply,{passive:true});
  window.addEventListener('pagehide',closeSheet,{once:true});
})();
</script>
"""


def refine_public_connection_mobile_sheet_v42(source: str) -> str:
    """Open selected protocol servers in a mobile bottom-sheet instead of inline below the grid."""
    if _MARKER not in source:
        source = source.replace("</style>", _CSS + "\n</style>", 1)
        source = source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
    return refine_public_connection_v2ray_multilink_action_v44(source)
