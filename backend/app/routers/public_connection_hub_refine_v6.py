from __future__ import annotations


_REFINEMENT_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_HUB_REFINEMENT_V6 */
body[data-public-connect-ui="v6"] .page{
  width:min(1080px,94vw);
  padding:18px 0 44px;
}
body[data-public-connect-ui="v6"] .topin{
  width:min(1080px,94vw);
  height:64px;
}
body[data-public-connect-ui="v6"] .mark{
  width:36px;
  height:36px;
  border-radius:11px;
}
body[data-public-connect-ui="v6"] .brand b{font-size:16px}
body[data-public-connect-ui="v6"] .avatar{width:32px;height:32px}
body[data-public-connect-ui="v6"] .theme{width:32px;height:32px}
body[data-public-connect-ui="v6"] .section-head{
  margin:22px 0 10px;
  align-items:center;
}
body[data-public-connect-ui="v6"] .section-head small,
body[data-public-connect-ui="v6"] .apps-head small{
  display:none;
}
body[data-public-connect-ui="v6"] .section-head h2{
  margin:0;
  font-size:18px;
}
body[data-public-connect-ui="v6"] .section-head p{
  max-width:560px;
  font-size:9px;
  line-height:1.8;
}
body[data-public-connect-ui="v6"] .traffic{
  grid-template-columns:150px 1fr;
  gap:14px;
  padding:14px 16px;
  border-radius:18px;
  box-shadow:0 10px 32px rgba(31,35,52,.055);
}
html[data-theme="dark"] body[data-public-connect-ui="v6"] .traffic{
  box-shadow:0 14px 34px rgba(0,0,0,.20);
}
body[data-public-connect-ui="v6"] .visual{gap:10px}
body[data-public-connect-ui="v6"] .donut{
  width:76px;
  height:76px;
  flex:0 0 76px;
}
body[data-public-connect-ui="v6"] .donut:before{inset:8px}
body[data-public-connect-ui="v6"] .donut b{font-size:16px}
body[data-public-connect-ui="v6"] .donut small{font-size:6px}
body[data-public-connect-ui="v6"] .visual h2{font-size:14px}
body[data-public-connect-ui="v6"] .visual em{margin-top:4px}
body[data-public-connect-ui="v6"] .stat{padding:2px 12px}
body[data-public-connect-ui="v6"] .stat strong{margin-top:5px;font-size:12px}
body[data-public-connect-ui="v6"] .smart-card{
  grid-template-columns:minmax(220px,.72fr) 1.28fr;
  gap:12px;
  padding:14px 16px;
  border-color:color-mix(in srgb,var(--p) 28%,var(--line));
  border-radius:18px;
  background:linear-gradient(135deg,color-mix(in srgb,var(--p) 7%,var(--surface)),var(--surface) 46%);
  box-shadow:none;
}
body[data-public-connect-ui="v6"] .eyebrow{font-size:7px}
body[data-public-connect-ui="v6"] .smart-title{margin-top:7px;gap:10px}
body[data-public-connect-ui="v6"] .smart-title h2{font-size:17px}
body[data-public-connect-ui="v6"] .smart-note{margin-top:8px;line-height:1.7}
body[data-public-connect-ui="v6"] .smart-icon,
body[data-public-connect-ui="v6"] .protocol-icon{
  color:#fff;
  background:linear-gradient(135deg,var(--p),var(--s));
  box-shadow:0 8px 20px color-mix(in srgb,var(--p) 18%,transparent);
}
body[data-public-connect-ui="v6"] .smart-icon{
  width:44px;
  height:44px;
  border-radius:13px;
}
body[data-public-connect-ui="v6"] .smart-action .action-row{
  min-height:72px;
  padding:10px 12px;
}
body[data-public-connect-ui="v6"] .smart-action .qr{display:none}
body[data-public-connect-ui="v6"] .smart-qr-btn{
  height:32px;
  padding:0 11px;
  border:1px solid color-mix(in srgb,var(--p) 30%,var(--line));
  border-radius:9px;
  background:color-mix(in srgb,var(--p) 8%,var(--surface));
  color:var(--p);
  font-size:8px;
  font-weight:900;
}
body[data-public-connect-ui="v6"] .protocol-toolbar{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  margin-bottom:10px;
  padding:8px;
  border:1px solid var(--line);
  border-radius:14px;
  background:var(--surface);
}
body[data-public-connect-ui="v6"] .protocol-toolbar-label{
  padding:0 7px;
  color:var(--muted);
  font-size:8px;
  font-weight:900;
  white-space:nowrap;
}
body[data-public-connect-ui="v6"] .protocol-filters{
  display:flex;
  flex-wrap:wrap;
  gap:6px;
}
body[data-public-connect-ui="v6"] .protocol-filter{
  height:31px;
  padding:0 11px;
  border:1px solid var(--line);
  border-radius:9px;
  background:var(--surface2);
  color:var(--muted);
  font-size:8px;
  font-weight:900;
}
body[data-public-connect-ui="v6"] .protocol-filter.active{
  border-color:color-mix(in srgb,var(--p) 40%,var(--line));
  background:color-mix(in srgb,var(--p) 10%,var(--surface));
  color:var(--p);
}
body[data-public-connect-ui="v6"] .protocol-filter[hidden]{display:none}
body[data-public-connect-ui="v6"] .protocols{
  grid-template-columns:repeat(4,minmax(0,1fr));
  gap:8px;
}
body[data-public-connect-ui="v6"] .protocol-choice{
  min-height:70px;
  padding:9px 10px;
  grid-template-columns:36px 1fr auto;
  gap:8px;
  border-radius:13px;
}
body[data-public-connect-ui="v6"] .protocol-choice.is-filtered{display:none}
body[data-public-connect-ui="v6"] .protocol-choice:not(.live-online).active{
  border-color:var(--p);
  box-shadow:0 0 0 1px color-mix(in srgb,var(--p) 18%,transparent);
}
body[data-public-connect-ui="v6"] .protocol-icon{
  width:36px;
  height:36px;
  border-radius:10px;
}
body[data-public-connect-ui="v6"] .protocol-text b{font-size:9px}
body[data-public-connect-ui="v6"] .protocol-choice:not(.live-online) em{
  color:var(--p);
  border-color:color-mix(in srgb,var(--p) 26%,transparent);
  background:color-mix(in srgb,var(--p) 6%,transparent);
}
body[data-public-connect-ui="v6"] .protocol-choice.live-online,
body[data-public-connect-ui="v6"] .protocol-choice.live-online.active{
  border-color:var(--ok);
  box-shadow:0 0 0 1px color-mix(in srgb,var(--ok) 22%,transparent);
}
body[data-public-connect-ui="v6"] .protocol-choice.live-online em{
  color:var(--ok);
  border-color:color-mix(in srgb,var(--ok) 32%,transparent);
  background:color-mix(in srgb,var(--ok) 8%,transparent);
}
body[data-public-connect-ui="v6"] .protocol-panel{
  margin-top:8px;
  border-radius:15px;
}
body[data-public-connect-ui="v6"] .panel-head{
  min-height:56px;
  padding:10px 12px;
}
body[data-public-connect-ui="v6"] .server-views{padding:10px}
body[data-public-connect-ui="v6"] .fact{
  min-height:70px;
  padding:10px;
  border-radius:10px;
}
body[data-public-connect-ui="v6"] .fact strong{margin:7px 0 6px}
body[data-public-connect-ui="v6"] .action-row{
  padding:10px 12px;
  border-radius:11px;
}
body[data-public-connect-ui="v6"] .advanced{
  margin-top:12px;
  border-radius:15px;
}
body[data-public-connect-ui="v6"] .advanced summary{padding:13px 15px}
body[data-public-connect-ui="v6"] .advanced-body{padding:0 12px 12px}
body[data-public-connect-ui="v6"] .apps{
  margin-top:14px;
  border-radius:15px;
}
body[data-public-connect-ui="v6"] .apps-head{padding:12px 14px}
body[data-public-connect-ui="v6"] .apps-head h2{margin:0;font-size:14px}
body[data-public-connect-ui="v6"] .qr-modal{
  position:fixed;
  inset:0;
  z-index:100;
  display:none;
  place-items:center;
  padding:18px;
  background:rgba(4,6,12,.68);
  backdrop-filter:blur(8px);
}
body[data-public-connect-ui="v6"] .qr-modal.open{display:grid}
body[data-public-connect-ui="v6"] .qr-modal-card{
  width:min(330px,92vw);
  padding:16px;
  border:1px solid var(--line);
  border-radius:18px;
  background:var(--surface);
  box-shadow:0 24px 70px rgba(0,0,0,.32);
  text-align:center;
}
body[data-public-connect-ui="v6"] .qr-modal-head{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  margin-bottom:12px;
}
body[data-public-connect-ui="v6"] .qr-modal-head b{font-size:12px}
body[data-public-connect-ui="v6"] .qr-close{
  width:32px;
  height:32px;
  border:1px solid var(--line);
  border-radius:9px;
  background:var(--surface2);
  color:var(--text);
  font-size:18px;
}
body[data-public-connect-ui="v6"] .qr-modal img{
  width:min(240px,72vw);
  height:auto;
  padding:8px;
  border-radius:14px;
  background:#fff;
}
body[data-public-connect-ui="v6"] .qr-modal p{
  margin:10px 0 0;
  color:var(--muted);
  font-size:8px;
  line-height:1.8;
}
@media(max-width:900px){
  body[data-public-connect-ui="v6"] .protocols{grid-template-columns:repeat(2,minmax(0,1fr))}
  body[data-public-connect-ui="v6"] .traffic{grid-template-columns:135px 1fr}
}
@media(max-width:720px){
  body[data-public-connect-ui="v6"] .topin{height:58px}
  body[data-public-connect-ui="v6"] .page{padding-top:10px}
  body[data-public-connect-ui="v6"] .traffic{grid-template-columns:1fr;padding:12px}
  body[data-public-connect-ui="v6"] .visual{justify-content:flex-start}
  body[data-public-connect-ui="v6"] .donut{width:68px;height:68px;flex-basis:68px}
  body[data-public-connect-ui="v6"] .stats{grid-template-columns:repeat(2,minmax(0,1fr))}
  body[data-public-connect-ui="v6"] .smart-card{grid-template-columns:1fr;padding:13px}
  body[data-public-connect-ui="v6"] .section-head{align-items:flex-start}
  body[data-public-connect-ui="v6"] .section-head p{display:none}
  body[data-public-connect-ui="v6"] .protocol-toolbar{align-items:flex-start;flex-direction:column}
  body[data-public-connect-ui="v6"] .protocol-filters{width:100%;overflow-x:auto;flex-wrap:nowrap;padding-bottom:2px}
  body[data-public-connect-ui="v6"] .protocol-filter{flex:0 0 auto}
  body[data-public-connect-ui="v6"] .protocols{grid-template-columns:1fr}
}
"""


_PROTOCOL_TOOLBAR = r"""
<div class="protocol-toolbar" aria-label="دسته‌بندی پروتکل‌ها">
  <span class="protocol-toolbar-label">دسته‌بندی پروتکل‌ها</span>
  <div class="protocol-filters">
    <button class="protocol-filter" type="button" data-hub-filter="recommended">پیشنهادی</button>
    <button class="protocol-filter" type="button" data-hub-filter="classic">VPN کلاسیک</button>
    <button class="protocol-filter" type="button" data-hub-filter="modern">مدرن</button>
    <button class="protocol-filter" type="button" data-hub-filter="all">همه پروتکل‌ها</button>
  </div>
