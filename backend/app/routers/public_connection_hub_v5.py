from __future__ import annotations

import html
import json
import re
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..branding_models import BrandingSettings
from ..database import get_db
from ..models import Node, User
from .account_delivery import (
    DOWNLOADS,
    _public_payload,
    _subscription_from_share_token,
    _usage_payload,
)
from .download_assets import public_downloads_by_platform


router = APIRouter(prefix="/v1/connect", tags=["public-connection-hub-v5"])


def h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def safe_color(value: Any, fallback: str) -> str:
    value = str(value or "").strip()
    return value if re.fullmatch(r"#[0-9A-Fa-f]{6}", value) else fallback


def protocol_meta(protocol: str) -> tuple[str, str, str]:
    protocol = str(protocol or "").strip().lower()
    return {
        "cisco": ("Cisco / OpenConnect", "C", "#17b6d8"),
        "openvpn": ("OpenVPN", "O", "#f59e0b"),
        "wireguard": ("WireGuard", "W", "#ef476f"),
        "l2tp": ("L2TP / IPsec", "L2", "#65c93a"),
        "v2ray": ("V2Ray / Xray", "V", "#8b5cf6"),
        "xray": ("V2Ray / Xray", "V", "#8b5cf6"),
    }.get(protocol, (protocol or "Protocol", "•", "#8b5cf6"))


def _items(cred: dict[str, Any]) -> list[dict[str, Any]]:
    raw = cred.get("items") or []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _server_name(item: dict[str, Any], node_names: dict[int, str], index: int) -> str:
    try:
        node_id = int(item.get("node_id") or 0)
    except (TypeError, ValueError):
        node_id = 0
    return str(
        node_names.get(node_id)
        or item.get("node")
        or item.get("country")
        or item.get("location")
        or f"Server {index + 1}"
    ).strip()


def _copy(value: Any, label: str = "کپی") -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    return f'<button class="copy-btn" type="button" data-copy="{h(value)}">{h(label)}</button>'


def _fact(label: str, value: Any) -> str:
    value = str(value or "").strip() or "—"
    return (
        '<div class="fact">'
        f'<small>{h(label)}</small>'
        f'<strong dir="ltr" title="{h(value)}">{h(value)}</strong>'
        f'{_copy(value) if value != "—" else ""}'
        '</div>'
    )


def _file_action(protocol: str, item: dict[str, Any], index: int, prefix: str) -> str:
    config = str(item.get("config") or "").strip()
    if not config:
        return '<div class="empty-inline">کانفیگ هنوز آماده نشده است.</div>'
    ext = "ovpn" if protocol == "openvpn" else "conf"
    filename = str(item.get("filename") or f"{protocol}-{index + 1}.{ext}")
    source_id = f"{prefix}-{protocol}-{index}"
    qr = str(item.get("qr") or "").strip()
    qr_html = f'<img class="qr" src="{h(qr)}" alt="QR">' if qr and protocol == "wireguard" else ""
    return (
        '<div class="action-row">'
        f'{qr_html}'
        f'<textarea id="{h(source_id)}" class="hidden-source" readonly>{h(config)}</textarea>'
        '<div class="action-copy"><b>کانفیگ آماده است</b><small>فایل را دانلود و داخل برنامه مربوط وارد کنید.</small></div>'
        f'<button class="primary-btn download-config" type="button" data-target="{h(source_id)}" data-filename="{h(filename)}">دانلود کانفیگ</button>'
        '</div>'
    )


def _v2ray_action(item: dict[str, Any]) -> str:
    uri = str(item.get("uri") or "").strip()
    if not uri:
        return '<div class="empty-inline">لینک اتصال هنوز آماده نشده است.</div>'
    qr = str(item.get("qr") or "").strip()
    qr_html = f'<img class="qr" src="{h(qr)}" alt="QR V2Ray">' if qr else ""
    return (
        '<div class="action-row">'
        f'{qr_html}'
        '<div class="action-copy"><b>لینک اتصال آماده است</b><small>برای Hiddify، v2rayN و کلاینت‌های سازگار.</small></div>'
        '<div class="action-buttons">'
        f'{_copy(uri, "کپی لینک")}'
        f'<a class="primary-btn" href="{h(uri)}" target="_blank" rel="noopener noreferrer">باز کردن</a>'
        '</div></div>'
    )


