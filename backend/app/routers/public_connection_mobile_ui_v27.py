from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_MOBILE_UI_V27"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_MOBILE_UI_V27 */
@media(max-width:720px){
  body.v27-mobile-ui .apps,
  body.v27-mobile-ui .protocol-panel .panel-head{
    display:none!important;
  }

  body.v27-mobile-ui .protocol-panel.v24-canonical-panel{
    display:none!important;
    margin:0!important;
    border:1px solid var(--line)!important;
    border-radius:18px!important;
    background:var(--surface)!important;
    box-shadow:0 12px 34px rgba(0,0,0,.08)!important;
    overflow:hidden!important;
  }

  body.v27-mobile-ui .protocol-panel.v24-canonical-panel.v27-active-protocol{
    display:block!important;
  }

  body.v27-mobile-ui .v27-connect-nav{
    margin:14px 0 10px;
    padding:12px;
    border:1px solid var(--line);
    border-radius:18px;
    background:var(--surface);
    box-shadow:0 10px 28px rgba(0,0,0,.06);
  }

  body.v27-mobile-ui .v27-connect-head{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:10px;
    margin-bottom:10px;
  }

  body.v27-mobile-ui .v27-connect-title{
    display:flex;
    align-items:center;
    gap:8px;
    min-width:0;
    font-size:14px;
    font-weight:900;
  }

  body.v27-mobile-ui .v27-connect-title:before{
    content:'';
    width:8px;
    height:8px;
    flex:0 0 8px;
    border-radius:50%;
    background:linear-gradient(135deg,var(--p),var(--s));
    box-shadow:0 0 0 4px color-mix(in srgb,var(--p) 12%,transparent);
  }

  body.v27-mobile-ui .v27-connect-count{
    min-height:26px;
    padding:0 9px;
    display:inline-flex;
    align-items:center;
    justify-content:center;
    border:1px solid var(--line);
    border-radius:999px;
    background:var(--surface2);
    color:var(--muted);
    font-size:10px;
    font-weight:900;
    white-space:nowrap;
  }

  body.v27-mobile-ui .v27-protocol-strip,
  body.v27-mobile-ui .v27-server-strip{
    display:flex;
    gap:8px;
    overflow-x:auto;
    overflow-y:hidden;
    padding:2px 1px 4px;
    scroll-snap-type:x proximity;
    overscroll-behavior-inline:contain;
    -webkit-overflow-scrolling:touch;
    scrollbar-width:none;
  }

  body.v27-mobile-ui .v27-protocol-strip::-webkit-scrollbar,
  body.v27-mobile-ui .v27-server-strip::-webkit-scrollbar{
    display:none;
  }

  body.v27-mobile-ui .v27-server-strip{
    margin-top:9px;
    padding-top:9px;
    border-top:1px solid var(--line);
  }

  body.v27-mobile-ui .v27-protocol-btn,
  body.v27-mobile-ui .v27-server-btn{
    flex:0 0 auto;
    scroll-snap-align:start;
    border:1px solid var(--line);
    background:var(--surface2);
    color:var(--text);
    font-weight:900;
    white-space:nowrap;
    transition:border-color .16s ease,background .16s ease,transform .16s ease;
  }

  body.v27-mobile-ui .v27-protocol-btn{
    min-height:43px;
    padding:0 12px;
    display:inline-flex;
    align-items:center;
    gap:8px;
    border-radius:13px;
    font-size:12px;
  }

  body.v27-mobile-ui .v27-protocol-btn .v27-protocol-icon{
    width:28px;
    height:28px;
    display:grid;
    place-items:center;
    border-radius:9px;
    background:linear-gradient(135deg,var(--p),var(--s));
    color:#fff;
    font-size:10px;
    font-weight:900;
  }

  body.v27-mobile-ui .v27-protocol-btn .v27-live-dot{
    width:7px;
    height:7px;
    border-radius:50%;
    background:var(--muted);
    opacity:.45;
  }

  body.v27-mobile-ui .v27-protocol-btn.v27-online .v27-live-dot{
    background:var(--ok);
    opacity:1;
    box-shadow:0 0 0 3px color-mix(in srgb,var(--ok) 13%,transparent);
  }

  body.v27-mobile-ui .v27-protocol-btn.v27-active,
  body.v27-mobile-ui .v27-server-btn.v27-active{
    border-color:var(--p);
    background:color-mix(in srgb,var(--p) 10%,var(--surface));
    color:var(--p);
  }

  body.v27-mobile-ui .v27-protocol-btn:active,
  body.v27-mobile-ui .v27-server-btn:active{
    transform:scale(.98);
  }

  body.v27-mobile-ui .v27-server-btn{
    min-height:36px;
    padding:0 11px;
    border-radius:11px;
    font-size:11px;
  }

  body.v27-mobile-ui .protocol-panel .server-views{
    display:block!important;
    padding:10px!important;
  }

  body.v27-mobile-ui .protocol-panel .server-view{
    display:none!important;
    position:relative!important;
    margin:0!important;
    padding:10px!important;
    border:0!important;
    border-radius:0!important;
    background:transparent!important;
  }

  body.v27-mobile-ui .protocol-panel .server-view.v27-active-server{
    display:block!important;
  }

  body.v27-mobile-ui .protocol-panel .server-view:before{
    display:none!important;
    content:none!important;
  }

  body.v27-mobile-ui .protocol-panel .facts{
    display:grid!important;
    grid-template-columns:1fr!important;
    gap:7px!important;
  }

  body.v27-mobile-ui .protocol-panel .fact{
    min-height:0!important;
    padding:10px 11px!important;
    display:grid!important;
    grid-template-columns:minmax(0,1fr) auto!important;
    grid-template-rows:auto auto!important;
    align-items:center!important;
    gap:4px 8px!important;
    border:1px solid var(--line)!important;
    border-radius:12px!important;
    background:var(--surface2)!important;
    text-align:right!important;
  }

  body.v27-mobile-ui .protocol-panel .fact small{
    grid-column:1 / -1!important;
    color:var(--muted)!important;
    font-size:10px!important;
    line-height:1.5!important;
  }

  body.v27-mobile-ui .protocol-panel .fact strong{
    grid-column:1!important;
    margin:0!important;
    min-width:0!important;
    white-space:normal!important;
    overflow-wrap:anywhere!important;
    word-break:break-word!important;
    direction:ltr!important;
    text-align:left!important;
    font-size:12px!important;
    line-height:1.55!important;
  }

  body.v27-mobile-ui .protocol-panel .fact .copy-btn{
    grid-column:2!important;
    grid-row:2!important;
    min-width:62px!important;
    min-height:34px!important;
    padding:0 9px!important;
  }

  body.v27-mobile-ui .protocol-panel .action-row,
  body.v27-mobile-ui .protocol-panel .v13-modern-action,
  body.v27-mobile-ui .protocol-panel .v13-client-only,
  body.v27-mobile-ui .tp-v48-xray-profile{
    margin:7px 0!important;
    padding:10px!important;
    display:flex!important;
    flex-wrap:wrap!important;
    align-items:center!important;
    gap:8px!important;
    border:1px solid var(--line)!important;
    border-radius:12px!important;
    background:var(--surface2)!important;
  }

  body.v27-mobile-ui .protocol-panel .qr{
    width:64px!important;
    height:64px!important;
    flex:0 0 64px!important;
    padding:4px!important;
    border-radius:10px!important;
  }

  body.v27-mobile-ui .protocol-panel .action-buttons,
  body.v27-mobile-ui .protocol-panel .v13-action-buttons,
  body.v27-mobile-ui .protocol-panel .v13-client-only>div,
  body.v27-mobile-ui .tp-v48-profile-actions{
    width:100%!important;
    display:grid!important;
    grid-template-columns:repeat(2,minmax(0,1fr))!important;
    gap:7px!important;
  }

  body.v27-mobile-ui .protocol-panel .copy-btn,
  body.v27-mobile-ui .protocol-panel .primary-btn,
  body.v27-mobile-ui .protocol-panel .download-config,
  body.v27-mobile-ui .protocol-panel .v13-secondary,
  body.v27-mobile-ui .protocol-panel .v13-app,
  body.v27-mobile-ui .protocol-panel .v17-action,
  body.v27-mobile-ui .protocol-panel button,
  body.v27-mobile-ui .protocol-panel a{
    width:100%;
    min-height:40px!important;
    padding:8px 10px!important;
    display:inline-flex!important;
    align-items:center!important;
    justify-content:center!important;
    border-radius:10px!important;
    font-size:11px!important;
    line-height:1.4!important;
    text-align:center!important;
  }

  body.v27-mobile-ui .protocol-panel textarea.hidden-source{
    display:none!important;
  }

  body.v27-mobile-ui .advanced{
    margin-top:12px!important;
  }
}

