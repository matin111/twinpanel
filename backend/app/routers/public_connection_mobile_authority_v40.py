from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_MOBILE_AUTHORITY_V40"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_MOBILE_AUTHORITY_V40 */
@media(max-width:720px){
  /* V40 is the final mobile presentation authority. Retire V27's parallel nav. */
  body.v40-mobile-final .v27-connect-nav{
    display:none!important;
  }

  /* V24 hid the canonical selector; V40 restores only real protocol choices. */
  body.v40-mobile-final .protocols{
    display:grid!important;
    grid-template-columns:repeat(2,minmax(0,1fr))!important;
    gap:7px!important;
    overflow:visible!important;
    padding:0!important;
  }
  body.v40-mobile-final .protocol-choice:not(.v40-real-protocol){
    display:none!important;
  }
  body.v40-mobile-final .protocol-choice.v40-real-protocol{
    display:grid!important;
    visibility:visible!important;
    opacity:1!important;
  }

  /* V36 is the single accordion. These selectors deliberately outrank V24/V27. */
  body.v40-mobile-final .protocol-panel.v24-canonical-panel,
  body.v40-mobile-final.v27-mobile-ui .protocol-panel.v24-canonical-panel{
    display:none!important;
  }
  body.v40-mobile-final .protocol-panel.v24-canonical-panel.v36-open,
  body.v40-mobile-final.v27-mobile-ui .protocol-panel.v24-canonical-panel.v36-open{
    display:block!important;
  }
  body.v40-mobile-final .protocol-panel.v36-open .panel-head{
    display:flex!important;
  }
  body.v40-mobile-final .protocol-panel.v36-open .server-views{
    display:grid!important;
    grid-template-columns:1fr!important;
  }
  body.v40-mobile-final .protocol-panel.v36-open .server-view{
    display:block!important;
  }

  /* V2Ray/Xray: preserve data, retire only legacy action surfaces. */
  body.v40-mobile-final .protocol-panel[data-v40-v2ray="1"] [data-v40-retired-actions="1"]{
    display:none!important;
  }
  body.v40-mobile-final .protocol-panel[data-v40-v2ray="1"] .v31-client-card{
    display:none!important;
  }
  body.v40-mobile-final .protocol-panel[data-v40-v2ray="1"] .v34-client-card{
    display:flex!important;
  }
  body.v40-mobile-final .protocol-panel[data-v40-v2ray="1"] .v34-server-actions,
  body.v40-mobile-final .protocol-panel[data-v40-v2ray="1"] .v38-all-actions{
    display:grid!important;
    grid-template-columns:repeat(2,minmax(0,1fr))!important;
    gap:7px!important;
  }
  body.v40-mobile-final .protocol-panel[data-v40-v2ray="1"] .v34-server-actions>a,
  body.v40-mobile-final .protocol-panel[data-v40-v2ray="1"] .v34-server-actions>button,
  body.v40-mobile-final .protocol-panel[data-v40-v2ray="1"] .v38-all-actions>a,
  body.v40-mobile-final .protocol-panel[data-v40-v2ray="1"] .v38-all-actions>button{
    width:100%!important;
    min-height:40px!important;
  }
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectMobileAuthorityV40">
(function(){
  const MOBILE='(max-width:720px)';
  let initialized=false;
  let resizeTimer=null;

  function normalize(value){
    const key=String(value||'').trim().toLowerCase();
    if(key==='xray')return'v2ray';
    if(key==='naiveproxy')return'naive';
    if(key==='openconnect'||key==='ocserv'||key==='anyconnect')return'cisco';
    return key;
  }

  function panelKey(panel){
    const direct=normalize(panel?.dataset?.v34Protocol||panel?.dataset?.modernProtocol||'');
    if(direct)return direct;
    const choice=[...document.querySelectorAll('.protocol-choice')]
      .find(item=>String(item.dataset.protocol||'')===String(panel?.id||''));
    return normalize(choice?.dataset?.protocolKey||choice?.dataset?.protocol||panel?.id||'');
  }

  function choiceFor(panel){
    if(!panel?.id)return null;
    return [...document.querySelectorAll('.protocol-choice')]
      .find(choice=>String(choice.dataset.protocol||'')===String(panel.id));
  }

  function realPanels(){
    return [...document.querySelectorAll('.protocol-panel.v24-canonical-panel')]
      .filter(panel=>!panel.classList.contains('v24-empty')&&Boolean(panel.querySelector('.server-view')));
  }

  function retireV27(){
    document.body.classList.remove('v27-mobile-ui');
    if(document.body.dataset.tpMobilePresentation==='v27'){
      delete document.body.dataset.tpMobilePresentation;
    }
    document.querySelector('.v27-connect-nav')?.remove();
    document.querySelectorAll('.v27-active-protocol').forEach(node=>node.classList.remove('v27-active-protocol'));
    document.querySelectorAll('.v27-active-server').forEach(node=>node.classList.remove('v27-active-server'));
  }

  function restoreRealProtocols(){
    const list=document.querySelector('.protocols');
    if(list){
      list.hidden=false;
      list.removeAttribute('aria-hidden');
      list.style.removeProperty('display');
    }

    document.querySelectorAll('.protocol-choice').forEach(choice=>choice.classList.remove('v40-real-protocol'));
    realPanels().forEach(panel=>{
      const choice=choiceFor(panel);
      if(!choice)return;
      choice.hidden=false;
      choice.removeAttribute('aria-hidden');
      choice.removeAttribute('data-v31-hide');
      choice.classList.remove('v13-pending','tp-v20-hidden-pending');
      choice.style.removeProperty('display');
      choice.classList.add('v40-real-protocol');
    });
  }

  function initialAccordionState(){
    if(initialized)return;
    document.querySelectorAll('.protocol-choice.v40-real-protocol').forEach(choice=>{
      choice.classList.remove('active');
      choice.setAttribute('aria-expanded','false');
    });
    realPanels().forEach(panel=>{
      panel.classList.remove('active','v36-open','v27-active-protocol');
      panel.setAttribute('aria-hidden','true');
    });
    initialized=true;
  }

  function retireLegacyV2rayActions(view,row){
    view.querySelectorAll('[data-v39-retired="1"]').forEach(node=>{
      node.removeAttribute('data-v39-retired');
      if(node.getAttribute('aria-hidden')==='true')node.removeAttribute('aria-hidden');
    });
    view.querySelectorAll(
      ':scope > .action-row,'+
      ':scope > .v13-modern-action,'+
      ':scope > .v13-client-only,'+
      ':scope > .tp-v48-xray-profile,'+
      ':scope > .v31-canonical-actions'
    ).forEach(node=>{
      if(node===row)return;
      node.dataset.v40RetiredActions='1';
      node.setAttribute('aria-hidden','true');
    });
  }

  function simplifyServer(view){
    const row=view.querySelector(':scope > .v34-server-actions');
    if(!row)return;
    retireLegacyV2rayActions(view,row);
    row.removeAttribute('data-v39-retired');
    row.removeAttribute('aria-hidden');

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
      panel.dataset.v40V2ray='1';
      panel.querySelectorAll('.server-view').forEach(simplifyServer);
      simplifyMulti(panel);
    });
  }

  function apply(){
    if(!window.matchMedia(MOBILE).matches){
      document.body.classList.remove('v40-mobile-final');
      delete document.body.dataset.tpMobileAuthority;
      initialized=false;
      return;
    }
    document.body.classList.add('v40-mobile-final');
    document.body.dataset.tpMobileAuthority='v40';
    retireV27();
    restoreRealProtocols();
    initialAccordionState();
    simplifyV2ray();
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,320);
  window.setTimeout(apply,980);
  window.setTimeout(apply,1600);

  window.addEventListener('resize',()=>{
    clearTimeout(resizeTimer);
    resizeTimer=window.setTimeout(apply,260);
  },{passive:true});
  window.addEventListener('pagehide',()=>clearTimeout(resizeTimer),{once:true});
})();
</script>
"""


def refine_public_connection_mobile_authority_v40(source: str) -> str:
    """Retire V27 mobile selection and make V36 the single final accordion authority."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