def _item_detail(protocol: str, item: dict[str, Any], username: str, password: str, index: int, prefix: str) -> str:
    host = item.get("host") or item.get("server") or item.get("server_ip") or item.get("endpoint") or "—"
    port = item.get("port")
    user = item.get("username") or username
    secret = item.get("password") or password
    if protocol == "openvpn":
        return _file_action(protocol, item, index, prefix)
    if protocol == "wireguard":
        return _file_action(protocol, item, index, prefix)
    if protocol in {"v2ray", "xray"}:
        return _v2ray_action(item)
    if protocol == "cisco":
        address = f"{host}:{port}" if port else str(host)
        facts = [_fact("Server & Port", address), _fact("Username", user), _fact("Password", secret)]
    else:
        facts = [_fact("Server", host), _fact("Username", user), _fact("Password", secret)]
        if item.get("psk"):
            facts.append(_fact("IPsec Secret", item.get("psk")))
    return f'<div class="facts">{"".join(facts)}</div>'


def _best_connection(credentials: list[dict[str, Any]]) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    priority = ("v2ray", "xray", "wireguard", "openvpn", "cisco", "l2tp")
    normalized = [(str(c.get("protocol") or "").lower(), c) for c in credentials if isinstance(c, dict)]
    for wanted in priority:
        for protocol, cred in normalized:
            if protocol != wanted:
                continue
            items = _items(cred)
            if items:
                return protocol, cred, items[0]
    return None


def render_smart_connect(payload: dict[str, Any], username: str, password: str, node_names: dict[int, str]) -> str:
    credentials = payload.get("credentials") or []
    if not isinstance(credentials, list):
        credentials = []
    best = _best_connection(credentials)
    if not best:
        return '<div class="smart-empty"><b>اتصال هنوز آماده نیست</b><span>بعد از آماده‌شدن اکانت، بهترین گزینه اتصال اینجا نمایش داده می‌شود.</span></div>'
    protocol, cred, item = best
    title, icon, color = protocol_meta(protocol)
    name = _server_name(item, node_names, 0)
    detail = _item_detail(
        protocol,
        item,
        str(cred.get("username") or username or ""),
        str(cred.get("password") or cred.get("secret") or password or ""),
        0,
        "smart",
    )
    return (
        f'<div class="smart-card" style="--smart:{h(color)}">'
        '<div class="smart-copy">'
        '<span class="eyebrow">پیشنهاد هوشمند</span>'
        f'<div class="smart-title"><span class="smart-icon">{h(icon)}</span><div><h2>{h(title)}</h2><p>{h(name)} · آماده اتصال</p></div></div>'
        '<p class="smart-note">بر اساس کانفیگ‌های واقعی موجود در همین اشتراک انتخاب شده است.</p>'
        '</div>'
        f'<div class="smart-action">{detail}</div>'
        '</div>'
    )


def render_protocols(payload: dict[str, Any], username: str, password: str, node_names: dict[int, str]) -> tuple[str, str]:
    credentials = payload.get("credentials") or []
    if not isinstance(credentials, list):
        credentials = []
    cards: list[str] = []
    panels: list[str] = []
    index = 0
    for cred in credentials:
        if not isinstance(cred, dict):
            continue
        protocol = str(cred.get("protocol") or "").lower()
        items = _items(cred)
        if not items:
            continue
        title, icon, color = protocol_meta(protocol)
        pane_id = f"hub-protocol-{index}"
        active = " active" if index == 0 else ""
        cards.append(
            f'<button class="protocol-choice{active}" type="button" data-protocol="{h(pane_id)}" data-protocol-key="{h(protocol)}" style="--pc:{h(color)}">'
            f'<span class="protocol-icon">{h(icon)}</span><span class="protocol-text"><b>{h(title)}</b><small>{len(items)} سرور آماده</small></span><em>آماده</em>'
            '</button>'
        )
        server_tabs: list[str] = []
        server_views: list[str] = []
        for item_index, item in enumerate(items):
            server_id = f"{pane_id}-server-{item_index}"
            server_active = " active" if item_index == 0 else ""
            name = _server_name(item, node_names, item_index)
            server_tabs.append(
                f'<button class="server-tab{server_active}" type="button" data-server="{h(server_id)}"><i></i><span>{h(name)}</span></button>'
            )
            body = _item_detail(
                protocol,
                item,
                str(cred.get("username") or username or ""),
                str(cred.get("password") or cred.get("secret") or password or ""),
                item_index,
                pane_id,
            )
            server_views.append(f'<div id="{h(server_id)}" class="server-view{server_active}">{body}</div>')
        panels.append(
            f'<section id="{h(pane_id)}" class="protocol-panel{active}">'
            f'<div class="panel-head"><div><span>اتصال سریع</span><h3>{h(title)}</h3></div><div class="server-tabs">{"".join(server_tabs)}</div></div>'
            f'<div class="server-views">{"".join(server_views)}</div>'
            '</section>'
        )
        index += 1
    if not cards:
        return '<div class="empty-state">پروتکل آماده‌ای برای این اشتراک وجود ندارد.</div>', ""
    return "".join(cards), "".join(panels)


