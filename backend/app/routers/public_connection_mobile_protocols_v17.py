from __future__ import annotations


_MOBILE_PROTOCOLS_V17_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_MOBILE_PROTOCOLS_V17 */
/* TWINPANEL_MOBILE_ADAPTIVE_DELIVERY_V294 */
.v17-mobile-stack{display:none}

@media(max-width:720px){
  body.v17-ready .protocol-toolbar,
  body.v17-ready .protocols,
  body.v17-ready .protocol-panel,
  body.v17-ready .multi-link-card,
  body.v17-ready .smart-card,
  body.v17-ready .v17-hidden{display:none!important}
  body.v17-ready .v9-mobile-stack{display:none!important}

  .v17-mobile-stack{display:flex;flex-direction:column;gap:7px;margin-top:8px}
  .v17-protocol-card,.v17-ha-card{overflow:hidden;border:1px solid var(--line);border-radius:14px;background:var(--surface);box-shadow:0 7px 22px rgba(0,0,0,.07)}
  .v17-protocol-card[open],.v17-ha-card[open]{border-color:color-mix(in srgb,var(--pc,var(--p)) 42%,var(--line))}
  .v17-summary{min-height:50px;padding:7px 9px;display:grid;grid-template-columns:34px minmax(0,1fr) auto 16px;align-items:center;gap:7px;list-style:none;cursor:pointer;-webkit-tap-highlight-color:transparent}
  .v17-summary::-webkit-details-marker{display:none}
  .v17-mark{width:34px;height:34px;display:grid;place-items:center;border-radius:10px;background:linear-gradient(135deg,var(--pc,var(--p)),var(--s));color:#fff;font-size:9px;font-weight:950}
  .v17-title{min-width:0}
  .v17-title b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10.5px;line-height:1.4}
  .v17-title small{display:block;margin-top:1px;color:var(--muted);font-size:7px}
  .v17-count{min-width:50px;height:24px;padding:0 7px;display:inline-flex;align-items:center;justify-content:center;border:1px solid color-mix(in srgb,var(--pc,var(--p)) 30%,var(--line));border-radius:999px;background:color-mix(in srgb,var(--pc,var(--p)) 7%,var(--surface));color:var(--pc,var(--p));font-size:7px;font-weight:900;white-space:nowrap}
  .v17-chevron{color:var(--muted);font-size:14px;transition:transform .18s ease}
  .v17-protocol-card[open] .v17-chevron,.v17-ha-card[open] .v17-chevron{transform:rotate(180deg)}
  .v17-body{padding:7px;border-top:1px solid var(--line)}
  .v17-device-app{min-height:32px;margin:0 0 7px;padding:5px 8px;display:flex;align-items:center;justify-content:space-between;gap:7px;border:1px solid color-mix(in srgb,var(--p) 24%,var(--line));border-radius:10px;background:color-mix(in srgb,var(--p) 6%,var(--surface2))}
  .v17-device-app span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted);font-size:7px}
  .v17-device-app a{flex:0 0 auto;color:var(--p);font-size:7px;font-weight:900}
  .v17-server-list{display:flex;flex-direction:column;gap:5px}
  .v17-server-row{min-height:48px;padding:6px 7px;display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:7px;border:1px solid var(--line);border-radius:11px;background:var(--surface2)}
  .v17-server-copy{min-width:0}
  .v17-server-copy b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:9px}
  .v17-server-copy small{display:block;margin-top:2px;color:var(--muted);font-size:6.5px}
  .v17-server-actions{display:flex;align-items:center;justify-content:flex-end;gap:4px;min-width:0}
  .v17-action{min-height:30px;max-width:132px;padding:0 8px;display:inline-flex;align-items:center;justify-content:center;overflow:hidden;text-overflow:ellipsis;border:1px solid color-mix(in srgb,var(--p) 28%,var(--line));border-radius:8px;background:var(--surface);color:var(--text);font-size:7px;font-weight:900;text-decoration:none;white-space:nowrap}
  .v17-action.primary{border-color:color-mix(in srgb,var(--p) 42%,var(--line));background:color-mix(in srgb,var(--p) 10%,var(--surface));color:var(--p)}
  .v17-config-first .v17-advanced-action{width:30px;min-width:30px;padding:0;font-size:0}
  .v17-config-first .v17-advanced-action::before{content:"•••";font-size:9px;letter-spacing:1px}
  .v17-credential-first .v17-advanced-action{border-color:color-mix(in srgb,var(--pc,var(--p)) 44%,var(--line));color:var(--pc,var(--p));background:color-mix(in srgb,var(--pc,var(--p)) 8%,var(--surface))}
  .v17-details{display:none;grid-column:1/-1;padding:7px 8px;border-radius:9px;background:var(--surface);color:var(--muted);font-size:6.5px;line-height:1.8;direction:ltr;text-align:left;white-space:pre-wrap;overflow-wrap:anywhere}
  .v17-server-row.show-details .v17-details{display:block}
  .v17-pending{padding:9px;color:var(--muted);font-size:7px;text-align:center}
}

