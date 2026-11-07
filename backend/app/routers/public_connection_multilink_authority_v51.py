from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_MULTILINK_AUTHORITY_V51"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_MULTILINK_AUTHORITY_V51 */
body.v51-multilink .v30-subscription-card,
body.v51-multilink .v34-subscription-card,
body.v51-multilink .v37-multi-card,
body.v51-multilink .v38-all-card,
body.v51-multilink .v49-v2ray-summary,
body.v51-multilink .v49-v2ray-groups{
  display:none!important;
}
body.v51-multilink .v51-multi-card{
  margin:12px;
  padding:12px;
  border:1px solid color-mix(in srgb,var(--p) 34%,var(--line));
  border-radius:15px;
  background:linear-gradient(145deg,color-mix(in srgb,var(--p) 7%,var(--surface2)),var(--surface2));
}
body.v51-multilink .v51-multi-head{
  display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px;
}
body.v51-multilink .v51-multi-title{display:grid;gap:2px}
body.v51-multilink .v51-multi-title b{font-size:14px;line-height:1.5}
body.v51-multilink .v51-multi-title small,
body.v51-multilink .v51-multi-count{color:var(--muted);font-size:10px;font-weight:800}
body.v51-multilink .v51-multi-count{padding:4px 8px;border:1px solid var(--line);border-radius:999px;white-space:nowrap}
body.v51-multilink .v51-multi-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
body.v51-multilink .v51-multi-actions>a,
body.v51-multilink .v51-multi-actions>button{
  min-height:42px;padding:9px 11px;display:inline-flex;align-items:center;justify-content:center;
  border:1px solid var(--line);border-radius:10px;background:var(--surface);color:var(--text);
  font:inherit;font-size:12px;font-weight:900;text-align:center;text-decoration:none;cursor:pointer;
}
body.v51-multilink .v51-multi-actions .v51-primary{border-color:var(--p);background:var(--p);color:#fff}
body.v51-multilink .v51-single-title{margin:13px 12px 6px;color:var(--muted);font-size:11px;font-weight:900}

@media(max-width:720px){
  body.v51-multilink .v51-mobile-categories{
    display:flex!important;gap:7px;overflow-x:auto;padding:0 0 10px;margin:0 0 8px;scrollbar-width:none;
  }
  body.v51-multilink .v51-mobile-categories::-webkit-scrollbar{display:none}
  body.v51-multilink .v51-mobile-category{
    flex:0 0 auto;min-height:34px;padding:0 11px;border:1px solid var(--line);border-radius:10px;
    background:var(--surface2);color:var(--muted);font:inherit;font-size:11px;font-weight:900;cursor:pointer;
  }
  body.v51-multilink .v51-mobile-category.active{border-color:var(--p);background:color-mix(in srgb,var(--p) 12%,var(--surface));color:var(--p)}
  body.v51-multilink .protocols{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:7px!important}
  body.v51-multilink .protocol-choice[data-v51-filtered="1"]{display:none!important}
  body.v51-multilink .v51-multi-card{margin:10px;padding:11px}
  body.v51-multilink .v51-multi-actions{grid-template-columns:1fr}
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectMultilinkAuthorityV51">
(function(){
  const MULTI=new Set([
    'openvpn','wireguard','v2ray','hysteria2','tuic','anytls','naive',
    'shadowtls','snell','socks5','mieru','trusttunnel','amneziawg','sudoku'
  ]);
  const BUNDLE=new Set(['openvpn','wireguard','amneziawg']);
  const CLASSIC=new Set(['cisco','openvpn','wireguard','l2tp']);
  const MODERN=new Set([
    'v2ray','hysteria2','tuic','anytls','naive','shadowtls','snell','socks5','mieru',
    'trusttunnel','amneziawg','sudoku'
  ]);
  const RECOMMENDED=new Set(['v2ray','wireguard','openvpn','hysteria2','tuic']);
  const CLIENT={
    openvpn:'openvpn',wireguard:'wireguard',v2ray:'v2ray',hysteria2:'karing',
    tuic:'karing',anytls:'karing',naive:'karing',shadowtls:'karing',snell:'hiddify',socks5:'singbox',
    mieru:'karing',trusttunnel:'trusttunnel',amneziawg:'amneziawg',sudoku:'sudoku'
  };
  let applyTimer=null;

  function normalize(value){
    const key=String(value||'').trim().toLowerCase();
    if(key==='xray')return'v2ray';
    if(key==='naiveproxy')return'naive';
    if(key==='openconnect'||key==='ocserv'||key==='anyconnect')return'cisco';
    return key;
  }

  function token(){
    const match=String(window.location.pathname||'').match(/^\/v1\/connect\/([^/]+)/);
    if(!match)return'';
    try{return decodeURIComponent(match[1])}catch(_error){return match[1]}
  }

  function panelKey(panel){
    const direct=normalize(panel?.dataset?.v34Protocol||panel?.dataset?.modernProtocol||'');
    if(direct)return direct;
    const choice=[...document.querySelectorAll('.protocol-choice')]
      .find(item=>String(item.dataset.protocol||'')===String(panel?.id||''));
    return normalize(choice?.dataset?.protocolKey||choice?.dataset?.protocol||'');
  }

  function choiceFor(panel){
    return [...document.querySelectorAll('.protocol-choice')]
      .find(item=>String(item.dataset.protocol||'')===String(panel?.id||''))||null;
  }

  function serverCount(panel){
    const choice=choiceFor(panel);
    const text=String(choice?.textContent||'');
    const match=text.match(/(\d+)\s*سرور/);
    if(match)return Number(match[1])||0;
    const tabs=panel?.querySelectorAll?.('.server-tab')?.length||0;
    if(tabs)return tabs;
    return panel?.querySelectorAll?.('.server-view')?.length||0;
  }

  function multiUrl(protocol){
    const value=token();if(!value||!MULTI.has(protocol))return'';
    return window.location.origin+'/v1/connect/'+encodeURIComponent(value)+'/multi/'+encodeURIComponent(protocol);
  }

  function platform(){
    const explicit=String(document.body?.dataset?.tpPlatform||document.documentElement?.dataset?.tpPlatform||'').toLowerCase();
    return explicit||'unknown';
  }

  function v2rayClient(){
    const p=platform();
    if(p==='android')return'v2rayNG';
    if(p==='ios')return'V2Box';
    return'v2rayN';
  }

  function accountName(){
    const selectors=['[data-account-username]','[data-username]','.account-username','.user-username','.username'];
    for(const selector of selectors){
      const node=document.querySelector(selector);if(!node)continue;
      const value=String(node.dataset?.accountUsername||node.dataset?.username||node.textContent||'').trim();
      if(value)return value.replace(/\s+/g,'-');
    }
    return token();
  }

  function profileFor(protocol){
    return (accountName()||token()||'user')+'-'+protocol;
  }

  function fallbackCopy(value){
    const area=document.createElement('textarea');area.value=String(value||'');area.readOnly=true;
    area.style.position='fixed';area.style.left='-9999px';document.body.appendChild(area);
    area.focus();area.select();area.setSelectionRange(0,area.value.length);
    let ok=false;try{ok=document.execCommand('copy')}catch(_error){}area.remove();return ok;
  }

  async function copy(value){
    const raw=String(value||'');if(!raw)return false;
    if(navigator.clipboard&&window.isSecureContext){try{await navigator.clipboard.writeText(raw);return true}catch(_error){}}
    return fallbackCopy(raw);
  }

  function notify(message){
    const toast=document.getElementById('toast');if(!toast)return;
    toast.textContent=message;toast.classList.add('show');clearTimeout(window.__tpV51Toast);
    window.__tpV51Toast=setTimeout(()=>toast.classList.remove('show'),1700);
  }

  function decodeBase64Utf8(value){
    try{
      const bytes=Uint8Array.from(atob(String(value||'').replace(/\s+/g,'')),c=>c.charCodeAt(0));
      return new TextDecoder().decode(bytes);
    }catch(_error){return String(value||'')}
  }

  function copyDialog(label){
    const shade=document.createElement('div');
    shade.setAttribute('role','dialog');shade.setAttribute('aria-modal','true');
    shade.setAttribute('aria-label','کپی کانفیگ');
    Object.assign(shade.style,{position:'fixed',inset:'0',zIndex:'2147483647',background:'rgba(0,0,0,.72)',display:'grid',placeItems:'center',padding:'16px'});
    const panel=document.createElement('div');
    Object.assign(panel.style,{width:'min(92vw,650px)',background:'var(--surface,#171a24)',color:'var(--text,#fff)',padding:'18px',borderRadius:'14px',border:'1px solid var(--line,#505464)',display:'grid',gap:'10px',direction:'rtl'});
    const title=document.createElement('strong');title.textContent='کپی '+label;
    const hint=document.createElement('small');hint.textContent='در حال دریافت کانفیگ‌ها...';
    const area=document.createElement('textarea');area.value='';area.readOnly=true;area.rows=10;
    area.setAttribute('aria-label','متن کانفیگ');
    Object.assign(area.style,{width:'100%',boxSizing:'border-box',direction:'ltr',fontFamily:'monospace',fontSize:'12px',borderRadius:'8px',padding:'10px'});
    const controls=document.createElement('div');Object.assign(controls.style,{display:'flex',gap:'8px',justifyContent:'flex-start',flexWrap:'wrap'});
    const copyButton=document.createElement('button');copyButton.type='button';copyButton.textContent='کپی کانفیگ';copyButton.disabled=true;
    const downloadButton=document.createElement('button');downloadButton.type='button';downloadButton.textContent='دانلود فایل';downloadButton.disabled=true;
    const closeButton=document.createElement('button');closeButton.type='button';closeButton.textContent='بستن';
    let filename='vpn-config.txt';
    copyButton.addEventListener('click',()=>{
      area.focus();area.select();area.setSelectionRange(0,area.value.length);
      copy(area.value).then(ok=>{hint.textContent=ok?'کانفیگ در کلیپ‌بورد کپی شد ✓':'متن انتخاب شده است؛ Ctrl+C را فشار دهید.'});
    });
    downloadButton.addEventListener('click',()=>{
      if(!area.value)return;
      const blob=new Blob([area.value],{type:'text/plain;charset=utf-8'});
      const objectUrl=URL.createObjectURL(blob);
      const link=document.createElement('a');link.href=objectUrl;link.download=filename;
      document.body.appendChild(link);link.click();link.remove();
      setTimeout(()=>URL.revokeObjectURL(objectUrl),1000);
    });
    const close=()=>shade.remove();
    closeButton.addEventListener('click',close);
    shade.addEventListener('click',event=>{if(event.target===shade)close()});
    controls.append(copyButton,downloadButton,closeButton);
    panel.append(title,hint,area,controls);shade.appendChild(panel);document.body.appendChild(shade);
    return {area,copyButton,downloadButton,hint,setFilename:value=>{filename=value}};
  }

  async function copyAll(url,format){
    const isSingbox=format==='singbox';
    const label=isSingbox?'JSON مخصوص sing-box':format==='yaml'?'YAML مخصوص Clash / Mihomo':'کانفیگ‌ها';
    // An explicit second click is necessary for Clipboard permission after
    // asynchronous network fetch. The dialog also supports Ctrl+C and download.
    const dialog=copyDialog(label);
    try{
      const source=isSingbox?url+(url.includes('?')?'&':'?')+'format=singbox':url;
      const response=await fetch(source,{cache:'no-store'});if(!response.ok)throw new Error(String(response.status));
      const kind=String(response.headers.get('X-TwinPanel-Multi-Kind')||'').toLowerCase();
      if(kind==='bundle')throw new Error('binary bundle cannot be copied as text');
      const data=await response.text();
      const payload=kind==='uri'?decodeBase64Utf8(data):data;
      if(!payload)throw new Error('empty payload');
      if(isSingbox){const parsed=JSON.parse(payload);if(!Array.isArray(parsed.outbounds)||!parsed.outbounds.length)throw new Error('invalid singbox payload')}
      dialog.area.value=payload;
      dialog.copyButton.disabled=false;dialog.downloadButton.disabled=false;
      dialog.setFilename((profileFor('shadowtls')||'vpn')+(isSingbox?'-singbox.json':format==='yaml'?'-clash.yaml':'-config.txt'));
      dialog.hint.textContent='کانفیگ آماده است؛ «کپی کانفیگ» را بزنید یا فایل را دانلود کنید. اگر کپی خودکار مسدود شد، متن را انتخاب کرده Ctrl+C بزنید.';
    }catch(_error){
      dialog.area.value='';dialog.copyButton.disabled=true;dialog.downloadButton.disabled=true;
      dialog.hint.textContent='دریافت کانفیگ انجام نشد. لینک اشتراک را کپی کنید یا دوباره تلاش کنید.';
    }
  }

  function importHref(client,url,profile){
    const key=String(client||'').toLowerCase();
    if(key==='karing')return 'karing://install-config?url='+encodeURIComponent(url)+'&name='+encodeURIComponent(profile);
    if(key==='hiddify')return 'hiddify://import/'+encodeURI(url)+'#'+encodeURIComponent(profile);
    if(key==='v2ray'&&platform()==='android')return 'v2rayng://install-sub?url='+encodeURIComponent(url);
    return'';
  }

  function action(tag,label,handler,primary){
    const node=document.createElement(tag);node.textContent=label;
    if(primary)node.classList.add('v51-primary');
    if(tag==='button'){node.type='button';node.addEventListener('click',handler)}
    return node;
  }

  function retireOld(panel){
    panel.querySelectorAll('.v30-subscription-card,.v34-subscription-card,.v37-multi-card,.v38-all-card,.v38-server-list-title,.v51-single-title')
      .forEach(node=>node.remove());
  }

  function singleTitle(panel){
    const views=panel.querySelector('.server-views');if(!views||panel.querySelector(':scope > .v51-single-title'))return;
    const title=document.createElement('div');title.className='v51-single-title';title.textContent='سرورهای تکی';
    views.insertAdjacentElement('beforebegin',title);
  }

  function buildMulti(panel,protocol){
    if(!MULTI.has(protocol))return;
    if(panel.querySelector(':scope > .v51-multi-card,:scope > .v52-multi-card'))return;
    const url=multiUrl(protocol);if(!url)return;
    const count=serverCount(panel);if(count<=0)return;
    const rawClient=CLIENT[protocol]||'';
    const client=rawClient==='v2ray'?v2rayClient():rawClient;
    const profile=profileFor(protocol);

    const card=document.createElement('section');card.className='v51-multi-card';card.dataset.v51Protocol=protocol;
    const head=document.createElement('div');head.className='v51-multi-head';
    const title=document.createElement('div');title.className='v51-multi-title';
    const strong=document.createElement('b');strong.textContent='همه سرورها';
    const small=document.createElement('small');small.textContent='Multi-Link · '+profile;
    const counter=document.createElement('span');counter.className='v51-multi-count';counter.textContent=count+' سرور';
    title.append(strong,small);head.append(title,counter);

    const actions=document.createElement('div');actions.className='v51-multi-actions';
    if(BUNDLE.has(protocol)){
      // Real ZIP attachments only; no app import or new-tab preview.
      const download=action('a','دانلود همه فایل‌ها',null,true);
      download.href=url;download.setAttribute('download','');actions.appendChild(download);
    }else{
      // Karing's Clash plugin import can treat ShadowTLS as an isolated
      // transport. Its native sing-box JSON import preserves each full
      // Shadowsocks -> ShadowTLS detour pair, verified by a live proxy test.
      const clientUrl=protocol==='shadowtls'
        ? url+(url.includes('?')?'&':'?')+'format=singbox'
        : url;
      const deep=importHref(rawClient,clientUrl,profile);
      if(deep){
        const add=action('a','افزودن همه به '+client,null,true);add.href=deep;actions.appendChild(add);
        actions.appendChild(action('button','کپی لینک اشتراک',()=>{
          copy(url).then(ok=>notify(ok?'لینک اشتراک کپی شد ✓':'کپی خودکار ممکن نشد؛ از نوار آدرس لینک را کپی کنید'));
        },false));
      }else if(rawClient==='v2ray'){
        actions.appendChild(action('button','کپی لینک برای '+client,()=>copy(url).then(ok=>notify(ok?'لینک اشتراک کپی شد ✓':'کپی انجام نشد')),true));
      }else{
        actions.appendChild(action('button','کپی لینک مولتی‌لینک',()=>copy(url).then(ok=>notify(ok?'لینک اشتراک کپی شد ✓':'کپی انجام نشد')),true));
      }
      if(protocol==='shadowtls'){
        actions.appendChild(action('button','کپی YAML برای Clash',()=>copyAll(url,'yaml'),false));
        actions.appendChild(action('button','کپی JSON برای sing-box',()=>copyAll(url,'singbox'),false));
      }else{
        actions.appendChild(action('button','کپی همه کانفیگ‌ها',()=>copyAll(url),false));
      }
    }
    card.append(head,actions);
    panel.querySelector('.panel-head')?.insertAdjacentElement('afterend',card);
    singleTitle(panel);
  }

  function choiceKey(choice){return normalize(choice?.dataset?.protocolKey||choice?.dataset?.protocol||'')}

  function ensureMobileCategories(){
    if(!window.matchMedia('(max-width:720px)').matches)return;
    const protocols=document.querySelector('.protocols');if(!protocols)return;
    let bar=document.querySelector('.v51-mobile-categories');
    if(!bar){
      bar=document.createElement('div');bar.className='v51-mobile-categories';
      const categories=[['recommended','پیشنهادی'],['classic','VPN کلاسیک'],['modern','مدرن'],['all','همه پروتکل‌ها']];
      categories.forEach(([key,label])=>{
        const button=document.createElement('button');button.type='button';button.className='v51-mobile-category';button.dataset.category=key;button.textContent=label;
        button.addEventListener('click',()=>filterCategory(key));bar.appendChild(button);
      });
      protocols.insertAdjacentElement('beforebegin',bar);
    }
    if(!bar.querySelector('.active'))filterCategory('all');
  }

  function inCategory(protocol,category){
    if(category==='all')return true;
    if(category==='classic')return CLASSIC.has(protocol);
    if(category==='modern')return MODERN.has(protocol);
    return RECOMMENDED.has(protocol);
  }

  function filterCategory(category){
    document.querySelectorAll('.v51-mobile-category').forEach(button=>button.classList.toggle('active',button.dataset.category===category));
    document.querySelectorAll('.protocol-choice').forEach(choice=>{
      const key=choiceKey(choice);choice.dataset.v51Filtered=inCategory(key,category)?'0':'1';
    });
    document.querySelectorAll('.protocol-panel').forEach(panel=>{
      const key=panelKey(panel);if(inCategory(key,category))return;
      panel.classList.remove('active','v36-open','v42-sheet-open');panel.setAttribute('aria-hidden','true');
    });
  }

  function apply(){
    document.body.classList.add('v51-multilink');document.body.dataset.tpMultilinkAuthority='v51';
    ensureMobileCategories();
    document.querySelectorAll('.protocol-panel').forEach(panel=>{
      const protocol=panelKey(panel);retireOld(panel);buildMulti(panel,protocol);
    });
  }

  function schedule(){clearTimeout(applyTimer);applyTimer=setTimeout(apply,40)}
  apply();
  window.setTimeout(apply,180);
  window.addEventListener('resize',schedule,{passive:true});
})();
</script>
"""


def refine_public_connection_multilink_authority_v51(source: str) -> str:
    """Final UI authority for config-bearing protocol Multi-Links without prefetching meta endpoints."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
