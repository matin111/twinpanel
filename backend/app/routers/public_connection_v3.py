from __future__ import annotations

import html
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


router = APIRouter(prefix="/v1/connect", tags=["public-connection-v3"])


def h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def safe_color(value: Any, fallback: str) -> str:
    value = str(value or "").strip()
    return value if re.fullmatch(r"#[0-9A-Fa-f]{6}", value) else fallback


def protocol_meta(protocol: str) -> tuple[str, str, str, str]:
    protocol = str(protocol or "").lower()
    return {
        "cisco": ("Cisco AnyConnect", "IP + Username + Password", "C", "#27b7d6"),
        "openvpn": ("OpenVPN", "دانلود فایل OVPN", "O", "#ff8a24"),
        "wireguard": ("WireGuard", "QR + فایل کانفیگ", "W", "#ef476f"),
        "l2tp": ("L2TP / IPsec", "IP + Username + Password + PSK", "L2TP", "#74d63f"),
        "v2ray": ("V2Ray / Xray", "QR + لینک اتصال", "V", "#7c3aed"),
        "xray": ("V2Ray / Xray", "QR + لینک اتصال", "V", "#7c3aed"),
    }.get(protocol, (protocol or "Protocol", "اتصال", "•", "#8b5cf6"))


def platform_meta(platform: str) -> tuple[str, str]:
    return {
        "windows": ("Windows", "WIN"),
        "macos": ("macOS", "MAC"),
        "android": ("Android", "AND"),
        "ios": ("iPhone / iPad", "iOS"),
        "linux": ("Linux", "LNX"),
    }.get(platform, (platform, "APP"))


def copy_button(value: Any, label: str = "کپی") -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return f'<button class="btn" type="button" data-copy="{h(text)}">{h(label)}</button>'


def fact(label: str, value: Any) -> str:
    text = str(value or "").strip() or "—"
    button = copy_button(text) if text != "—" else ""
    return (
        '<article class="fact">'
        f'<small>{h(label)}</small>'
        f'<strong dir="ltr" title="{h(text)}">{h(text)}</strong>'
        f'{button}'
        '</article>'
    )


def live_server_name(item: dict[str, Any], node_names: dict[int, str], index: int) -> str:
    try:
        node_id = int(item.get("node_id"))
    except (TypeError, ValueError):
        node_id = 0
    return str(
        node_names.get(node_id)
        or item.get("node")
        or item.get("name")
        or item.get("label")
        or item.get("country")
        or item.get("location")
        or f"Server {index + 1}"
    ).strip()


def file_download_card(protocol: str, index: int, server_name: str, item: dict[str, Any]) -> str:
    config = str(item.get("config") or "").strip()
    if not config:
        return (
            '<div class="delivery-card empty">'
            f'<div><small>سرور</small><strong>{h(server_name)}</strong></div>'
            '<span>کانفیگ هنوز آماده نشده است.</span>'
            '</div>'
        )

    source_id = f"cfg-{protocol}-{index}"
    filename = str(item.get("filename") or "").strip()
    if not filename:
        filename = f"openvpn-{index + 1}.ovpn" if protocol == "openvpn" else f"wireguard-{index + 1}.conf"

    qr = str(item.get("qr") or "").strip()
    qr_html = f'<img class="qr" src="{h(qr)}" alt="QR {h(server_name)}">' if qr and protocol == "wireguard" else ""

    return (
        '<div class="delivery-card">'
        '<div class="delivery-copy">'
        f'<span class="server-name">{h(server_name)}</span>'
        f'<small>{"WireGuard" if protocol == "wireguard" else "OpenVPN"}</small>'
        '</div>'
        f'{qr_html}'
        f'<textarea id="{h(source_id)}" class="hidden-source" readonly>{h(config)}</textarea>'
        f'<button class="primary-btn download-config" type="button" data-target="{h(source_id)}" data-filename="{h(filename)}">دانلود کانفیگ</button>'
        '</div>'
    )


