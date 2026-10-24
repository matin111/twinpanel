from __future__ import annotations

import base64
import html
import json
import re
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ProtocolCredential, SubscriptionProtocol
from .account_delivery import _public_payload, _subscription_from_share_token


router = APIRouter(tags=["public-connection-modern-delivery-v13"])

CLASSIC_PROTOCOLS = ("cisco", "openvpn", "wireguard", "l2tp", "v2ray")
MODERN_PROTOCOLS = (
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
    "snell",
    "mieru",
    "trusttunnel",
    "amneziawg",
    "sudoku",
)
CANONICAL_PROTOCOLS = CLASSIC_PROTOCOLS + MODERN_PROTOCOLS

PROTOCOL_META: dict[str, tuple[str, str, str]] = {
    "cisco": ("Cisco / OpenConnect", "C", "#17b6d8"),
    "openvpn": ("OpenVPN", "O", "#f59e0b"),
    "wireguard": ("WireGuard", "W", "#ef476f"),
    "l2tp": ("L2TP / IPsec", "L2", "#65c93a"),
    "v2ray": ("V2Ray / Xray", "V", "#8b5cf6"),
    "hysteria2": ("Hysteria2", "H2", "#8b5cf6"),
    "tuic": ("TUIC", "T", "#7c3aed"),
    "anytls": ("AnyTLS", "A", "#6d28d9"),
    "naive": ("NaiveProxy", "N", "#5b21b6"),
    "shadowtls": ("ShadowTLS", "ST", "#9333ea"),
    "snell": ("Snell", "S", "#a855f7"),
    "mieru": ("Mieru", "M", "#8b5cf6"),
    "trusttunnel": ("TrustTunnel", "TT", "#7c3aed"),
    "amneziawg": ("AmneziaWG", "AW", "#6d28d9"),
    "sudoku": ("Sudoku", "SU", "#9333ea"),
}

_PLATFORMS = ("windows", "android", "ios", "macos")
_KARING = {p: ("Karing", "https://karing.app/en/quickstart") for p in _PLATFORMS}
_HIDDIFY = {
    p: ("Hiddify", "https://hiddify.com/app/How-to-install-Hiddify-app/")
    for p in _PLATFORMS
}

# Stable official/project pages are intentionally preferred to version-pinned
# binary URLs so customer pages do not go stale when upstream clients release.
CLIENTS: dict[str, dict[str, tuple[str, str]]] = {
    "cisco": {
        "windows": ("OpenConnect / Cisco Client", "https://www.infradead.org/openconnect/"),
        "android": ("OpenConnect", "https://www.infradead.org/openconnect/"),
        "ios": ("Cisco Secure Client", "https://www.cisco.com/site/us/en/products/security/secure-client/index.html"),
        "macos": ("OpenConnect / Cisco Client", "https://www.infradead.org/openconnect/"),
    },
    "openvpn": {p: ("OpenVPN Connect", "https://openvpn.net/client/") for p in _PLATFORMS},
    "wireguard": {p: ("WireGuard", "https://www.wireguard.com/install/") for p in _PLATFORMS},
    "v2ray": _HIDDIFY,
    "hysteria2": _KARING,
    "tuic": _KARING,
    "anytls": _KARING,
    "naive": _KARING,
    "shadowtls": _KARING,
    "snell": {
        "windows": ("sing-box Desktop", "https://github.com/SagerNet/sing-box-for-desktop/releases/latest"),
        "android": ("sing-box", "https://github.com/SagerNet/sing-box/releases/latest"),
        "ios": ("sing-box", "https://github.com/SagerNet/sing-box-for-apple"),
        "macos": ("sing-box", "https://github.com/SagerNet/sing-box-for-apple"),
    },
    "mieru": _KARING,
    "trusttunnel": {
        "windows": ("TrustTunnel GUI", "https://github.com/blazuryk/TrustTunnel-GUI-Client/releases/latest"),
        "android": ("TrustTunnel", "https://github.com/TrustTunnel/TrustTunnel"),
        "ios": ("TrustTunnel", "https://github.com/TrustTunnel/TrustTunnel"),
        "macos": ("TrustTunnel", "https://github.com/TrustTunnel/TrustTunnel"),
    },
    "amneziawg": {
        "windows": ("AmneziaWG", "https://github.com/amnezia-vpn/amneziawg-windows-client/releases/latest"),
        "android": ("AmneziaWG", "https://play.google.com/store/apps/details?id=org.amnezia.awg"),
        "ios": ("AmneziaWG", "https://apps.apple.com/app/amneziawg/id6478942365"),
        "macos": ("AmneziaWG", "https://apps.apple.com/app/amneziawg/id6478942365"),
    },
    "sudoku": {
        "windows": ("Sudoku Desktop", "https://github.com/SUDOKU-ASCII/sudoku-desktop/releases/latest"),
        "android": ("Sudodroid", "https://github.com/SUDOKU-ASCII/sudoku-android/releases/latest"),
        "ios": ("Anywhere Proxy", "https://apps.apple.com/us/app/anywhere-proxy/id6758235178"),
        "macos": ("Sudoku Desktop", "https://github.com/SUDOKU-ASCII/sudoku-desktop/releases/latest"),
    },
}