</div>
"""


_QR_MODAL = r"""
<div id="hubQrModal" class="qr-modal" aria-hidden="true" role="dialog" aria-modal="true" aria-label="QR اتصال">
  <div class="qr-modal-card">
    <div class="qr-modal-head"><b>QR اتصال</b><button id="hubQrClose" class="qr-close" type="button" aria-label="بستن">×</button></div>
    <img id="hubQrImage" src="" alt="QR اتصال">
    <p>QR را داخل برنامه سازگار اسکن کنید. اطلاعات اتصال از همان کانفیگ واقعی اشتراک شماست.</p>
  </div>
</div>
"""


_REFINEMENT_SCRIPT = r"""
<script id="twinpanelPublicConnectRefinementV6">
(function(){
  const cards=[...document.querySelectorAll('.protocol-choice')];
  const buttons=[...document.querySelectorAll('[data-hub-filter]')];
  const modern=new Set(['hysteria2','tuic','anytls','vless','trojan','shadowsocks','shadowtls','mieru','naiveproxy','naive','trusttunnel','snell','sudoku']);
  const classic=new Set(['cisco','openconnect','openvpn','wireguard','l2tp']);
  const recommended=new Set(['v2ray','xray','wireguard','openvpn']);

  function key(card){return String(card.dataset.protocolKey||'').trim().toLowerCase()}
  function belongs(card,filter){
    const value=key(card);
    if(filter==='all')return true;
    if(filter==='recommended')return recommended.has(value);
    if(filter==='classic')return classic.has(value);
    if(filter==='modern')return modern.has(value);
    return true;
  }
  function has(filter){return cards.some(card=>belongs(card,filter))}
  function activateVisible(){
    const visible=cards.filter(card=>!card.classList.contains('is-filtered'));
    if(!visible.length)return;
    const active=visible.find(card=>card.classList.contains('active'));
    if(!active)visible[0].click();
  }
  function apply(filter){
    cards.forEach(card=>card.classList.toggle('is-filtered',!belongs(card,filter)));
    buttons.forEach(button=>button.classList.toggle('active',button.dataset.hubFilter===filter));
    activateVisible();
  }
  buttons.forEach(button=>{
    const filter=button.dataset.hubFilter||'all';
    if(filter!=='all'&&!has(filter))button.hidden=true;
    button.addEventListener('click',()=>apply(filter));
  });
  const initial=has('recommended')?'recommended':has('classic')?'classic':'all';
  apply(initial);

  const modal=document.getElementById('hubQrModal');
  const modalImage=document.getElementById('hubQrImage');
  const close=document.getElementById('hubQrClose');
  function closeQr(){if(!modal)return;modal.classList.remove('open');modal.setAttribute('aria-hidden','true');if(modalImage)modalImage.src=''}
  function openQr(src){if(!modal||!modalImage||!src)return;modalImage.src=src;modal.classList.add('open');modal.setAttribute('aria-hidden','false');if(close)close.focus()}
  document.querySelectorAll('.smart-action .qr').forEach(image=>{
    const src=image.getAttribute('src')||'';
    const row=image.closest('.action-row');
    if(!row||!src)return;
    image.remove();
    let actions=row.querySelector('.action-buttons');
    if(!actions){actions=document.createElement('div');actions.className='action-buttons';row.appendChild(actions)}
    const button=document.createElement('button');
    button.type='button';
    button.className='smart-qr-btn';
    button.textContent='نمایش QR';
    button.addEventListener('click',()=>openQr(src));
    actions.appendChild(button);
  });
  if(close)close.addEventListener('click',closeQr);
  if(modal)modal.addEventListener('click',event=>{if(event.target===modal)closeQr()});
  document.addEventListener('keydown',event=>{if(event.key==='Escape')closeQr()});
})();
</script>
"""


def refine_public_connection_hub_html(source: str) -> str:
    """Refine the already-rendered V5/V4-live page without changing delivery data."""
    if "TWINPANEL_PUBLIC_CONNECT_HUB_REFINEMENT_V6" in source:
        return source

    source = source.replace(
        "<body>",
        '<body data-public-connect-ui="v6">',
        1,
    )
    source = source.replace(
        "</style>",
        _REFINEMENT_CSS + "\n</style>",
        1,
    )
    source = source.replace(
        '<section class="protocols">',
        _PROTOCOL_TOOLBAR + '\n<section class="protocols">',
        1,
    )
    source = source.replace(
        '<div id="toast" class="toast">',
        _QR_MODAL + '\n<div id="toast" class="toast">',
        1,
    )
    source = source.replace(
        "</body>",
        _REFINEMENT_SCRIPT + "\n</body>",
        1,
    )
    return source
