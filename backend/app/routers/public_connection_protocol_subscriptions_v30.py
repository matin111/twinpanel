from __future__ import annotations

import base64
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from .account_delivery import _public_payload, _subscription_from_share_token
from .public_connection_modern_delivery_v13 import _items
from .public_connection_modern_import_v15 import standard_share_uri
from .public_connection_modern_names_v14 import _profile_name


router = APIRouter(tags=["public-connection-protocol-subscriptions-v30"])

_MARKER = "TWINPANEL_PUBLIC_PROTOCOL_SUBSCRIPTIONS_V30"

SUPPORTED_PROTOCOLS = ("v2ray", "hysteria2", "tuic", "anytls")
PROTOCOL_TITLES = {
    "v2ray": "V2Ray / Xray",
    "hysteria2": "Hysteria2",
    "tuic": "TUIC",
    "anytls": "AnyTLS",
}
_EXPECTED_SCHEMES = {
    "hysteria2": ("hysteria2://", "hy2://"),
    "tuic": ("tuic://",),
    "anytls": ("anytls://",),
}


def _normalize_protocol(value: Any) -> str:
    protocol = str(value or "").strip().lower()
    if protocol == "xray":
        return "v2ray"
    return protocol


def _active_subscription_payload(token: str, db: Session) -> tuple[Any, dict[str, Any]]:
    sub = _subscription_from_share_token(token, db)
    status = str(getattr(sub.status, "value", sub.status) or "").strip().lower()
    if status != "active":
        raise HTTPException(status_code=403, detail="اشتراک فعال نیست")
    payload = _public_payload(db, sub)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=404, detail="اطلاعات اتصال آماده نیست")
    return sub, payload


def _stored_uri(protocol: str, item: dict[str, Any]) -> str:
    uri = str(item.get("uri") or "").strip()
    if not uri:
        return ""
    if protocol == "v2ray":
        # Preserve V7 parity: Xray/V2Ray credentials already expose canonical
        # VLESS/VMess/Trojan/Shadowsocks share URIs through Account Delivery.
        return uri if "://" in uri else ""
    schemes = _EXPECTED_SCHEMES.get(protocol) or ()
    return uri if uri.lower().startswith(schemes) else ""


def _item_share_uri(sub: Any, protocol: str, item: dict[str, Any]) -> str:
    protocol = _normalize_protocol(protocol)
    if protocol == "v2ray":
        return _stored_uri(protocol, item)

    # V15 is already the canonical lossless share-link builder for these
    # protocols. Prefer it so subscription and single-server delivery stay in
    # exact semantic parity. Fall back only to an already stored matching URI.
    profile_name = _profile_name(sub, protocol, item)
    generated = str(standard_share_uri(protocol, item, profile_name) or "").strip()
    if generated:
        return generated
    return _stored_uri(protocol, item)


def _protocol_uris_from_payload(
    sub: Any,
    payload: dict[str, Any],
    protocol: str,
) -> list[str]:
    protocol = _normalize_protocol(protocol)
    if protocol not in SUPPORTED_PROTOCOLS:
        return []

    result: list[str] = []
    seen: set[str] = set()
    credentials = payload.get("credentials") or []
    if not isinstance(credentials, list):
        return result

    for credential in credentials:
        if not isinstance(credential, dict):
            continue
        credential_protocol = _normalize_protocol(credential.get("protocol"))
        if credential_protocol != protocol:
            continue
        for item in _items(credential):
            uri = _item_share_uri(sub, protocol, item)
            if not uri or uri in seen:
                continue
            seen.add(uri)
            result.append(uri)
    return result


def _encode_subscription(uris: list[str]) -> str:
    raw = "\n".join(str(uri).strip() for uri in uris if str(uri).strip()).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _protocol_subscription_content(token: str, protocol: str, db: Session) -> tuple[str, str, int]:
    protocol = _normalize_protocol(protocol)
    if protocol not in SUPPORTED_PROTOCOLS:
        raise HTTPException(status_code=404, detail="برای این پروتکل لینک اشتراک مشترک ارائه نمی‌شود")

    sub, payload = _active_subscription_payload(token, db)
    uris = _protocol_uris_from_payload(sub, payload, protocol)
    if not uris:
        raise HTTPException(status_code=404, detail="لینک اشتراک این پروتکل هنوز آماده نیست")
    return _encode_subscription(uris), protocol, len(uris)


@router.get(
    "/{token}/sub/{protocol}",
    name="public_protocol_subscription_v30",
)
def public_protocol_subscription_v30(
    token: str,
    protocol: str,
    db: Session = Depends(get_db),
):
    """Return one standard Base64 subscription feed for all real nodes of a protocol."""
    content, normalized, count = _protocol_subscription_content(token, protocol, db)
    title = PROTOCOL_TITLES[normalized]
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "Profile-Title": f"TwinPanel-{normalized}",
            "Profile-Update-Interval": "12",
            "X-TwinPanel-Protocol": normalized,
            "X-TwinPanel-Node-Count": str(count),
            "Content-Disposition": f'inline; filename="twinpanel-{normalized}-subscription.txt"',
        },
    )


