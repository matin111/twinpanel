from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_REFERENCE_LAYOUT_V38"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_REFERENCE_LAYOUT_V38 */
body.v38-reference .v37-multi-card{display:none!important}
body.v38-reference .v38-all-card{
  margin:12px;
  padding:13px;
  border:1px solid color-mix(in srgb,var(--p) 34%,var(--line));
  border-radius:14px;
  background:linear-gradient(145deg,color-mix(in srgb,var(--p) 7%,var(--surface2)),var(--surface2));
}
body.v38-reference .v38-all-head{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  margin-bottom:10px;
}
body.v38-reference .v38-all-head b{font-size:14px;line-height:1.5}
body.v38-reference .v38-all-head span{color:var(--muted);font-size:11px;font-weight:800}
body.v38-reference .v38-all-actions{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:8px;
}
body.v38-reference .v38-all-actions>a,
body.v38-reference .v38-all-actions>button{
  min-height:42px;
  padding:9px 12px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  border:1px solid var(--line);
  border-radius:10px;
  background:var(--surface);
  color:var(--text);
  font:inherit;
  font-size:12px;
  font-weight:900;
  line-height:1.4;
  text-align:center;
  text-decoration:none;
  cursor:pointer;
}
body.v38-reference .v38-primary{
  border-color:var(--p)!important;
  background:var(--p)!important;
  color:#fff!important;
}
body.v38-reference .v38-copy{color:var(--p)!important}

