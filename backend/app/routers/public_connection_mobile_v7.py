from __future__ import annotations

import html
import re
from urllib.parse import quote


_MOBILE_V7_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_MOBILE_V7 */
body[data-public-connect-mobile="v7"] .multi-link-card{
  margin-top:12px;
  padding:14px 16px;
  border:1px solid color-mix(in srgb,var(--p) 28%,var(--line));
  border-radius:15px;
  background:linear-gradient(135deg,color-mix(in srgb,var(--p) 7%,var(--surface)),var(--surface) 48%);
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:14px;
}
body[data-public-connect-mobile="v7"] .multi-link-copy{min-width:0}
body[data-public-connect-mobile="v7"] .multi-link-copy small{
  color:var(--p);
  font-size:7px;
  font-weight:900;
}
body[data-public-connect-mobile="v7"] .multi-link-copy h3{
  margin:5px 0 4px;
  font-size:14px;
}
body[data-public-connect-mobile="v7"] .multi-link-copy p{
  margin:0;
  color:var(--muted);
  font-size:8px;
  line-height:1.8;
}
body[data-public-connect-mobile="v7"] .multi-link-actions{
  display:flex;
  align-items:center;
  flex-wrap:wrap;
  justify-content:flex-end;
  gap:7px;
}
body[data-public-connect-mobile="v7"] .mobile-send-btn{
  height:32px;
  padding:0 11px;
  border:1px solid color-mix(in srgb,var(--p) 32%,var(--line));
  border-radius:9px;
  background:color-mix(in srgb,var(--p) 8%,var(--surface));
  color:var(--p);
  font-size:8px;
  font-weight:900;
}
body[data-public-connect-mobile="v7"] .mobile-send-config,
body[data-public-connect-mobile="v7"] .mobile-send-link{display:none}

