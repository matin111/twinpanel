from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_PRESENTATION_V29"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_PRESENTATION_V29 */

/* Presentation-only cleanup. Connection data and delivery endpoints stay canonical. */
body.v29-ready .smart-card,
body.v29-ready .smart-empty,
body.v29-ready .multi-link-card,
body.v29-ready .tp-win-v2ray-note,
body.v29-ready .action-copy,
body.v29-ready .v13-action-copy,
body.v29-ready .v13-client-only>span,
body.v29-ready .protocol-panel .qr,
body.v29-ready .protocol-panel [data-v29-hide="1"]{
  display:none!important;
}

body.v29-ready .section-head p,
body.v29-ready .section-head small,
body.v29-ready .apps-head small,
body.v29-ready .platform-title small,
body.v29-ready .app-card small{
  display:none!important;
}

body.v29-ready .section-head{
  margin:24px 0 12px;
}
body.v29-ready .section-head h2{
  margin:0;
  font-size:21px!important;
  line-height:1.45!important;
  letter-spacing:-.01em;
}
body.v29-ready .protocol-text b,
body.v29-ready .panel-head h3,
body.v29-ready .platform-title b,
body.v29-ready .app-card b{
  font-size:13px!important;
  line-height:1.55!important;
}
body.v29-ready .protocol-text small,
body.v29-ready .panel-head span,
body.v29-ready .fact small{
  font-size:11px!important;
  line-height:1.55!important;
}
body.v29-ready .fact strong{
  font-size:12.5px!important;
  line-height:1.6!important;
}
body.v29-ready .copy-btn,
body.v29-ready .primary-btn,
body.v29-ready .download-config,
body.v29-ready .v13-secondary,
body.v29-ready .v13-app,
body.v29-ready .tp-v48-profile-actions a,
body.v29-ready .tp-v48-profile-actions button{
  min-height:40px!important;
  padding:9px 13px!important;
  border-radius:10px!important;
  font-size:12px!important;
  line-height:1.35!important;
  font-weight:900!important;
}
body.v29-ready .action-buttons,
body.v29-ready .v13-action-buttons,
body.v29-ready .v13-client-only>div,
body.v29-ready .tp-v48-profile-actions{
  display:flex!important;
  flex-wrap:wrap!important;
  gap:8px!important;
}
body.v29-ready .action-row,
body.v29-ready .v13-modern-action,
body.v29-ready .v13-client-only,
body.v29-ready .tp-v48-xray-profile{
  gap:10px!important;
}
body.v29-ready .apps-head h2{
  margin:0!important;
  font-size:17px!important;
}
body.v29-ready .device,
body.v29-ready .allbtn{
  font-size:11px!important;
}