def render_apps(uploaded: dict[str, list[dict]]) -> str:
    platform_labels = {
        "windows": ("Windows", "WIN"),
        "macos": ("macOS", "MAC"),
        "android": ("Android", "AND"),
        "ios": ("iPhone / iPad", "iOS"),
        "linux": ("Linux", "LNX"),
    }
    groups: list[str] = []
    for platform in ("windows", "macos", "android", "ios", "linux"):
        title, mark = platform_labels[platform]
        cards: list[str] = []
        for item in DOWNLOADS.get(platform) or []:
            cards.append(
                f'<a class="app-card" href="{h(item.get("url") or "#")}" target="_blank" rel="noopener noreferrer"><span>↗</span><div><b>{h(item.get("name") or "App")}</b><small>لینک رسمی</small></div></a>'
            )
        for item in uploaded.get(platform) or []:
            cards.append(
                f'<a class="app-card uploaded" href="{h(item.get("url") or "#")}"><span>↓</span><div><b>{h(item.get("name") or "App")}</b><small>{h(item.get("note") or "دانلود مستقیم")}</small></div></a>'
            )
        groups.append(
            f'<section class="platform-group" data-platform="{platform}"><div class="platform-title"><span>{mark}</span><div><b>{title}</b><small>برنامه‌های مناسب دستگاه شما</small></div></div><div class="app-grid">{"".join(cards)}</div></section>'
        )
    return "".join(groups)