@media(max-width:720px){
  body[data-public-connect-mobile="v7"] .topin{
    width:96vw;
    height:52px;
    gap:8px;
  }
  body[data-public-connect-mobile="v7"] .brand{gap:7px}
  body[data-public-connect-mobile="v7"] .mark{
    width:30px;
    height:30px;
    border-radius:9px;
  }
  body[data-public-connect-mobile="v7"] .brand b{font-size:14px}
  body[data-public-connect-mobile="v7"] .avatar,
  body[data-public-connect-mobile="v7"] .theme{
    width:29px;
    height:29px;
  }
  body[data-public-connect-mobile="v7"] .page{
    width:96vw;
    padding:8px 0 26px;
  }
  body[data-public-connect-mobile="v7"] .traffic{
    padding:9px 10px;
    gap:7px;
    border-radius:14px;
  }
  body[data-public-connect-mobile="v7"] .visual{
    gap:8px;
    justify-content:flex-start;
  }
  body[data-public-connect-mobile="v7"] .donut{
    width:52px;
    height:52px;
    flex-basis:52px;
  }
  body[data-public-connect-mobile="v7"] .donut:before{inset:6px}
  body[data-public-connect-mobile="v7"] .donut b{font-size:12px}
  body[data-public-connect-mobile="v7"] .visual h2{font-size:12px}
  body[data-public-connect-mobile="v7"] .stats{
    grid-template-columns:repeat(3,minmax(0,1fr));
    gap:0;
  }
  body[data-public-connect-mobile="v7"] .stat{
    min-width:0;
    padding:6px 5px;
    border-left:0;
    border-bottom:1px solid var(--line);
  }
  body[data-public-connect-mobile="v7"] .stat:nth-last-child(-n+2){border-bottom:0}
  body[data-public-connect-mobile="v7"] .stat small{font-size:6px}
  body[data-public-connect-mobile="v7"] .stat strong{
    margin-top:3px;
    font-size:9px;
    white-space:nowrap;
  }
  body[data-public-connect-mobile="v7"] .section-head{
    margin:14px 0 6px;
  }
  body[data-public-connect-mobile="v7"] .section-head h2{font-size:15px}
  body[data-public-connect-mobile="v7"] .smart-card{
    padding:10px;
    gap:7px;
    border-radius:14px;
  }
  body[data-public-connect-mobile="v7"] .smart-icon{
    width:36px;
    height:36px;
    border-radius:10px;
  }
  body[data-public-connect-mobile="v7"] .smart-title{margin-top:4px;gap:8px}
  body[data-public-connect-mobile="v7"] .smart-title h2{font-size:14px}
  body[data-public-connect-mobile="v7"] .smart-note{display:none}
  body[data-public-connect-mobile="v7"] .smart-action .action-row{
    min-height:0;
    padding:8px;
  }
  body[data-public-connect-mobile="v7"] .action-copy b{font-size:9px}
  body[data-public-connect-mobile="v7"] .action-copy small{font-size:7px}
  body[data-public-connect-mobile="v7"] .protocol-toolbar{
    margin-bottom:7px;
    padding:5px;
    border-radius:11px;
  }
  body[data-public-connect-mobile="v7"] .protocol-toolbar-label{display:none}
  body[data-public-connect-mobile="v7"] .protocol-filters{gap:5px}
  body[data-public-connect-mobile="v7"] .protocol-filter{
    height:27px;
    padding:0 9px;
    font-size:7px;
  }
  body[data-public-connect-mobile="v7"] .protocols{
    grid-template-columns:repeat(2,minmax(0,1fr));
    gap:6px;
  }
  body[data-public-connect-mobile="v7"] .protocol-choice{
    min-height:56px;
    padding:7px;
    grid-template-columns:30px 1fr;
    gap:6px;
  }
  body[data-public-connect-mobile="v7"] .protocol-choice em{display:none}
  body[data-public-connect-mobile="v7"] .protocol-icon{
    width:30px;
    height:30px;
    border-radius:8px;
    font-size:10px;
  }
  body[data-public-connect-mobile="v7"] .protocol-text b{font-size:8px}
  body[data-public-connect-mobile="v7"] .protocol-text small{font-size:6px}
  body[data-public-connect-mobile="v7"] .protocol-panel{
    margin-top:6px;
    border-radius:12px;
  }
  body[data-public-connect-mobile="v7"] .panel-head{
    min-height:44px;
    padding:8px;
    gap:7px;
  }
  body[data-public-connect-mobile="v7"] .panel-head h3{font-size:11px}
  body[data-public-connect-mobile="v7"] .server-tabs{gap:4px}
  body[data-public-connect-mobile="v7"] .server-tab{
    height:27px;
    padding:0 8px;
    font-size:7px;
  }
  body[data-public-connect-mobile="v7"] .server-views{padding:7px}
  body[data-public-connect-mobile="v7"] .action-row{
    gap:7px;
    padding:8px;
    border-radius:9px;
  }
  body[data-public-connect-mobile="v7"] .action-buttons{gap:5px}
  body[data-public-connect-mobile="v7"] .copy-btn,
  body[data-public-connect-mobile="v7"] .primary-btn,
  body[data-public-connect-mobile="v7"] .mobile-send-btn{
    min-height:30px;
    height:auto;
    padding:7px 9px;
    font-size:7px;
  }
  body[data-public-connect-mobile="v7"] .mobile-send-config,
  body[data-public-connect-mobile="v7"] .mobile-send-link{display:inline-flex}
  body[data-public-connect-mobile="v7"] .multi-link-card{
    margin-top:8px;
    padding:10px;
    border-radius:12px;
    align-items:stretch;
    flex-direction:column;
    gap:8px;
  }
  body[data-public-connect-mobile="v7"] .multi-link-copy h3{font-size:12px}
  body[data-public-connect-mobile="v7"] .multi-link-copy p{font-size:7px}
  body[data-public-connect-mobile="v7"] .multi-link-actions{
    justify-content:stretch;
    display:grid;
    grid-template-columns:repeat(2,minmax(0,1fr));
  }
  body[data-public-connect-mobile="v7"] .multi-link-actions>*{width:100%}
  body[data-public-connect-mobile="v7"] .apps{margin-top:10px;border-radius:12px}
  body[data-public-connect-mobile="v7"] .apps-head{padding:9px 10px}
  body[data-public-connect-mobile="v7"] .apps-head h2{font-size:12px}
  body[data-public-connect-mobile="v7"] .platforms{padding:8px}
  body[data-public-connect-mobile="v7"] .app-grid{
    grid-template-columns:repeat(2,minmax(0,1fr));
    gap:6px;
  }
  body[data-public-connect-mobile="v7"] .app-card{
    min-height:52px;
    padding:7px;
    grid-template-columns:28px 1fr;
    gap:6px;
  }
  body[data-public-connect-mobile="v7"] .app-card>span{
    width:28px;
    height:28px;
  }
}