_CSS = r"""
/* TWINPANEL_PUBLIC_PROTOCOL_SUBSCRIPTIONS_V30 */
body.v30-ready .v30-subscription-card{
  margin:12px;
  padding:14px;
  border:1px solid color-mix(in srgb,var(--p) 32%,var(--line));
  border-radius:14px;
  background:linear-gradient(145deg,color-mix(in srgb,var(--p) 7%,var(--surface2)),var(--surface2));
}
body.v30-ready .v30-subscription-head{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  margin-bottom:10px;
}
body.v30-ready .v30-subscription-head b{
  font-size:14px;
  line-height:1.5;
}
body.v30-ready .v30-subscription-count{
  color:var(--muted);
  font-size:11px;
  font-weight:800;
  white-space:nowrap;
}
body.v30-ready .v30-subscription-actions{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:8px;
}
body.v30-ready .v30-subscription-actions>a,
body.v30-ready .v30-subscription-actions>button,
body.v30-ready .v30-client-downloads>a{
  min-height:42px;
  padding:9px 11px;
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
  line-height:1.35;
  text-align:center;
  text-decoration:none;
  cursor:pointer;
}
body.v30-ready .v30-subscription-actions .v30-primary{
  border-color:var(--p);
  background:var(--p);
  color:#fff;
}
body.v30-ready .v30-client-downloads{
  margin-top:8px;
  display:flex;
  flex-wrap:wrap;
  gap:7px;
}
body.v30-ready .v30-client-downloads>a{
  min-height:36px;
  padding:7px 10px;
  color:var(--muted);
  font-size:11px;
}
body.v30-ready .v30-single-servers{
  margin:0 12px 12px;
  border:1px solid var(--line);
  border-radius:12px;
  overflow:hidden;
  background:var(--surface2);
}
body.v30-ready .v30-single-servers>summary{
  min-height:44px;
  padding:0 12px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  color:var(--text);
  font-size:12px;
  font-weight:900;
  cursor:pointer;
  list-style:none;
}
body.v30-ready .v30-single-servers>summary::-webkit-details-marker{display:none}
body.v30-ready .v30-single-servers>summary:after{
  content:'⌄';
  color:var(--muted);
  font-size:16px;
}
body.v30-ready .v30-single-servers[open]>summary:after{content:'⌃'}
body.v30-ready .v30-single-servers>.server-views{
  border-top:1px solid var(--line);
}
body.v30-ready .protocol-panel[data-v30-subscription="1"] .server-view .v13-app{
  display:none!important;
}

@media(max-width:720px){
  body.v30-ready .v30-subscription-card{
    margin:10px;
    padding:12px;
  }
  body.v30-ready .v30-subscription-actions{
    grid-template-columns:1fr;
  }
  body.v30-ready .v30-client-downloads{
    display:grid;
    grid-template-columns:repeat(2,minmax(0,1fr));
  }
  body.v30-ready .v30-client-downloads>a{
    width:100%;
  }
  body.v30-ready .v30-client-v2rayn{
    display:none!important;
  }
  body.v30-ready .v30-single-servers .server-views{
    padding:10px!important;
  }
}

@media(max-width:390px){
  body.v30-ready .v30-client-downloads{
    grid-template-columns:1fr;
  }
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicProtocolSubscriptionsV30">
(function(){
  const token=__TOKEN__;
  const MOBILE='(max-width:720px)';
  const SUPPORTED=new Set(['v2ray','hysteria2','tuic','anytls']);
  const TITLES={v2ray:'V2Ray / Xray',hysteria2:'Hysteria2',tuic:'TUIC',anytls:'AnyTLS'};
  const KARING='https://karing.app/en/quickstart';
  const HIDDIFY='https://github.com/hiddify/hiddify-app/releases/latest';
  const V2RAYN='https://github.com/2dust/v2rayN/releases/latest';

  const text=el=>String(el?.textContent||'').trim();
  const normalize=value=>{
    const p=String(value||'').trim().toLowerCase();
    return p==='xray'?'v2ray':p;
  };

  function panelProtocol(panel){
    const modern=normalize(panel?.dataset?.modernProtocol||'');
    if(modern)return modern;
    const choice=[...document.querySelectorAll('.protocol-choice')]
      .find(item=>String(item.dataset.protocol||'')===String(panel?.id||''));
    return normalize(choice?.dataset?.protocolKey||choice?.dataset?.protocol||'');
  }

  function subscriptionUrl(protocol){
    return window.location.origin+'/v1/connect/'+encodeURIComponent(token)+'/sub/'+encodeURIComponent(protocol);
  }

  function notify(message){
    const toast=document.getElementById('toast');
    if(!toast)return;
    toast.textContent=message;
    toast.classList.add('show');
    clearTimeout(window.__tpV30Toast);
    window.__tpV30Toast=setTimeout(()=>toast.classList.remove('show'),1800);
  }

  function fallbackCopy(value){
    const area=document.createElement('textarea');
    area.value=String(value||'');
    area.setAttribute('readonly','');
    area.style.position='fixed';
    area.style.left='-9999px';
    document.body.appendChild(area);
    area.focus();area.select();area.setSelectionRange(0,area.value.length);
    let ok=false;
    try{ok=document.execCommand('copy')}catch(_error){}
    area.remove();
    return ok;
  }

  async function copy(value){
    if(navigator.clipboard&&window.isSecureContext){
      try{await navigator.clipboard.writeText(value);return true}catch(_error){}
    }
    return fallbackCopy(value);
  }

  function normalizeExistingLabels(){
    document.querySelectorAll('.protocol-panel .v13-app').forEach(link=>{
      const value=text(link).replace(/^دانلود\s+/,'').trim();
      if(value)link.textContent='دانلود '+value;
    });
    document.querySelectorAll('.protocol-panel .v15-standard-link').forEach(button=>button.textContent='کپی لینک');
    document.querySelectorAll('.protocol-panel .tp-v15-copy-config,.protocol-panel .tp-v15-classic-copy')
      .forEach(button=>button.textContent='کپی کانفیگ');
    document.querySelectorAll('.protocol-panel .download-config,.protocol-panel .tp-v16-safe-download,.protocol-panel .v13-secondary')
      .forEach(link=>link.textContent='دانلود کانفیگ');
    document.querySelectorAll('.protocol-panel .v13-karing-inline,.protocol-panel .v13-karing-import')
      .forEach(link=>link.textContent='اتصال به Karing');
  }

  function buildSubscriptionCard(panel,protocol){
    if(panel.querySelector('.v30-subscription-card'))return;
    const count=panel.querySelectorAll('.server-view').length;
    const url=subscriptionUrl(protocol);
    const title=TITLES[protocol]||protocol;
    const karing='karing://install-config?url='+encodeURIComponent(url)+'&name='+encodeURIComponent('TwinPanel '+title);

    const card=document.createElement('section');
    card.className='v30-subscription-card';
    card.dataset.v30Protocol=protocol;
    card.innerHTML='\
      <div class="v30-subscription-head">\
        <b>همه سرورها</b>\
        <span class="v30-subscription-count">'+count+' سرور</span>\
      </div>\
      <div class="v30-subscription-actions">\
        <a class="v30-primary v30-karing-all" href="'+karing+'">افزودن همه به Karing</a>\
        <button type="button" class="v30-copy-sub">کپی لینک اشتراک</button>\
      </div>\
      <div class="v30-client-downloads">\
        <a href="'+KARING+'" target="_blank" rel="noopener noreferrer">دانلود Karing</a>\
        <a href="'+HIDDIFY+'" target="_blank" rel="noopener noreferrer">دانلود Hiddify</a>\
        <a class="v30-client-v2rayn" href="'+V2RAYN+'" target="_blank" rel="noopener noreferrer">دانلود v2rayN</a>\
      </div>';
    card.querySelector('.v30-copy-sub')?.addEventListener('click',async()=>{
      notify(await copy(url)?'لینک اشتراک کپی شد ✓':'کپی انجام نشد');
    });
    const head=panel.querySelector('.panel-head');
    if(head)head.insertAdjacentElement('afterend',card);
    else panel.insertAdjacentElement('afterbegin',card);
    panel.dataset.v30Subscription='1';
  }

  function collapseMobileServers(panel){
    if(!window.matchMedia(MOBILE).matches)return;
    if(panel.querySelector('.v30-single-servers'))return;
    const views=panel.querySelector('.server-views');
    if(!views)return;
    const details=document.createElement('details');
    details.className='v30-single-servers';
    const summary=document.createElement('summary');
    summary.textContent='سرورهای تکی';
    details.appendChild(summary);
    views.insertAdjacentElement('beforebegin',details);
    details.appendChild(views);
  }

  function apply(){
    document.body.classList.add('v30-ready');
    document.body.dataset.tpProtocolSubscriptions='v30';
    normalizeExistingLabels();
    document.querySelectorAll('.protocol-panel.v24-canonical-panel').forEach(panel=>{
      const protocol=panelProtocol(panel);
      if(!SUPPORTED.has(protocol))return;
      buildSubscriptionCard(panel,protocol);
      collapseMobileServers(panel);
    });
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,180);
  window.addEventListener('resize',()=>window.setTimeout(apply,60),{passive:true});
})();
</script>
"""


def refine_public_connection_protocol_subscriptions_v30(source: str, token: str) -> str:
    """Add beginner-friendly per-protocol subscriptions without changing credentials."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    script = _SCRIPT.replace("__TOKEN__", json.dumps(str(token), ensure_ascii=True))
    return source.replace("</body>", script + f"\n<!-- {_MARKER} -->\n</body>", 1)
