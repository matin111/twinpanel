from __future__ import annotations

import json


_V9_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_HUB_V9 */
.v9-mobile-stack,.v9-apps-drawer{display:none}

@media(max-width:720px){
  body.v9-ready .protocol-toolbar,
  body.v9-ready .protocols,
  body.v9-ready .protocol-panel,
  body.v9-ready .multi-link-card,
  body.v9-ready .apps,
  body.v9-ready .v9-legacy-hide{display:none}

  body.v9-ready .page{padding-top:8px}
  body.v9-ready .section-head{margin:12px 2px 8px}
  body.v9-ready .section-head h2{font-size:16px}

  .v9-mobile-stack{
    display:flex;
    flex-direction:column;
    gap:12px;
    margin-top:8px;
  }
  .v9-config-card{
    overflow:hidden;
    border:1px solid color-mix(in srgb,var(--p) 24%,var(--line));
    border-radius:19px;
    background:linear-gradient(145deg,color-mix(in srgb,var(--p) 5%,var(--surface)),var(--surface));
    box-shadow:0 12px 32px rgba(0,0,0,.12);
  }
  .v9-card-head{
    min-height:58px;
    padding:11px 13px;
    display:flex;
    align-items:center;
    gap:10px;
    border-bottom:1px solid var(--line);
  }
  .v9-protocol-mark{
    width:36px;
    height:36px;
    flex:0 0 36px;
    display:grid;
    place-items:center;
    border-radius:11px;
    background:linear-gradient(135deg,var(--p),var(--s));
    color:white;
    font-size:12px;
    font-weight:950;
  }
  .v9-card-title{min-width:0;flex:1}
  .v9-card-title b{display:block;font-size:12px;line-height:1.5}
  .v9-card-title small{display:block;margin-top:2px;color:var(--muted);font-size:7px}
  .v9-chip{
    min-width:58px;
    height:27px;
    padding:0 9px;
    display:inline-flex;
    align-items:center;
    justify-content:center;
    border:1px solid color-mix(in srgb,var(--p) 42%,var(--line));
    border-radius:999px;
    color:var(--p);
    background:color-mix(in srgb,var(--p) 8%,transparent);
    font-size:7px;
    font-weight:900;
  }
  .v9-card-body{padding:10px}
  .v9-server-list{display:flex;flex-direction:column;gap:8px}
  .v9-server-row{
    min-height:58px;
    padding:8px 9px;
    display:grid;
    grid-template-columns:minmax(0,1fr) 42px 42px;
    align-items:center;
    gap:7px;
    border:1px solid var(--line);
    border-radius:14px;
    background:var(--surface2);
  }
  .v9-server-main{
    min-width:0;
    display:flex;
    align-items:center;
    gap:9px;
  }
  .v9-server-icon{
    width:31px;
    height:31px;
    flex:0 0 31px;
    display:grid;
    place-items:center;
    border-radius:9px;
    background:color-mix(in srgb,var(--p) 10%,var(--surface));
    border:1px solid color-mix(in srgb,var(--p) 18%,var(--line));
    color:var(--p);
  }
  .v9-server-icon svg{width:17px;height:17px;display:block}
  .v9-server-copy{min-width:0}
  .v9-server-copy b{
    display:block;
    overflow:hidden;
    text-overflow:ellipsis;
    white-space:nowrap;
    font-size:10px;
  }
  .v9-server-copy small{
    display:block;
    margin-top:3px;
    color:var(--muted);
    font-size:6.5px;
  }
  .v9-icon-btn{
    width:42px;
    height:42px;
    display:grid;
    place-items:center;
    border:1px solid color-mix(in srgb,var(--p) 24%,var(--line));
    border-radius:12px;
    background:var(--surface);
    color:var(--text);
    text-decoration:none;
  }
  .v9-icon-btn.mobile{
    color:var(--p);
    background:color-mix(in srgb,var(--p) 10%,var(--surface));
    border-color:color-mix(in srgb,var(--p) 40%,var(--line));
  }
  .v9-icon-btn svg{width:20px;height:20px;display:block}
  .v9-details{
    display:none;
    grid-column:1/-1;
    margin-top:2px;
    padding:8px;
    border-radius:10px;
    background:var(--surface);
    color:var(--muted);
    font-size:7px;
    line-height:1.8;
    direction:ltr;
    text-align:left;
    word-break:break-all;
  }
  .v9-server-row.open .v9-details{display:block}
  .v9-multi .v9-card-head{border-bottom:0}
  .v9-multi .v9-card-body{padding-top:0}
  .v9-insecure-note{
    display:none;
    margin-top:8px;
    padding:8px 10px;
    border:1px solid color-mix(in srgb,#f59e0b 28%,var(--line));
    border-radius:11px;
    background:color-mix(in srgb,#f59e0b 7%,var(--surface));
    color:var(--muted);
    font-size:6.5px;
    line-height:1.8;
  }
  body.v9-insecure .v9-insecure-note{display:block}

  .v9-apps-drawer{
    display:block;
    margin-top:12px;
    border:1px solid var(--line);
    border-radius:15px;
    background:var(--surface);
    overflow:hidden;
  }
  .v9-apps-drawer summary{
    cursor:pointer;
    list-style:none;
    padding:12px 13px;
    font-size:11px;
    font-weight:900;
  }
  .v9-apps-drawer summary::-webkit-details-marker{display:none}
  .v9-apps-list{
    padding:0 9px 9px;
    display:grid;
    grid-template-columns:repeat(2,minmax(0,1fr));
    gap:7px;
  }
  .v9-app-link{
    min-height:44px;
    padding:8px;
    display:flex;
    align-items:center;
    gap:7px;
    border:1px solid var(--line);
    border-radius:11px;
    background:var(--surface2);
    color:var(--text);
    text-decoration:none;
    font-size:7.5px;
    font-weight:850;
  }
}
"""


_V9_SCRIPT_TEMPLATE = r"""
<script id="twinpanelPublicConnectHubV9">
(function(){
  if(!window.matchMedia('(max-width:720px)').matches)return;
  const token=__TOKEN__;
  const body=document.body;
  const toast=document.getElementById('toast');
  if(!window.isSecureContext)body.classList.add('v9-insecure');

  const icons={
    server:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="4" y="4" width="16" height="6" rx="2"/><rect x="4" y="14" width="16" height="6" rx="2"/><path d="M8 7h.01M8 17h.01"/></svg>',
    download:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3v12m0 0 4-4m-4 4-4-4"/><path d="M5 19h14"/></svg>',
    phone:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M10 5h4M11 18.5h2"/></svg>',
    copy:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M5 16H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v1"/></svg>',
    info:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 10v6M12 7h.01"/></svg>'
  };
  function notify(text){
    if(!toast)return;
    toast.textContent=text;toast.classList.add('show');
    clearTimeout(window.__v9Toast);window.__v9Toast=setTimeout(()=>toast.classList.remove('show'),1700);
  }
  function safeName(value,fallback){
    const raw=String(value||'').split(/[\\/]/).pop()||fallback;
    return raw.replace(/[^A-Za-z0-9._-]+/g,'-')||fallback;
  }
  function fileUrl(protocol,index){
    return '/v1/connect/'+encodeURIComponent(token)+'/file/'+encodeURIComponent(protocol)+'/'+index;
  }
  function protocolMeta(key,title){
    const map={
      openvpn:['O','OpenVPN','OpenVPN'],
      wireguard:['W','WireGuard','WireGuard'],
      v2ray:['V','V2Ray / Xray','V2Ray'],
      xray:['V','V2Ray / Xray','V2Ray'],
      cisco:['C','Cisco / OpenConnect','OpenConnect'],
      l2tp:['L2','L2TP / IPsec','L2TP']
    };
    return map[key]||['•',title||key||'VPN',title||key||'VPN'];
  }
  async function copyText(value){
    if(navigator.clipboard&&window.isSecureContext){
      try{await navigator.clipboard.writeText(value);return true}catch(_error){}
    }
    const area=document.createElement('textarea');area.value=value;area.style.position='fixed';area.style.opacity='0';
    document.body.appendChild(area);area.select();let ok=false;try{ok=document.execCommand('copy')}catch(_error){}area.remove();return ok;
  }
  function downloadReal(url,filename){
    const a=document.createElement('a');a.href=url;a.download=filename||'';a.rel='noopener';document.body.appendChild(a);a.click();a.remove();
  }
  async function sendRealFile(url,filename,protocol){
    const mime=protocol==='openvpn'?'application/x-openvpn-profile':'application/octet-stream';
    if(window.isSecureContext&&navigator.share&&typeof File!=='undefined'){
      try{
        const response=await fetch(url,{cache:'no-store'});
        if(!response.ok)throw new Error('download failed');
        const bytes=await response.arrayBuffer();
        const file=new File([bytes],filename,{type:mime});
        const payload={files:[file],title:protocol==='openvpn'?'OpenVPN profile':'WireGuard profile'};
        if(!navigator.canShare||navigator.canShare(payload)){
          await navigator.share(payload);return;
        }
      }catch(error){if(error&&error.name==='AbortError')return;}
    }
    downloadReal(url,filename);
    notify('فایل واقعی دانلود شد؛ روی فایل بزنید و برنامه VPN را انتخاب کنید');
  }
  function actionButton(kind,label){
    const el=document.createElement('button');el.type='button';el.className='v9-icon-btn '+(kind==='phone'?'mobile':'');el.innerHTML=icons[kind]||icons.info;el.setAttribute('aria-label',label);el.title=label;return el;
  }
  function actionLink(kind,label,href){
    const el=document.createElement('a');el.className='v9-icon-btn '+(kind==='phone'?'mobile':'');el.href=href;el.innerHTML=icons[kind]||icons.info;el.setAttribute('aria-label',label);el.title=label;return el;
  }
  function makeCard(mark,title,chip,subtitle){
    const card=document.createElement('section');card.className='v9-config-card';
    const head=document.createElement('div');head.className='v9-card-head';
    head.innerHTML='<span class="v9-protocol-mark">'+mark+'</span><div class="v9-card-title"><b>'+title+'</b><small>'+subtitle+'</small></div><span class="v9-chip">'+chip+'</span>';
    const content=document.createElement('div');content.className='v9-card-body';
    const list=document.createElement('div');list.className='v9-server-list';content.appendChild(list);card.append(head,content);return [card,list];
  }
  function serverRow(name,subtitle){
    const row=document.createElement('div');row.className='v9-server-row';
    const main=document.createElement('div');main.className='v9-server-main';main.innerHTML='<span class="v9-server-icon">'+icons.server+'</span><div class="v9-server-copy"><b></b><small></small></div>';
    main.querySelector('b').textContent=name;main.querySelector('small').textContent=subtitle;row.appendChild(main);return row;
  }

  const mount=document.createElement('div');mount.className='v9-mobile-stack';
  const toolbar=document.querySelector('.protocol-toolbar');
  if(toolbar)toolbar.parentNode.insertBefore(mount,toolbar);else document.querySelector('.page')?.appendChild(mount);

  const smart=document.querySelector('.smart-card');
  if(smart){smart.classList.add('v9-legacy-hide');const prev=smart.previousElementSibling;if(prev&&prev.classList.contains('section-head'))prev.classList.add('v9-legacy-hide');}
  const quickHead=[...document.querySelectorAll('.section-head')].find(el=>(el.textContent||'').includes('اتصال سریع'));
  if(quickHead)quickHead.querySelector('h2') && (quickHead.querySelector('h2').textContent='کانفیگ‌های اتصال');

  const multi=document.querySelector('.multi-link-card');
  if(multi){
    const [card,list]=makeCard('★','High Availability Config','V2Ray','مولتی‌سرور · یک لینک برای همه کانفیگ‌های V2Ray/Xray');card.classList.add('v9-multi');
    const row=serverRow('Multi Server','مولتی‌لینک همیشه به‌روز');
    const copySource=multi.querySelector('[data-v7-copy-url]');const shareSource=multi.querySelector('[data-v7-share-url]');
    const url=copySource?.dataset.v7CopyUrl||shareSource?.dataset.v7ShareUrl||'';
    const copy=actionButton('copy','کپی مولتی‌لینک');copy.addEventListener('click',async()=>notify(await copyText(new URL(url,location.href).href)?'مولتی‌لینک کپی شد':'کپی انجام نشد'));
    const phone=actionButton('phone','ارسال مولتی‌لینک به موبایل');phone.addEventListener('click',()=>shareSource?shareSource.click():copy.click());
    row.append(copy,phone);list.appendChild(row);mount.appendChild(card);
  }

  document.querySelectorAll('.protocol-panel').forEach(panel=>{
    const choice=document.querySelector('.protocol-choice[data-protocol="'+CSS.escape(panel.id)+'"]');
    const key=String(choice?.dataset.protocolKey||'').toLowerCase();
    const title=(panel.querySelector('.panel-head h3')?.textContent||key||'VPN').trim();
    const [mark,display,chip]=protocolMeta(key,title);
    const tabs=[...panel.querySelectorAll('.server-tab')];
    const views=[...panel.querySelectorAll('.server-view')];
    if(!views.length)return;
    const [card,list]=makeCard(mark,display,chip,views.length+' کانفیگ آماده');
    views.forEach((view,index)=>{
      const server=(tabs[index]?.textContent||('Server '+(index+1))).trim();
      const row=serverRow(server,index===0?'Default':'Server '+(index+1));
      const download=view.querySelector('.download-config');
      const direct=view.querySelector('a.primary-btn[href]');
      if((key==='openvpn'||key==='wireguard')&&download){
        const extension=key==='openvpn'?'ovpn':'conf';
        const filename=safeName(download.dataset.filename,key+'-'+(index+1)+'.'+extension);
        const url=fileUrl(key,index);
        const dl=actionLink('download','دانلود فایل واقعی',url);dl.download=filename;
        const phone=actionButton('phone',key==='openvpn'?'باز کردن با OpenVPN Connect':'باز کردن با WireGuard');
        phone.addEventListener('click',()=>sendRealFile(url,filename,key));
        row.append(dl,phone);
      }else if((key==='v2ray'||key==='xray')&&direct){
        const uri=direct.getAttribute('href')||'';
        const copy=actionButton('copy','کپی کانفیگ');copy.addEventListener('click',async()=>notify(await copyText(uri)?'کانفیگ کپی شد':'کپی انجام نشد'));
        const phone=actionLink('phone','باز کردن در برنامه',uri);row.append(copy,phone);
      }else{
        const text=[...view.querySelectorAll('.fact')].map(f=>(f.textContent||'').trim()).filter(Boolean).join(' · ');
        const copy=actionButton('copy','کپی اطلاعات');copy.addEventListener('click',async()=>notify(await copyText(text)?'اطلاعات کپی شد':'کپی انجام نشد'));
        const info=actionButton('info','نمایش اطلاعات');
        const detail=document.createElement('div');detail.className='v9-details';detail.textContent=text||'اطلاعات این اتصال در دسترس است.';
        info.addEventListener('click',()=>row.classList.toggle('open'));row.append(copy,info,detail);
      }
      list.appendChild(row);
    });
    mount.appendChild(card);
  });

  const insecure=document.createElement('div');insecure.className='v9-insecure-note';insecure.textContent='این لینک روی HTTP باز شده است. فایل OpenVPN/WireGuard حالا به‌صورت فایل واقعی دانلود می‌شود؛ برای باز شدن مستقیم Share/Open-With داخل اپ‌ها، لینک HTTPS لازم است.';mount.appendChild(insecure);

  const apps=document.querySelector('.apps');
  if(apps){
    const drawer=document.createElement('details');drawer.className='v9-apps-drawer';drawer.innerHTML='<summary>دانلود برنامه‌های اتصال</summary><div class="v9-apps-list"></div>';
    const list=drawer.querySelector('.v9-apps-list');
    [...apps.querySelectorAll('a.app-card')].slice(0,10).forEach(link=>{
      const item=document.createElement('a');item.className='v9-app-link';item.href=link.getAttribute('href')||'#';item.target='_blank';item.rel='noopener noreferrer';item.textContent=(link.querySelector('b')?.textContent||'برنامه').trim();list.appendChild(item);
    });
    apps.parentNode.insertBefore(drawer,apps.nextSibling);
  }
  body.classList.add('v9-ready');
})();
</script>
"""


def refine_public_connection_hub_v9(source: str, token: str) -> str:
    """Replace dense phone tabs with reference-style protocol/server cards using real file endpoints."""
    if "TWINPANEL_PUBLIC_CONNECT_HUB_V9" in source:
        return source
    source = source.replace("</style>", _V9_CSS + "\n</style>", 1)
    script = _V9_SCRIPT_TEMPLATE.replace(
        "__TOKEN__",
        json.dumps(str(token), ensure_ascii=True),
    )
    source = source.replace("</body>", script + "\n</body>", 1)
    return source
