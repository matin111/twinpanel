from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_PROTOCOL_ACTION_AUTHORITY_V22"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_PROTOCOL_ACTION_AUTHORITY_V22 */
@media(max-width:720px){
  .v17-server-row.v22-manual-invalid{display:none!important}
  .v17-server-copy small.v22-endpoint{
    color:var(--muted);
    font-size:12px;
    line-height:1.55;
    direction:ltr;
    text-align:right;
    unicode-bidi:plaintext;
  }
  .v17-details.v22-details{
    color:var(--text);
    background:color-mix(in srgb,var(--surface) 94%,var(--p) 6%);
    border:1px solid var(--line);
    font-size:12px;
    line-height:1.9;
  }
  .v17-action{font-size:12px;min-height:40px;padding:0 12px}
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectProtocolActionAuthorityV22">
(function(){
  const MOBILE='(max-width:720px)';
  let observer=null;
  let timer=null;
  let patching=false;

  function normalize(value){
    const key=String(value||'').trim().toLowerCase();
    if(key==='naiveproxy')return'naive';
    if(key==='openconnect'||key==='ocserv'||key==='anyconnect')return'cisco';
    if(key==='v2ray')return'xray';
    return key;
  }
  function text(el){return String(el?.textContent||'').trim()}
  function toast(message){
    const el=document.getElementById('toast');
    if(!el)return;
    el.textContent=message;el.classList.add('show');
    clearTimeout(window.__tpV22Toast);
    window.__tpV22Toast=setTimeout(()=>el.classList.remove('show'),1800);
  }
  function fallbackCopy(value){
    const area=document.createElement('textarea');
    area.value=String(value||'');area.readOnly=true;
    area.style.position='fixed';area.style.left='-9999px';area.style.top='0';
    document.body.appendChild(area);area.focus();area.select();
    area.setSelectionRange(0,area.value.length);
    let ok=false;try{ok=document.execCommand('copy')}catch(_error){}
    area.remove();return ok;
  }
  async function copy(value){
    const raw=String(value||'');if(!raw)return false;
    if(navigator.clipboard&&window.isSecureContext){
      try{await navigator.clipboard.writeText(raw);return true}catch(_error){}
    }
    return fallbackCopy(raw);
  }
  function button(label,handler,primary){
    const el=document.createElement('button');
    el.type='button';el.className='v17-action'+(primary?' primary':'');el.textContent=label;
    el.addEventListener('click',handler);return el;
  }
  function cloneAction(source,label,primary){
    if(!source)return null;
    let out;
    if(source.tagName==='A'){
      out=document.createElement('a');out.href=source.getAttribute('href')||'#';
      if(source.target)out.target=source.target;
      if(source.rel)out.rel=source.rel;
      if(source.hasAttribute('download'))out.setAttribute('download',source.getAttribute('download')||'');
    }else{
      out=document.createElement('button');out.type='button';out.addEventListener('click',()=>source.click());
    }
    out.className='v17-action'+(primary?' primary':'');out.textContent=label;return out;
  }
  function sourceValue(id){
    const el=document.getElementById(String(id||''));
    return el?String('value' in el?el.value:el.textContent||''):'';
  }
  function canonicalCopy(view){
    const target=view.querySelector('[data-tp-copy-target]');
    if(target){const value=sourceValue(target.dataset.tpCopyTarget);if(value)return value}
    const direct=view.querySelector('.copy-btn[data-copy]');
    if(direct&&String(direct.dataset.copy||'').trim())return String(direct.dataset.copy||'');
    const download=view.querySelector('.download-config[data-target]');
    if(download){const value=sourceValue(download.dataset.target);if(value)return value}
    const open=view.querySelector('a.v13-open-uri[href]');
    if(open)return String(open.getAttribute('href')||'');
    return'';
  }
  function canonicalFacts(view){
    return [...view.querySelectorAll('.fact')].map(fact=>{
      const label=text(fact.querySelector('small'));
      const value=text(fact.querySelector('strong'));
      return label&&value&&value!=='—'?[label,value]:null;
    }).filter(Boolean);
  }
  function token(value){
    return String(value||'').trim().toLowerCase().replace(/[\s_:\-\/]+/g,'');
  }
  function isServerLabel(label){
    const t=token(label);
    return ['server','serveraddress','address','host','hostname','gateway','آدرس','آدرسسرور','سرور'].some(v=>t.includes(token(v)));
  }
  function isPortLabel(label){const t=token(label);return t.includes('port')||t.includes('پورت')}
  function isUserLabel(label){
    const t=token(label);
    return ['username','user','account','نامکاربری','کاربری','یوزر'].some(v=>t.includes(token(v)));
  }
  function isPasswordLabel(label){
    const t=token(label);
    return ['password','pass','رمزعبور','رمز'].some(v=>t.includes(token(v)));
  }
  function isSecretLabel(label){
    const t=token(label);
    return ['ipsecsecret','secret','psk','presharedkey','sharedsecret','کلیدمشترک','رمزipsec','سکرت'].some(v=>t.includes(token(v)));
  }
  function pick(rows,predicate){return rows.find(row=>predicate(row[0]))||null}
  function manualDetails(view,key){
    const facts=canonicalFacts(view);
    const server=pick(facts,isServerLabel);
    const port=pick(facts,isPortLabel);
    const user=pick(facts,isUserLabel);
    const password=pick(facts,isPasswordLabel);
    const secret=pick(facts,isSecretLabel);
    if(!server||!user||!password)return[];
    if(key==='l2tp'&&!secret)return[];
    return [server,port,user,password,key==='l2tp'?secret:null].filter(Boolean);
  }
  function detailsText(rows){return rows.map(row=>row[0]+': '+row[1]).join('\n')}
  function endpointFrom(rows){
    const server=pick(rows,isServerLabel);
    const port=pick(rows,isPortLabel);
    if(!server)return'';
    return port?server[1]+':'+port[1]:server[1];
  }
  function choiceFor(panel){
    return [...document.querySelectorAll('.protocol-choice')].find(choice=>choice.dataset.protocol===panel.id)||null;
  }
  function keyFor(panel){return normalize(choiceFor(panel)?.dataset.protocolKey||panel.dataset.modernProtocol||'')}
  function panelForKey(key){
    return [...document.querySelectorAll('.protocol-panel')].find(panel=>keyFor(panel)===key)||null;
  }
  function setDetails(row,rows){
    row.querySelectorAll('.v17-details').forEach(el=>el.remove());
    if(!rows.length)return;
    const detail=document.createElement('div');
    detail.className='v17-details v22-details';detail.textContent=detailsText(rows);row.appendChild(detail);
  }
  function addDetails(actions,row,rows){
    if(!rows.length)return;
    actions.appendChild(button('جزئیات',()=>row.classList.toggle('show-details'),false));
  }
  function updateEndpoint(row,rows,index){
    const small=row.querySelector('.v17-server-copy small');if(!small)return;
    const endpoint=endpointFrom(rows);
    small.textContent=endpoint||('سرور '+(index+1));
    small.classList.toggle('v22-endpoint',Boolean(endpoint));
  }
  function addCopyConfig(actions,view,label){
    const value=canonicalCopy(view);if(!value)return;
    actions.appendChild(button(label,async()=>toast(await copy(value)?'کپی شد ✓':'کپی انجام نشد'),false));
  }
  function fileDownload(view){
    return view.querySelector('.download-config,.tp-v16-safe-download,a[href*="modern-config"]');
  }
  function modernDetails(view,key){
    const facts=canonicalFacts(view);
    if(facts.length)return facts;
    const raw=canonicalCopy(view);
    if(!raw)return[];
    try{
      const doc=JSON.parse(raw);
      const rows=Array.isArray(doc?.outbounds)?doc.outbounds:[];
      const type=key==='naive'?'naive':key;
      const out=rows.find(item=>item&&String(item.type||'').toLowerCase()===type)||null;
      if(!out)return[];
      const result=[];
      if(out.server)result.push(['Server',String(out.server)]);
      if(out.server_port)result.push(['Port',String(out.server_port)]);
      if(out.username)result.push(['Username',String(out.username)]);
      if(out.uuid)result.push(['UUID',String(out.uuid)]);
      if(out.password)result.push(['Password',String(out.password)]);
      if(out.psk)result.push(['PSK',String(out.psk)]);
      if(out.userkey)result.push(['User Key',String(out.userkey)]);
      const sni=String(out?.tls?.server_name||'');if(sni)result.push(['SNI',sni]);
      return result;
    }catch(_error){return[]}
  }
  function rebuildManual(view,row,key,index){
    const actions=row.querySelector('.v17-server-actions');if(!actions)return false;
    const rows=manualDetails(view,key);
    if(!rows.length){row.classList.add('v22-manual-invalid');return false}
    row.classList.remove('v22-manual-invalid');
    actions.replaceChildren();setDetails(row,rows);updateEndpoint(row,rows,index);
    const value=detailsText(rows);
    actions.appendChild(button('کپی اطلاعات',async()=>toast(await copy(value)?'اطلاعات کپی شد ✓':'کپی انجام نشد'),true));
    addDetails(actions,row,rows);
    return true;
  }
  function rebuildFile(view,row,key,index){
    const actions=row.querySelector('.v17-server-actions');if(!actions)return;
    const rows=canonicalFacts(view);actions.replaceChildren();setDetails(row,rows);updateEndpoint(row,rows,index);
    addCopyConfig(actions,view,'کپی کانفیگ');
    const source=fileDownload(view);const download=cloneAction(source,'دانلود کانفیگ',true);if(download)actions.appendChild(download);
    addDetails(actions,row,rows);
  }
  function rebuildXray(view,row,index){
    const actions=row.querySelector('.v17-server-actions');if(!actions)return;
    const rows=canonicalFacts(view);actions.replaceChildren();setDetails(row,rows);updateEndpoint(row,rows,index);
    const direct=view.querySelector('.copy-btn[data-copy]');
    if(direct&&String(direct.dataset.copy||'').trim()){
      actions.appendChild(button('کپی لینک',async()=>toast(await copy(direct.dataset.copy)?'لینک کپی شد ✓':'کپی انجام نشد'),false));
    }
    const open=view.querySelector('a.primary-btn[href],a.v13-open-uri[href]');
    const action=cloneAction(open,'باز کردن در برنامه',true);if(action)actions.appendChild(action);
    addDetails(actions,row,rows);
  }
  function rebuildModern(view,row,key,index){
    const actions=row.querySelector('.v17-server-actions');if(!actions)return;
    const rows=modernDetails(view,key);actions.replaceChildren();setDetails(row,rows);updateEndpoint(row,rows,index);
    addCopyConfig(actions,view,key==='trusttunnel'||key==='sudoku'?'کپی لینک / کانفیگ':'کپی کانفیگ');
    const box=view.querySelector('.v13-modern-action');
    const primary=box?.querySelector('.primary-btn');
    const secondary=box?.querySelector('.v13-secondary,.tp-v16-safe-download');
    if(primary){
      const href=String(primary.getAttribute?.('href')||'');
      const label=primary.classList.contains('v15-karing-inline')||href.startsWith('karing:')?'افزودن به Karing':(/^[a-z0-9+.-]+:\/\//i.test(href)?'باز کردن در برنامه':'دانلود کانفیگ');
      const action=cloneAction(primary,label,true);if(action)actions.appendChild(action);
    }
    if(secondary&&secondary!==primary){
      const action=cloneAction(secondary,'دانلود فایل',false);if(action)actions.appendChild(action);
    }
    addDetails(actions,row,rows);
  }
  function patchCard(card){
    const key=normalize(card.dataset.protocolKey||'');if(!key)return;
    const panel=panelForKey(key);if(!panel)return;
    const views=[...panel.querySelectorAll('.server-view')];
    const rows=[...card.querySelectorAll('.v17-server-list>.v17-server-row:not(.v18-not-ready)')];
    const manual=key==='cisco'||key==='l2tp';
    const fileBased=['openvpn','wireguard','amneziawg'].includes(key);
    const modern=['hysteria2','tuic','anytls','naive','shadowtls','snell','mieru','trusttunnel','sudoku'].includes(key);
    let valid=0;
    rows.forEach((row,index)=>{
      const view=views[index];if(!view){row.remove();return}
      if(manual){if(rebuildManual(view,row,key,index))valid+=1;return}
      valid+=1;
      if(fileBased){rebuildFile(view,row,key,index);return}
      if(key==='xray'){rebuildXray(view,row,index);return}
      if(modern){rebuildModern(view,row,key,index);return}
    });
    card.querySelectorAll('.v18-not-ready').forEach(row=>row.remove());
    const liveRows=[...card.querySelectorAll('.v17-server-list>.v17-server-row:not(.v22-manual-invalid)')];
    const count=card.querySelector('.v17-count');if(count)count.textContent=liveRows.length+' سرور';
    if(!liveRows.length)card.remove();
  }
  function patch(){
    if(patching||!window.matchMedia(MOBILE).matches)return;
    patching=true;
    try{document.querySelectorAll('.v17-protocol-card[data-protocol-key]').forEach(patchCard)}
    finally{patching=false}
    document.body.dataset.tpProtocolActionsV22='ready';
  }
  function reconnectObserver(){
    const stack=document.querySelector('.v17-mobile-stack');
    if(!stack){window.setTimeout(reconnectObserver,80);return}
    observer?.disconnect();
    observer=new MutationObserver(()=>{
      clearTimeout(timer);
      timer=window.setTimeout(()=>{
        observer?.disconnect();patch();reconnectObserver();
      },0);
    });
    observer.observe(stack,{childList:true,subtree:true});
    patch();
  }
  window.setTimeout(reconnectObserver,0);
})();
</script>
"""


def refine_public_connection_protocol_action_authority_v22(source: str) -> str:
    """Keep mobile actions protocol-native and bind details to the real source server view."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