@media(max-width:720px){
  body.v38-reference.v36-mobile-compact .protocol-panel{display:none!important}
  body.v38-reference.v36-mobile-compact .protocol-panel.v36-open{display:block!important}
  body.v38-reference .v38-all-card{margin:10px;padding:11px}
  body.v38-reference .v38-all-actions{grid-template-columns:1fr}
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectReferenceLayoutV38">
(function(){
  const SUBSCRIPTIONS=new Set(['v2ray','hysteria2','tuic','anytls']);
  const MULTI=new Set([
    'openvpn','wireguard','v2ray','hysteria2','tuic','anytls','naive',
    'shadowtls','snell','mieru','trusttunnel','amneziawg','sudoku'
  ]);
  const NATIVE_BUNDLES=new Set(['openvpn','wireguard','amneziawg']);
  const text=node=>String(node?.textContent||'').trim();

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
    return normalize(choice?.dataset?.protocolKey||choice?.dataset?.protocol||'');
  }

  function token(){
    const match=String(window.location.pathname||'').match(/^\/v1\/connect\/([^/]+)/);
    if(!match)return'';
    try{return decodeURIComponent(match[1])}catch(_error){return match[1]}
  }

  function subscriptionUrl(protocol){
    const value=token();
    if(!value||!SUBSCRIPTIONS.has(protocol))return'';
    return window.location.origin+'/v1/connect/'+encodeURIComponent(value)+'/sub/'+encodeURIComponent(protocol);
  }

  function multiUrl(protocol){
    const value=token();
    if(!value||!MULTI.has(protocol))return'';
    return window.location.origin+'/v1/connect/'+encodeURIComponent(value)+'/multi/'+encodeURIComponent(protocol);
  }

  async function subscriptionCount(protocol){
    const url=subscriptionUrl(protocol);if(!url)return 0;
    try{
      const response=await fetch(url,{cache:'no-store',headers:{Accept:'text/plain'}});
      if(!response.ok)return 0;
      const encoded=String(await response.text()).trim();if(!encoded)return 0;
      const decoded=atob(encoded.replace(/\s+/g,''));
      return decoded.split(/\r?\n/).map(row=>row.trim()).filter(Boolean).length;
    }catch(_error){return 0}
  }

  async function multiMeta(protocol){
    const url=multiUrl(protocol);if(!url)return null;
    try{
      const response=await fetch(url+'/meta',{cache:'no-store',headers:{Accept:'application/json'}});
      if(!response.ok)return null;
      return await response.json();
    }catch(_error){return null}
  }

  function fallbackCopy(value){
    const area=document.createElement('textarea');
    area.value=String(value||'');area.readOnly=true;area.style.position='fixed';area.style.left='-9999px';
    document.body.appendChild(area);area.focus();area.select();area.setSelectionRange(0,area.value.length);
    let ok=false;try{ok=document.execCommand('copy')}catch(_error){}area.remove();return ok;
  }

  async function copy(value){
    const raw=String(value||'').trim();if(!raw)return false;
    if(navigator.clipboard&&window.isSecureContext){
      try{await navigator.clipboard.writeText(raw);return true}catch(_error){}
    }
    return fallbackCopy(raw);
  }

  function notify(message){
    const toast=document.getElementById('toast');if(!toast)return;
    toast.textContent=message;toast.classList.add('show');
    clearTimeout(window.__tpV38Toast);
    window.__tpV38Toast=setTimeout(()=>toast.classList.remove('show'),1500);
  }

  function link(label,href,primary){
    const node=document.createElement('a');node.textContent=label;node.href=href;
    if(primary)node.classList.add('v38-primary');
    if(/^https?:\/\//i.test(href)){node.target='_blank';node.rel='noopener noreferrer'}
    return node;
  }

  function button(label,handler,primary,copyClass){
    const node=document.createElement('button');node.type='button';node.textContent=label;
    if(primary)node.classList.add('v38-primary');
    if(copyClass)node.classList.add('v38-copy');
    node.addEventListener('click',handler);
    return node;
  }

  function clientName(panel){
    const label=text(panel.querySelector('.v34-client-card a'));
    return label.replace(/^دانلود\s+/,'').trim();
  }

  function importHref(protocol,client,url){
    const name=String(client||'').toLowerCase();
    if(name.includes('hiddify')){
      return 'hiddify://import/'+encodeURI(url)+'#TwinPanel-'+encodeURIComponent(protocol);
    }
    if(name.includes('karing')){
      return 'karing://install-config?url='+encodeURIComponent(url)+'&name='+encodeURIComponent('TwinPanel '+protocol);
    }
    return'';
  }

  function allCard(panel,protocol,url,count,kind){
    const card=document.createElement('section');card.className='v38-all-card';
    const head=document.createElement('div');head.className='v38-all-head';
    const title=document.createElement('b');title.textContent='همه سرورها';
    const counter=document.createElement('span');counter.textContent=String(count)+' سرور';
    head.append(title,counter);

    const actions=document.createElement('div');actions.className='v38-all-actions';
    const client=clientName(panel);
    const deep=importHref(protocol,client,url);
    const subscription=SUBSCRIPTIONS.has(protocol);
    const bundle=kind==='bundle'||NATIVE_BUNDLES.has(protocol);

    if(subscription&&deep){
      actions.appendChild(link('افزودن همه به '+client,deep,true));
      actions.appendChild(button('کپی لینک اشتراک',async()=>{
        notify(await copy(url)?'لینک اشتراک کپی شد ✓':'کپی انجام نشد');
      },false,true));
    }else if(subscription){
      actions.appendChild(button('کپی لینک اشتراک',async()=>{
        notify(await copy(url)?'لینک اشتراک کپی شد ✓':'کپی انجام نشد');
      },true,false));
    }else if(bundle){
      actions.appendChild(link('دانلود همه کانفیگ‌ها',url,true));
      actions.appendChild(button('کپی لینک همه سرورها',async()=>{
        notify(await copy(url)?'لینک همه سرورها کپی شد ✓':'کپی انجام نشد');
      },false,true));
    }else if(deep){
      actions.appendChild(link('افزودن همه به '+client,deep,true));
      actions.appendChild(button('کپی لینک همه سرورها',async()=>{
        notify(await copy(url)?'لینک همه سرورها کپی شد ✓':'کپی انجام نشد');
      },false,true));
    }else{
      actions.appendChild(button('کپی لینک همه سرورها',async()=>{
        notify(await copy(url)?'لینک همه سرورها کپی شد ✓':'کپی انجام نشد');
      },true,false));
    }

    card.append(head,actions);
    panel.querySelector('.panel-head')?.insertAdjacentElement('afterend',card);
    return card;
  }

  async function build(panel){
    if(panel.dataset.v38Requested==='1')return;
    const protocol=panelKey(panel);if(!MULTI.has(protocol))return;
    panel.dataset.v38Requested='1';

    panel.querySelectorAll('.v37-multi-card,.v38-all-card').forEach(node=>node.remove());

    if(SUBSCRIPTIONS.has(protocol)){
      const url=subscriptionUrl(protocol);
      const count=await subscriptionCount(protocol);
      if(!url||count<=0){delete panel.dataset.v38Requested;return}
      allCard(panel,protocol,url,count,'subscription');
      panel.dataset.v38Ready='1';
      return;
    }

    const url=multiUrl(protocol);
    const meta=await multiMeta(protocol);
    const count=Number(meta?.node_count||0);
    if(!url||!meta||count<=0){delete panel.dataset.v38Requested;return}
    allCard(panel,protocol,url,count,String(meta.kind||''));
    panel.dataset.v38Ready='1';
  }

  function apply(){
    document.body.classList.add('v38-reference');
    document.body.dataset.tpPublicReference='v38';
    document.querySelectorAll('.v37-multi-card').forEach(node=>node.remove());
    document.querySelectorAll('.protocol-panel').forEach(panel=>{void build(panel)});
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,250);
  window.setTimeout(apply,800);
})();
</script>
"""


def refine_public_connection_reference_layout_v38(source: str) -> str:
    """Restore the reference all-servers card after V37 without changing delivery/dataplane state."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
