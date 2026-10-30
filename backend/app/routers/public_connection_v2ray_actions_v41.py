from __future__ import annotations

from . import public_connection_all_multilink_v34 as multilink
from . import public_connection_modern_delivery_v13 as modern_delivery
from .public_connection_mobile_sheet_v42 import refine_public_connection_mobile_sheet_v42
from .public_connection_v2ray_multilink_v43 import apply_v2ray_multilink_v43


apply_v2ray_multilink_v43()
# Keep backend compatibility metadata unchanged. The final customer-facing
# client card below is rewritten per device to the V2Ray/Xray client family.
modern_delivery.CLIENTS["v2ray"] = modern_delivery._KARING
multilink.PROTOCOL_CLIENT["v2ray"] = "karing"

_MARKER = "TWINPANEL_PUBLIC_CONNECT_V2RAY_ACTIONS_V41"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_V2RAY_ACTIONS_V41 */
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .v34-client-card{
  display:flex!important;
  visibility:visible!important;
  opacity:1!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .tp-v48-xray-profiles{
  display:grid!important;
  gap:9px!important;
  width:100%!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .tp-v48-xray-profiles[data-v41-collapsed="1"]{
  display:none!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .tp-v41-profile-toggle{
  width:100%!important;
  min-height:40px!important;
  margin:8px 0 0!important;
  padding:0 12px!important;
  border:1px solid var(--line)!important;
  border-radius:12px!important;
  background:var(--surface2)!important;
  color:var(--text)!important;
  font:inherit!important;
  font-size:12px!important;
  font-weight:850!important;
  cursor:pointer!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .tp-v48-xray-profile{
  display:grid!important;
  gap:8px!important;
  width:100%!important;
  padding:10px!important;
  border:1px solid var(--line)!important;
  border-radius:12px!important;
  background:var(--surface2)!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .tp-v48-profile-actions{
  display:grid!important;
  grid-template-columns:repeat(2,minmax(0,1fr))!important;
  gap:7px!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .tp-v48-profile-actions>a,
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .tp-v48-profile-actions>button{
  width:100%!important;
  min-height:40px!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .tp-v48-profile-actions .tp-v48-karing{
  border-color:var(--p)!important;
  background:var(--p)!important;
  color:#fff!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .tp-v48-profile-actions .copy-btn{
  color:var(--p)!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .v34-server-actions[data-v41-duplicate="1"],
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] [data-v41-retired-actions="1"]{
  display:none!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .v34-server-actions:not([data-v41-duplicate="1"]){
  display:grid!important;
  grid-template-columns:repeat(2,minmax(0,1fr))!important;
  gap:7px!important;
  margin-top:8px!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .v34-server-actions:not([data-v41-duplicate="1"])>a,
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .v34-server-actions:not([data-v41-duplicate="1"])>button{
  width:100%!important;
  min-height:40px!important;
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectV2rayActionsV41">
(function(){
  let timer=null;

  const CLIENTS={
    windows:{name:'v2rayN',url:'https://github.com/2dust/v2rayN/releases/latest'},
    macos:{name:'v2rayN',url:'https://github.com/2dust/v2rayN/releases/latest'},
    linux:{name:'v2rayN',url:'https://github.com/2dust/v2rayN/releases/latest'},
    android:{name:'v2rayNG',url:'https://github.com/2dust/v2rayNG/releases/latest'},
    ios:{name:'V2Box',url:'https://apps.apple.com/us/app/v2box-v2ray-client/id6446814690'},
    unknown:{name:'v2rayN / v2rayNG / V2Box',url:'https://github.com/2dust/v2rayN/releases/latest'}
  };

  function normalize(value){
    const key=String(value||'').trim().toLowerCase();
    if(key==='xray')return'v2ray';
    return key;
  }

  function panelKey(panel){
    const direct=normalize(panel?.dataset?.v34Protocol||panel?.dataset?.modernProtocol||'');
    if(direct)return direct;
    const choice=[...document.querySelectorAll('.protocol-choice')]
      .find(item=>String(item.dataset.protocol||'')===String(panel?.id||''));
    return normalize(choice?.dataset?.protocolKey||choice?.dataset?.protocol||panel?.id||'');
  }

  function platform(){
    const explicit=String(document.body?.dataset?.tpPlatform||document.documentElement?.dataset?.tpPlatform||'').trim().toLowerCase();
    if(CLIENTS[explicit])return explicit;
    const ua=String(navigator.userAgent||'');
    const navPlatform=String(navigator.platform||'');
    const haystack=(ua+' '+navPlatform).toLowerCase();
    if(/android/i.test(ua))return'android';
    if(/iphone|ipad|ipod/i.test(ua))return'ios';
    if(/macintosh|mac os|macintel/i.test(haystack)&&Number(navigator.maxTouchPoints||0)>1)return'ios';
    if(/windows|win32|win64|winarm/i.test(haystack))return'windows';
    if(/macintosh|mac os|macintel/i.test(haystack))return'macos';
    if(/linux|x11|cros/i.test(haystack))return'linux';
    return'unknown';
  }

  function canonicalRow(view){
    return view.querySelector(':scope > .v34-server-actions');
  }

  function profileRows(view){
    return [...view.querySelectorAll(':scope > .tp-v48-xray-profiles > .tp-v48-xray-profile')];
  }

  function retireDirectLegacyActions(view,row,profiles){
    view.querySelectorAll(
      ':scope > .action-row,'+
      ':scope > .v13-modern-action,'+
      ':scope > .v13-client-only,'+
      ':scope > .v31-canonical-actions'
    ).forEach(node=>{
      if(node===row||profiles.includes(node))return;
      node.dataset.v41RetiredActions='1';
      node.setAttribute('aria-hidden','true');
    });
  }

  function simplifyProfile(profile){
    profile.removeAttribute('data-v40-retired-actions');
    profile.removeAttribute('aria-hidden');
    profile.removeAttribute('hidden');
    profile.style.removeProperty('display');

    const actions=profile.querySelector('.tp-v48-profile-actions');
    if(!actions)return;

    const primary=actions.querySelector('.tp-v48-karing');
    const copy=actions.querySelector('.copy-btn[data-copy]');

    [...actions.children].forEach(node=>{
      if(node!==primary&&node!==copy)node.remove();
    });

    if(primary){
      primary.textContent='ارسال به Karing';
      primary.setAttribute('aria-label','ارسال این اتصال به Karing');
    }
    if(copy){
      copy.textContent='کپی کانفیگ';
      copy.setAttribute('aria-label','کپی کانفیگ این اتصال');
    }

    actions.dataset.v41ProfileActions='1';
  }

  function simplifyCanonicalFallback(view,row){
    if(!row)return;

    row.removeAttribute('data-v41-duplicate');
    row.removeAttribute('aria-hidden');
    row.removeAttribute('hidden');
    row.style.removeProperty('display');

    const primary=row.querySelector('.v34-primary');
    const copy=row.querySelector('.v34-copy');

    [...row.children].forEach(node=>{
      if(node!==primary&&node!==copy)node.remove();
    });

    if(primary){
      const href=String(primary.getAttribute('href')||'');
      if(!href.startsWith('karing://')){
        const raw=String(primary.dataset?.copyTarget||primary.getAttribute('data-copy')||'').trim();
        if(raw){
          primary.setAttribute('href','karing://install-config?url='+encodeURIComponent(raw)+'&name='+encodeURIComponent('TwinPanel V2Ray'));
        }
      }
      primary.textContent='ارسال به Karing';
      primary.setAttribute('aria-label','ارسال کانفیگ به Karing');
    }
    if(copy){
      copy.textContent='کپی کانفیگ';
      copy.setAttribute('aria-label','کپی کانفیگ');
    }

    row.dataset.v41Canonical='1';
    retireDirectLegacyActions(view,row,[]);
  }

  function rewriteClientDownload(panel){
    const card=panel.querySelector('.v34-client-card');
    if(!card)return;
    const client=CLIENTS[platform()]||CLIENTS.unknown;
    card.hidden=false;
    card.removeAttribute('aria-hidden');
    card.style.removeProperty('display');
    card.dataset.v41ClientDownload='1';
    card.dataset.v41V2rayClient=client.name;

    const link=card.querySelector('a');
    if(link){
      link.href=client.url;
      link.target='_blank';
      link.rel='noopener noreferrer';
      link.textContent='دانلود '+client.name;
      link.setAttribute('aria-label','دانلود '+client.name+' برای V2Ray / Xray');
      link.dataset.client=client.name.toLowerCase();
    }
  }

  function ensureProfileAccordion(view,wrapper,profiles){
    let toggle=view.querySelector(':scope > .tp-v41-profile-toggle');
    if(!toggle){
      toggle=document.createElement('button');
      toggle.type='button';
      toggle.className='tp-v41-profile-toggle';
      wrapper.before(toggle);
    }

    if(!wrapper.dataset.v41AccordionReady){
      wrapper.dataset.v41AccordionReady='1';
      wrapper.dataset.v41Collapsed='1';
      wrapper.setAttribute('aria-hidden','true');
    }

    const sync=()=>{
      const collapsed=wrapper.dataset.v41Collapsed==='1';
      toggle.textContent=collapsed?'مشاهده کانفیگ‌ها ('+profiles.length+')':'بستن کانفیگ‌ها';
      toggle.setAttribute('aria-expanded',collapsed?'false':'true');
      wrapper.setAttribute('aria-hidden',collapsed?'true':'false');
    };

    if(toggle.dataset.v41Bound!=='1'){
      toggle.dataset.v41Bound='1';
      toggle.addEventListener('click',()=>{
        wrapper.dataset.v41Collapsed=wrapper.dataset.v41Collapsed==='1'?'0':'1';
        sync();
      });
    }
    sync();
  }

  function simplifyServer(view){
    const row=canonicalRow(view);
    const profiles=profileRows(view);

    if(profiles.length){
      const wrapper=view.querySelector(':scope > .tp-v48-xray-profiles');
      if(wrapper){
        wrapper.removeAttribute('data-v40-retired-actions');
        wrapper.removeAttribute('hidden');
        wrapper.style.removeProperty('display');
        wrapper.dataset.v41ProfileCount=String(profiles.length);
      }

      profiles.forEach(simplifyProfile);
      retireDirectLegacyActions(view,row,profiles);

      if(wrapper){
        ensureProfileAccordion(view,wrapper,profiles);
      }

      if(row){
        row.dataset.v41Duplicate='1';
        row.setAttribute('aria-hidden','true');
      }
      return;
    }

    simplifyCanonicalFallback(view,row);
  }

  function apply(){
    document.body.classList.add('v41-v2ray-two-actions');
    document.querySelectorAll('.protocol-panel').forEach(panel=>{
      if(panelKey(panel)!=='v2ray')return;
      panel.dataset.v41V2ray='1';
      rewriteClientDownload(panel);
      panel.querySelectorAll('.server-view').forEach(simplifyServer);
    });
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,250);
  window.setTimeout(apply,850);
  window.setTimeout(apply,1600);
  window.addEventListener('resize',()=>{
    clearTimeout(timer);
    timer=window.setTimeout(apply,220);
  },{passive:true});
  window.addEventListener('pagehide',()=>clearTimeout(timer),{once:true});
})();
</script>
"""


def refine_public_connection_v2ray_actions_v41(source: str) -> str:
    """Preserve real Xray profiles, collapse them by default, and show the right V2Ray client per device."""
    if _MARKER not in source:
        source = source.replace("</style>", _CSS + "\n</style>", 1)
        source = source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
    return refine_public_connection_mobile_sheet_v42(source)
