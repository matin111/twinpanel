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
    'shadowtls','snell','mieru','trusttunnel','amneziawg','sudoku'
  ]);
  const CLASSIC=new Set(['cisco','openvpn','wireguard','l2tp']);
  const MODERN=new Set([
    'v2ray','hysteria2','tuic','anytls','naive','shadowtls','snell','mieru',
    'trusttunnel','amneziawg','sudoku'
  ]);
  const RECOMMENDED=new Set(['v2ray','wireguard','openvpn','hysteria2','tuic']);
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

  function multiUrl(protocol){
    const value=token();if(!value||!MULTI.has(protocol))return'';
    return window.location.origin+'/v1/connect/'+encodeURIComponent(value)+'/multi/'+encodeURIComponent(protocol);
  }

  function metaUrl(protocol){
    const url=multiUrl(protocol);return url?url+'/meta':'';
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

  async function copyAll(url,kind){
    try{
      const response=await fetch(url,{cache:'no-store'});if(!response.ok)throw new Error(String(response.status));
      const text=await response.text();
      const payload=kind==='uri'?decodeBase64Utf8(text):text;
      const ok=await copy(payload);
      notify(ok?'همه کانفیگ‌ها کپی شد ✓':'کپی انجام نشد');
    }catch(_error){notify('دریافت همه کانفیگ‌ها انجام نشد')}
  }

  function profileFrom(response,protocol){
    return String(response.headers.get('Profile-Title')||token()+'-'+protocol).trim()||(token()+'-'+protocol);
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
    panel.querySelectorAll('.v30-subscription-card,.v34-subscription-card,.v37-multi-card,.v38-all-card,.v38-server-list-title,.v51-multi-card,.v51-single-title')
      .forEach(node=>node.remove());
  }

  function singleTitle(panel){
    const views=panel.querySelector('.server-views');if(!views)return;
    const title=document.createElement('div');title.className='v51-single-title';title.textContent='سرورهای تکی';
    views.insertAdjacentElement('beforebegin',title);
  }

  async function buildMulti(panel,protocol){
    if(!MULTI.has(protocol))return;
    const url=multiUrl(protocol),meta=metaUrl(protocol);if(!url||!meta)return;
    let response,payload;
    try{
      response=await fetch(meta,{cache:'no-store',headers:{Accept:'application/json'}});
      if(!response.ok)return;
      payload=await response.json();
    }catch(_error){return}

    const count=Number(payload?.node_count||0);if(count<=0)return;
    const kind=String(payload?.kind||'').toLowerCase();
    const rawClient=String(payload?.client||'').toLowerCase();
    const client=rawClient==='v2ray'?v2rayClient():rawClient;
    const profile=profileFrom(response,protocol);

    const card=document.createElement('section');card.className='v51-multi-card';card.dataset.v51Protocol=protocol;
    const head=document.createElement('div');head.className='v51-multi-head';
    const title=document.createElement('div');title.className='v51-multi-title';
    const strong=document.createElement('b');strong.textContent='همه سرورها';
    const small=document.createElement('small');small.textContent='Multi-Link · '+profile;
    const counter=document.createElement('span');counter.className='v51-multi-count';counter.textContent=count+' سرور';
    title.append(strong,small);head.append(title,counter);

    const actions=document.createElement('div');actions.className='v51-multi-actions';
    const deep=importHref(rawClient,url,profile);
    if(kind==='bundle'){
      const download=action('a','دانلود همه کانفیگ‌ها',null,true);download.href=url;download.target='_blank';download.rel='noopener noreferrer';actions.appendChild(download);
      actions.appendChild(action('button','کپی لینک بسته',()=>copy(url).then(ok=>notify(ok?'لینک بسته کپی شد ✓':'کپی انجام نشد')),false));
    }else{
      if(deep){
        const add=action('a','افزودن همه به '+client,null,true);add.href=deep;actions.appendChild(add);
      }else if(rawClient==='v2ray'){
        actions.appendChild(action('button','کپی لینک برای '+client,()=>copy(url).then(ok=>notify(ok?'لینک اشتراک کپی شد ✓':'کپی انجام نشد')),true));
      }else{
        const open=action('a','باز کردن مولتی‌لینک',null,true);open.href=url;open.target='_blank';open.rel='noopener noreferrer';actions.appendChild(open);
      }
      actions.appendChild(action('button','کپی همه کانفیگ‌ها',()=>copyAll(url,kind),false));
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

  async function apply(){
    document.body.classList.add('v51-multilink');document.body.dataset.tpMultilinkAuthority='v51';
    ensureMobileCategories();
    const panels=[...document.querySelectorAll('.protocol-panel')];
    for(const panel of panels){
      const protocol=panelKey(panel);retireOld(panel);await buildMulti(panel,protocol);
    }
  }

  function schedule(){clearTimeout(applyTimer);applyTimer=setTimeout(apply,80)}
  apply();window.setTimeout(apply,350);window.setTimeout(apply,1100);
  window.addEventListener('resize',schedule,{passive:true});
})();
</script>
"""


def refine_public_connection_multilink_authority_v51(source: str) -> str:
    """Final UI authority for all config-bearing protocol Multi-Links and mobile categories."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
