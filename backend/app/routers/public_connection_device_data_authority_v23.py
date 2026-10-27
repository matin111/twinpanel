from __future__ import annotations

import json
from typing import Iterable


_MARKER = "TWINPANEL_PUBLIC_CONNECT_DEVICE_DATA_AUTHORITY_V23"

# Canonical field semantics are exact and mutually exclusive.  Device-specific
# UI is allowed to change presentation/actions, but never these connection
# facts or their values.
_ROLE_BY_LABEL = {
    "server & port": "endpoint",
    "server:port": "endpoint",
    "server and port": "endpoint",
    "آدرس سرور و پورت": "endpoint",
    "سرور و پورت": "endpoint",
    "server": "server",
    "server address": "server",
    "address": "server",
    "host": "server",
    "hostname": "server",
    "gateway": "server",
    "آدرس": "server",
    "آدرس سرور": "server",
    "سرور": "server",
    "port": "port",
    "پورت": "port",
    "username": "username",
    "user": "username",
    "account": "username",
    "نام کاربری": "username",
    "کاربری": "username",
    "یوزر": "username",
    "password": "password",
    "pass": "password",
    "رمز عبور": "password",
    "رمز": "password",
    "ipsec secret": "secret",
    "secret": "secret",
    "psk": "secret",
    "pre-shared key": "secret",
    "preshared key": "secret",
    "shared secret": "secret",
    "کلید مشترک": "secret",
    "رمز ipsec": "secret",
    "سکرت": "secret",
}


def canonical_role(label: str) -> str:
    """Return the one canonical semantic role for a rendered connection fact."""
    normalized = " ".join(str(label or "").strip().lower().split())
    return _ROLE_BY_LABEL.get(normalized, "info")