def _h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _status_value(sub: Any) -> str:
    status = getattr(sub, "status", "")
    return str(getattr(status, "value", status) or "").strip().lower()


def _items(cred: dict[str, Any]) -> list[dict[str, Any]]:
    raw = cred.get("items") or []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _desired_protocols(db: Session, subscription_id: int) -> list[str]:
    selected = {
        str(row.protocol or "").strip().lower()
        for row in (
            db.query(SubscriptionProtocol)
            .filter(SubscriptionProtocol.subscription_id == int(subscription_id))
            .all()
        )
    }
    return [p for p in CANONICAL_PROTOCOLS if p in selected]


def _credential_state(db: Session, subscription_id: int, protocol: str, *, active: bool) -> str:
    if not active:
        return "اشتراک غیرفعال است"
    cred = (
        db.query(ProtocolCredential)
        .filter(
            ProtocolCredential.subscription_id == int(subscription_id),
            ProtocolCredential.protocol == protocol,
        )
        .order_by(ProtocolCredential.id.desc())
        .first()
    )
    if cred is None:
        return "در انتظار ساخت کانفیگ"
    if not bool(getattr(cred, "is_active", False)):
        return "پروتکل برای این اشتراک غیرفعال است"
    return "Credential ساخته شده؛ مسیر Runtime هنوز آماده تحویل نیست"


def _sudoku_uri(item: dict[str, Any]) -> str:
    try:
        cfg = json.loads(str(item.get("config") or ""))
    except Exception:
        return ""
    if not isinstance(cfg, dict):
        return ""
    host = str(cfg.get("server_address") or item.get("server") or item.get("server_ip") or "").strip()
    try:
        port = int(cfg.get("server_port") or item.get("port") or 0)
    except (TypeError, ValueError):
        port = 0
    key = str(cfg.get("key") or "").strip()
    if not host or port <= 0 or not key:
        return ""
    ascii_mode = str(cfg.get("ascii") or "").strip().lower()
    if ascii_mode == "prefer_ascii":
        ascii_mode = "ascii"
    elif ascii_mode == "prefer_entropy":
        ascii_mode = "entropy"
    payload: dict[str, Any] = {
        "n": "TwinPanel Sudoku",
        "h": host,
        "p": port,
        "k": key,
        "e": str(cfg.get("aead") or "chacha20-poly1305"),
        "m": int(cfg.get("local_port") or 1080),
    }
    if ascii_mode:
        payload["a"] = ascii_mode
    if cfg.get("enable_pure_downlink") is False:
        payload["x"] = True
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sudoku://" + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _client_links(protocol: str) -> str:
    if protocol == "l2tp":
        return '<span class="v13-native-client">برنامه جدا لازم نیست؛ از VPN داخلی سیستم استفاده کنید.</span>'
    rows = CLIENTS.get(protocol) or {}
    links: list[str] = []
    for platform in _PLATFORMS:
        if platform not in rows:
            continue
        name, url = rows[platform]
        links.append(
            f'<a class="v13-app" data-v13-platform="{platform}" href="{_h(url)}" '
            f'target="_blank" rel="noopener noreferrer">دانلود {_h(name)}</a>'
        )
    return "".join(links)