def v2ray_card(index: int, server_name: str, item: dict[str, Any]) -> str:
    uri = str(item.get("uri") or "").strip()
    qr = str(item.get("qr") or "").strip()
    if not uri:
        return (
            '<div class="delivery-card empty">'
            f'<div><small>سرور</small><strong>{h(server_name)}</strong></div>'
            '<span>لینک اتصال هنوز آماده نشده است.</span>'
            '</div>'
        )

    qr_html = f'<img class="qr" src="{h(qr)}" alt="QR {h(server_name)}">' if qr else ""
    return (
        '<div class="delivery-card">'
        '<div class="delivery-copy">'
        f'<span class="server-name">{h(server_name)}</span>'
        '<small>V2Ray / Xray</small>'
        '</div>'
        f'{qr_html}'
        '<div class="delivery-actions">'
        f'{copy_button(uri, "کپی لینک")}'
        f'<a class="primary-btn" href="{h(uri)}" target="_blank" rel="noopener noreferrer">باز کردن لینک</a>'
        '</div>'
        '</div>'
    )


def connection_views(
    protocol: str,
    items: list[dict[str, Any]],
    fallback_username: str,
    fallback_password: str,
    node_names: dict[int, str],
) -> tuple[str, str]:
    tabs: list[str] = []
    views: list[str] = []

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            item = {}
        active = " active" if index == 0 else ""
        server_id = f"{protocol}-server-{index}"
        name = live_server_name(item, node_names, index)

        tabs.append(
            f'<button class="server-tab{active}" type="button" data-server="{h(server_id)}">'
            f'<span>{h(name)}</span><i></i></button>'
        )

        if protocol == "openvpn":
            body = file_download_card("openvpn", index, name, item)
        elif protocol == "wireguard":
            body = file_download_card("wireguard", index, name, item)
        elif protocol in {"v2ray", "xray"}:
            body = v2ray_card(index, name, item)
        else:
            host = item.get("host") or item.get("server") or item.get("server_ip") or item.get("endpoint") or "—"
            port = item.get("port")
            username = item.get("username") or fallback_username
            password = item.get("password") or fallback_password
            psk = item.get("psk")

            if protocol == "cisco":
                address = f"{host}:{port}" if port else str(host)
                facts = [fact("Server & Port", address), fact("Username", username), fact("Password", password)]
            else:
                facts = [fact("Server", host), fact("Username", username), fact("Password", password)]
                if psk:
                    facts.append(fact("PSK", psk))
            body = f'<div class="facts">{"".join(facts)}</div>'

        views.append(f'<div id="{h(server_id)}" class="server-view{active}">{body}</div>')

    if not items:
        return "", '<div class="empty-state">اطلاعات این پروتکل هنوز آماده نشده است.</div>'
    return "".join(tabs), "".join(views)


def render_protocols(
    payload: dict[str, Any],
    fallback_username: str,
    fallback_password: str,
    node_names: dict[int, str],
) -> tuple[str, str]:
    credentials = payload.get("credentials") or []
    if not isinstance(credentials, list):
        credentials = []

    cards: list[str] = []
    panels: list[str] = []
    pane_index = 0

    for cred in credentials:
        if not isinstance(cred, dict):
            continue
        protocol = str(cred.get("protocol") or "").lower()
        title, subtitle, icon, color = protocol_meta(protocol)
        items = cred.get("items") or []
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            items = []

        pane_id = f"protocol-pane-{pane_index}"
        active = " active" if pane_index == 0 else ""
        server_tabs, server_views = connection_views(
            protocol,
            items,
            str(cred.get("username") or fallback_username or ""),
            str(cred.get("password") or cred.get("secret") or fallback_password or ""),
            node_names,
        )

        cards.append(
            f'<button class="protocol-choice{active}" type="button" data-protocol="{pane_id}" style="--pc:{h(color)}">'
            f'<span class="protocol-icon">{h(icon)}</span><b>{h(title)}</b><small>{h(subtitle)}</small><em>فعال</em>'
            '</button>'
        )
        panels.append(
            f'<section id="{pane_id}" class="protocol-panel{active}">'
            '<div class="panel-head">'
            f'<div><h2>{h(title)}</h2><small>سرور را انتخاب کنید</small></div>'
            f'<div class="server-tabs">{server_tabs}</div>'
            '</div>'
            f'<div class="server-views">{server_views}</div>'
            '</section>'
        )
        pane_index += 1

    if not cards:
        return '<div class="empty-state">پروتکلی برای این اشتراک ثبت نشده است.</div>', ""
    return "".join(cards), "".join(panels)