def canonical_manual_projection(
    rows: Iterable[tuple[str, str]], protocol: str
) -> dict[str, object]:
    """Pure regression helper mirroring the browser's device-neutral manual view.

    It intentionally preserves canonical labels/values and never splits a
    composite ``Server & Port`` value.  Tests use this helper to protect the
    invariant that mobile/desktop/device UI cannot rewrite connection data.
    """
    facts: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for label, value in rows:
        label_text = str(label or "").strip()
        value_text = str(value or "").strip()
        if not label_text or not value_text or value_text == "—":
            continue
        identity = (label_text, value_text)
        if identity in seen:
            continue
        seen.add(identity)
        facts.append(
            {
                "label": label_text,
                "value": value_text,
                "role": canonical_role(label_text),
            }
        )

    def first(role: str) -> dict[str, str] | None:
        return next((fact for fact in facts if fact["role"] == role), None)

    endpoint = first("endpoint")
    server = first("server")
    port = first("port")
    username = first("username")
    password = first("password")
    secret = first("secret")
    key = str(protocol or "").strip().lower()

    if not (endpoint or server) or username is None or password is None:
        return {"valid": False, "endpoint": "", "rows": []}
    if key == "l2tp" and secret is None:
        return {"valid": False, "endpoint": "", "rows": []}

    if endpoint is not None:
        endpoint_value = endpoint["value"]
    else:
        endpoint_value = str(server["value"] if server else "")
        port_value = str(port["value"] if port else "")
        if port_value and not endpoint_value.endswith(f":{port_value}"):
            endpoint_value = f"{endpoint_value}:{port_value}"

    allowed = {"endpoint", "server", "port", "username", "password"}
    if key == "l2tp":
        allowed.add("secret")
    projected = [fact for fact in facts if fact["role"] in allowed]
    return {"valid": True, "endpoint": endpoint_value, "rows": projected}


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_DEVICE_DATA_AUTHORITY_V23 */
@media(max-width:720px){
  .v17-server-row.v23-manual-invalid{display:none!important}
  .v17-server-copy small.v23-endpoint{
    color:var(--muted);
    font-size:12px;
    line-height:1.55;
    direction:ltr;
    text-align:right;
    unicode-bidi:plaintext;
  }
  .v17-details.v23-details{
    color:var(--text);
    background:color-mix(in srgb,var(--surface) 94%,var(--p) 6%);
    border:1px solid var(--line);
    font-size:12px;
    line-height:1.9;
  }
  .v17-action{font-size:12px;min-height:40px;padding:0 12px}
}
"""


_SCRIPT_TEMPLATE = r"""
<script id="twinpanelPublicConnectDeviceDataAuthorityV23">
(function(){
  const MOBILE='(max-width:720px)';
  const ROLE_BY_LABEL=__ROLE_MAP__;
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
  function normalizedLabel(value){return String(value||'').trim().toLowerCase().replace(/\s+/g,' ')}
  function roleForLabel(value){return ROLE_BY_LABEL[normalizedLabel(value)]||'info'}
  function toast(message){
    const el=document.getElementById('toast');
    if(!el)return;
    el.textContent=message;el.classList.add('show');
    clearTimeout(window.__tpV23Toast);
    window.__tpV23Toast=setTimeout(()=>el.classList.remove('show'),1800);
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
    const seen=new Set();
    return [...view.querySelectorAll('.fact')].map(fact=>{
      const label=text(fact.querySelector('small'));
      const value=text(fact.querySelector('strong'));
      const copyNode=fact.querySelector('[data-copy]');
      const copyValue=String(copyNode?.dataset?.copy||value).trim();
      if(!label||!value||value==='—')return null;
      const identity=label+'\u0000'+value;
      if(seen.has(identity))return null;
      seen.add(identity);
      return{label,value,copyValue,role:roleForLabel(label)};
    }).filter(Boolean);
  }
  function firstRole(rows,role){return rows.find(row=>row.role===role)||null}
  function manualProjection(view,key){
    const facts=canonicalFacts(view);
    const endpoint=firstRole(facts,'endpoint');
    const server=firstRole(facts,'server');
    const port=firstRole(facts,'port');
    const user=firstRole(facts,'username');
    const password=firstRole(facts,'password');
    const secret=firstRole(facts,'secret');
    if((!endpoint&&!server)||!user||!password)return null;
    if(key==='l2tp'&&!secret)return null;

    let endpointValue=endpoint?endpoint.value:server.value;
    if(!endpoint&&port&&port.value&&!endpointValue.endsWith(':'+port.value)){
      endpointValue=endpointValue+':'+port.value;
    }
    const allowed=new Set(['endpoint','server','port','username','password']);
    if(key==='l2tp')allowed.add('secret');
    return{rows:facts.filter(row=>allowed.has(row.role)),endpoint:endpointValue};
  }
  function detailsText(rows,useCopy){
    return rows.map(row=>row.label+': '+(useCopy?row.copyValue:row.value)).join('\n');
  }
  function choiceFor(panel){
    return [...document.querySelectorAll('.protocol-choice')].find(choice=>choice.dataset.protocol===panel.id)||null;
  }
  function keyFor(panel){return normalize(choiceFor(panel)?.dataset.protocolKey||panel.dataset.modernProtocol||'')}
  function panelForKey(key){
    return [...document.querySelectorAll('.protocol-panel')].find(panel=>keyFor(panel)===key)||null;
  }
  function rowName(row){return text(row.querySelector('.v17-server-copy b'))}
  function sourceViewForRow(row,panel){
    const bound=String(row.dataset.sourceViewId||'').trim();
    if(bound){
      const current=document.getElementById(bound);
      if(current&&panel.contains(current)&&current.classList.contains('server-view'))return current;
      delete row.dataset.sourceViewId;
    }

    const used=new Set(
      [...row.closest('.v17-server-list')?.querySelectorAll('.v17-server-row[data-source-view-id]')||[]]
        .filter(item=>item!==row)
        .map(item=>String(item.dataset.sourceViewId||''))
        .filter(Boolean)
    );
    const name=rowName(row);
    const tabs=[...panel.querySelectorAll('.server-tab[data-server]')];
    let tab=tabs.find(item=>text(item)===name&&!used.has(String(item.dataset.server||'')))||null;
    if(!tab)tab=tabs.find(item=>!used.has(String(item.dataset.server||'')))||null;
    const sourceId=String(tab?.dataset?.server||'').trim();
    const view=sourceId?document.getElementById(sourceId):null;
    if(!view||!panel.contains(view)||!view.classList.contains('server-view'))return null;
    row.dataset.sourceViewId=sourceId;
    return view;
  }
  function setDetails(row,rows){
    row.querySelectorAll('.v17-details').forEach(el=>el.remove());
    if(!rows.length)return;
    const detail=document.createElement('div');
    detail.className='v17-details v23-details';detail.textContent=detailsText(rows,false);row.appendChild(detail);
  }
  function addDetails(actions,row,rows){
    if(!rows.length)return;
    actions.appendChild(button('جزئیات',()=>row.classList.toggle('show-details'),false));
  }
  function updateEndpoint(row,endpoint,index){
    const small=row.querySelector('.v17-server-copy small');if(!small)return;
    small.textContent=endpoint||('سرور '+(index+1));
    small.classList.toggle('v23-endpoint',Boolean(endpoint));
  }
  function endpointFromFacts(rows){
    const endpoint=firstRole(rows,'endpoint');if(endpoint)return endpoint.value;
    const server=firstRole(rows,'server');if(!server)return'';
    const port=firstRole(rows,'port');
    if(port&&port.value&&!server.value.endsWith(':'+port.value))return server.value+':'+port.value;
    return server.value;
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
      function push(label,value,role){const rawValue=String(value??'').trim();if(rawValue)result.push({label,value:rawValue,copyValue:rawValue,role:role||'info'})}
      push('Server',out.server,'server');
      push('Port',out.server_port,'port');
      push('Username',out.username,'username');
      push('UUID',out.uuid,'info');
      push('Password',out.password,'password');
      push('PSK',out.psk,'secret');
      push('User Key',out.userkey,'info');
      push('SNI',out?.tls?.server_name,'info');
      return result;
    }catch(_error){return[]}
  }
  function rebuildManual(view,row,key,index){
    const actions=row.querySelector('.v17-server-actions');if(!actions)return false;
    const projection=manualProjection(view,key);
    if(!projection){row.classList.add('v23-manual-invalid');return false}
    row.classList.remove('v23-manual-invalid');
    actions.replaceChildren();setDetails(row,projection.rows);updateEndpoint(row,projection.endpoint,index);
    const copyValue=detailsText(projection.rows,true);
    actions.appendChild(button('کپی اطلاعات',async()=>toast(await copy(copyValue)?'اطلاعات کپی شد ✓':'کپی انجام نشد'),true));
    addDetails(actions,row,projection.rows);
    return true;
  }
  function rebuildFile(view,row,index){
    const actions=row.querySelector('.v17-server-actions');if(!actions)return;
    const rows=canonicalFacts(view);actions.replaceChildren();setDetails(row,rows);updateEndpoint(row,endpointFromFacts(rows),index);
    addCopyConfig(actions,view,'کپی کانفیگ');
    const source=fileDownload(view);const download=cloneAction(source,'دانلود کانفیگ',true);if(download)actions.appendChild(download);
    addDetails(actions,row,rows);
  }
  function rebuildXray(view,row,index){
    const actions=row.querySelector('.v17-server-actions');if(!actions)return;
    const rows=canonicalFacts(view);actions.replaceChildren();setDetails(row,rows);updateEndpoint(row,endpointFromFacts(rows),index);
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
    const rows=modernDetails(view,key);actions.replaceChildren();setDetails(row,rows);updateEndpoint(row,endpointFromFacts(rows),index);
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
    const rows=[...card.querySelectorAll('.v17-server-list>.v17-server-row:not(.v18-not-ready)')];
    const manual=key==='cisco'||key==='l2tp';
    const fileBased=['openvpn','wireguard','amneziawg'].includes(key);
    const modern=['hysteria2','tuic','anytls','naive','shadowtls','snell','mieru','trusttunnel','sudoku'].includes(key);
    rows.forEach((row,index)=>{
      const view=sourceViewForRow(row,panel);if(!view)return;
      if(manual){rebuildManual(view,row,key,index);return}
      if(fileBased){rebuildFile(view,row,index);return}
      if(key==='xray'){rebuildXray(view,row,index);return}
      if(modern){rebuildModern(view,row,key,index);return}
    });
    card.querySelectorAll('.v18-not-ready').forEach(row=>row.remove());
    const liveRows=[...card.querySelectorAll('.v17-server-list>.v17-server-row:not(.v23-manual-invalid)')];
    const count=card.querySelector('.v17-count');if(count)count.textContent=liveRows.length+' سرور';
    if(!liveRows.length)card.remove();
  }
  function patch(){
    if(patching||!window.matchMedia(MOBILE).matches)return;
    patching=true;
    try{document.querySelectorAll('.v17-protocol-card[data-protocol-key]').forEach(patchCard)}
    finally{patching=false}
    document.body.dataset.tpDeviceDataV23='ready';
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

_SCRIPT = _SCRIPT_TEMPLATE.replace(
    "__ROLE_MAP__",
    json.dumps(_ROLE_BY_LABEL, ensure_ascii=False, separators=(",", ":")),
)


def refine_public_connection_device_data_authority_v23(source: str) -> str:
    """Render device-specific mobile UI from one canonical connection source.

    The final device layer may change layout/actions, but it must preserve the
    exact connection facts emitted by the canonical server views.
    """
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
