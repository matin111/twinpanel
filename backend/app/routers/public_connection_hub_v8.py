from __future__ import annotations


_V8_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_HUB_V8 */
body[data-public-connect-mobile="v7"] .v8-app-launch{
  display:none;
}

@media(max-width:720px){
  body[data-public-connect-mobile="v7"]{
    background:var(--bg);
  }
  body[data-public-connect-mobile="v7"] .top{
    position:sticky;
    top:0;
    box-shadow:0 1px 0 var(--line);
  }
  body[data-public-connect-mobile="v7"] .topin{
    width:100%;
    height:54px;
    padding:0 12px;
  }
  body[data-public-connect-mobile="v7"] .brand b{font-size:14px}
  body[data-public-connect-mobile="v7"] .mark{
    width:32px;
    height:32px;
    border-radius:10px;
  }
  body[data-public-connect-mobile="v7"] .theme{
    width:30px;
    height:30px;
    border-radius:9px;
  }
  body[data-public-connect-mobile="v7"] .page{
    width:100%;
    max-width:640px;
    padding:10px 12px 30px;
  }
  body[data-public-connect-mobile="v7"] .traffic{
    display:block;
    padding:11px;
    border-radius:16px;
    box-shadow:none;
  }
  body[data-public-connect-mobile="v7"] .visual{
    justify-content:space-between;
    gap:8px;
  }
  body[data-public-connect-mobile="v7"] .donut{
    width:58px;
    height:58px;
    flex:0 0 58px;
  }
  body[data-public-connect-mobile="v7"] .donut:before{inset:7px}
  body[data-public-connect-mobile="v7"] .donut b{font-size:13px}
  body[data-public-connect-mobile="v7"] .donut small{font-size:6px}
  body[data-public-connect-mobile="v7"] .visual h2{font-size:13px}
  body[data-public-connect-mobile="v7"] .stats{
    margin-top:9px;
    display:grid;
    grid-template-columns:repeat(3,minmax(0,1fr));
    gap:6px;
  }
  body[data-public-connect-mobile="v7"] .stat{
    min-width:0;
    padding:7px 4px;
    border:1px solid var(--line);
    border-radius:10px;
    background:var(--surface2);
    text-align:center;
  }
  body[data-public-connect-mobile="v7"] .stat small{font-size:6px}
  body[data-public-connect-mobile="v7"] .stat strong{
    margin-top:3px;
    font-size:9px;
    white-space:nowrap;
  }
  body[data-public-connect-mobile="v7"] .section-head{
    margin:15px 2px 7px;
  }
  body[data-public-connect-mobile="v7"] .section-head small,
  body[data-public-connect-mobile="v7"] .section-head p{display:none}
  body[data-public-connect-mobile="v7"] .section-head h2{
    margin:0;
    font-size:15px;
  }
  body[data-public-connect-mobile="v7"] .smart-card{
    display:block;
    padding:10px;
    border-radius:15px;
    box-shadow:none;
  }
  body[data-public-connect-mobile="v7"] .smart-copy{display:none}
  body[data-public-connect-mobile="v7"] .smart-action{width:100%}
  body[data-public-connect-mobile="v7"] .smart-action .action-row{
    padding:9px;
    border:0;
    background:transparent;
  }
  body[data-public-connect-mobile="v7"] .protocol-toolbar{
    margin:0 0 7px;
    padding:4px;
    border-radius:11px;
    overflow-x:auto;
    scrollbar-width:none;
  }
  body[data-public-connect-mobile="v7"] .protocol-toolbar::-webkit-scrollbar{display:none}
  body[data-public-connect-mobile="v7"] .protocol-toolbar-label{display:none}
  body[data-public-connect-mobile="v7"] .protocol-filters{
    width:max-content;
    flex-wrap:nowrap;
    gap:4px;
  }
  body[data-public-connect-mobile="v7"] .protocol-filter{
    height:28px;
    padding:0 9px;
    font-size:7px;
    border-radius:8px;
  }
  body[data-public-connect-mobile="v7"] .protocols{
    display:flex;
    gap:7px;
    overflow-x:auto;
    scroll-snap-type:x proximity;
    padding:1px 0 5px;
    scrollbar-width:none;
  }
  body[data-public-connect-mobile="v7"] .protocols::-webkit-scrollbar{display:none}
  body[data-public-connect-mobile="v7"] .protocol-choice{
    flex:0 0 132px;
    min-height:60px;
    padding:8px;
    border-radius:13px;
    grid-template-columns:34px 1fr;
    gap:7px;
    scroll-snap-align:start;
  }
  body[data-public-connect-mobile="v7"] .protocol-icon{
    width:34px;
    height:34px;
    border-radius:10px;
    font-size:11px;
  }
  body[data-public-connect-mobile="v7"] .protocol-text b{font-size:8.5px}
  body[data-public-connect-mobile="v7"] .protocol-text small{font-size:6px}
  body[data-public-connect-mobile="v7"] .protocol-choice em{display:none}
  body[data-public-connect-mobile="v7"] .protocol-panel{
    margin-top:5px;
    border-radius:15px;
    overflow:hidden;
  }
  body[data-public-connect-mobile="v7"] .panel-head{
    min-height:auto;
    padding:9px 10px;
    gap:7px;
    flex-direction:row;
    align-items:center;
  }
  body[data-public-connect-mobile="v7"] .panel-head>div:first-child span{display:none}
  body[data-public-connect-mobile="v7"] .panel-head h3{font-size:12px;margin:0}
  body[data-public-connect-mobile="v7"] .server-tabs{
    margin-right:auto;
    width:auto;
    max-width:68%;
  }
  body[data-public-connect-mobile="v7"] .server-tab{
    height:27px;
    padding:0 8px;
    font-size:7px;
  }
  body[data-public-connect-mobile="v7"] .server-views{padding:8px}
  body[data-public-connect-mobile="v7"] .action-row{
    padding:0;
    border:0;
    background:transparent;
    gap:7px;
  }
  body[data-public-connect-mobile="v7"] .action-copy,
  body[data-public-connect-mobile="v7"] .action-row>.qr{
    display:none;
  }
  body[data-public-connect-mobile="v7"] .action-buttons{
    display:none;
  }
  body[data-public-connect-mobile="v7"] .v8-app-launch{
    width:100%;
    display:block;
    border:1px solid var(--line);
    border-radius:14px;
    background:var(--surface2);
    overflow:hidden;
  }
  body[data-public-connect-mobile="v7"] .v8-app-head{
    display:flex;
    align-items:center;
    gap:10px;
    padding:10px;
  }
  body[data-public-connect-mobile="v7"] .v8-app-icon{
    width:40px;
    height:40px;
    flex:0 0 40px;
    display:grid;
    place-items:center;
    border-radius:12px;
    color:#fff;
    font-weight:900;
    font-size:13px;
    background:linear-gradient(135deg,var(--p),var(--s));
    box-shadow:0 8px 20px color-mix(in srgb,var(--p) 22%,transparent);
  }
  body[data-public-connect-mobile="v7"] .v8-app-copy{
    min-width:0;
    flex:1;
  }
  body[data-public-connect-mobile="v7"] .v8-app-copy b{
    display:block;
    font-size:10px;
  }
  body[data-public-connect-mobile="v7"] .v8-app-copy small{
    display:block;
    margin-top:3px;
    color:var(--muted);
    font-size:7px;
    line-height:1.65;
  }
  body[data-public-connect-mobile="v7"] .v8-primary{
    width:100%;
    height:42px;
    border:0;
    border-top:1px solid color-mix(in srgb,var(--p) 18%,var(--line));
    background:linear-gradient(135deg,var(--p),var(--s));
    color:#fff;
    font-size:9px;
    font-weight:900;
    display:flex;
    align-items:center;
    justify-content:center;
    gap:7px;
  }
  body[data-public-connect-mobile="v7"] .v8-tools{
    display:flex;
    gap:1px;
    border-top:1px solid var(--line);
    background:var(--line);
  }
  body[data-public-connect-mobile="v7"] .v8-tools button{
    flex:1;
    min-height:34px;
    padding:6px 4px;
    border:0;
    background:var(--surface);
    color:var(--muted);
    font-size:7px;
    font-weight:900;
  }
  body[data-public-connect-mobile="v7"] .v8-http-note{
    display:none;
    padding:7px 9px;
    color:var(--muted);
    font-size:6.5px;
    line-height:1.7;
    background:color-mix(in srgb,var(--p) 4%,var(--surface));
    border-top:1px solid var(--line);
  }
  body[data-public-connect-mobile="v7"].v8-insecure .v8-http-note{display:block}
  body[data-public-connect-mobile="v7"] .multi-link-card{
    margin-top:9px;
    padding:10px;
    border-radius:14px;
    gap:8px;
  }
  body[data-public-connect-mobile="v7"] .multi-link-copy small{display:none}
  body[data-public-connect-mobile="v7"] .multi-link-copy h3{font-size:12px;margin:0 0 3px}
  body[data-public-connect-mobile="v7"] .multi-link-copy p{font-size:7px;line-height:1.65}
  body[data-public-connect-mobile="v7"] .multi-link-actions{
    display:grid;
    grid-template-columns:repeat(2,minmax(0,1fr));
    gap:5px;
  }
  body[data-public-connect-mobile="v7"] .multi-link-actions>*{
    width:100%;
    min-height:31px;
    font-size:7px;
  }
  body[data-public-connect-mobile="v7"] .apps{
    margin-top:10px;
    border-radius:15px;
  }
  body[data-public-connect-mobile="v7"] .apps-head{
    padding:10px;
  }
  body[data-public-connect-mobile="v7"] .apps-head small{display:none}
  body[data-public-connect-mobile="v7"] .apps-head h2{font-size:12px;margin:0}
  body[data-public-connect-mobile="v7"] .tools{gap:4px}
  body[data-public-connect-mobile="v7"] .device,
  body[data-public-connect-mobile="v7"] .allbtn{
    height:27px;
    padding:0 8px;
    font-size:7px;
  }
  body[data-public-connect-mobile="v7"] .platforms{padding:8px}
  body[data-public-connect-mobile="v7"] .platform-title{margin-bottom:7px}
  body[data-public-connect-mobile="v7"] .app-grid{
    display:flex;
    overflow-x:auto;
    gap:7px;
    scrollbar-width:none;
  }
  body[data-public-connect-mobile="v7"] .app-grid::-webkit-scrollbar{display:none}
  body[data-public-connect-mobile="v7"] .app-card{
    flex:0 0 150px;
    min-height:52px;
    padding:8px;
    border-radius:11px;
    grid-template-columns:28px 1fr;
    gap:7px;
  }
  body[data-public-connect-mobile="v7"] .app-card>span{
    width:28px;
    height:28px;
    border-radius:8px;
  }
}
"""


_V8_SCRIPT = r"""
<script id="twinpanelPublicConnectHubV8">
(function(){
  const body=document.body;
  const toast=document.getElementById('toast');
  const isMobile=/android|iphone|ipad|ipod|mobile/i.test(navigator.userAgent||'')||window.matchMedia('(max-width:720px)').matches;
  if(!window.isSecureContext)body.classList.add('v8-insecure');
  function notify(text){
    if(!toast)return;
    toast.textContent=text;
    toast.classList.add('show');
    clearTimeout(window.__v8Toast);
    window.__v8Toast=setTimeout(()=>toast.classList.remove('show'),1600);
  }
  async function copy(value){
    if(navigator.clipboard&&window.isSecureContext){
      try{await navigator.clipboard.writeText(value);return true}catch(_error){}
    }
    const area=document.createElement('textarea');
    area.value=value;area.style.position='fixed';area.style.opacity='0';document.body.appendChild(area);area.select();
    let ok=false;try{ok=document.execCommand('copy')}catch(_error){}area.remove();return ok;
  }
  function openQr(src){
    const modal=document.getElementById('hubQrModal');
    const image=document.getElementById('hubQrImage');
    if(!modal||!image||!src)return false;
    image.src=src;
    modal.classList.add('open');
    modal.setAttribute('aria-hidden','false');
    return true;
  }
  function protocolFor(panel){
    const choice=document.querySelector('.protocol-choice[data-protocol="'+CSS.escape(panel.id)+'"]');
    return String(choice?.dataset.protocolKey||'').toLowerCase();
  }
  function label(protocol){
    if(protocol==='openvpn')return['O','OpenVPN Connect','پروفایل آماده است؛ با یک لمس برای Import ارسال می‌شود.'];
    if(protocol==='wireguard')return['W','WireGuard','کانفیگ واقعی آماده است؛ Import از فایل یا Share سیستم انجام می‌شود.'];
    if(protocol==='v2ray'||protocol==='xray')return['V','V2Ray / Xray','لینک واقعی همین سرور مستقیماً به کلاینت سازگار تحویل می‌شود.'];
    return['↗','برنامه اتصال','اطلاعات اتصال همین پروتکل آماده است.'];
  }
  function buildLaunch(view,panel){
    if(view.querySelector('.v8-app-launch'))return;
    const protocol=protocolFor(panel);
    const [mark,name,help]=label(protocol);
    const download=view.querySelector('.download-config');
    const share=view.querySelector('.mobile-send-config');
    const direct=view.querySelector('a.primary-btn[href]');
    const qr=view.querySelector('.qr');
    if(!download&&!direct)return;
    const card=document.createElement('section');card.className='v8-app-launch';
    const head=document.createElement('div');head.className='v8-app-head';
    head.innerHTML='<span class="v8-app-icon">'+mark+'</span><div class="v8-app-copy"><b>'+name+'</b><small>'+help+'</small></div>';
    card.appendChild(head);
    const primary=document.createElement(direct?'a':'button');
    primary.className='v8-primary';
    if(direct){
      primary.href=direct.getAttribute('href')||'#';
      primary.rel='noopener noreferrer';
      primary.textContent='باز کردن در برنامه';
    }else{
      primary.type='button';
      primary.textContent=protocol==='openvpn'?'وارد کردن در OpenVPN Connect':'وارد کردن در WireGuard';
      primary.addEventListener('click',()=>{
        if(isMobile&&share){share.click();return}
        if(download)download.click();
      });
    }
    card.appendChild(primary);
    const tools=document.createElement('div');tools.className='v8-tools';
    const copyBtn=document.createElement('button');copyBtn.type='button';copyBtn.textContent='کپی';
    copyBtn.addEventListener('click',async()=>{
      if(direct){notify(await copy(direct.getAttribute('href')||'')?'کپی شد':'کپی انجام نشد');return}
      const source=document.getElementById(download?.dataset.target||'');
      notify(await copy(source?.value||'')?'کانفیگ کپی شد':'کپی انجام نشد');
    });
    const fileBtn=document.createElement('button');fileBtn.type='button';fileBtn.textContent=download?'دانلود فایل':'اشتراک';
    fileBtn.addEventListener('click',()=>{
      if(download){download.click();return}
      const multi=document.querySelector('[data-v7-share-url]');if(multi)multi.click();
    });
    tools.append(copyBtn,fileBtn);
    if(qr){
      const qrBtn=document.createElement('button');qrBtn.type='button';qrBtn.textContent='QR';
      qrBtn.addEventListener('click',()=>openQr(qr.getAttribute('src')||''));
      tools.appendChild(qrBtn);
    }
    card.appendChild(tools);
    const note=document.createElement('div');note.className='v8-http-note';note.textContent='برای Share مستقیم به برنامه، دامنه HTTPS بهترین تجربه را می‌دهد؛ روی HTTP دانلود/کپی به‌عنوان مسیر امن استفاده می‌شود.';card.appendChild(note);
    view.appendChild(card);
  }
  document.querySelectorAll('.protocol-panel').forEach(panel=>panel.querySelectorAll('.server-view').forEach(view=>buildLaunch(view,panel)));
})();
</script>
"""


def refine_public_connection_hub_v8(source: str) -> str:
    """Apply the mobile-first V8 presentation layer without touching delivery data."""
    if "TWINPANEL_PUBLIC_CONNECT_HUB_V8" in source:
        return source
    source = source.replace("</style>", _V8_CSS + "\n</style>", 1)
    source = source.replace("</body>", _V8_SCRIPT + "\n</body>", 1)
    return source