@media(max-width:380px){
  body[data-public-connect-mobile="v7"] .stats{grid-template-columns:repeat(2,minmax(0,1fr))}
  body[data-public-connect-mobile="v7"] .protocols{grid-template-columns:1fr 1fr}
  body[data-public-connect-mobile="v7"] .app-grid{grid-template-columns:1fr}
}
"""


_MOBILE_V7_SCRIPT = r"""
<script id="twinpanelPublicConnectMobileV7">
(function(){
  const toast=document.getElementById('toast');
  function notify(text){
    if(!toast)return;
    toast.textContent=text;
    toast.classList.add('show');
    clearTimeout(window.__mobileV7Toast);
    window.__mobileV7Toast=setTimeout(()=>toast.classList.remove('show'),1800);
  }
  function isMobile(){
    return /android|iphone|ipad|ipod|mobile/i.test(navigator.userAgent||'') || window.matchMedia('(max-width:720px)').matches;
  }
  function absolute(value){
    try{return new URL(value,window.location.href).href}catch(_error){return value}
  }
  function fallbackCopy(value){
    const area=document.createElement('textarea');
    area.value=value;
    area.style.position='fixed';
    area.style.opacity='0';
    document.body.appendChild(area);
    area.select();
    let ok=false;
    try{ok=document.execCommand('copy')}catch(_error){}
    area.remove();
    return ok;
  }
  async function copy(value){
    if(navigator.clipboard&&window.isSecureContext){
      try{await navigator.clipboard.writeText(value);return true}catch(_error){}
    }
    return fallbackCopy(value);
  }
  function downloadText(content,filename){
    const blob=new Blob([content],{type:'text/plain;charset=utf-8'});
    const url=URL.createObjectURL(blob);
    const link=document.createElement('a');
    link.href=url;
    link.download=filename||'config.txt';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1200);
  }
  async function shareFile(sourceId,filename){
    const source=document.getElementById(sourceId||'');
    if(!source)return;
    const content=source.value||source.textContent||'';
    const name=filename||'config.txt';
    if(window.isSecureContext&&navigator.share&&typeof File!=='undefined'){
      try{
        const file=new File([content],name,{type:'text/plain'});
        const payload={files:[file],title:'کانفیگ VPN'};
        if(!navigator.canShare||navigator.canShare(payload)){
          await navigator.share(payload);
          notify('کانفیگ برای برنامه ارسال شد');
          return;
        }
      }catch(error){
        if(error&&error.name==='AbortError')return;
      }
    }
    downloadText(content,name);
    notify('فایل دانلود شد؛ آن را با برنامه مربوط باز کنید');
  }
  async function shareText(value,label){
    if(window.isSecureContext&&navigator.share){
      try{
        await navigator.share({title:label||'کانفیگ VPN',text:value});
        return true;
      }catch(error){
        if(error&&error.name==='AbortError')return true;
      }
    }
    const ok=await copy(value);
    notify(ok?'لینک کپی شد؛ داخل برنامه Import کنید':'کپی انجام نشد');
    return ok;
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

  document.querySelectorAll('.download-config').forEach(download=>{
    const row=download.closest('.action-row');
    if(!row||row.querySelector('.mobile-send-config'))return;
    let actions=row.querySelector('.action-buttons');
    if(!actions){actions=document.createElement('div');actions.className='action-buttons';row.appendChild(actions)}
    const button=document.createElement('button');
    button.type='button';
    button.className='mobile-send-btn mobile-send-config';
    button.textContent='ارسال به موبایل';
    button.addEventListener('click',()=>shareFile(download.dataset.target||'',download.dataset.filename||'config.txt'));
    actions.appendChild(button);
  });

  document.querySelectorAll('.action-row a.primary-btn[href]').forEach(link=>{
    const value=link.getAttribute('href')||'';
    if(!/^(vmess|vless|trojan|ss|hysteria2|hy2|tuic):/i.test(value))return;
    link.textContent='باز کردن در برنامه';
    const row=link.closest('.action-row');
    if(!row||row.querySelector('.mobile-send-link'))return;
    let actions=row.querySelector('.action-buttons');
    if(!actions){actions=document.createElement('div');actions.className='action-buttons';row.appendChild(actions)}
    const button=document.createElement('button');
    button.type='button';
    button.className='mobile-send-btn mobile-send-link';
    button.textContent='ارسال به موبایل';
    button.addEventListener('click',()=>shareText(value,'کانفیگ V2Ray / Xray'));
    actions.appendChild(button);
  });

  document.querySelectorAll('[data-v7-copy-url]').forEach(button=>{
    button.addEventListener('click',async()=>{
      const ok=await copy(absolute(button.dataset.v7CopyUrl||''));
      notify(ok?'مولتی‌لینک کپی شد':'کپی انجام نشد');
    });
  });
  document.querySelectorAll('[data-v7-share-url]').forEach(button=>{
    button.addEventListener('click',async()=>{
      const url=absolute(button.dataset.v7ShareUrl||'');
      const qr=button.dataset.v7Qr||'';
      if(!isMobile()&&qr&&openQr(qr))return;
      if(window.isSecureContext&&navigator.share){
        try{
          await navigator.share({title:'مولتی‌لینک V2Ray / Xray',url});
          return;
        }catch(error){
          if(error&&error.name==='AbortError')return;
        }
      }
      const ok=await copy(url);
      notify(ok?'مولتی‌لینک کپی شد؛ داخل برنامه اضافه کنید':'کپی انجام نشد');
    });
  });
  document.querySelectorAll('[data-v7-qr]').forEach(button=>{
    button.addEventListener('click',()=>openQr(button.dataset.v7Qr||''));
  });
})();
</script>
"""


def _multilink_section(token: str) -> str:
    encoded = quote(str(token), safe="")
    subscription_url = f"/v1/connect/{encoded}/subscription/v2ray"
    qr_url = f"{subscription_url}/qr"
    return (
        '<section class="multi-link-card">'
        '<div class="multi-link-copy">'
        '<small>V2RAY SUBSCRIPTION</small>'
        '<h3>مولتی‌لینک V2Ray / Xray</h3>'
        '<p>همه سرورهای واقعی ویتوری این اشتراک در یک لینک؛ برای Import و بروزرسانی ساده‌تر در کلاینت‌های سازگار.</p>'
        '</div>'
        '<div class="multi-link-actions">'
        f'<button class="copy-btn" type="button" data-v7-copy-url="{html.escape(subscription_url, quote=True)}">کپی مولتی‌لینک</button>'
        f'<button class="mobile-send-btn" type="button" data-v7-share-url="{html.escape(subscription_url, quote=True)}" data-v7-qr="{html.escape(qr_url, quote=True)}">ارسال به موبایل</button>'
        f'<button class="copy-btn" type="button" data-v7-qr="{html.escape(qr_url, quote=True)}">نمایش QR</button>'
        '</div>'
        '</section>'
    )


def refine_public_connection_mobile_v7(source: str, token: str) -> str:
    """Compact the phone UI and replace redundant advanced account content with a real V2Ray feed."""
    if "TWINPANEL_PUBLIC_CONNECT_MOBILE_V7" in source:
        return source

    source = source.replace(
        '<body data-public-connect-ui="v6">',
        '<body data-public-connect-ui="v6" data-public-connect-mobile="v7">',
        1,
    )

    has_v2ray = (
        'data-protocol-key="v2ray"' in source
        or 'data-protocol-key="xray"' in source
    )
    replacement = _multilink_section(token) if has_v2ray else ""
    source = re.sub(
        r'<details class="advanced">.*?</details>',
        replacement,
        source,
        count=1,
        flags=re.S,
    )
    source = source.replace(
        "</style>",
        _MOBILE_V7_CSS + "\n</style>",
        1,
    )
    source = source.replace(
        "</body>",
        _MOBILE_V7_SCRIPT + "\n</body>",
        1,
    )
    return source
