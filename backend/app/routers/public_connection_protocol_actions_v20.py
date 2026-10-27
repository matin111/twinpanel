from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_PROTOCOL_ACTIONS_V20"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_PROTOCOL_ACTIONS_V20 */

/* Readability: the public connection page must stay legible on every device. */
.protocol-choice .protocol-text b{font-size:14px;line-height:1.45}
.protocol-choice .protocol-text small,.protocol-choice em{font-size:11px;line-height:1.55}
.panel-head span,.server-tab,.v13-app,.v13-secondary,.copy-btn,.primary-btn{font-size:12px;line-height:1.5}
.panel-head h3{font-size:18px;line-height:1.4}
.fact small{font-size:12px;line-height:1.5}
.fact strong{font-size:14px;line-height:1.55}
.v13-action-copy b,.v13-pending-body b{font-size:13px}
.v13-action-copy small,.v13-pending-body small,.v13-pending-body p,.v13-native-client,.v13-client-only>span{font-size:11px;line-height:1.7}
.tp-v20-hidden-pending{display:none!important}

@media(max-width:720px){
  .v17-summary{min-height:68px;padding:10px 12px;grid-template-columns:44px minmax(0,1fr) auto 20px;gap:10px}
  .v17-mark{width:44px;height:44px;border-radius:12px;font-size:13px}
  .v17-title b{font-size:15px;line-height:1.5}
  .v17-title small{font-size:12px;line-height:1.55;margin-top:3px}
  .v17-count{min-width:68px;height:30px;padding:0 10px;font-size:11px}
  .v17-body{padding:0 10px 10px}
  .v17-device-app{min-height:44px;padding:8px 11px}
  .v17-device-app span,.v17-device-app a{font-size:12px;line-height:1.5}
  .v17-server-list{gap:8px}
  .v17-server-row{min-height:68px;padding:10px;gap:10px}
  .v17-server-copy b{font-size:14px;line-height:1.5}
  .v17-server-copy small{font-size:11px;line-height:1.5;margin-top:4px}
  .v17-server-actions{gap:7px;flex-wrap:wrap;justify-content:flex-end}
  .v17-action{min-height:38px;padding:0 11px;border-radius:10px;font-size:11px;line-height:1.4}
  .v17-details{padding:10px;font-size:12px;line-height:1.85;border-radius:10px}
  .v17-pending{font-size:12px;line-height:1.7;padding:12px}
}