def program_downloads_html(uploaded: dict[str, list[dict]]) -> str:
    groups: list[str] = []
    for platform in ("windows", "macos", "android", "ios", "linux"):
        title, icon = platform_meta(platform)
        official = DOWNLOADS.get(platform) or []
        assets = uploaded.get(platform) or []

        official_cards = "".join(
            '<a class="app-card" href="{}" target="_blank" rel="noopener noreferrer"><span>↗</span><div><b>{}</b><small>لینک رسمی</small></div></a>'.format(
                h(str(item.get("url") or "#")), h(str(item.get("name") or "برنامه اتصال"))
            )
            for item in official
        )

        uploaded_cards = "".join(
            '<a class="app-card uploaded" href="{}"><span>↓</span><div><b>{}</b><small>{}</small></div></a>'.format(
                h(str(item.get("url") or "#")),
                h(str(item.get("name") or "فایل برنامه")),
                h(str(item.get("note") or "دانلود مستقیم")),
            )
            for item in assets
        )

        groups.append(
            f'<section class="platform-group" data-platform="{h(platform)}">'
            f'<div class="platform-title"><span>{h(icon)}</span><div><b>{h(title)}</b><small>برنامه‌های مناسب این دستگاه</small></div></div>'
            f'<div class="app-grid">{official_cards}{uploaded_cards}</div>'
            '</section>'
        )
    return "".join(groups)


