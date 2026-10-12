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
    _share_url,
    _subscription_from_share_token,
    _usage_payload,
)
from .download_assets import public_downloads_by_platform


router = APIRouter(prefix="/v1/connect", tags=["public-connection-v2"])


def h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def safe_color(value: Any, fallback: str) -> str:
    value = str(value or "").strip()
    return value if re.fullmatch(r"#[0-9A-Fa-f]{6}", value) else fallback


def protocol_meta(protocol: str) -> tuple[str, str, str, str]:
    protocol = str(protocol or "").lower()
    return {
        "cisco": ("Cisco AnyConnect", "IP + Username + Password", "C", "#27b7d6"),
        "openvpn": ("OpenVPN", "دانلود کانفیگ", "O", "#ff8a24"),
        "wireguard": ("WireGuard", "دانلود کانفیگ", "W", "#ef476f"),
        "l2tp": ("L2TP / IPsec", "IP + Username + Password + PSK", "L2TP", "#74d63f"),
        "v2ray": ("V2Ray / Xray", "دانلود کانفیگ", "V", "#7c3aed"),
        "xray": ("V2Ray / Xray", "دانلود کانفیگ", "V", "#7c3aed"),
    }.get(protocol, (protocol or "Protocol", "کانفیگ", "•", "#8b5cf6"))


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
    return f'<button class="copy-btn" type="button" data-copy="{h(text)}">{h(label)}</button>'


def fact_card(label: str, value: Any, *, copy: bool = True) -> str:
    text = str(value or "").strip() or "—"
    button = copy_button(text) if copy and text != "—" else ""
    return (
        '<article class="fact-card">'
        f'<small>{h(label)}</small>'
        f'<strong dir="ltr" title="{h(text)}">{h(text)}</strong>'
        f'{button}'
        '</article>'
    )


def live_server_name(
    item: dict[str, Any],
    node_names: dict[int, str],
    index: int,
) -> str:
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


