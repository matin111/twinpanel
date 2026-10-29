from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_FINAL_PRESENTATION_V37"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_FINAL_PRESENTATION_V37 */
body.v37-ready .v34-subscription-card{display:none!important}
body.v37-ready .v37-multi-card{
  margin:12px;
  padding:13px;
  border:1px solid color-mix(in srgb,var(--p) 34%,var(--line));
  border-radius:14px;
  background:linear-gradient(145deg,color-mix(in srgb,var(--p) 7%,var(--surface2)),var(--surface2));
}
body.v37-ready .v37-multi-head{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  margin-bottom:10px;
}
body.v37-ready .v37-multi-head b{font-size:14px;line-height:1.5}
body.v37-ready .v37-multi-head span{color:var(--muted);font-size:11px;font-weight:800}
body.v37-ready .v37-multi-actions{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:8px;
}
body.v37-ready .v37-multi-actions>a,
body.v37-ready .v37-multi-actions>button{
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
body.v37-ready .v37-primary{
  border-color:var(--p)!important;
  background:var(--p)!important;
  color:#fff!important;
}
body.v37-ready .v37-copy{color:var(--p)!important}

@media(max-width:720px){
  body.v37-ready .v37-multi-card{margin:10px;padding:11px}
  body.v37-ready .v37-multi-actions{grid-template-columns:1fr}
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectFinalPresentationV37">
(function(){
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
    return normalize(choice?.dataset?.protocolKey||'');
  }

  function token(){
    const match=String(window.location.pathname||'').match(/^\/v1\/connect\/([^/]+)/);
    if(!match)return'';
    try{return decodeURIComponent(match[1])}catch(_error){return match[1]}
  }

  function multiUrl(protocol){
    const value=token();
    if(!value||!MULTI.has(protocol))return'';
    return window.location.origin+'/v1/connect/'+encodeURIComponent(value)+'/multi/'+encodeURIComponent(protocol);
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
    clearTimeout(window.__tpV37Toast);
    window.__tpV37Toast=setTimeout(()=>toast.classList.remove('show'),1500);
  }

  function link(label,href,primary){
    const node=document.createElement('a');node.textContent=label;node.href=href;
    if(primary)node.classList.add('v37-primary');
    if(/^https?:\/\//i.test(href)){node.target='_blank';node.rel='noopener noreferrer'}
    return node;
  }

  function button(label,handler,primary,copyClass){
    const node=document.createElement('button');node.type='button';node.textContent=label;
    if(primary)node.classList.add('v37-primary');
    if(copyClass)node.classList.add('v37-copy');
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

  function removeNoise(){
    document.querySelectorAll('.smart-card,.smart-empty').forEach(node=>node.remove());
    document.querySelectorAll('.section-head').forEach(node=>{
      const heading=text(node.querySelector('h2'));
      if(heading==='اتصال هوشمند'){
        node.remove();
        return;
      }
      node.querySelectorAll('small,p').forEach(extra=>extra.remove());
    });
    document.querySelectorAll('.panel-head>div>span,.v34-single-label').forEach(node=>node.remove());
    document.querySelectorAll('.v34-subscription-card').forEach(node=>node.remove());
  }

  async function buildMulti(panel){
    if(panel.dataset.v37MultiRequested==='1')return;
    const protocol=panelKey(panel);
    if(!MULTI.has(protocol))return;
    const url=multiUrl(protocol);if(!url)return;

    panel.dataset.v37MultiRequested='1';
    const meta=await multiMeta(protocol);
    if(!meta||Number(meta.node_count||0)<=0){
      delete panel.dataset.v37MultiRequested;
      return;
    }

    panel.querySelectorAll('.v37-multi-card').forEach(node=>node.remove());
    const card=document.createElement('section');card.className='v37-multi-card';
    const head=document.createElement('div');head.className='v37-multi-head';
    const title=document.createElement('b');title.textContent='همه سرورها';
    const count=document.createElement('span');count.textContent=String(meta.node_count)+' سرور';
    head.append(title,count);

    const actions=document.createElement('div');actions.className='v37-multi-actions';
    const client=clientName(panel);
    const deep=importHref(protocol,client,url);
    const bundle=String(meta.kind||'')==='bundle'||NATIVE_BUNDLES.has(protocol);

    if(bundle){
      actions.appendChild(link('دانلود همه کانفیگ‌ها',url,true));
    }else if(deep){
      actions.appendChild(link('افزودن همه به '+client,deep,true));
    }else{
      actions.appendChild(button('کپی لینک همه سرورها',async()=>{
        notify(await copy(url)?'لینک همه سرورها کپی شد ✓':'کپی انجام نشد');
      },true,false));
    }

    if(bundle||deep){
      actions.appendChild(button('کپی لینک همه سرورها',async()=>{
        notify(await copy(url)?'لینک همه سرورها کپی شد ✓':'کپی انجام نشد');
      },false,true));
    }

    card.append(head,actions);
    const clientCard=panel.querySelector('.v34-client-card');
    if(clientCard)clientCard.insertAdjacentElement('beforebegin',card);
    else panel.querySelector('.panel-head')?.insertAdjacentElement('afterend',card);
    panel.dataset.v37MultiReady='1';
  }

  function apply(){
    document.body.classList.add('v37-ready');
    document.body.dataset.tpPublicFinal='v37';
    removeNoise();
    document.querySelectorAll('.protocol-panel').forEach(panel=>{void buildMulti(panel)});
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,220);
  window.setTimeout(apply,700);
})();
</script>
"""


def refine_public_connection_final_presentation_v37(source: str) -> str:
    """Restore all-protocol multi links and remove customer-facing presentation noise after V34."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