/* Phone: replace the horizontal chooser with vertical protocol/server cards. */
@media(max-width:720px){
  body.v29-ready.v27-mobile-ui .v27-connect-nav,
  body.v29-ready.v27-mobile-ui .v28-scroll-hint,
  body.v29-ready.v27-mobile-ui .protocols{
    display:none!important;
  }

  body.v29-ready.v27-mobile-ui .protocol-panel.v24-canonical-panel{
    display:block!important;
    margin:12px 0 0!important;
    border:1px solid var(--line)!important;
    border-radius:18px!important;
    background:var(--surface)!important;
    box-shadow:0 8px 24px rgba(0,0,0,.07)!important;
    overflow:hidden!important;
  }

  body.v29-ready.v27-mobile-ui .protocol-panel .panel-head{
    min-height:62px!important;
    padding:14px 16px!important;
    display:flex!important;
    align-items:center!important;
    flex-direction:row!important;
    border-bottom:1px solid var(--line)!important;
    background:color-mix(in srgb,var(--surface2) 68%,var(--surface))!important;
  }
  body.v29-ready.v27-mobile-ui .protocol-panel .panel-head>div:first-child{
    min-width:0;
  }
  body.v29-ready.v27-mobile-ui .protocol-panel .panel-head>div:first-child>span{
    display:none!important;
  }
  body.v29-ready.v27-mobile-ui .protocol-panel .panel-head h3{
    margin:0!important;
    font-size:16px!important;
    line-height:1.45!important;
  }
  body.v29-ready.v27-mobile-ui .protocol-panel .server-tabs{
    display:none!important;
  }

  body.v29-ready.v27-mobile-ui .protocol-panel .server-views{
    display:flex!important;
    flex-direction:column!important;
    gap:10px!important;
    padding:12px!important;
  }

  body.v29-ready.v27-mobile-ui .protocol-panel .server-view,
  body.v29-ready.v27-mobile-ui .protocol-panel .server-view.v27-active-server{
    display:block!important;
    position:relative!important;
    margin:0!important;
    padding:48px 11px 11px!important;
    border:1px solid var(--line)!important;
    border-radius:14px!important;
    background:var(--surface2)!important;
  }

  body.v29-ready.v27-mobile-ui .protocol-panel .server-view:before{
    content:attr(data-v24-server-label)!important;
    position:absolute!important;
    top:0!important;
    right:0!important;
    left:0!important;
    min-height:42px!important;
    padding:0 12px!important;
    display:flex!important;
    align-items:center!important;
    border-bottom:1px solid var(--line)!important;
    color:var(--text)!important;
    font-size:13px!important;
    font-weight:900!important;
    line-height:1.4!important;
    pointer-events:none!important;
  }

  /* Modern protocols connect through their real URI/config/import actions. */
  body.v29-ready.v27-mobile-ui .protocol-panel[data-modern-protocol] .facts{
    display:none!important;
  }

  body.v29-ready.v27-mobile-ui .protocol-panel .facts{
    display:grid!important;
    grid-template-columns:1fr!important;
    gap:8px!important;
  }
  body.v29-ready.v27-mobile-ui .protocol-panel .fact{
    min-height:0!important;
    padding:10px 11px!important;
    display:grid!important;
    grid-template-columns:minmax(0,1fr) auto!important;
    grid-template-rows:auto auto!important;
    gap:4px 8px!important;
    align-items:center!important;
    border:0!important;
    border-bottom:1px solid var(--line)!important;
    border-radius:0!important;
    background:transparent!important;
    text-align:right!important;
  }
  body.v29-ready.v27-mobile-ui .protocol-panel .fact:last-child{
    border-bottom:0!important;
  }
  body.v29-ready.v27-mobile-ui .protocol-panel .fact small{
    grid-column:1 / -1!important;
    color:var(--muted)!important;
    font-size:11px!important;
  }
  body.v29-ready.v27-mobile-ui .protocol-panel .fact strong{
    grid-column:1!important;
    margin:0!important;
    font-size:13px!important;
    white-space:normal!important;
    overflow-wrap:anywhere!important;
    word-break:break-word!important;
    direction:ltr!important;
    text-align:left!important;
  }
  body.v29-ready.v27-mobile-ui .protocol-panel .fact .copy-btn{
    grid-column:2!important;
    grid-row:2!important;
    width:auto!important;
    min-width:60px!important;
  }

  body.v29-ready.v27-mobile-ui .protocol-panel .action-row,
  body.v29-ready.v27-mobile-ui .protocol-panel .v13-modern-action,
  body.v29-ready.v27-mobile-ui .protocol-panel .v13-client-only,
  body.v29-ready.v27-mobile-ui .tp-v48-xray-profile{
    margin:0!important;
    padding:0!important;
    border:0!important;
    background:transparent!important;
  }
  body.v29-ready.v27-mobile-ui .protocol-panel .action-buttons,
  body.v29-ready.v27-mobile-ui .protocol-panel .v13-action-buttons,
  body.v29-ready.v27-mobile-ui .protocol-panel .v13-client-only>div,
  body.v29-ready.v27-mobile-ui .tp-v48-profile-actions{
    width:100%!important;
    display:grid!important;
    grid-template-columns:repeat(2,minmax(0,1fr))!important;
    gap:8px!important;
  }
  body.v29-ready.v27-mobile-ui .protocol-panel .copy-btn,
  body.v29-ready.v27-mobile-ui .protocol-panel .primary-btn,
  body.v29-ready.v27-mobile-ui .protocol-panel .download-config,
  body.v29-ready.v27-mobile-ui .protocol-panel .v13-secondary,
  body.v29-ready.v27-mobile-ui .protocol-panel .v13-app,
  body.v29-ready.v27-mobile-ui .protocol-panel button,
  body.v29-ready.v27-mobile-ui .protocol-panel a{
    width:100%!important;
    min-height:42px!important;
    padding:9px 10px!important;
    font-size:12px!important;
    line-height:1.35!important;
    text-align:center!important;
  }
  body.v29-ready .advanced{
    margin-top:14px!important;
  }
  body.v29-ready .advanced summary{
    font-size:13px!important;
  }
  body.v29-ready .apps{
    margin-top:14px!important;
  }
  body.v29-ready .app-card b{
    font-size:12px!important;
  }
}

