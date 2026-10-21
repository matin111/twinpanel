from __future__ import annotations

import html
import re
from urllib.parse import quote


_V8_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_HUB_V8 */
@media (max-width:720px){
  body[data-public-connect-mobile="v7"] .page{width:min(100%,640px);padding:10px 12px 28px}
  body[data-public-connect-mobile="v7"] .topin{height:56px;width:100%;padding:0 12px}
  body[data-public-connect-mobile="v7"] .brand b{font-size:14px}
  body[data-public-connect-mobile="v7"] .mark{width:34px;height:34px;border-radius:11px}
  body[data-public-connect-mobile="v7"] .theme{width:32px;height:32px;border-radius:10px}
  body[data-public-connect-mobile="v7"] .traffic{display:block;padding:12px;border-radius:18px;box-shadow:none}
  body[data-public-connect-mobile="v7"] .visual{justify-content:space-between;gap:10px}
  body[data-public-connect-mobile="v7"] .donut{width:64px;height:64px;flex-basis:64px}
  body[data-public-connect-mobile="v7"] .donut:before{inset:7px}
  body[data-public-connect-mobile="v7"] .donut b{font-size:14px}
  body[data-public-connect-mobile="v7"] .visual h2{font-size:14px}
  body[data-public-connect-mobile="v7"] .stats{margin-top:10px;grid-template-columns:repeat(3,1fr);gap:6px}
  body[data-public-connect-mobile="v7"] .stat{padding:8px 5px;border:1px solid var(--line);border-radius:10px;background:var(--surface2);text-align:center}
  body[data-public-connect-mobile="v7"] .stat:nth-child(4),
  body[data-public-connect-mobile="v7"] .stat:nth-child(5){grid-column:span 1}
  body[data-public-connect-mobile="v7"] .stat small{font-size:7px}
  body[data-public-connect-mobile="v7"] .stat strong{font-size:10px;margin-top:4px}
  body[data-public-connect-mobile="v7"] .section-head{margin:16px 2px 8px}
  body[data-public-connect-mobile="v7"] .section-head small{display:none}
  body[data-public-connect-mobile="v7"] .section-head h2{font-size:16px;margin:0}
  body[data-public-connect-mobile="v7"] .section-head p{display:none}
  body[data-public-connect-mobile="v7"] .smart-card{padding:12px;border-radius:16px;gap:10px}
  body[data-public-connect-mobile="v7"] .smart-copy{display:none}
  body[data-public-connect-mobile="v7"] .smart-action{width:100%}
  body[data-public-connect-mobile="v7"] .hub-filter-bar{padding:5px;border-radius:12px;margin:8px 0;gap:5px}
  body[data-public-connect-mobile="v7"] .hub-filter{height:32px;padding:0 11px;font-size:8px}
  body[data-public-connect-mobile="v7"] .protocols{grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}
  body[data-public-connect-mobile="v7"] .protocol-choice{min-height:62px;padding:8px;border-radius:13px;grid-template-columns:34px 1fr;gap:8px}
  body[data-public-connect-mobile="v7"] .protocol-icon{width:34px;height:34px;border-radius:10px;font-size:12px}
  body[data-public-connect-mobile="v7"] .protocol-text b{font-size:9px}
  body[data-public-connect-mobile="v7"] .protocol-text small{font-size:6.5px}
  body[data-public-connect-mobile="v7"] .protocol-choice em{display:none}
  body[data-public-connect-mobile="v7"] .protocol-panel{margin-top:8px;border-radius:16px}
  body[data-public-connect-mobile="v7"] .panel-head{min-height:auto;padding:10px 11px;gap:8px}
  body[data-public-connect-mobile="v7"] .panel-head h3{font-size:13px}
  body[data-public-connect-mobile="v7"] .server-views{padding:10px}
  body[data-public-connect-mobile="v7"] .action-row{padding:11px;border-radius:14px;gap:8px;background:var(--surface2)}
  body[data-public-connect-mobile="v7"] .action-copy b{font-size:10px}
  body[data-public-connect-mobile="v7"] .action-copy small{font-size:7px;line-height:1.7}
  body[data-public-connect-mobile="v7"] .v8-primary-action{height:42px;width:100%;border:0;border-radius:12px;background:linear-gradient(135deg,var(--p),var(--s));color:#fff;font-size:10px;font-weight:900;display:flex;align-items:center;justify-content:center;gap:8px}
  body[data-public-connect-mobile="v7"] .v8-secondary-actions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;width:100%;margin-top:7px}
  body[data-public-connect-mobile="v7"] .v8-secondary-actions>*{height:32px;width:100%;font-size:7.5px;border-radius:9px}
  body[data-public-connect-mobile="v7"] .qr{width:72px;height:72px}
  body[data-public-connect-mobile="v7"] .multi-link-card{padding:12px;border-radius:16px;margin-top:10px}
  body[data-public-connect-mobile="v7"] .multi-link-copy h3{font-size:13px}
  body[data-public-connect-mobile="v7"] .multi-link-copy p{font-size:7.5px;line-height:1.8}
  body[data-public-connect-mobile="v7"] .multi-link-actions{display:grid;grid-template-columns:1fr 1fr;gap:6px;width:100%}
  body[data-public-connect-mobile="v7"] .multi-link-actions>*{width:100%;height:34px}
  body[data-public-connect-mobile="v7"] .apps{margin-top:10px;border-radius:16px}
  body[data-public-connect-mobile="v7"] .apps-head{padding:11px}
  body[data-public-connect-mobile="v7"] .apps-head small{display:none}
  body[data-public-connect-mobile="v7"] .apps-head h2{font-size:13px;margin:0}
  body[data-public-connect-mobile="v7"] .platforms{padding:10px}
  body[data-public-connect-mobile="v7"] .app-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}
  body[data-public-connect-mobile="v7"] .app-card{min-height:54px;padding:8px;border-radius:11px;grid-template-columns:28px 1fr;gap:7px}
  body[data-public-connect-mobile="v7"] .app-card>span{width:28px;height:28px;border-radius:8px}
}
"""


_V8_SCRIPT = r"""
<script>
(function(){
  function mobile(){return /android|iphone|ipad|ipod/i.test(navigator.userAgent||'')}
  function toast(message){
    const node=document.getElementById('toast');
    if(!node)return;
    node.textContent=message;node.classList.add('show');
    clearTimeout(window.__v8Toast);window.__v8Toast=setTimeout(()=>node.classList.remove('show'),1500);
  }
  function configFrom(button){
    const target=document.getElementById(button.dataset.target||'');
    return target?String(target.value||''):'';
  }
  async function shareFile(button,protocol){
    const content=configFrom(button);
    if(!content)return;
    const filename=button.dataset.filename||((protocol==='openvpn')?'profile.ovpn':'wireguard.conf');
    const type=protocol==='openvpn'?'application/x-openvpn-profile':'text/plain';
    const file=new File([content],filename,{type});
    if(window.isSecureContext&&navigator.share&&(!navigator.canShare||navigator.canShare({files:[file]}))){
      try{await navigator.share({files:[file],title:protocol==='openvpn'?'OpenVPN profile':'WireGuard config'});return}catch(error){if(error&&error.name==='AbortError')return}
    }
    button.click();
  }
  document.querySelectorAll('.server-view').forEach(view=>{
    const panel=view.closest('.protocol-panel');
    if(!panel)return;
    const title=(panel.querySelector('.panel-head h3')?.textContent||'').toLowerCase();
    const download=view.querySelector('.download-config');
    const row=view.querySelector('.action-row');
    if(!row)return;
    if(download&&(title.includes('openvpn')||title.includes('wireguard'))){
      const protocol=title.includes('openvpn')?'openvpn':'wireguard';
      const primary=document.createElement('button');
      primary.type='button';
      primary.className='v8-primary-action';
      primary.textContent=protocol==='openvpn'?'باز کردن در OpenVPN Connect':'باز کردن در WireGuard';
      primary.addEventListener('click',async()=>{
        if(mobile())await shareFile(download,protocol);else download.click();
      });
      const secondary=document.createElement('div');secondary.className='v8-secondary-actions';
      const qr=view.querySelector('.qr');
      if(qr){const q=document.createElement('button');q.type='button';q.className='copy-btn';q.textContent='QR';q.onclick=()=>qr.scrollIntoView({behavior:'smooth',block:'center'});secondary.appendChild(q)}
      const clone=download.cloneNode(true);clone.textContent='دانلود فایل';secondary.appendChild(clone);
      row.appendChild(primary);row.appendChild(secondary);
    }
    const open=row.querySelector('a.primary-btn[href]');
    if(open&&!download){
      open.classList.add('v8-primary-action');
      open.textContent='باز کردن در برنامه';
    }
  });
})();
</script>
"""


def refine_public_connection_hub_v8(source: str) -> str:
    if "TWINPANEL_PUBLIC_CONNECT_HUB_V8" in source:
        return source
    source = source.replace("</style>", _V8_CSS + "\n</style>", 1)
    source = source.replace("</body>", _V8_SCRIPT + "\n</body>", 1)
    return source