def download_only_card(
    protocol: str,
    index: int,
    server_name: str,
    item: dict[str, Any],
) -> str:
    config = str(item.get("config") or "").strip()
    uri = str(item.get("uri") or "").strip()
    payload = config or uri

    if not payload:
        return (
            '<div class="config-only empty-config">'
            f'<div><small>سرور</small><strong>{h(server_name)}</strong></div>'
            '<span>کانفیگ این سرور هنوز آماده نشده است.</span>'
            '</div>'
        )

    source_id = f"download-source-{protocol}-{index}"
    filename = str(item.get("filename") or "").strip()
    if not filename:
        if protocol == "openvpn":
            filename = f"openvpn-{index + 1}.ovpn"
        elif protocol == "wireguard":
            filename = f"wireguard-{index + 1}.conf"
        elif protocol in {"v2ray", "xray"}:
            filename = f"v2ray-{index + 1}.txt"
        else:
            filename = f"{protocol}-{index + 1}.conf"

    kind = {
        "openvpn": "OVPN",
        "wireguard": "CONF",
        "v2ray": "V2RAY",
        "xray": "XRAY",
    }.get(protocol, "CONFIG")

    return (
        '<div class="config-only">'
        '<div class="config-only-copy">'
        '<span class="config-file-icon">↓</span>'
        f'<div><small>کانفیگ سرور</small><strong>{h(server_name)}</strong><em>{h(kind)}</em></div>'
        '</div>'
        f'<textarea id="{h(source_id)}" class="hidden-config" readonly>{h(payload)}</textarea>'
        f'<button class="download-main download-config" type="button" data-target="{h(source_id)}" data-filename="{h(filename)}">دانلود کانفیگ</button>'
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

        server_id = f"{protocol}-server-{index}"
        active = " active" if index == 0 else ""
        name = live_server_name(item, node_names, index)

        tabs.append(
            f'<button class="server-tab{active}" type="button" data-server="{h(server_id)}">'
            f'<span>{h(name)}</span><i></i></button>'
        )

        if protocol not in {"cisco", "l2tp"}:
            body = download_only_card(protocol, index, name, item)
            views.append(
                f'<div id="{h(server_id)}" class="server-view{active}">{body}</div>'
            )
            continue

        host = item.get("host") or item.get("server") or item.get("server_ip") or item.get("endpoint") or "—"
        port = item.get("port")
        username = item.get("username") or fallback_username
        password = item.get("password") or fallback_password
        psk = item.get("psk")

        if protocol == "cisco":
            server_value = f"{host}:{port}" if port else str(host)
            facts = [
                fact_card("Server & Port", server_value),
                fact_card("Username", username),
                fact_card("Password", password),
            ]
        else:
            facts = [
                fact_card("Server", host),
                fact_card("Username", username),
                fact_card("Password", password),
            ]
            if psk:
                facts.append(fact_card("PSK", psk))

        views.append(
            f'<div id="{h(server_id)}" class="server-view{active}">'
            f'<div class="facts-grid">{"".join(facts)}</div>'
            '</div>'
        )

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

    selector_cards: list[str] = []
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

        selector_cards.append(
            f'<button class="protocol-choice{active}" type="button" data-protocol="{pane_id}" style="--protocol-color:{h(color)}">'
            f'<span class="protocol-icon">{h(icon)}</span>'
            f'<b>{h(title)}</b>'
            f'<small>{h(subtitle)}</small>'
            '<em>فعال</em>'
            '</button>'
        )

        panels.append(
            f'<section id="{pane_id}" class="protocol-panel{active}">'
            '<div class="protocol-panel-head">'
            f'<div><h2>{h(title)}</h2><small>سرور را انتخاب کنید</small></div>'
            f'<div class="server-tabs">{server_tabs}</div>'
            '</div>'
            f'<div class="server-views">{server_views}</div>'
            '</section>'
        )
        pane_index += 1

    if not selector_cards:
        return '<div class="empty-state">پروتکلی برای این اشتراک ثبت نشده است.</div>', ""

    return "".join(selector_cards), "".join(panels)


def program_downloads_html(uploaded: dict[str, list[dict]]) -> str:
    groups: list[str] = []
    for platform in ("windows", "macos", "android", "ios", "linux"):
        title, icon = platform_meta(platform)
        official_items = DOWNLOADS.get(platform) or []
        upload_items = uploaded.get(platform) or []

        official_cards: list[str] = []
        for item in official_items:
            name = str(item.get("name") or "برنامه اتصال")
            url = str(item.get("url") or "#")
            official_cards.append(
                '<a class="app-card official" href="{}" target="_blank" rel="noopener noreferrer">'
                '<span class="app-logo">↗</span><div><b>{}</b><small>لینک رسمی برنامه</small></div><em>باز کردن</em>'
                '</a>'.format(h(url), h(name))
            )

        uploaded_cards: list[str] = []
        for item in upload_items:
            name = str(item.get("name") or "فایل برنامه")
            note = str(item.get("note") or "دانلود مستقیم")
            protocol = str(item.get("protocol") or "other")
            url = str(item.get("url") or "#")
            size = int(item.get("file_size") or 0)
            size_label = f"{size / 1024 / 1024:.1f} MB" if size else "فایل"
            uploaded_cards.append(
                '<a class="app-card uploaded" href="{}">'
                '<span class="app-logo">↓</span><div><b>{}</b><small>{}</small></div>'
                '<span class="asset-meta"><i>{}</i><em>{}</em></span>'
                '</a>'.format(h(url), h(name), h(note), h(protocol.upper()), h(size_label))
            )

        upload_block = ""
        if uploaded_cards:
            upload_block = (
                '<div class="apps-subsection uploaded-subsection">'
                '<div class="apps-subhead"><b>فایل‌های آپلودشده</b><span>دانلود مستقیم از سرور</span></div>'
                f'<div class="apps-grid">{"".join(uploaded_cards)}</div>'
                '</div>'
            )

        groups.append(
            f'<section class="platform-group" data-platform="{h(platform)}">'
            '<div class="platform-title">'
            f'<span class="platform-icon">{h(icon)}</span><div><b>{h(title)}</b><small>برنامه‌های مناسب این دستگاه</small></div>'
            '</div>'
            '<div class="apps-subsection">'
            '<div class="apps-subhead"><b>لینک برنامه‌ها</b><span>نسخه رسمی</span></div>'
            f'<div class="apps-grid">{"".join(official_cards)}</div>'
            '</div>'
            f'{upload_block}'
            '</section>'
        )
    return "".join(groups)


@router.get("/{token}", response_class=HTMLResponse)
def public_connection_page_v2(token: str, db: Session = Depends(get_db)):
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
    share_url = _share_url(db, sub)

    used = float(usage.get("used_gb") or 0)
    total = usage.get("total_gb")
    remaining = usage.get("remaining_gb")
    percent = max(0.0, min(100.0, float(usage.get("percent") or 0)))

    total_label = "∞" if total is None else f"{float(total or 0):.0f} GB"
    remaining_label = "∞" if remaining is None else f"{float(remaining or 0):.0f} GB"
    used_label = f"{used:.1f} GB"

    created_at = getattr(sub, "created_at", None)
    starts_at = getattr(sub, "starts_at", None) or created_at
    start_label = starts_at.strftime("%Y/%m/%d") if starts_at else "—"
    expires_at = getattr(sub, "expires_at", None)
    expires_label = expires_at.strftime("%Y/%m/%d") if expires_at else "—"

    customer_name = (
        getattr(user, "full_name", None)
        or getattr(user, "email", None)
        or "کاربر"
    ) if user else "کاربر"
    avatar = next((ch.upper() for ch in str(customer_name) if not ch.isspace()), "U")
    service_label = (username or f"SERVICE-{sub.id}").replace("_", "-").upper()

    protocol_cards, protocol_panels = render_protocols(
        payload,
        username,
        password,
        node_names,
    )
    downloads = public_downloads_by_platform(db)
    apps_html = program_downloads_html(downloads)

    active_badge = (
        '<span class="status-pill online"><i></i>اشتراک فعال</span>'
        if status == "active"
        else '<span class="status-pill offline"><i></i>اشتراک غیرفعال</span>'
    )

    subscription_bar = (
        '<section class="subscription-bar">'
        '<div class="subscription-copy"><small>لینک اشتراک</small>'
        f'<code dir="ltr" title="{h(share_url)}">{h(share_url)}</code></div>'
        '<div class="subscription-actions">'
        f'{copy_button(share_url, "کپی لینک")}'
        f'<a class="action-btn" href="{h(share_url)}" target="_blank" rel="noopener noreferrer">باز کردن</a>'
        '</div></section>'
    )

    page = """<!doctype html>
<html lang="fa" dir="rtl" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light">
<title>__BRAND_NAME__ · __SERVICE_LABEL__</title>
<style>
:root{--bg:#05070b;--header:#050609;--surface:#0b1017;--surface-2:#101722;--surface-3:#151e2b;--line:#202a39;--line-soft:#182131;--text:#f4f7fb;--muted:#7e8ba0;--primary:__PRIMARY__;--secondary:__SECONDARY__;--success:#29d37d;--danger:#f05268;--orange:#ff9f43;--shadow:0 18px 55px rgba(0,0,0,.24)}
*{box-sizing:border-box}html{background:var(--bg)}body{margin:0;min-height:100vh;background:var(--bg);color:var(--text);font-family:Tahoma,Arial,sans-serif;-webkit-font-smoothing:antialiased}button,a,textarea{font:inherit}button{cursor:pointer}a{color:inherit;text-decoration:none}
.topbar{height:72px;border-bottom:1px solid #171c25;background:rgba(4,6,9,.97);display:flex;align-items:center;position:sticky;top:0;z-index:30;backdrop-filter:blur(14px)}.topbar-inner{width:min(1320px,94vw);margin:auto;display:flex;align-items:center;justify-content:space-between;gap:20px}.brand{display:flex;align-items:center;gap:10px;font-size:19px;font-weight:900}.brand-mark{width:40px;height:40px;border-radius:12px;display:grid;place-items:center;background:linear-gradient(145deg,var(--primary),var(--secondary));box-shadow:0 10px 28px color-mix(in srgb,var(--primary) 28%,transparent)}.profile{display:flex;align-items:center;gap:11px;direction:rtl}.profile-avatar{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;background:linear-gradient(145deg,#8d62ff,#6845e5);font-weight:900}.profile-copy{display:grid;gap:2px}.profile-copy strong{font-size:12px}.profile-copy small{font-size:8px;color:var(--muted)}.service-name{font-size:13px;font-weight:900;padding-left:13px;border-left:1px solid #272f3d}.status-pill{height:27px;padding:0 10px;border-radius:999px;display:inline-flex;align-items:center;gap:6px;font-size:8px;font-weight:900}.status-pill i{width:6px;height:6px;border-radius:50%;background:currentColor}.status-pill.online{color:#68e7a7;background:#09281b;border:1px solid #155f3e}.status-pill.offline{color:#ff8fa0;background:#2b1016;border:1px solid #66303a}.theme-btn{width:37px;height:37px;border:1px solid var(--line);border-radius:11px;background:#111722;color:var(--text)}
.page{width:min(1320px,94vw);margin:0 auto;padding:24px 0 58px}.traffic-card{position:relative;overflow:hidden;display:grid;grid-template-columns:220px minmax(0,1fr);align-items:center;gap:24px;min-height:148px;padding:17px 24px;border:1px solid #252c45;border-radius:19px;background:radial-gradient(circle at 92% 20%,rgba(103,77,210,.19),transparent 30%),linear-gradient(110deg,#0b0f16,#0d1018 64%,#141329);box-shadow:var(--shadow)}.traffic-card:after{content:"";position:absolute;inset:auto 22px 20px 22px;height:3px;border-radius:999px;background:linear-gradient(90deg,rgba(124,58,237,.04),rgba(124,58,237,.22),rgba(41,211,125,.06))}.traffic-visual{display:flex;align-items:center;gap:16px;min-width:0}.donut{--size:110px;flex:0 0 var(--size);width:var(--size);height:var(--size);aspect-ratio:1;border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--orange) calc(var(--percent)*1%),#303444 0);position:relative;box-shadow:inset 0 0 0 1px rgba(255,255,255,.03)}.donut:before{content:"";position:absolute;inset:12px;border-radius:50%;background:#0d1119;box-shadow:inset 0 0 0 1px #242b38}.donut-center{position:relative;text-align:center;z-index:1}.donut-center b{display:block;font-size:23px}.donut-center small{display:block;color:var(--muted);font-size:7px;margin-top:3px}.traffic-title{min-width:0}.traffic-title h2{margin:0;font-size:17px;white-space:nowrap}.traffic-title small{display:inline-flex;margin-top:6px;padding:4px 7px;border-radius:999px;background:#0b3a29;color:#58dfa0;font-size:7px;font-weight:900}.traffic-stats{display:grid;grid-template-columns:repeat(5,minmax(90px,1fr));align-items:center;height:88px}.traffic-stat{height:60px;padding:0 17px;border-left:1px solid #202632;display:flex;flex-direction:column;justify-content:center}.traffic-stat:last-child{border-left:0}.traffic-stat small{color:var(--muted);font-size:8px}.traffic-stat strong{margin-top:7px;font-size:15px;white-space:nowrap}
.section-head{display:flex;justify-content:space-between;align-items:end;margin:24px 0 11px}.section-head small{display:block;color:#9a78ff;font-size:8px;font-weight:900;margin-bottom:4px}.section-head h2{margin:0;font-size:19px}.section-head p{margin:4px 0 0;color:var(--muted);font-size:8px}.protocol-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px}.protocol-choice{position:relative;min-height:118px;padding:13px;border:1px solid var(--line);border-radius:15px;background:linear-gradient(180deg,#0d1219,#0c1118);color:var(--text);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;transition:.18s ease;box-shadow:0 12px 28px rgba(0,0,0,.11)}.protocol-choice:hover{transform:translateY(-2px);border-color:#3b4557}.protocol-choice.active{border-color:color-mix(in srgb,var(--primary) 78%,#fff 0%);box-shadow:0 0 0 1px color-mix(in srgb,var(--primary) 20%,transparent),0 14px 34px rgba(0,0,0,.2)}.protocol-choice.active:after{content:"✓";position:absolute;top:10px;right:10px;width:21px;height:21px;border-radius:50%;display:grid;place-items:center;background:#2196df;color:#fff;font-size:9px}.protocol-icon{width:46px;height:46px;border-radius:50%;display:grid;place-items:center;background:var(--protocol-color);color:#fff;font-size:12px;font-weight:900;box-shadow:0 8px 18px color-mix(in srgb,var(--protocol-color) 25%,transparent)}.protocol-choice b{font-size:11px}.protocol-choice small{font-size:8px;color:var(--muted)}.protocol-choice em{font-style:normal;font-size:7px;font-weight:900;color:var(--protocol-color);padding:2px 8px;border-radius:999px;background:color-mix(in srgb,var(--protocol-color) 9%,#0c1118)}
.protocol-panels{margin-top:11px}.protocol-panel{display:none;border:1px solid var(--line);border-radius:17px;background:#0b1017;overflow:hidden}.protocol-panel.active{display:block}.protocol-panel-head{min-height:70px;padding:14px 16px;border-bottom:1px solid #1c2430;display:flex;align-items:center;justify-content:space-between;gap:18px}.protocol-panel-head h2{margin:0;font-size:15px}.protocol-panel-head small{display:block;margin-top:4px;color:var(--muted);font-size:8px}.server-tabs{display:flex;flex-wrap:wrap;gap:7px;justify-content:flex-start}.server-tab{height:32px;min-width:68px;max-width:190px;padding:0 12px;border:1px solid #384259;border-radius:9px;background:#121826;color:#9eabc0;font-size:8px;font-weight:900;display:inline-flex;align-items:center;gap:7px}.server-tab span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.server-tab i{width:6px;height:6px;flex:0 0 6px;border-radius:50%;background:#31d685}.server-tab.active{border-color:#7958e9;color:#bcaaff;background:#15112a}.server-views{padding:15px}.server-view{display:none}.server-view.active{display:block}.facts-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.facts-grid:has(.fact-card:nth-child(4)){grid-template-columns:repeat(4,minmax(0,1fr))}.fact-card{position:relative;min-height:94px;padding:15px 14px 12px;border:1px solid #202a38;border-radius:12px;background:#10151d;text-align:center;overflow:hidden}.fact-card:before{content:"";position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,transparent,color-mix(in srgb,var(--primary) 48%,transparent),transparent);opacity:.5}.fact-card small{display:block;color:#7e8ba0;font-size:7px}.fact-card strong{display:block;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin:9px 0 8px;font:700 10px ui-monospace,SFMono-Regular,Consolas,monospace;color:#f7f8fb}.copy-btn,.action-btn{height:28px;padding:0 10px;border:1px solid #3b2f64;border-radius:8px;background:#1b1431;color:#bda6ff;font-size:8px;font-weight:900;display:inline-flex;align-items:center;justify-content:center}.copy-btn:hover,.action-btn:hover{border-color:#7150d5;background:#241943}.config-only{min-height:92px;padding:14px 15px;border:1px solid #202a38;border-radius:13px;background:linear-gradient(120deg,#10151d,#0c121a);display:flex;align-items:center;justify-content:space-between;gap:16px}.config-only-copy{display:flex;align-items:center;gap:12px;min-width:0}.config-file-icon{width:44px;height:44px;flex:0 0 44px;border-radius:12px;display:grid;place-items:center;background:linear-gradient(145deg,#231a45,#17132a);border:1px solid #40336c;color:#bda6ff;font-size:18px}.config-only small{display:block;color:var(--muted);font-size:7px}.config-only strong{display:block;margin-top:4px;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:420px}.config-only em{display:inline-block;margin-top:5px;padding:2px 7px;border-radius:999px;background:#151d2a;color:#8090a8;font-style:normal;font-size:6px}.hidden-config{position:absolute!important;width:1px!important;height:1px!important;opacity:0!important;pointer-events:none!important}.download-main{height:38px;padding:0 17px;border:1px solid #684dd2;border-radius:10px;background:linear-gradient(135deg,var(--primary),var(--secondary));color:#fff;font-size:9px;font-weight:900;box-shadow:0 8px 22px color-mix(in srgb,var(--primary) 18%,transparent)}.empty-config span{color:var(--muted);font-size:8px}
.subscription-bar{margin-top:11px;min-height:58px;padding:9px 11px;border:1px solid var(--line);border-radius:13px;background:#0b1017;display:flex;align-items:center;justify-content:space-between;gap:14px}.subscription-copy{min-width:0;display:grid;gap:4px}.subscription-copy small{color:var(--muted);font-size:7px}.subscription-copy code{max-width:760px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font:9px ui-monospace,SFMono-Regular,Consolas,monospace}.subscription-actions{display:flex;gap:6px;flex:0 0 auto}
.apps-card{margin-top:20px;border:1px solid var(--line);border-radius:18px;background:linear-gradient(180deg,#0b1017,#090d13);overflow:hidden}.apps-head{padding:16px 18px;border-bottom:1px solid #1c2430;display:flex;align-items:center;justify-content:space-between;gap:16px}.apps-head small{display:block;color:#9a78ff;font-size:8px;font-weight:900;margin-bottom:4px}.apps-head h2{margin:0;font-size:17px}.apps-head p{margin:4px 0 0;color:var(--muted);font-size:8px}.device-tools{display:flex;align-items:center;gap:7px}.device-badge{height:30px;padding:0 10px;border:1px solid #315140;border-radius:9px;background:#0b2519;color:#65dfa1;display:flex;align-items:center;font-size:8px;font-weight:900}.show-all-apps{height:30px;padding:0 10px;border:1px solid #3b2f64;border-radius:9px;background:#171225;color:#bda6ff;font-size:8px;font-weight:900}.platform-groups{padding:14px}.platform-group{display:none}.platform-group.device-active{display:block}.platform-group.show-all{display:block;margin-bottom:16px}.platform-group.show-all:last-child{margin-bottom:0}.platform-title{display:flex;align-items:center;gap:9px;margin-bottom:12px}.platform-icon{width:38px;height:38px;border-radius:11px;background:linear-gradient(145deg,#1c2640,#121a2b);border:1px solid #2a3750;display:grid;place-items:center;color:#c9d6ef;font-size:8px;font-weight:900}.platform-title b{display:block;font-size:12px}.platform-title small{display:block;margin-top:3px;color:var(--muted);font-size:7px}.apps-subsection+.apps-subsection{margin-top:14px;padding-top:14px;border-top:1px dashed #222c3a}.apps-subhead{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}.apps-subhead b{font-size:9px}.apps-subhead span{color:var(--muted);font-size:7px}.apps-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.app-card{min-height:72px;padding:10px;border:1px solid #202a38;border-radius:11px;background:#10151d;display:grid;grid-template-columns:34px minmax(0,1fr) auto;align-items:center;gap:9px;transition:.16s}.app-card:hover{border-color:#46546d;transform:translateY(-1px)}.app-logo{width:34px;height:34px;border-radius:10px;background:#182237;display:grid;place-items:center;color:#bcaaff;font-weight:900}.app-card b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:9px}.app-card small{display:block;margin-top:4px;color:var(--muted);font-size:7px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.app-card>em{font-style:normal;color:#bcaaff;font-size:7px;white-space:nowrap}.app-card.uploaded{border-color:#203b30;background:#0d1814}.app-card.uploaded .app-logo{background:#123022;color:#62dca0}.asset-meta{display:grid;gap:3px;text-align:left}.asset-meta i,.asset-meta em{font-style:normal;font-size:6px;white-space:nowrap}.asset-meta i{color:#62dca0}.asset-meta em{color:var(--muted)}
.toast{position:fixed;left:50%;bottom:24px;transform:translate(-50%,14px);padding:9px 14px;border:1px solid #2a3342;border-radius:9px;background:#111723;color:#fff;font-size:9px;opacity:0;pointer-events:none;transition:.18s;z-index:99}.toast.show{opacity:1;transform:translate(-50%,0)}
html[data-theme="light"]{--bg:#f5f7fb;--header:#fff;--surface:#fff;--surface-2:#f8faff;--surface-3:#eef2f8;--line:#dfe5ef;--line-soft:#edf1f6;--text:#182033;--muted:#738098}html[data-theme="light"] body{background:#f5f7fb}html[data-theme="light"] .topbar{background:rgba(255,255,255,.96);border-color:#e6ebf2}html[data-theme="light"] .traffic-card{background:linear-gradient(110deg,#fff,#faf9ff);border-color:#ddd8f2}html[data-theme="light"] .donut:before{background:#fff}html[data-theme="light"] .protocol-choice,html[data-theme="light"] .protocol-panel,html[data-theme="light"] .fact-card,html[data-theme="light"] .config-only,html[data-theme="light"] .subscription-bar,html[data-theme="light"] .apps-card,html[data-theme="light"] .app-card{background:#fff}html[data-theme="light"] .fact-card strong{color:#182033}html[data-theme="light"] .app-card.uploaded{background:#f4fff8}
@media(max-width:1100px){.traffic-card{grid-template-columns:1fr}.traffic-visual{justify-content:center}.traffic-stats{grid-template-columns:repeat(5,1fr);width:100%}.protocol-grid{grid-template-columns:repeat(3,1fr)}.facts-grid,.facts-grid:has(.fact-card:nth-child(4)){grid-template-columns:repeat(2,1fr)}.apps-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:760px){.topbar{height:auto;padding:11px 0}.topbar-inner{align-items:flex-start}.profile{flex-wrap:wrap}.service-name{border-left:0}.page{padding-top:15px}.traffic-card{padding:16px}.traffic-visual{justify-content:flex-start}.traffic-stats{grid-template-columns:repeat(2,1fr);height:auto;gap:6px}.traffic-stat{border:1px solid var(--line);border-radius:10px;height:58px;padding:0 11px}.protocol-grid{grid-template-columns:repeat(2,1fr)}.protocol-panel-head{align-items:flex-start;flex-direction:column}.server-tabs{justify-content:flex-start}.facts-grid,.facts-grid:has(.fact-card:nth-child(4)){grid-template-columns:1fr}.config-only{align-items:flex-start;flex-direction:column}.download-main{width:100%}.subscription-bar,.apps-head{align-items:flex-start;flex-direction:column}.subscription-copy code{max-width:80vw}.apps-grid{grid-template-columns:1fr}.device-tools{width:100%;justify-content:space-between}}
@media(max-width:480px){.brand span:last-of-type{display:none}.profile-copy{display:none}.protocol-grid{grid-template-columns:1fr 1fr;gap:8px}.protocol-choice{min-height:103px}.traffic-visual{flex-direction:row}.donut{--size:92px}.traffic-title h2{font-size:15px}}
</style>
</head>
<body>
<header class="topbar">
  <div class="topbar-inner">
    <div class="brand"><span class="brand-mark">__BRAND_MARK__</span><span>__BRAND_NAME__</span><button id="themeBtn" class="theme-btn" type="button">☀</button></div>
    <div class="profile">
      <span class="profile-avatar">__AVATAR__</span>
      <div class="profile-copy"><strong>__CUSTOMER_NAME__</strong><small>حساب کاربری</small></div>
      <span class="service-name">__SERVICE_LABEL__</span>
      __ACTIVE_BADGE__
    </div>
  </div>
</header>
<main class="page">
  <section class="traffic-card">
    <div class="traffic-visual">
      <div class="donut" style="--percent:__PERCENT__"><div class="donut-center"><b>__PERCENT_LABEL__%</b><small>مصرف شده</small></div></div>
      <div class="traffic-title"><h2>مصرف ترافیک</h2><small>LIVE</small></div>
    </div>
    <div class="traffic-stats">
      <div class="traffic-stat"><small>مصرف‌شده</small><strong>__USED__</strong></div>
      <div class="traffic-stat"><small>باقی‌مانده</small><strong>__REMAINING__</strong></div>
      <div class="traffic-stat"><small>حجم کل</small><strong>__TOTAL__</strong></div>
      <div class="traffic-stat"><small>تاریخ شروع</small><strong>__START__</strong></div>
      <div class="traffic-stat"><small>تاریخ انقضا</small><strong>__EXPIRES__</strong></div>
    </div>
  </section>

  <div class="section-head">
    <div><small>پروتکل‌های فعال</small><h2>انتخاب پروتکل</h2><p>پروتکل را انتخاب کن تا اطلاعات همان اتصال نمایش داده شود.</p></div>
  </div>
  <section class="protocol-grid">__PROTOCOL_CARDS__</section>
  <div class="protocol-panels">__PROTOCOL_PANELS__</div>
  __SUBSCRIPTION_BAR__

  <section class="apps-card" id="appsSection">
    <div class="apps-head">
      <div><small>APPS & DOWNLOADS</small><h2>برنامه‌های اتصال</h2><p>برنامه مناسب دستگاه شما به‌صورت خودکار نمایش داده می‌شود.</p></div>
      <div class="device-tools"><span id="deviceBadge" class="device-badge">در حال تشخیص دستگاه…</span><button id="showAllApps" class="show-all-apps" type="button">همه سیستم‌ها</button></div>
    </div>
    <div class="platform-groups">__APPS_HTML__</div>
  </section>
</main>
<div id="toast" class="toast">کپی شد</div>
<script>
(function(){
  var root=document.documentElement;
  var toast=document.getElementById('toast');
  try{var saved=localStorage.getItem('twinpanel.connect.theme');if(saved)root.dataset.theme=saved;}catch(e){}
  document.getElementById('themeBtn').addEventListener('click',function(){var next=root.dataset.theme==='light'?'dark':'light';root.dataset.theme=next;try{localStorage.setItem('twinpanel.connect.theme',next)}catch(e){}});

  function showToast(text){toast.textContent=text;toast.classList.add('show');clearTimeout(window.__tpToast);window.__tpToast=setTimeout(function(){toast.classList.remove('show')},1200)}
  function fallbackCopy(text){var ta=document.createElement('textarea');ta.value=text;ta.setAttribute('readonly','');ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();ta.setSelectionRange(0,ta.value.length);var ok=false;try{ok=document.execCommand('copy')}catch(e){}ta.remove();return ok}
  async function copyText(text){if(navigator.clipboard&&window.isSecureContext){try{await navigator.clipboard.writeText(text);return true}catch(e){}}return fallbackCopy(text)}

  document.querySelectorAll('.protocol-choice').forEach(function(btn){btn.addEventListener('click',function(){var id=btn.getAttribute('data-protocol');document.querySelectorAll('.protocol-choice').forEach(function(x){x.classList.remove('active')});document.querySelectorAll('.protocol-panel').forEach(function(x){x.classList.remove('active')});btn.classList.add('active');var pane=document.getElementById(id);if(pane)pane.classList.add('active')})});
  document.querySelectorAll('.server-tab').forEach(function(btn){btn.addEventListener('click',function(){var panel=btn.closest('.protocol-panel');if(!panel)return;var id=btn.getAttribute('data-server');panel.querySelectorAll('.server-tab').forEach(function(x){x.classList.remove('active')});panel.querySelectorAll('.server-view').forEach(function(x){x.classList.remove('active')});btn.classList.add('active');var view=document.getElementById(id);if(view)view.classList.add('active')})});

  function detectPlatform(){
    var ua=(navigator.userAgent||'').toLowerCase();
    var platform=((navigator.userAgentData&&navigator.userAgentData.platform)||navigator.platform||'').toLowerCase();
    if(/android/.test(ua))return 'android';
    if(/iphone|ipad|ipod/.test(ua)||(platform==='macintel'&&navigator.maxTouchPoints>1))return 'ios';
    if(/windows|win32|win64/.test(ua+' '+platform))return 'windows';
    if(/macintosh|mac os|macintel/.test(ua+' '+platform))return 'macos';
    if(/linux|x11|cros/.test(ua+' '+platform))return 'linux';
    return 'unknown';
  }
  var platformNames={windows:'Windows',macos:'macOS',android:'Android',ios:'iPhone / iPad',linux:'Linux',unknown:'دستگاه نامشخص'};
  var detected=detectPlatform();
  var groups=[].slice.call(document.querySelectorAll('.platform-group'));
  function showDetected(){groups.forEach(function(g){g.classList.remove('show-all');g.classList.toggle('device-active',detected==='unknown'||g.getAttribute('data-platform')===detected)});document.getElementById('deviceBadge').textContent=detected==='unknown'?'همه سیستم‌ها':platformNames[detected];document.getElementById('showAllApps').textContent='همه سیستم‌ها'}
  showDetected();
  document.getElementById('showAllApps').addEventListener('click',function(){var isAll=groups.some(function(g){return g.classList.contains('show-all')});if(isAll){showDetected();return}groups.forEach(function(g){g.classList.remove('device-active');g.classList.add('show-all')});this.textContent='فقط دستگاه من';document.getElementById('deviceBadge').textContent='همه سیستم‌ها'});

  document.addEventListener('click',async function(ev){
    var copy=ev.target.closest('[data-copy]');
    if(copy){var ok=await copyText(copy.getAttribute('data-copy')||'');showToast(ok?'کپی شد':'کپی انجام نشد');return}
    var dl=ev.target.closest('.download-config');
    if(dl){var el=document.getElementById(dl.getAttribute('data-target')||'');if(!el)return;var blob=new Blob([el.value||el.textContent||''],{type:'text/plain;charset=utf-8'});var url=URL.createObjectURL(blob);var a=document.createElement('a');a.href=url;a.download=dl.getAttribute('data-filename')||'config.txt';document.body.appendChild(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(url)},1000);showToast('دانلود آماده شد')}
  });
})();
</script>
</body>
</html>"""

    replacements = {
        "__BRAND_NAME__": h(brand_name),
        "__BRAND_MARK__": h(brand_mark),
        "__PRIMARY__": primary,
        "__SECONDARY__": secondary,
        "__SERVICE_LABEL__": h(service_label),
        "__AVATAR__": h(avatar),
        "__CUSTOMER_NAME__": h(customer_name),
        "__ACTIVE_BADGE__": active_badge,
        "__PERCENT__": f"{percent:.1f}",
        "__PERCENT_LABEL__": f"{percent:.0f}",
        "__USED__": h(used_label),
        "__REMAINING__": h(remaining_label),
        "__TOTAL__": h(total_label),
        "__START__": h(start_label),
        "__EXPIRES__": h(expires_label),
        "__PROTOCOL_CARDS__": protocol_cards,
        "__PROTOCOL_PANELS__": protocol_panels,
        "__SUBSCRIPTION_BAR__": subscription_bar,
        "__APPS_HTML__": apps_html,
    }
    for key, value in replacements.items():
        page = page.replace(key, value)

    return HTMLResponse(page)