def _modern_action(token: str, protocol: str, item: dict[str, Any]) -> str:
    node_id = int(item.get("node_id") or 0)
    config_format = str(item.get("config_format") or "").strip().lower()
    uri = str(item.get("uri") or "").strip()
    if protocol == "sudoku" and not uri:
        uri = _sudoku_uri(item)
    config_path = (
        f"/v1/connect/{quote(str(token), safe='')}/modern-config/"
        f"{quote(protocol, safe='')}/{node_id}"
    )

    if uri:
        primary = f'<a class="primary-btn v13-open-uri" href="{_h(uri)}">باز کردن در برنامه</a>'
    elif config_format == "sing-box" and protocol != "snell":
        primary = (
            f'<button class="primary-btn v13-karing-import" type="button" '
            f'data-config-path="{_h(config_path)}">افزودن مستقیم به Karing</button>'
        )
    elif protocol == "mieru":
        primary = (
            f'<button class="primary-btn v13-karing-import" type="button" '
            f'data-config-path="{_h(config_path)}?profile=karing">افزودن مستقیم به Karing</button>'
        )
    else:
        primary = f'<a class="primary-btn" href="{_h(config_path)}">دانلود کانفیگ</a>'

    return (
        f'<div class="v13-modern-action" data-v13-protocol="{_h(protocol)}">'
        '<div class="v13-action-copy"><b>کانفیگ واقعی آماده است</b>'
        '<small>برنامه مناسب همین دستگاه نمایش داده می‌شود.</small></div>'
        f'<div class="v13-action-buttons">{primary}'
        f'<a class="v13-secondary" href="{_h(config_path)}">دانلود فایل</a>'
        f'{_client_links(protocol)}</div></div>'
    )


def _classic_client_action(protocol: str) -> str:
    links = _client_links(protocol)
    if not links:
        return ""
    return (
        f'<div class="v13-client-only" data-v13-protocol="{_h(protocol)}">'
        '<span>برنامه پیشنهادی همین دستگاه</span>'
        f'<div>{links}</div></div>'
    )


def _pending_card(protocol: str, reason: str, pane_id: str) -> tuple[str, str]:
    title, icon, color = PROTOCOL_META[protocol]
    card = (
        f'<button class="protocol-choice v13-pending" type="button" data-protocol="{_h(pane_id)}" '
        f'data-protocol-key="{_h(protocol)}" style="--pc:{_h(color)}">'
        f'<span class="protocol-icon">{_h(icon)}</span>'
        f'<span class="protocol-text"><b>{_h(title)}</b><small>{_h(reason)}</small></span>'
        '<em>در انتظار</em></button>'
    )
    panel = (
        f'<section id="{_h(pane_id)}" class="protocol-panel v13-pending-panel" '
        f'data-modern-protocol="{_h(protocol)}">'
        f'<div class="panel-head"><div><span>وضعیت پروتکل</span><h3>{_h(title)}</h3></div></div>'
        f'<div class="v13-pending-body"><b>هنوز قابل اتصال نیست</b><p>{_h(reason)}</p>'
        '<small>به محض آماده‌شدن Provision/Runtime، کانفیگ واقعی همین‌جا ظاهر می‌شود.</small>'
        f'<div class="v13-pending-apps">{_client_links(protocol)}</div></div></section>'
    )
    return card, panel


def _insert_before_panel_end(
    source: str,
    pane_id: str,
    fragment: str,
    *,
    modern_protocol: str | None = None,
) -> str:
    marker = f'<section id="{pane_id}"'
    start = source.find(marker)
    if start < 0:
        return source
    tag_end = source.find(">", start)
    if tag_end < 0:
        return source
    if modern_protocol and "data-modern-protocol=" not in source[start:tag_end]:
        attr = f' data-modern-protocol="{_h(modern_protocol)}"'
        source = source[:tag_end] + attr + source[tag_end:]
        tag_end += len(attr)
    end = source.find("</section>", tag_end)
    if end < 0:
        return source
    return source[:end] + fragment + source[end:]


def _mieru_karing_yaml(item: dict[str, Any]) -> str:
    try:
        cfg = json.loads(str(item.get("config") or ""))
    except Exception:
        return ""
    profiles = cfg.get("profiles") if isinstance(cfg, dict) else None
    if not isinstance(profiles, list) or not profiles or not isinstance(profiles[0], dict):
        return ""
    profile = profiles[0]
    user = profile.get("user") if isinstance(profile.get("user"), dict) else {}
    servers = profile.get("servers") if isinstance(profile.get("servers"), list) else []
    server = servers[0] if servers and isinstance(servers[0], dict) else {}
    bindings = server.get("portBindings") if isinstance(server.get("portBindings"), list) else []
    binding = bindings[0] if bindings and isinstance(bindings[0], dict) else {}
    host = str(server.get("domainName") or server.get("ipAddress") or item.get("server") or "").strip()
    try:
        port = int(binding.get("port") or item.get("port") or 0)
    except (TypeError, ValueError):
        port = 0
    username = str(user.get("name") or "").strip()
    password = str(user.get("password") or "").strip()
    if not host or port <= 0 or not username or not password:
        return ""
    q = lambda value: json.dumps(str(value), ensure_ascii=False)
    return "\n".join([
        "proxies:",
        f"  - name: {q('TwinPanel Mieru')}",
        "    type: mieru",
        f"    server: {q(host)}",
        f"    port: {port}",
        "    transport: TCP",
        "    udp: true",
        f"    username: {q(username)}",
        f"    password: {q(password)}",
        "    multiplexing: MULTIPLEXING_LOW",
        "proxy-groups:",
        f"  - name: {q('PROXY')}",
        "    type: select",
        "    proxies:",
        f"      - {q('TwinPanel Mieru')}",
        "rules:",
        "  - MATCH,PROXY",
        "",
    ])