@media(max-width:430px){
  .v17-summary{grid-template-columns:32px minmax(0,1fr) auto 14px;padding:6px 7px}
  .v17-mark{width:32px;height:32px}
  .v17-server-row{grid-template-columns:minmax(0,1fr);gap:5px}
  .v17-server-actions{justify-content:flex-start;flex-wrap:wrap}
  .v17-action{max-width:calc(50vw - 34px)}
}
"""


_MOBILE_PROTOCOLS_V17_SCRIPT = r"""
<script id="twinpanelPublicConnectMobileProtocolsV17">
(function(){
  function start(){
    if(!window.matchMedia('(max-width:720px)').matches)return;

    const body=document.body;
    const platform=String(body.dataset.tpPlatform||'unknown').toLowerCase();
    const platformNames={android:'Android',ios:'iPhone / iPad',windows:'Windows',macos:'macOS',linux:'Linux',unknown:'دستگاه شما'};
    const credentialFirst=new Set(['cisco','l2tp']);
    const meta={
      cisco:['C','Cisco / OpenConnect','#17b6d8'],openvpn:['O','OpenVPN','#f59e0b'],wireguard:['W','WireGuard','#ef476f'],l2tp:['L2','L2TP / IPsec','#65c93a'],v2ray:['V','V2Ray / Xray','#8b5cf6'],xray:['V','V2Ray / Xray','#8b5cf6'],hysteria2:['H2','Hysteria2','#8b5cf6'],tuic:['T','TUIC','#7c3aed'],anytls:['A','AnyTLS','#6d28d9'],naive:['N','NaiveProxy','#5b21b6'],shadowtls:['ST','ShadowTLS','#9333ea'],snell:['S','Snell','#a855f7'],mieru:['M','Mieru','#8b5cf6'],trusttunnel:['TT','TrustTunnel','#7c3aed'],amneziawg:['AW','AmneziaWG','#6d28d9'],sudoku:['SU','Sudoku','#9333ea']
    };

    function normalize(value){const key=String(value||'').trim().toLowerCase();if(key==='naiveproxy')return'naive';if(key==='openconnect'||key==='ocserv'||key==='anyconnect')return'cisco';return key}
    function text(el){return String(el?.textContent||'').trim()}
    function choiceFor(panel){return [...document.querySelectorAll('.protocol-choice')].find(choice=>choice.dataset.protocol===panel.id)||null}
    function protocolFor(panel){const choice=choiceFor(panel);return normalize(choice?.dataset.protocolKey||panel.dataset.modernProtocol||'')}
    function titleFor(panel,key){return meta[key]?.[1]||text(panel.querySelector('.panel-head h3'))||key||'VPN'}
    function appFor(panel){if(platform==='unknown')return null;return panel.querySelector('.v13-app[data-v13-platform="'+platform+'"]')}
    function makeAction(source,label,primary){
      if(!source)return null;let out;
      if(source.tagName==='A'){out=document.createElement('a');out.href=source.getAttribute('href')||'#';if(source.target)out.target=source.target;if(source.rel)out.rel=source.rel;if(source.hasAttribute('download'))out.setAttribute('download',source.getAttribute('download')||'')}
      else{out=document.createElement('button');out.type='button';out.addEventListener('click',()=>source.click())}
      out.className='v17-action'+(primary?' primary':'');out.textContent=label;return out
    }
    function primaryLabel(source,key){if(source?.classList.contains('v13-karing-import'))return'افزودن به Karing';const href=String(source?.getAttribute?.('href')||'');if(/^(vmess|vless|trojan|ss|hysteria2|hy2|tuic|karing):/i.test(href))return'باز کردن در برنامه';if(key==='openvpn')return'OpenVPN';if(key==='wireguard')return'WireGuard';return credentialFirst.has(key)?'اتصال':'باز کردن'}
    function factText(view){return [...view.querySelectorAll('.fact')].map(fact=>{const label=text(fact.querySelector('small'));const value=text(fact.querySelector('strong'));return label&&value?label+': '+value:''}).filter(Boolean).join('\n')}
    function addAdvanced(row,actions,details,key){
      if(!details)return;const button=document.createElement('button');button.type='button';button.className='v17-action v17-advanced-action'+(credentialFirst.has(key)?' primary':'');button.textContent='جزئیات';const detail=document.createElement('div');detail.className='v17-details';detail.textContent=details;button.addEventListener('click',()=>row.classList.toggle('show-details'));actions.appendChild(button);row.appendChild(detail)
    }
    function makeServerRow(view,name,key,index){
      const row=document.createElement('div');row.className='v17-server-row';row.dataset.protocolKey=key;
      const copy=document.createElement('div');copy.className='v17-server-copy';copy.innerHTML='<b></b><small></small>';copy.querySelector('b').textContent=name;copy.querySelector('small').textContent='سرور '+(index+1);row.appendChild(copy);
      const actions=document.createElement('div');actions.className='v17-server-actions';const modern=view.querySelector('.v13-modern-action');const primary=modern?.querySelector('.primary-btn')||view.querySelector('a.primary-btn[href]')||view.querySelector('button.primary-btn');const secondary=modern?.querySelector('.v13-secondary');const download=view.querySelector('.download-config');const details=factText(view);
      if(credentialFirst.has(key))addAdvanced(row,actions,details,key);
      if(primary){const action=makeAction(primary,primaryLabel(primary,key),true);if(action)actions.appendChild(action)}else if(download){const action=makeAction(download,'دانلود کانفیگ',true);if(action)actions.appendChild(action)}
      if(!credentialFirst.has(key)){if(secondary){const action=makeAction(secondary,'دانلود',false);if(action)actions.appendChild(action)}else if(download&&primary){const action=makeAction(download,'دانلود',false);if(action)actions.appendChild(action)}addAdvanced(row,actions,details,key)}
      if(!actions.childElementCount){const button=document.createElement('button');button.type='button';button.className='v17-action primary';button.textContent='مشاهده';button.addEventListener('click',()=>{const choice=choiceFor(view.closest('.protocol-panel'));if(choice)choice.click()});actions.appendChild(button)}
      row.appendChild(actions);return row
    }
    function makeProtocolCard(panel){
      const key=protocolFor(panel);if(!key)return null;const info=meta[key]||['•',titleFor(panel,key),'#8b5cf6'];const views=[...panel.querySelectorAll('.server-view')];const tabs=[...panel.querySelectorAll('.server-tab')];const card=document.createElement('details');card.className='v17-protocol-card '+(credentialFirst.has(key)?'v17-credential-first':'v17-config-first');card.dataset.protocolKey=key;card.style.setProperty('--pc',info[2]);
      const summary=document.createElement('summary');summary.className='v17-summary';summary.innerHTML='<span class="v17-mark"></span><span class="v17-title"><b></b><small></small></span><span class="v17-count"></span><span class="v17-chevron">⌄</span>';summary.querySelector('.v17-mark').textContent=info[0];summary.querySelector('.v17-title b').textContent=info[1];summary.querySelector('.v17-title small').textContent=views.length?'آماده اتصال':'در حال آماده‌سازی';summary.querySelector('.v17-count').textContent=views.length?views.length+' سرور':'در انتظار';
      const bodyBox=document.createElement('div');bodyBox.className='v17-body';const app=appFor(panel);if(app){const appRow=document.createElement('div');appRow.className='v17-device-app';const label=(text(app)||'دانلود برنامه').replace(/^دانلود\s*/,'');const note=document.createElement('span');note.textContent='برنامه مناسب '+(platformNames[platform]||platformNames.unknown);const link=document.createElement('a');link.href=app.getAttribute('href')||'#';link.target='_blank';link.rel='noopener noreferrer';link.textContent=label;appRow.append(note,link);bodyBox.appendChild(appRow)}
      if(views.length){const list=document.createElement('div');list.className='v17-server-list';views.forEach((view,serverIndex)=>{const name=text(tabs[serverIndex])||('Server '+(serverIndex+1));list.appendChild(makeServerRow(view,name,key,serverIndex))});bodyBox.appendChild(list)}else{const pending=document.createElement('div');pending.className='v17-pending';pending.textContent='این پروتکل برای اشتراک فعال است و هنوز کانفیگ قابل تحویل ندارد.';bodyBox.appendChild(pending)}
      card.append(summary,bodyBox);return card
    }
    function makeHighAvailability(){
      const source=document.querySelector('.multi-link-card');if(!source)return null;const copySource=source.querySelector('[data-v7-copy-url]');const shareSource=source.querySelector('[data-v7-share-url]');if(!copySource&&!shareSource)return null;const card=document.createElement('details');card.className='v17-ha-card';card.style.setProperty('--pc','#38bdf8');const summary=document.createElement('summary');summary.className='v17-summary';summary.innerHTML='<span class="v17-mark">HA</span><span class="v17-title"><b>High Availability Config</b><small>Multi Server</small></span><span class="v17-count">V2Ray</span><span class="v17-chevron">⌄</span>';const bodyBox=document.createElement('div');bodyBox.className='v17-body';const row=document.createElement('div');row.className='v17-server-row';const copy=document.createElement('div');copy.className='v17-server-copy';copy.innerHTML='<b>Multi Server</b><small>یک لینک برای سرورهای V2Ray / Xray</small>';const actions=document.createElement('div');actions.className='v17-server-actions';if(copySource){const action=makeAction(copySource,'کپی لینک',false);if(action)actions.appendChild(action)}if(shareSource&&(platform==='android'||platform==='ios')){const action=makeAction(shareSource,'ارسال به برنامه',true);if(action)actions.appendChild(action)}row.append(copy,actions);bodyBox.appendChild(row);card.append(summary,bodyBox);return card
    }
    function bindAccordion(mount){const cards=[...mount.querySelectorAll('details')];cards.forEach(card=>{card.addEventListener('toggle',()=>{if(!card.open)return;cards.forEach(other=>{if(other!==card)other.open=false})})});if(cards.length===1)cards[0].open=true}

    const oldMount=document.querySelector('.v9-mobile-stack');const mount=document.createElement('div');mount.className='v17-mobile-stack';const anchor=oldMount||document.querySelector('.protocol-toolbar')||document.querySelector('.protocols');if(anchor&&anchor.parentNode)anchor.parentNode.insertBefore(mount,anchor);else document.querySelector('.page')?.appendChild(mount);
    const ha=makeHighAvailability();if(ha)mount.appendChild(ha);
    const seen=new Set();document.querySelectorAll('.protocol-panel').forEach(panel=>{const key=protocolFor(panel);if(!key||seen.has(key))return;seen.add(key);const card=makeProtocolCard(panel);if(card)mount.appendChild(card)});document.querySelectorAll('.v13-pending-panel[data-modern-protocol]').forEach(panel=>{const key=protocolFor(panel);if(!key||seen.has(key))return;seen.add(key);const card=makeProtocolCard(panel);if(card)mount.appendChild(card)});
    bindAccordion(mount);
    const smart=document.querySelector('.smart-card');if(smart){smart.classList.add('v17-hidden');const prev=smart.previousElementSibling;if(prev?.classList.contains('section-head'))prev.classList.add('v17-hidden')}
    const quick=[...document.querySelectorAll('.section-head')].find(el=>text(el.querySelector('h2')).includes('اتصال سریع'));if(quick?.querySelector('h2'))quick.querySelector('h2').textContent='سرورهای اتصال';
    body.classList.add('v17-ready');body.dataset.tpMobileAdaptive='v294';
  }
  window.setTimeout(start,0);
})();
</script>
"""


def refine_public_connection_mobile_protocols_v17(source: str) -> str:
    """Render a compact, protocol-aware mobile stack without changing desktop."""
    if "TWINPANEL_PUBLIC_CONNECT_MOBILE_PROTOCOLS_V17" in source:
        return source
    source = source.replace("</style>", _MOBILE_PROTOCOLS_V17_CSS + "\n</style>", 1)
    source = source.replace("</body>", _MOBILE_PROTOCOLS_V17_SCRIPT + "\n</body>", 1)
    return source