@media(max-width:390px){
  body.v27-mobile-ui .protocol-panel .action-buttons,
  body.v27-mobile-ui .protocol-panel .v13-action-buttons,
  body.v27-mobile-ui .protocol-panel .v13-client-only>div,
  body.v27-mobile-ui .tp-v48-profile-actions{
    grid-template-columns:1fr!important;
  }
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectMobileUiV27">
(function(){
  const MOBILE='(max-width:720px)';
  let activePanelId='';
  let activeServerByPanel={};
  let liveObserver=null;
  let resizeTimer=null;

  const text=el=>String(el?.textContent||'').trim();
  const visiblePanels=()=>[...document.querySelectorAll('.protocol-panel.v24-canonical-panel')]
    .filter(panel=>!panel.classList.contains('v24-empty'));

  function originalChoice(panel){
    if(!panel?.id)return null;
    return [...document.querySelectorAll('.protocol-choice')]
      .find(choice=>String(choice.dataset.protocol||'')===panel.id)||null;
  }

  function protocolTitle(panel){
    const choice=originalChoice(panel);
    return text(choice?.querySelector('.protocol-text b'))||
      text(panel?.querySelector('.panel-head h3'))||
      panel?.id||'Protocol';
  }

  function protocolIcon(panel){
    const choice=originalChoice(panel);
    return text(choice?.querySelector('.protocol-icon'))||'•';
  }

  function serverLabel(panel,index){
    const tabs=[...panel.querySelectorAll('.server-tab')];
    return text(tabs[index]?.querySelector('span'))||text(tabs[index])||('سرور '+(index+1));
  }

  function ensureNav(){
    let nav=document.querySelector('.v27-connect-nav');
    if(nav)return nav;
    const panels=visiblePanels();
    if(!panels.length)return null;
    nav=document.createElement('section');
    nav.className='v27-connect-nav';
    nav.setAttribute('aria-label','انتخاب اتصال');
    nav.innerHTML='\
      <div class="v27-connect-head">\
        <div class="v27-connect-title">اتصال‌ها</div>\
        <div class="v27-connect-count"></div>\
      </div>\
      <div class="v27-protocol-strip" role="tablist"></div>\
      <div class="v27-server-strip" role="tablist"></div>';
    panels[0].parentNode.insertBefore(nav,panels[0]);
    return nav;
  }

  function selectServer(panel,index,scroll){
    if(!panel)return;
    const views=[...panel.querySelectorAll('.server-view')];
    if(!views.length)return;
    const safe=Math.max(0,Math.min(index,views.length-1));
    activeServerByPanel[panel.id]=safe;
    views.forEach((view,i)=>view.classList.toggle('v27-active-server',i===safe));
    document.querySelectorAll('.v27-server-btn').forEach((button,i)=>{
      button.classList.toggle('v27-active',i===safe);
      button.setAttribute('aria-selected',i===safe?'true':'false');
    });
    if(scroll){
      document.querySelectorAll('.v27-server-btn')[safe]?.scrollIntoView({behavior:'smooth',block:'nearest',inline:'center'});
    }
  }

  function renderServers(panel){
    const nav=ensureNav();
    if(!nav||!panel)return;
    const strip=nav.querySelector('.v27-server-strip');
    const views=[...panel.querySelectorAll('.server-view')];
    strip.innerHTML='';
    strip.style.display=views.length>1?'flex':'none';
    views.forEach((view,index)=>{
      const button=document.createElement('button');
      button.type='button';
      button.className='v27-server-btn';
      button.textContent=serverLabel(panel,index);
      button.setAttribute('role','tab');
      button.addEventListener('click',()=>selectServer(panel,index,true));
      strip.appendChild(button);
    });
    const current=Number.isInteger(activeServerByPanel[panel.id])?activeServerByPanel[panel.id]:0;
    selectServer(panel,current,false);
  }

  function selectProtocol(panelId,scroll){
    const panels=visiblePanels();
    const panel=panels.find(item=>item.id===panelId)||panels[0];
    if(!panel)return;
    activePanelId=panel.id;
    panels.forEach(item=>item.classList.toggle('v27-active-protocol',item===panel));
    document.querySelectorAll('.v27-protocol-btn').forEach(button=>{
      const active=button.dataset.panelId===panel.id;
      button.classList.toggle('v27-active',active);
      button.setAttribute('aria-selected',active?'true':'false');
    });
    renderServers(panel);
    if(scroll){
      document.querySelector('.v27-protocol-btn.v27-active')?.scrollIntoView({behavior:'smooth',block:'nearest',inline:'center'});
    }
  }

  function syncLive(){
    document.querySelectorAll('.v27-protocol-btn').forEach(button=>{
      const panel=document.getElementById(button.dataset.panelId||'');
      const choice=originalChoice(panel);
      button.classList.toggle('v27-online',Boolean(choice?.classList.contains('live-online')));
    });
  }

  function bindLive(){
    liveObserver?.disconnect();
    liveObserver=new MutationObserver(syncLive);
    document.querySelectorAll('.protocol-choice').forEach(choice=>{
      liveObserver.observe(choice,{attributes:true,attributeFilter:['class']});
    });
    syncLive();
  }

  function build(){
    if(!window.matchMedia(MOBILE).matches)return deactivate();
    const panels=visiblePanels();
    if(!panels.length)return;
    document.body.classList.add('v27-mobile-ui');
    document.body.dataset.tpMobilePresentation='v27';
    const nav=ensureNav();
    if(!nav)return;
    const strip=nav.querySelector('.v27-protocol-strip');
    const count=nav.querySelector('.v27-connect-count');
    strip.innerHTML='';
    count.textContent=panels.length+' پروتکل';

    panels.forEach(panel=>{
      const button=document.createElement('button');
      button.type='button';
      button.className='v27-protocol-btn';
      button.dataset.panelId=panel.id;
      button.setAttribute('role','tab');
      const icon=document.createElement('span');
      icon.className='v27-protocol-icon';
      icon.textContent=protocolIcon(panel);
      const label=document.createElement('span');
      label.textContent=protocolTitle(panel);
      const dot=document.createElement('i');
      dot.className='v27-live-dot';
      button.append(icon,label,dot);
      button.addEventListener('click',()=>selectProtocol(panel.id,true));
      strip.appendChild(button);
    });

    if(!activePanelId||!panels.some(panel=>panel.id===activePanelId)){
      const online=panels.find(panel=>originalChoice(panel)?.classList.contains('live-online'));
      activePanelId=(online||panels[0]).id;
    }
    selectProtocol(activePanelId,false);
    bindLive();
  }

  function deactivate(){
    document.body.classList.remove('v27-mobile-ui');
    delete document.body.dataset.tpMobilePresentation;
    document.querySelector('.v27-connect-nav')?.remove();
    document.querySelectorAll('.v27-active-protocol').forEach(node=>node.classList.remove('v27-active-protocol'));
    document.querySelectorAll('.v27-active-server').forEach(node=>node.classList.remove('v27-active-server'));
    liveObserver?.disconnect();
  }

  build();
  window.setTimeout(build,0);
  window.setTimeout(build,180);
  window.addEventListener('resize',()=>{
    clearTimeout(resizeTimer);
    resizeTimer=setTimeout(build,120);
  });
})();
</script>
"""


def refine_public_connection_mobile_ui_v27(source: str) -> str:
    """Present canonical Public Connect data as one compact protocol/server view on phones."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