def _ready_modern_item(token: str, protocol: str, node_id: int, db: Session) -> dict[str, Any]:
    sub = _subscription_from_share_token(token, db)
    if _status_value(sub) != "active":
        raise HTTPException(status_code=403, detail="اشتراک فعال نیست")
    if protocol not in _desired_protocols(db, int(sub.id)):
        raise HTTPException(status_code=404, detail="پروتکل برای این اشتراک فعال نیست")
    payload = _public_payload(db, sub)
    credentials = payload.get("credentials") if isinstance(payload, dict) else []
    for cred in credentials if isinstance(credentials, list) else []:
        if not isinstance(cred, dict):
            continue
        if str(cred.get("protocol") or "").strip().lower() != protocol:
            continue
        for item in _items(cred):
            try:
                item_node_id = int(item.get("node_id") or 0)
            except (TypeError, ValueError):
                item_node_id = 0
            if item_node_id == int(node_id):
                return item
    raise HTTPException(status_code=404, detail="کانفیگ آماده نیست")


@router.get("/{token}/modern-config/{protocol}/{node_id}")
def public_modern_config_v13(
    token: str,
    protocol: str,
    node_id: int,
    profile: str | None = None,
    db: Session = Depends(get_db),
):
    protocol = str(protocol or "").strip().lower()
    if protocol not in MODERN_PROTOCOLS:
        raise HTTPException(status_code=404, detail="پروتکل پشتیبانی نمی‌شود")
    item = _ready_modern_item(token, protocol, node_id, db)
    config = str(item.get("config") or "").strip()
    if not config:
        raise HTTPException(status_code=404, detail="کانفیگ آماده نیست")

    if protocol == "mieru" and str(profile or "").strip().lower() == "karing":
        content = _mieru_karing_yaml(item)
        if not content:
            raise HTTPException(status_code=404, detail="پروفایل Karing آماده نیست")
        filename = f"twinpanel-{protocol}-{node_id}.yaml"
        media_type = "text/yaml"
    else:
        config_format = str(item.get("config_format") or "").strip().lower()
        if config_format in {"sing-box", "mieru-json", "sudoku-json"}:
            filename = f"twinpanel-{protocol}-{node_id}.json"
            media_type = "application/json"
        elif protocol == "amneziawg" or config_format in {"amneziawg", "amneziawg-conf"}:
            filename = f"twinpanel-{protocol}-{node_id}.conf"
            media_type = "text/plain"
        else:
            filename = f"twinpanel-{protocol}-{node_id}.txt"
            media_type = "text/plain"
        content = config

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


_CSS = r"""
/* TWINPANEL_PUBLIC_MODERN_DELIVERY_V13 */
.protocol-choice.v13-pending{opacity:.82;border-style:dashed}.protocol-choice.v13-pending em{color:var(--muted);border-color:var(--line)}
.protocol-panel[data-modern-protocol] .server-view>.facts{display:none}
.v13-modern-action,.v13-client-only,.v13-pending-body{margin:14px;padding:14px;border:1px solid var(--line);border-radius:14px;background:var(--surface2)}
.v13-modern-action{display:flex;align-items:center;justify-content:space-between;gap:12px}
.v13-action-copy b,.v13-pending-body b{display:block;font-size:10px}.v13-action-copy small,.v13-pending-body small,.v13-pending-body p{display:block;margin-top:5px;color:var(--muted);font-size:8px;line-height:1.8}
.v13-action-buttons,.v13-client-only>div,.v13-pending-apps{display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.v13-app,.v13-secondary{display:none;padding:8px 10px;border-radius:10px;border:1px solid var(--line);background:var(--surface);font-size:8px;font-weight:900}
.v13-native-client{font-size:8px;color:var(--muted)}.v13-client-only{display:flex;align-items:center;justify-content:space-between;gap:10px}.v13-client-only>span{font-size:8px;color:var(--muted)}
.v13-pending-apps{margin-top:12px}.v13-pending-panel{border-style:dashed}
@media(max-width:760px){.v13-modern-action,.v13-client-only{align-items:stretch;flex-direction:column}.v13-action-buttons,.v13-client-only>div{width:100%}.v13-action-buttons>*{flex:1;text-align:center}}
"""