@router.get("/{token}", response_class=HTMLResponse)
def public_connection_page_v3(token: str, db: Session = Depends(get_db)):
    sub = _subscription_from_share_token(token, db)
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

    status = str(getattr(sub.status, "value", sub.status)).lower()
    account = payload.get("account") if isinstance(payload.get("account"), dict) else {}
    username = str((account or {}).get("username") or getattr(sub, "account_username", "") or "")
    password = str((account or {}).get("password") or "")

    used = float(usage.get("used_gb") or 0)
    total = usage.get("total_gb")
    remaining = usage.get("remaining_gb")
    percent = max(0.0, min(100.0, float(usage.get("percent") or 0)))
    total_label = "∞" if total is None else f"{float(total or 0):.0f} GB"
    remaining_label = "∞" if remaining is None else f"{float(remaining or 0):.0f} GB"
    used_label = f"{used:.1f} GB"

    starts_at = getattr(sub, "starts_at", None) or getattr(sub, "created_at", None)
    start_label = starts_at.strftime("%Y/%m/%d") if starts_at else "—"
    expires_at = getattr(sub, "expires_at", None)
    expires_label = expires_at.strftime("%Y/%m/%d") if expires_at else "—"

    customer_name = (getattr(user, "full_name", None) or getattr(user, "email", None) or "کاربر") if user else "کاربر"
    avatar = next((ch.upper() for ch in str(customer_name) if not ch.isspace()), "U")
    service_label = (username or f"SERVICE-{sub.id}").replace("_", "-").upper()

    protocol_cards, protocol_panels = render_protocols(payload, username, password, node_names)
    apps_html = program_downloads_html(public_downloads_by_platform(db))
    active_badge = '<span class="status on"><i></i>اشتراک فعال</span>' if status == "active" else '<span class="status off"><i></i>غیرفعال</span>'

    page = """<!doctype html><html lang="fa" dir="rtl" data-theme="dark"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark light">
<title>__BRAND__ · __SERVICE__</title>
<style>
:root{--bg:#05070b;--surface:#0b1017;--surface2:#101722;--line:#202a39;--text:#f4f7fb;--muted:#7e8ba0;--p:__PRIMARY__;--s:__SECONDARY__;--ok:#29d37d;--orange:#ff9f43}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Tahoma,Arial,sans-serif}a{text-decoration:none;color:inherit}button,a,textarea{font:inherit}.top{height:72px;border-bottom:1px solid #171c25;background:#050609;position:sticky;top:0;z-index:20}.topin{width:min(1320px,94vw);height:100%;margin:auto;display:flex;align-items:center;justify-content:space-between}.brand,.profile{display:flex;align-items:center;gap:10px}.mark,.avatar{display:grid;place-items:center;background:linear-gradient(145deg,var(--p),var(--s));font-weight:900}.mark{width:40px;height:40px;border-radius:12px}.avatar{width:38px;height:38px;border-radius:50%}.brand b{font-size:19px}.profile-copy strong{display:block;font-size:12px}.profile-copy small{font-size:8px;color:var(--muted)}.service{font-size:13px;font-weight:900;padding-left:12px;border-left:1px solid #273041}.status{height:27px;padding:0 10px;border-radius:999px;display:flex;align-items:center;gap:6px;font-size:8px;font-weight:900}.status i{width:6px;height:6px;border-radius:50%;background:currentColor}.status.on{color:#68e7a7;background:#09281b;border:1px solid #155f3e}.status.off{color:#ff9cab;background:#2b1016;border:1px solid #66303a}.page{width:min(1320px,94vw);margin:auto;padding:24px 0 56px}.traffic{display:grid;grid-template-columns:220px 1fr;gap:22px;align-items:center;min-height:148px;padding:18px 24px;border:1px solid #252c45;border-radius:19px;background:radial-gradient(circle at 92% 20%,rgba(103,77,210,.2),transparent 30%),linear-gradient(110deg,#0b0f16,#0d1018 65%,#141329)}.visual{display:flex;align-items:center;gap:16px}.donut{width:110px;height:110px;flex:0 0 110px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--orange) calc(var(--pct)*1%),#303444 0);position:relative}.donut:before{content:"";position:absolute;inset:12px;border-radius:50%;background:#0d1119}.donut div{position:relative;text-align:center}.donut b{font-size:23px}.donut small{display:block;font-size:7px;color:var(--muted)}.visual h2{font-size:17px;margin:0}.visual em{display:inline-block;margin-top:6px;font-style:normal;font-size:7px;color:#58dfa0;background:#0b3a29;padding:4px 7px;border-radius:999px}.stats{display:grid;grid-template-columns:repeat(5,1fr)}.stat{padding:0 17px;border-left:1px solid #202632}.stat:last-child{border-left:0}.stat small{font-size:8px;color:var(--muted)}.stat strong{display:block;margin-top:7px;font-size:15px}.section-head{margin:24px 0 11px}.section-head small{color:#9a78ff;font-size:8px;font-weight:900}.section-head h2{margin:3px 0 0;font-size:19px}.protocols{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}.protocol-choice{position:relative;min-height:118px;border:1px solid var(--line);border-radius:15px;background:linear-gradient(180deg,#0d1219,#0c1118);color:var(--text);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px}.protocol-choice.active{border-color:var(--p);box-shadow:0 0 0 1px color-mix(in srgb,var(--p) 20%,transparent)}.protocol-choice.active:after{content:"✓";position:absolute;top:10px;right:10px;width:21px;height:21px;border-radius:50%;display:grid;place-items:center;background:#2196df;font-size:9px}.protocol-icon{width:46px;height:46px;border-radius:50%;display:grid;place-items:center;background:var(--pc);font-weight:900}.protocol-choice b{font-size:11px}.protocol-choice small{font-size:8px;color:var(--muted)}.protocol-choice em{font-style:normal;font-size:7px;color:var(--pc);background:color-mix(in srgb,var(--pc) 9%,#0c1118);padding:2px 8px;border-radius:999px}.protocol-panel{display:none;margin-top:11px;border:1px solid var(--line);border-radius:17px;background:var(--surface);overflow:hidden}.protocol-panel.active{display:block}.panel-head{min-height:70px;padding:14px 16px;border-bottom:1px solid #1c2430;display:flex;align-items:center;justify-content:space-between;gap:18px}.panel-head h2{margin:0;font-size:15px}.panel-head small{font-size:8px;color:var(--muted)}.server-tabs{display:flex;flex-wrap:wrap;gap:7px}.server-tab{height:32px;max-width:190px;padding:0 12px;border:1px solid #384259;border-radius:9px;background:#121826;color:#9eabc0;font-size:8px;font-weight:900;display:flex;align-items:center;gap:7px}.server-tab span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.server-tab i{width:6px;height:6px;border-radius:50%;background:#31d685}.server-tab.active{border-color:#7958e9;color:#bcaaff;background:#15112a}.server-views{padding:15px}.server-view{display:none}.server-view.active{display:block}.facts{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.facts:has(.fact:nth-child(4)){grid-template-columns:repeat(4,1fr)}.fact{min-height:94px;padding:15px;border:1px solid #202a38;border-radius:12px;background:#10151d;text-align:center}.fact small{font-size:7px;color:var(--muted)}.fact strong{display:block;margin:9px 0 8px;font:700 10px ui-monospace,Consolas,monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.btn,.primary-btn{height:30px;padding:0 11px;border-radius:8px;border:1px solid #3b2f64;background:#1b1431;color:#c7b5ff;font-size:8px;font-weight:900;display:inline-flex;align-items:center;justify-content:center}.primary-btn{height:36px;background:linear-gradient(135deg,#8b5cf6,#6d28d9);color:#fff;border:0}.delivery-card{min-height:118px;padding:16px;border:1px solid #202a38;border-radius:13px;background:#10151d;display:flex;align-items:center;gap:14px}.delivery-copy{min-width:0;margin-left:auto}.server-name{display:block;font-size:14px;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.delivery-copy small{display:block;margin-top:5px;color:var(--muted);font-size:7px}.delivery-actions{display:flex;gap:7px}.qr{width:96px;height:96px;border-radius:12px;background:#fff;padding:5px}.hidden-source{display:none}.empty-state,.delivery-card.empty{padding:22px;color:var(--muted);text-align:center}.apps{margin-top:20px;border:1px solid var(--line);border-radius:18px;background:linear-gradient(180deg,#0b1017,#090d13);overflow:hidden}.apps-head{padding:16px 18px;border-bottom:1px solid #1c2430;display:flex;align-items:center;justify-content:space-between}.apps-head small{color:#9a78ff;font-size:8px;font-weight:900}.apps-head h2{margin:4px 0 0;font-size:17px}.tools{display:flex;gap:7px}.device,.allbtn{height:30px;padding:0 10px;border-radius:9px;font-size:8px;font-weight:900}.device{border:1px solid #315140;background:#0b2519;color:#65dfa1;display:flex;align-items:center}.allbtn{border:1px solid #3b2f64;background:#171225;color:#bda6ff}.platforms{padding:14px}.platform-group{display:none}.platform-group.device-active{display:block}.platform-group.show-all{display:block;margin-bottom:16px}.platform-title{display:flex;align-items:center;gap:9px;margin-bottom:12px}.platform-title>span{width:38px;height:38px;border-radius:11px;background:#182237;display:grid;place-items:center;font-size:8px;font-weight:900}.platform-title b{font-size:12px}.platform-title small{display:block;margin-top:3px;font-size:7px;color:var(--muted)}.app-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.app-card{min-height:72px;padding:10px;border:1px solid #202a38;border-radius:11px;background:#10151d;display:grid;grid-template-columns:34px 1fr;align-items:center;gap:9px}.app-card>span{width:34px;height:34px;border-radius:10px;background:#182237;display:grid;place-items:center;color:#bcaaff}.app-card b{font-size:9px}.app-card small{display:block;margin-top:4px;font-size:7px;color:var(--muted)}.app-card.uploaded{border-color:#203b30;background:#0d1814}.toast{position:fixed;left:50%;bottom:24px;transform:translate(-50%,14px);padding:9px 14px;border:1px solid #2a3342;border-radius:9px;background:#111723;color:#fff;font-size:9px;opacity:0;transition:.18s}.toast.show{opacity:1;transform:translate(-50%,0)}
@media(max-width:1050px){.traffic{grid-template-columns:1fr}.stats{grid-template-columns:repeat(5,1fr)}.protocols{grid-template-columns:repeat(3,1fr)}.app-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:760px){.top{height:auto;padding:11px 0}.topin{align-items:flex-start}.profile{flex-wrap:wrap}.page{padding-top:15px}.traffic{padding:16px}.stats{grid-template-columns:repeat(2,1fr);gap:6px}.stat{border:1px solid var(--line);border-radius:10px;padding:11px}.protocols{grid-template-columns:repeat(2,1fr)}.panel-head{align-items:flex-start;flex-direction:column}.facts,.facts:has(.fact:nth-child(4)){grid-template-columns:1fr}.delivery-card{align-items:flex-start;flex-wrap:wrap}.delivery-copy{width:100%}.apps-head{align-items:flex-start;flex-direction:column;gap:10px}.app-grid{grid-template-columns:1fr}}@media(max-width:480px){.brand b,.profile-copy{display:none}.visual{gap:10px}.donut{width:92px;height:92px;flex-basis:92px}.protocol-choice{min-height:103px}.qr{width:84px;height:84px}}
</style></head><body>
<header class="top"><div class="topin"><div class="brand"><span class="mark">__MARK__</span><b>__BRAND__</b></div><div class="profile"><span class="avatar">__AVATAR__</span><div class="profile-copy"><strong>__CUSTOMER__</strong><small>حساب کاربری</small></div><span class="service">__SERVICE__</span>__STATUS__</div></div></header>
<main class="page">
<section class="traffic"><div class="visual"><div class="donut" style="--pct:__PERCENT__"><div><b>__PERCENT_LABEL__%</b><small>مصرف شده</small></div></div><div><h2>مصرف ترافیک</h2><em>LIVE</em></div></div><div class="stats"><div class="stat"><small>مصرف‌شده</small><strong>__USED__</strong></div><div class="stat"><small>باقی‌مانده</small><strong>__REMAIN__</strong></div><div class="stat"><small>حجم کل</small><strong>__TOTAL__</strong></div><div class="stat"><small>تاریخ شروع</small><strong>__START__</strong></div><div class="stat"><small>تاریخ انقضا</small><strong>__EXPIRE__</strong></div></div></section>
<div class="section-head"><small>پروتکل‌های فعال</small><h2>انتخاب پروتکل</h2></div><section class="protocols">__PCARDS__</section><div>__PPANELS__</div>
<section class="apps" id="apps"><div class="apps-head"><div><small>APPS & DOWNLOADS</small><h2>برنامه‌های اتصال</h2></div><div class="tools"><span id="device" class="device">در حال تشخیص…</span><button id="all" class="allbtn" type="button">همه سیستم‌ها</button></div></div><div class="platforms">__APPS__</div></section>
</main><div id="toast" class="toast">کپی شد</div>
<script>(function(){var toast=document.getElementById('toast');function show(t){toast.textContent=t;toast.classList.add('show');clearTimeout(window.__t);window.__t=setTimeout(function(){toast.classList.remove('show')},1200)}function fb(t){var a=document.createElement('textarea');a.value=t;a.style.position='fixed';a.style.opacity='0';document.body.appendChild(a);a.select();var ok=false;try{ok=document.execCommand('copy')}catch(e){}a.remove();return ok}async function cp(t){if(navigator.clipboard&&window.isSecureContext){try{await navigator.clipboard.writeText(t);return true}catch(e){}}return fb(t)}document.querySelectorAll('.protocol-choice').forEach(function(b){b.onclick=function(){var id=b.dataset.protocol;document.querySelectorAll('.protocol-choice').forEach(function(x){x.classList.remove('active')});document.querySelectorAll('.protocol-panel').forEach(function(x){x.classList.remove('active')});b.classList.add('active');var p=document.getElementById(id);if(p)p.classList.add('active')}});document.querySelectorAll('.server-tab').forEach(function(b){b.onclick=function(){var p=b.closest('.protocol-panel');if(!p)return;p.querySelectorAll('.server-tab').forEach(function(x){x.classList.remove('active')});p.querySelectorAll('.server-view').forEach(function(x){x.classList.remove('active')});b.classList.add('active');var v=document.getElementById(b.dataset.server);if(v)v.classList.add('active')}});function detect(){var u=(navigator.userAgent||'').toLowerCase(),p=((navigator.userAgentData&&navigator.userAgentData.platform)||navigator.platform||'').toLowerCase();if(/android/.test(u))return'android';if(/iphone|ipad|ipod/.test(u)||(p==='macintel'&&navigator.maxTouchPoints>1))return'ios';if(/windows|win32|win64/.test(u+' '+p))return'windows';if(/macintosh|mac os|macintel/.test(u+' '+p))return'macos';if(/linux|x11|cros/.test(u+' '+p))return'linux';return'unknown'}var names={windows:'Windows',macos:'macOS',android:'Android',ios:'iPhone / iPad',linux:'Linux',unknown:'همه سیستم‌ها'},det=detect(),groups=[].slice.call(document.querySelectorAll('.platform-group'));function only(){groups.forEach(function(g){g.classList.remove('show-all');g.classList.toggle('device-active',det==='unknown'||g.dataset.platform===det)});document.getElementById('device').textContent=names[det];document.getElementById('all').textContent='همه سیستم‌ها'}only();document.getElementById('all').onclick=function(){var a=groups.some(function(g){return g.classList.contains('show-all')});if(a){only();return}groups.forEach(function(g){g.classList.remove('device-active');g.classList.add('show-all')});this.textContent='فقط دستگاه من';document.getElementById('device').textContent='همه سیستم‌ها'};document.addEventListener('click',async function(e){var b=e.target.closest('[data-copy]');if(b){show(await cp(b.dataset.copy||'')?'کپی شد':'کپی انجام نشد');return}var d=e.target.closest('.download-config');if(d){var el=document.getElementById(d.dataset.target||'');if(!el)return;var blob=new Blob([el.value||''],{type:'text/plain;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=d.dataset.filename||'config.txt';document.body.appendChild(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(url)},1000);show('دانلود آماده شد')}})})();</script></body></html>"""

    repl = {
        "__BRAND__": h(brand_name), "__MARK__": h(brand_mark), "__PRIMARY__": primary, "__SECONDARY__": secondary,
        "__SERVICE__": h(service_label), "__AVATAR__": h(avatar), "__CUSTOMER__": h(customer_name), "__STATUS__": active_badge,
        "__PERCENT__": f"{percent:.1f}", "__PERCENT_LABEL__": f"{percent:.0f}", "__USED__": h(used_label),
        "__REMAIN__": h(remaining_label), "__TOTAL__": h(total_label), "__START__": h(start_label), "__EXPIRE__": h(expires_label),
        "__PCARDS__": protocol_cards, "__PPANELS__": protocol_panels, "__APPS__": apps_html,
    }
    for key, value in repl.items():
        page = page.replace(key, value)
    return HTMLResponse(page)