@router.get("/{token}", response_class=HTMLResponse)
def public_connection_hub_v5(token: str, db: Session = Depends(get_db)):
    sub = _subscription_from_share_token(token, db)
    status = str(getattr(sub.status, "value", sub.status)).lower()
    payload = _public_payload(db, sub)
    usage = _usage_payload(db, sub)
    user = db.get(User, sub.user_id)
    branding = db.query(BrandingSettings).first()

    node_names = {
        int(node.id): str(node.name)
        for node in db.query(Node).all()
        if getattr(node, "id", None) is not None
    }

    brand_name = str(getattr(branding, "brand_name", None) or "TwinPanel").strip() or "TwinPanel"
    brand_mark = next((ch.upper() for ch in brand_name if not ch.isspace()), "T")
    primary = safe_color(getattr(branding, "primary_color", None), "#8B5CF6")
    secondary = safe_color(getattr(branding, "secondary_color", None), "#6D28D9")
    customer = str((getattr(user, "full_name", None) or getattr(user, "email", None) or "کاربر") if user else "کاربر")
    avatar = next((ch.upper() for ch in customer if not ch.isspace()), "U")

    account = payload.get("account") if isinstance(payload.get("account"), dict) else {}
    username = str((account or {}).get("username") or getattr(sub, "account_username", "") or "")
    password = str((account or {}).get("password") or "")
    service = (username or f"SERVICE-{sub.id}").replace("_", "-").upper()

    used = float(usage.get("used_gb") or 0)
    total = usage.get("total_gb")
    remaining = usage.get("remaining_gb")
    percent = max(0.0, min(100.0, float(usage.get("percent") or 0)))
    used_label = f"{used:.1f} GB"
    total_label = "∞" if total is None else f"{float(total or 0):.1f} GB"
    remaining_label = "∞" if remaining is None else f"{float(remaining or 0):.1f} GB"
    starts = getattr(sub, "starts_at", None)
    expires = getattr(sub, "expires_at", None)
    start_label = starts.strftime("%Y/%m/%d") if starts else "—"
    expire_label = expires.strftime("%Y/%m/%d") if expires else "—"

    safe_payload = payload if status == "active" else {**payload, "credentials": [], "account": {}}
    smart_html = render_smart_connect(safe_payload, username if status == "active" else "", password if status == "active" else "", node_names)
    protocol_cards, protocol_panels = render_protocols(safe_payload, username if status == "active" else "", password if status == "active" else "", node_names)
    apps_html = render_apps(public_downloads_by_platform(db))
    share_url = str(payload.get("subscription_link") or "")
    status_html = '<span class="status on"><i></i>اشتراک فعال</span>' if status == "active" else '<span class="status off"><i></i>غیرفعال</span>'

    page = r'''<!doctype html><html lang="fa" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark">
<title>__BRAND__ · __SERVICE__</title>
<style>
:root{--p:__PRIMARY__;--s:__SECONDARY__;--bg:#f5f6fa;--surface:#fff;--surface2:#f8f8fc;--surface3:#f1f2f8;--line:#e3e5ee;--text:#171a24;--muted:#737b8d;--ok:#16a765;--danger:#d84b62;--shadow:0 18px 50px rgba(31,35,52,.08)}html[data-theme="dark"]{--bg:#080a0f;--surface:#0f1219;--surface2:#141821;--surface3:#1a1f2a;--line:#252b37;--text:#f5f6f8;--muted:#8c94a3;--ok:#42d88b;--danger:#ff7890;--shadow:0 20px 54px rgba(0,0,0,.28);color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Tahoma,Arial,sans-serif;-webkit-font-smoothing:antialiased}button,a,textarea{font:inherit}a{color:inherit;text-decoration:none}button{cursor:pointer}.top{position:sticky;top:0;z-index:30;border-bottom:1px solid var(--line);background:color-mix(in srgb,var(--surface) 90%,transparent);backdrop-filter:blur(18px)}.topin{width:min(1180px,92vw);height:72px;margin:auto;display:flex;align-items:center;justify-content:space-between;gap:18px}.brand,.profile{display:flex;align-items:center;gap:10px}.mark,.avatar{display:grid;place-items:center;color:#fff;background:linear-gradient(135deg,var(--p),var(--s));font-weight:900}.mark{width:40px;height:40px;border-radius:13px}.avatar{width:36px;height:36px;border-radius:50%}.brand b{font-size:18px}.profile-copy strong{display:block;font-size:11px}.profile-copy small{font-size:8px;color:var(--muted)}.service{font-size:10px;font-weight:900;color:var(--muted)}.status{height:28px;padding:0 10px;border-radius:999px;display:flex;align-items:center;gap:6px;font-size:8px;font-weight:900}.status i{width:6px;height:6px;border-radius:50%;background:currentColor}.status.on{color:var(--ok);background:color-mix(in srgb,var(--ok) 10%,transparent);border:1px solid color-mix(in srgb,var(--ok) 30%,transparent)}.status.off{color:var(--danger);background:color-mix(in srgb,var(--danger) 9%,transparent);border:1px solid color-mix(in srgb,var(--danger) 28%,transparent)}.theme{width:34px;height:34px;border:1px solid var(--line);border-radius:10px;background:var(--surface2);color:var(--text)}.page{width:min(1180px,92vw);margin:auto;padding:24px 0 52px}.traffic{display:grid;grid-template-columns:180px 1fr;gap:22px;align-items:center;padding:20px;border:1px solid var(--line);border-radius:22px;background:var(--surface);box-shadow:var(--shadow)}.visual{display:flex;align-items:center;gap:14px}.donut{--pct:0;width:104px;height:104px;flex:0 0 104px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--p) calc(var(--pct)*1%),var(--surface3) 0);position:relative}.donut:before{content:"";position:absolute;inset:11px;border-radius:50%;background:var(--surface)}.donut div{position:relative;text-align:center}.donut b{font-size:21px}.donut small{display:block;font-size:7px;color:var(--muted)}.visual h2{margin:0;font-size:17px}.visual em{display:inline-block;margin-top:6px;padding:4px 8px;border-radius:999px;background:color-mix(in srgb,var(--ok) 10%,transparent);color:var(--ok);font-style:normal;font-size:7px;font-weight:900}.stats{display:grid;grid-template-columns:repeat(5,1fr)}.stat{padding:2px 16px;border-left:1px solid var(--line)}.stat:last-child{border-left:0}.stat small{font-size:8px;color:var(--muted)}.stat strong{display:block;margin-top:7px;font-size:14px}.section-head{display:flex;align-items:flex-end;justify-content:space-between;gap:14px;margin:26px 0 11px}.section-head small,.eyebrow{color:var(--p);font-size:8px;font-weight:900}.section-head h2{margin:4px 0 0;font-size:19px}.section-head p{margin:0;color:var(--muted);font-size:9px}.smart-card{display:grid;grid-template-columns:minmax(240px,.8fr) 1.2fr;gap:18px;padding:20px;border:1px solid color-mix(in srgb,var(--smart) 34%,var(--line));border-radius:22px;background:linear-gradient(135deg,color-mix(in srgb,var(--smart) 9%,var(--surface)),var(--surface) 45%);box-shadow:var(--shadow)}.smart-copy{display:flex;flex-direction:column;justify-content:center}.smart-title{display:flex;align-items:center;gap:12px;margin-top:10px}.smart-title h2{margin:0 0 4px;font-size:20px}.smart-title p,.smart-note{margin:0;color:var(--muted);font-size:9px}.smart-note{margin-top:14px;line-height:1.9}.smart-icon,.protocol-icon{display:grid;place-items:center;color:#fff;background:var(--smart,var(--pc));font-weight:900}.smart-icon{width:52px;height:52px;border-radius:16px}.smart-action{display:flex;align-items:center}.smart-action>.action-row,.smart-action>.facts{width:100%}.smart-empty,.empty-state{padding:28px;border:1px dashed var(--line);border-radius:18px;background:var(--surface);text-align:center}.smart-empty b{display:block;margin-bottom:7px}.smart-empty span,.empty-inline{color:var(--muted);font-size:9px}.protocols{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}.protocol-choice{min-height:86px;padding:11px;border:1px solid var(--line);border-radius:15px;background:var(--surface);color:var(--text);display:grid;grid-template-columns:40px 1fr auto;align-items:center;gap:10px;text-align:right}.protocol-choice.active{border-color:var(--p);box-shadow:0 0 0 1px color-mix(in srgb,var(--p) 20%,transparent)}.protocol-icon{width:40px;height:40px;border-radius:12px}.protocol-text b{display:block;font-size:10px}.protocol-text small{display:block;margin-top:4px;color:var(--muted);font-size:7px}.protocol-choice em{font-style:normal;font-size:7px;color:var(--pc);padding:4px 7px;border:1px solid color-mix(in srgb,var(--pc) 26%,transparent);border-radius:999px}.protocol-panel{display:none;margin-top:10px;border:1px solid var(--line);border-radius:18px;background:var(--surface);overflow:hidden}.protocol-panel.active{display:block}.panel-head{min-height:64px;padding:12px 14px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:16px}.panel-head span{color:var(--muted);font-size:7px}.panel-head h3{margin:3px 0 0;font-size:14px}.server-tabs{display:flex;flex-wrap:wrap;gap:6px}.server-tab{height:31px;max-width:190px;padding:0 10px;border:1px solid var(--line);border-radius:9px;background:var(--surface2);color:var(--muted);display:flex;align-items:center;gap:6px;font-size:8px;font-weight:900}.server-tab i{width:6px;height:6px;border-radius:50%;background:var(--ok)}.server-tab.active{border-color:var(--p);color:var(--text)}.server-views{padding:14px}.server-view{display:none}.server-view.active{display:block}.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px}.fact{min-height:86px;padding:13px;border:1px solid var(--line);border-radius:12px;background:var(--surface2);text-align:center}.fact small{font-size:7px;color:var(--muted)}.fact strong{display:block;margin:9px 0 8px;font:700 10px ui-monospace,Consolas,monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.copy-btn,.primary-btn{height:32px;padding:0 11px;border-radius:9px;font-size:8px;font-weight:900;display:inline-flex;align-items:center;justify-content:center}.copy-btn{border:1px solid color-mix(in srgb,var(--p) 30%,var(--line));background:color-mix(in srgb,var(--p) 8%,var(--surface));color:var(--p)}.primary-btn{border:0;background:linear-gradient(135deg,var(--p),var(--s));color:#fff}.action-row{display:flex;align-items:center;gap:12px;padding:14px;border:1px solid var(--line);border-radius:13px;background:var(--surface2)}.action-copy{min-width:0;margin-left:auto}.action-copy b{display:block;font-size:11px}.action-copy small{display:block;margin-top:4px;color:var(--muted);font-size:8px}.action-buttons{display:flex;gap:7px}.qr{width:88px;height:88px;padding:5px;border-radius:12px;background:#fff}.hidden-source{display:none}.advanced{margin-top:16px;border:1px solid var(--line);border-radius:18px;background:var(--surface);overflow:hidden}.advanced summary{list-style:none;padding:16px 18px;cursor:pointer;display:flex;align-items:center;justify-content:space-between;font-weight:900;font-size:11px}.advanced summary::-webkit-details-marker{display:none}.advanced summary:after{content:"+";font-size:18px;color:var(--p)}.advanced[open] summary:after{content:"−"}.advanced-body{padding:0 16px 16px;display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.share-card{grid-column:span 2;display:grid;grid-template-columns:90px 1fr;gap:12px;align-items:center;padding:12px;border:1px solid var(--line);border-radius:13px;background:var(--surface2)}.share-card img{width:82px;height:82px;padding:4px;border-radius:10px;background:#fff}.share-copy{min-width:0}.share-copy b{font-size:10px}.share-copy code{display:block;margin:6px 0;direction:ltr;text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--muted);font-size:7px}.apps{margin-top:18px;border:1px solid var(--line);border-radius:18px;background:var(--surface);overflow:hidden}.apps-head{padding:15px 16px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between}.apps-head small{color:var(--p);font-size:8px;font-weight:900}.apps-head h2{margin:4px 0 0;font-size:16px}.tools{display:flex;gap:7px}.device,.allbtn{height:30px;padding:0 10px;border-radius:9px;font-size:8px;font-weight:900}.device{border:1px solid color-mix(in srgb,var(--ok) 28%,var(--line));background:color-mix(in srgb,var(--ok) 8%,var(--surface));color:var(--ok);display:flex;align-items:center}.allbtn{border:1px solid var(--line);background:var(--surface2);color:var(--text)}.platforms{padding:14px}.platform-group{display:none}.platform-group.device-active{display:block}.platform-group.show-all{display:block;margin-bottom:18px}.platform-title{display:flex;align-items:center;gap:9px;margin-bottom:11px}.platform-title>span{width:38px;height:38px;border-radius:11px;background:var(--surface3);display:grid;place-items:center;font-size:8px;font-weight:900}.platform-title b{font-size:11px}.platform-title small{display:block;margin-top:3px;font-size:7px;color:var(--muted)}.app-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.app-card{min-height:67px;padding:10px;border:1px solid var(--line);border-radius:11px;background:var(--surface2);display:grid;grid-template-columns:32px 1fr;align-items:center;gap:9px}.app-card>span{width:32px;height:32px;border-radius:9px;background:var(--surface3);display:grid;place-items:center;color:var(--p)}.app-card b{font-size:8px}.app-card small{display:block;margin-top:4px;color:var(--muted);font-size:7px}.toast{position:fixed;left:50%;bottom:24px;z-index:60;transform:translate(-50%,14px);opacity:0;pointer-events:none;padding:10px 14px;border-radius:10px;background:#181a22;color:#fff;font-size:9px;transition:.2s}.toast.show{opacity:1;transform:translate(-50%,0)}
@media(max-width:900px){.protocols{grid-template-columns:repeat(2,1fr)}.app-grid{grid-template-columns:repeat(2,1fr)}.advanced-body{grid-template-columns:1fr 1fr}.share-card{grid-column:1/-1}}
@media(max-width:720px){.topin{height:64px}.profile-copy,.service{display:none}.page{width:min(94vw,680px);padding-top:14px}.traffic{grid-template-columns:1fr;padding:15px}.visual{justify-content:center}.stats{grid-template-columns:repeat(2,1fr)}.stat{padding:10px;border-left:0;border-bottom:1px solid var(--line)}.smart-card{grid-template-columns:1fr;padding:16px}.protocols{grid-template-columns:1fr}.protocol-choice{min-height:72px}.panel-head{align-items:flex-start;flex-direction:column}.server-tabs{width:100%;overflow-x:auto;flex-wrap:nowrap}.server-tab{flex:0 0 auto}.action-row{align-items:stretch;flex-direction:column}.action-copy{margin-left:0}.action-buttons{width:100%}.action-buttons>*{flex:1}.qr{align-self:center}.advanced-body{grid-template-columns:1fr}.share-card{grid-template-columns:70px 1fr}.share-card img{width:64px;height:64px}.app-grid{grid-template-columns:1fr}.section-head{align-items:flex-start;flex-direction:column}}
</style></head><body>
<header class="top"><div class="topin"><div class="brand"><button id="themeToggle" class="theme" type="button" aria-label="تغییر حالت">☾</button><span class="mark">__MARK__</span><b>__BRAND__</b></div><div class="profile"><span class="avatar">__AVATAR__</span><div class="profile-copy"><strong>__CUSTOMER__</strong><small>حساب کاربری</small></div><span class="service">__SERVICE__</span>__STATUS__</div></div></header>
<main class="page">
<section class="traffic"><div class="visual"><div class="donut" style="--pct:__PERCENT__"><div><b>__PERCENT_LABEL__%</b><small>مصرف شده</small></div></div><div><h2>وضعیت اشتراک</h2><em>LIVE</em></div></div><div class="stats"><div class="stat"><small>مصرف‌شده</small><strong>__USED__</strong></div><div class="stat"><small>باقی‌مانده</small><strong>__REMAIN__</strong></div><div class="stat"><small>حجم کل</small><strong>__TOTAL__</strong></div><div class="stat"><small>تاریخ شروع</small><strong>__START__</strong></div><div class="stat"><small>تاریخ انقضا</small><strong>__EXPIRE__</strong></div></div></section>
<div class="section-head"><div><small>SMART CONNECT</small><h2>اتصال هوشمند</h2></div><p>سریع‌ترین مسیر برای شروع اتصال، بدون درگیرشدن با جزئیات فنی.</p></div>
__SMART__
<div class="section-head"><div><small>QUICK CONNECT</small><h2>اتصال سریع</h2></div><p>پروتکل دلخواه را انتخاب کنید؛ فقط گزینه‌های واقعی و آماده نمایش داده می‌شوند.</p></div>
<section class="protocols">__PCARDS__</section><div>__PPANELS__</div>
<details class="advanced"><summary>تنظیمات حرفه‌ای و اطلاعات حساب</summary><div class="advanced-body"><div class="share-card"><img src="/v1/connect/__TOKEN__/qr" alt="Subscription QR"><div class="share-copy"><b>لینک اشتراک</b><code>__SHARE__</code>__SHARE_COPY__</div></div>__ACCOUNT_FACTS__</div></details>
<section class="apps" id="apps"><div class="apps-head"><div><small>APPS & DOWNLOADS</small><h2>برنامه‌های اتصال</h2></div><div class="tools"><span id="device" class="device">در حال تشخیص…</span><button id="all" class="allbtn" type="button">همه سیستم‌ها</button></div></div><div class="platforms">__APPS__</div></section>
</main><div id="toast" class="toast">کپی شد</div>
<script>
(function(){
const key='twinpanel_public_connect_theme',root=document.documentElement,theme=document.getElementById('themeToggle');
function setTheme(v){const x=v==='dark'?'dark':'light';root.dataset.theme=x;if(theme)theme.textContent=x==='dark'?'☀':'☾'}
let saved='';try{saved=localStorage.getItem(key)||''}catch(e){}setTheme(saved||(matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'));
if(theme)theme.onclick=function(){const next=root.dataset.theme==='dark'?'light':'dark';setTheme(next);try{localStorage.setItem(key,next)}catch(e){}};
const toast=document.getElementById('toast');function show(t){toast.textContent=t;toast.classList.add('show');clearTimeout(window.__hubToast);window.__hubToast=setTimeout(()=>toast.classList.remove('show'),1200)}
function fallbackCopy(t){const a=document.createElement('textarea');a.value=t;a.style.position='fixed';a.style.opacity='0';document.body.appendChild(a);a.select();let ok=false;try{ok=document.execCommand('copy')}catch(e){}a.remove();return ok}
async function copy(t){if(navigator.clipboard&&window.isSecureContext){try{await navigator.clipboard.writeText(t);return true}catch(e){}}return fallbackCopy(t)}
document.querySelectorAll('.protocol-choice').forEach(b=>b.onclick=function(){const id=b.dataset.protocol;document.querySelectorAll('.protocol-choice').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.protocol-panel').forEach(x=>x.classList.remove('active'));b.classList.add('active');const p=document.getElementById(id);if(p)p.classList.add('active')});
document.querySelectorAll('.server-tab').forEach(b=>b.onclick=function(){const p=b.closest('.protocol-panel');if(!p)return;p.querySelectorAll('.server-tab').forEach(x=>x.classList.remove('active'));p.querySelectorAll('.server-view').forEach(x=>x.classList.remove('active'));b.classList.add('active');const v=document.getElementById(b.dataset.server);if(v)v.classList.add('active')});
document.addEventListener('click',async e=>{const b=e.target.closest('[data-copy]');if(b){show(await copy(b.dataset.copy||'')?'کپی شد ✓':'کپی انجام نشد');return}const d=e.target.closest('.download-config');if(d){const el=document.getElementById(d.dataset.target||'');if(!el)return;const blob=new Blob([el.value||''],{type:'text/plain;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=d.dataset.filename||'config.txt';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);show('دانلود آماده شد')}});
function detect(){const u=(navigator.userAgent||'').toLowerCase(),p=((navigator.userAgentData&&navigator.userAgentData.platform)||navigator.platform||'').toLowerCase();if(/android/.test(u))return'android';if(/iphone|ipad|ipod/.test(u)||(p==='macintel'&&navigator.maxTouchPoints>1))return'ios';if(/windows|win32|win64/.test(u+' '+p))return'windows';if(/macintosh|mac os|macintel/.test(u+' '+p))return'macos';if(/linux|x11|cros/.test(u+' '+p))return'linux';return'unknown'}
const names={windows:'Windows',macos:'macOS',android:'Android',ios:'iPhone / iPad',linux:'Linux',unknown:'همه سیستم‌ها'},det=detect(),groups=[...document.querySelectorAll('.platform-group')];function only(){groups.forEach(g=>{g.classList.remove('show-all');g.classList.toggle('device-active',det==='unknown'||g.dataset.platform===det)});document.getElementById('device').textContent=names[det];document.getElementById('all').textContent='همه سیستم‌ها'}only();document.getElementById('all').onclick=function(){const all=groups.some(g=>g.classList.contains('show-all'));if(all){only();return}groups.forEach(g=>{g.classList.remove('device-active');g.classList.add('show-all')});this.textContent='فقط دستگاه من';document.getElementById('device').textContent='همه سیستم‌ها'};
})();
</script></body></html>'''

    account_facts = ""
    if status == "active":
        if username:
            account_facts += _fact("Username", username)
        if password:
            account_facts += _fact("Password", password)
    if not account_facts:
        account_facts = '<div class="fact"><small>Account</small><strong>—</strong></div>'

    repl = {
        "__BRAND__": h(brand_name), "__MARK__": h(brand_mark), "__PRIMARY__": primary, "__SECONDARY__": secondary,
        "__SERVICE__": h(service), "__AVATAR__": h(avatar), "__CUSTOMER__": h(customer), "__STATUS__": status_html,
        "__PERCENT__": f"{percent:.1f}", "__PERCENT_LABEL__": f"{percent:.0f}", "__USED__": h(used_label), "__REMAIN__": h(remaining_label),
        "__TOTAL__": h(total_label), "__START__": h(start_label), "__EXPIRE__": h(expire_label), "__SMART__": smart_html,
        "__PCARDS__": protocol_cards, "__PPANELS__": protocol_panels, "__TOKEN__": h(token), "__SHARE__": h(share_url),
        "__SHARE_COPY__": _copy(share_url, "کپی لینک"), "__ACCOUNT_FACTS__": account_facts, "__APPS__": apps_html,
    }
    for key, value in repl.items():
        page = page.replace(key, value)
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})