_SCRIPT = r"""
<script>
(function(){
  function platform(){
    const ua=(navigator.userAgent||'').toLowerCase();
    const p=(navigator.platform||'').toLowerCase();
    if(/iphone|ipad|ipod/.test(ua)||(p==='macintel'&&navigator.maxTouchPoints>1))return'ios';
    if(/android/.test(ua))return'android';
    if(/windows|win32|win64/.test(ua+' '+p))return'windows';
    if(/macintosh|mac os x/.test(ua)||p.includes('mac'))return'macos';
    return'other';
  }
  const current=platform();
  document.querySelectorAll('.v13-app').forEach(function(link){
    link.style.display=(current==='other'||link.dataset.v13Platform===current)?'inline-flex':'none';
  });
  const globalApps=document.getElementById('apps');
  if(globalApps)globalApps.hidden=true;
  document.querySelectorAll('.v13-karing-import').forEach(function(button){
    button.addEventListener('click',function(){
      const path=button.dataset.configPath||'';
      if(!path)return;
      const url=location.origin+path;
      location.href='karing://install-config?url='+encodeURIComponent(url)+'&name='+encodeURIComponent('TwinPanel');
    });
  });
})();
</script>
"""


def refine_public_connection_modern_delivery_v13(source: str, token: str, db: Session) -> str:
    """Expose all desired protocols and real device-aware Modern import actions."""
    if "TWINPANEL_PUBLIC_MODERN_DELIVERY_V13" in source:
        return source

    sub = _subscription_from_share_token(token, db)
    active = _status_value(sub) == "active"
    desired = _desired_protocols(db, int(sub.id))
    payload = _public_payload(db, sub) if active else {"credentials": []}
    credentials = payload.get("credentials") if isinstance(payload, dict) else []
    ready: dict[str, list[dict[str, Any]]] = {}
    for cred in credentials if isinstance(credentials, list) else []:
        if not isinstance(cred, dict):
            continue
        protocol = str(cred.get("protocol") or "").strip().lower()
        items = _items(cred)
        if protocol and items:
            ready[protocol] = items

    pane_by_protocol: dict[str, str] = {}
    for match in re.finditer(
        r'data-protocol="([^"]+)"[^>]*data-protocol-key="([^"]+)"', source
    ):
        pane_by_protocol[str(match.group(2)).strip().lower()] = str(match.group(1))

    for protocol, pane_id in list(pane_by_protocol.items()):
        if protocol in MODERN_PROTOCOLS and protocol in ready:
            source = _insert_before_panel_end(
                source,
                pane_id,
                "".join(_modern_action(token, protocol, item) for item in ready[protocol]),
                modern_protocol=protocol,
            )
        elif protocol in CLASSIC_PROTOCOLS:
            source = _insert_before_panel_end(
                source,
                pane_id,
                _classic_client_action(protocol),
            )

    missing_cards: list[str] = []
    missing_panels: list[str] = []
    for protocol in desired:
        if protocol in pane_by_protocol:
            continue
        reason = _credential_state(db, int(sub.id), protocol, active=active)
        pane_id = f"hub-v13-pending-{protocol}"
        card, panel = _pending_card(protocol, reason, pane_id)
        missing_cards.append(card)
        missing_panels.append(panel)

    if missing_cards:
        source = re.sub(
            r'(<section class="protocols">)(.*?)(</section>)',
            lambda match: match.group(1) + match.group(2) + "".join(missing_cards) + match.group(3),
            source,
            count=1,
            flags=re.S,
        )
        source = source.replace(
            '<details class="advanced">',
            "".join(missing_panels) + '<details class="advanced">',
            1,
        )

    source = source.replace("</style>", _CSS + "\n</style>", 1)
    source = source.replace("</body>", _SCRIPT + "\n</body>", 1)
    return source