@media(min-width:721px){
  .page{font-size:14px}
  .protocol-choice{min-height:78px}
  .server-view{font-size:14px}
  .primary-btn,.copy-btn,.v13-secondary,.v13-app{min-height:40px;padding:9px 13px}
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectProtocolActionsV20">
(function(){
  const MOBILE='(max-width:720px)';

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
    clearTimeout(window.__tpV20Toast);
    window.__tpV20Toast=setTimeout(()=>el.classList.remove('show'),1800);
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
  function findOutbound(doc,type){
    const rows=Array.isArray(doc?.outbounds)?doc.outbounds:[];
    return rows.find(row=>row&&typeof row==='object'&&String(row.type||'').toLowerCase()===type)||null;
  }
  function tlsSni(out){return String(out?.tls?.server_name||'').trim()}
  function line(label,value){
    const raw=String(value??'').trim();
    return raw?[label,raw]:null;
  }
  function jsonOrNull(raw){
    try{const value=JSON.parse(String(raw||''));return value&&typeof value==='object'?value:null}catch(_error){return null}
  }
  function protocolDetails(view,key){
    const raw=canonicalCopy(view);
    const doc=jsonOrNull(raw);
    let out=null,rows=[];

    if(key==='cisco'||key==='l2tp'||key==='trusttunnel')return canonicalFacts(view);
    if(key==='openvpn'||key==='wireguard'||key==='xray')return [];

    if(key==='hysteria2'&&doc){
      out=findOutbound(doc,'hysteria2');
      rows=[line('Server',out?.server),line('Port',out?.server_port),line('Password',out?.password),line('SNI',tlsSni(out))];
    }else if(key==='tuic'&&doc){
      out=findOutbound(doc,'tuic');
      rows=[line('Server',out?.server),line('Port',out?.server_port),line('UUID',out?.uuid),line('Password',out?.password),line('SNI',tlsSni(out))];
    }else if(key==='anytls'&&doc){
      out=findOutbound(doc,'anytls');
      rows=[line('Server',out?.server),line('Port',out?.server_port),line('Password',out?.password),line('SNI',tlsSni(out))];
    }else if(key==='naive'&&doc){
      out=findOutbound(doc,'naive');
      rows=[line('Server',out?.server),line('Port',out?.server_port),line('Username',out?.username),line('Password',out?.password),line('TLS Server Name',tlsSni(out))];
    }else if(key==='shadowtls'&&doc){
      out=findOutbound(doc,'shadowtls');
      rows=[line('Server',out?.server),line('Port',out?.server_port),line('Password',out?.password),line('Handshake / SNI',tlsSni(out)),line('Version',out?.version)];
    }else if(key==='snell'&&doc){
      out=findOutbound(doc,'snell');
      rows=[line('Server',out?.server),line('Port',out?.server_port),line('PSK',out?.psk),line('User Key',out?.userkey),line('Version',out?.version)];
    }else if(key==='mieru'&&doc){
      const profile=Array.isArray(doc.profiles)?doc.profiles[0]:null;
      const server=Array.isArray(profile?.servers)?profile.servers[0]:null;
      const binding=Array.isArray(server?.portBindings)?server.portBindings[0]:null;
      rows=[line('Server',server?.domainName||server?.ipAddress),line('Port',binding?.port),line('Username',profile?.user?.name),line('Password',profile?.user?.password)];
    }else if(key==='amneziawg'){
      const endpoint=String(raw).match(/^Endpoint\s*=\s*(.+)$/mi)?.[1];
      const address=String(raw).match(/^Address\s*=\s*(.+)$/mi)?.[1];
      const serverKey=String(raw).match(/^PublicKey\s*=\s*(.+)$/mi)?.[1];
      rows=[line('Endpoint',endpoint),line('Address',address),line('Server Public Key',serverKey)];
    }else if(key==='sudoku'&&doc){
      rows=[line('Server Address',doc.server_address),line('Key',doc.key),line('AEAD',doc.aead)];
    }

    rows=rows.filter(Boolean);
    return rows.length?rows:canonicalFacts(view);
  }
  function detailsText(rows){return rows.map(row=>row[0]+': '+row[1]).join('\n')}
  function choiceFor(panel){
    return [...document.querySelectorAll('.protocol-choice')].find(choice=>choice.dataset.protocol===panel.id)||null;
  }
  function keyFor(panel){return normalize(choiceFor(panel)?.dataset.protocolKey||panel.dataset.modernProtocol||'')}
  function panels(){
    const out=[],seen=new Set();
    document.querySelectorAll('.protocol-panel').forEach(panel=>{
      const key=keyFor(panel);if(!key||seen.has(key))return;seen.add(key);out.push(panel);
    });
    return out;
  }
  function cloneAction(source,label,primary){
    if(!source)return null;
    let out;
    if(source.tagName==='A'){
      out=document.createElement('a');out.href=source.getAttribute('href')||'#';
      if(source.target)out.target=source.target;if(source.rel)out.rel=source.rel;
    }else{
      out=document.createElement('button');out.type='button';out.addEventListener('click',()=>source.click());
    }
    out.className='v17-action'+(primary?' primary':'');out.textContent=label;return out;
  }
  function button(label,handler,primary){
    const el=document.createElement('button');el.type='button';el.className='v17-action'+(primary?' primary':'');el.textContent=label;el.addEventListener('click',handler);return el;
  }
  function setDetails(row,rows){
    row.querySelectorAll('.v17-details').forEach(el=>el.remove());
    if(!rows.length)return;
    const detail=document.createElement('div');detail.className='v17-details';detail.textContent=detailsText(rows);row.appendChild(detail);
  }
  function addDetailsAction(actions,row,rows){
    if(!rows.length)return;
    actions.appendChild(button('جزئیات',()=>row.classList.toggle('show-details'),false));
  }
  function addCopyAction(actions,view,label){
    const value=canonicalCopy(view);if(!value)return;
    actions.appendChild(button(label||'کپی کانفیگ',async()=>toast(await copy(value)?'کپی شد ✓':'کپی انجام نشد'),false));
  }
  function rebuildMobileActions(view,row,key){
    const actions=row.querySelector('.v17-server-actions');if(!actions)return;
    actions.replaceChildren();
    const rows=protocolDetails(view,key);setDetails(row,rows);

    const manual=key==='cisco'||key==='l2tp';
    const fileBased=['openvpn','wireguard','amneziawg'].includes(key);
    const uriBased=key==='xray';
    const modern=['hysteria2','tuic','anytls','naive','shadowtls','snell','mieru','trusttunnel','sudoku'].includes(key);

    if(manual){
      const value=detailsText(rows);
      if(value)actions.appendChild(button('کپی اطلاعات',async()=>toast(await copy(value)?'اطلاعات کپی شد ✓':'کپی انجام نشد'),true));
      addDetailsAction(actions,row,rows);
      return;
    }

    if(fileBased){
      addCopyAction(actions,view,'کپی کانفیگ');
      const download=view.querySelector('.download-config,.v13-secondary,.tp-v16-safe-download,a[href*="modern-config"]');
      const action=cloneAction(download,'دانلود کانفیگ',true);if(action)actions.appendChild(action);
      addDetailsAction(actions,row,rows);
      return;
    }

    if(uriBased){
      const uri=view.querySelector('.copy-btn[data-copy]');
      if(uri&&String(uri.dataset.copy||''))actions.appendChild(button('کپی لینک',async()=>toast(await copy(uri.dataset.copy)?'لینک کپی شد ✓':'کپی انجام نشد'),false));
      const open=view.querySelector('a.primary-btn[href],a.v13-open-uri[href]');
      const action=cloneAction(open,'باز کردن در برنامه',true);if(action)actions.appendChild(action);
      return;
    }

    if(modern){
      addCopyAction(actions,view,key==='trusttunnel'||key==='sudoku'?'کپی لینک / کانفیگ':'کپی کانفیگ');
      const modernBox=view.querySelector('.v13-modern-action');
      const primary=modernBox?.querySelector('.primary-btn');
      const secondary=modernBox?.querySelector('.v13-secondary,.tp-v16-safe-download');
      if(primary){
        const label=primary.classList.contains('v15-karing-inline')||String(primary.getAttribute('href')||'').startsWith('karing:')?'افزودن به Karing':(primary.tagName==='A'&&String(primary.getAttribute('href')||'').match(/^[a-z0-9+.-]+:\/\//i)?'باز کردن در برنامه':'دانلود کانفیگ');
        const action=cloneAction(primary,label,true);if(action)actions.appendChild(action);
      }
      if(secondary){const action=cloneAction(secondary,'دانلود فایل',false);if(action)actions.appendChild(action)}
      addDetailsAction(actions,row,rows);
    }
  }
  function removeFakePublicInventory(){
    document.querySelectorAll('.v18-not-ready').forEach(row=>row.remove());
    document.querySelectorAll('.v17-protocol-card').forEach(card=>{
      const list=card.querySelector('.v17-server-list');
      const realRows=list?[...list.querySelectorAll('.v17-server-row:not(.v18-not-ready)')]:[];
      const count=card.querySelector('.v17-count');
      const subtitle=card.querySelector('.v17-title small');
      if(count)count.textContent=realRows.length?realRows.length+' سرور':'بدون سرور';
      if(!realRows.length){card.remove();return}
      if(subtitle&&!card.classList.contains('v18-live-online'))subtitle.textContent='آماده اتصال';
      card.dataset.v18BaseSubtitle='آماده اتصال';
    });

    /* Pending Modern cards are internal provisioning state, not customer servers. */
    document.querySelectorAll('.protocol-choice.v13-pending,.v13-pending-panel').forEach(el=>el.classList.add('tp-v20-hidden-pending'));
  }
  function stripInvalidClassicDownloads(){
    document.querySelectorAll('.protocol-panel').forEach(panel=>{
      const key=keyFor(panel);if(key!=='cisco'&&key!=='l2tp')return;
      panel.querySelectorAll('.server-view .download-config,.server-view a[href*="modern-config"],.server-view .tp-v16-safe-download').forEach(el=>el.remove());
    });
  }
  function patchMobile(){
    if(!window.matchMedia(MOBILE).matches)return;
    const sourcePanels=panels();
    const cards=[...document.querySelectorAll('.v17-protocol-card')];
    cards.forEach((card,index)=>{
      const panel=sourcePanels[index];if(!panel)return;
      const key=keyFor(panel);card.dataset.protocolKey=key;
      const views=[...panel.querySelectorAll('.server-view')];
      const rows=[...card.querySelectorAll('.v17-server-list>.v17-server-row:not(.v18-not-ready)')];
      views.forEach((view,i)=>{if(rows[i])rebuildMobileActions(view,rows[i],key)});
    });
    removeFakePublicInventory();
  }
  function start(){
    stripInvalidClassicDownloads();
    window.setTimeout(patchMobile,100);
  }
  window.setTimeout(start,0);
})();
</script>
"""


def refine_public_connection_protocol_actions_v20(source: str) -> str:
    """Keep public connection actions protocol-correct, real-config-only and readable."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    source = source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
    return source