@media(max-width:390px){
  body.v29-ready.v27-mobile-ui .protocol-panel .action-buttons,
  body.v29-ready.v27-mobile-ui .protocol-panel .v13-action-buttons,
  body.v29-ready.v27-mobile-ui .protocol-panel .v13-client-only>div,
  body.v29-ready.v27-mobile-ui .tp-v48-profile-actions{
    grid-template-columns:1fr!important;
  }
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectPresentationV29">
(function(){
  const MOBILE='(max-width:720px)';
  const text=el=>String(el?.textContent||'').trim();

  function removeHeading(matchers){
    document.querySelectorAll('.section-head').forEach(head=>{
      const value=text(head);
      if(matchers.some(item=>value.includes(item)))head.remove();
    });
  }

  function simplifyHeading(){
    document.querySelectorAll('.section-head').forEach(head=>{
      const value=text(head);
      if(!value.includes('QUICK CONNECT')&&!value.includes('اتصال سریع'))return;
      const title=head.querySelector('h2');
      if(title)title.textContent='اتصال‌ها';
      head.querySelectorAll('small,p').forEach(node=>node.remove());
    });
  }

  function shortAppLabel(link){
    const raw=text(link).replace(/^دانلود\s+/,'').trim();
    if(!raw)return;
    link.textContent=raw;
  }

  function hideDuplicateActions(container){
    if(!container)return;
    const seen=new Set();
    [...container.querySelectorAll('a[href],button[data-config-path],button[data-copy]')].forEach(action=>{
      const key=action.tagName==='A'
        ?('href:'+String(action.getAttribute('href')||''))
        :(action.dataset.configPath?'config:'+action.dataset.configPath:'copy:'+String(action.dataset.copy||''));
      if(key.endsWith(':'))return;
      if(seen.has(key))action.dataset.v29Hide='1';
      else seen.add(key);
    });
  }

  function normalizeActions(){
    document.querySelectorAll('.protocol-panel .download-config,.protocol-panel .tp-v16-safe-download,.protocol-panel .v13-secondary')
      .forEach(node=>node.textContent='دانلود');

    document.querySelectorAll('.protocol-panel .v13-karing-import,.protocol-panel .v13-open-uri')
      .forEach(node=>node.textContent='اتصال');

    document.querySelectorAll('.protocol-panel .copy-btn,.protocol-panel .tp-win-v2ray-copy')
      .forEach(node=>node.textContent='کپی');

    document.querySelectorAll('.protocol-panel .v13-app').forEach(shortAppLabel);

    document.querySelectorAll('.protocol-panel button,.protocol-panel a').forEach(node=>{
      const value=text(node);
      if(/^نمایش\s*QR$/i.test(value)||value==='QR')node.dataset.v29Hide='1';
    });

    document.querySelectorAll('.v13-action-buttons,.action-buttons,.tp-win-v2ray-actions,.tp-v48-profile-actions')
      .forEach(hideDuplicateActions);

    document.querySelectorAll('.v13-action-buttons').forEach(container=>{
      const primary=container.querySelector('.primary-btn');
      const secondary=container.querySelector('.v13-secondary');
      if(!primary||!secondary)return;
      const p=text(primary);
      if(p.includes('دانلود'))secondary.dataset.v29Hide='1';
    });
  }

  function removeNoise(){
    removeHeading(['SMART CONNECT','اتصال هوشمند']);
    simplifyHeading();
    document.querySelectorAll('.smart-card,.smart-empty,.multi-link-card,.tp-win-v2ray-note')
      .forEach(node=>node.remove());
    document.querySelectorAll('.action-copy,.v13-action-copy').forEach(node=>node.remove());
  }

  function mobileCards(){
    if(!window.matchMedia(MOBILE).matches)return;
    document.querySelectorAll('.v27-connect-nav,.v28-scroll-hint').forEach(node=>node.remove());
    document.querySelectorAll('.protocol-panel.v24-canonical-panel').forEach(panel=>{
      panel.classList.remove('v27-active-protocol');
      panel.querySelectorAll('.server-view').forEach(view=>view.classList.add('v29-server-card'));
    });
    document.body.dataset.tpMobilePresentation='v29-cards';
  }

  function apply(){
    document.body.classList.add('v29-ready');
    document.body.dataset.tpPresentation='v29';
    removeNoise();
    normalizeActions();
    mobileCards();
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,180);
  window.addEventListener('resize',()=>window.setTimeout(apply,60),{passive:true});
})();
</script>
"""


def refine_public_connection_presentation_v29(source: str) -> str:
    """Make Public Connect concise and readable without changing connection data."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
