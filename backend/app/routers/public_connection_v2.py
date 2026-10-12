from __future__ import annotations

import html
import re
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..branding_models import BrandingSettings
from ..database import get_db
from ..models import User
from .account_delivery import (
    _public_payload,
    _share_url,
    _subscription_from_share_token,
    _usage_payload,
)


router = APIRouter(prefix="/v1/connect", tags=["public-connection-v2"])


def h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def safe_color(value: Any, fallback: str) -> str:
    value = str(value or "").strip()
    return value if re.fullmatch(r"#[0-9A-Fa-f]{6}", value) else fallback


def protocol_meta(protocol: str) -> tuple[str, str, str, str]:
    protocol = str(protocol or "").lower()
    return {
        "cisco": ("Cisco AnyConnect", "OpenConnect", "C", "#27b7d6"),
        "openvpn": ("OpenVPN", "فایل آماده", "O", "#ff8a24"),
        "wireguard": ("WireGuard", "فایل + QR", "W", "#ef476f"),
        "l2tp": ("L2TP / IPsec", "IPsec", "L2TP", "#74d63f"),
        "v2ray": ("V2Ray / Xray", "لینک + QR", "V", "#7c3aed"),
        "xray": ("V2Ray / Xray", "لینک + QR", "V", "#7c3aed"),
    }.get(protocol, (protocol or "Protocol", "اتصال", "•", "#8b5cf6"))


def copy_button(value: Any, label: str = "کپی") -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return f'<button class="copy-btn" type="button" data-copy="{h(text)}">{h(label)}</button>'


def fact_card(label: str, value: Any, *, copy: bool = True) -> str:
    text = str(value or "").strip()
    if not text:
        text = "—"
    button = copy_button(text) if copy and text != "—" else ""
    return (
        '<article class="fact-card">'
        f'<small>{h(label)}</small>'
        f'<strong dir="ltr" title="{h(text)}">{h(text)}</strong>'
        f'{button}'
        '</article>'
    )


def connection_views(
    protocol: str,
    items: list[dict[str, Any]],
    fallback_username: str,
    fallback_password: str,
) -> tuple[str, str]:
    tabs: list[str] = []
    views: list[str] = []

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            item = {}

        server_id = f"{protocol}-server-{index}"
        active = " active" if index == 0 else ""
        name = (
            item.get("name")
            or item.get("label")
            or item.get("country")
            or item.get("location")
            or f"سرور {index + 1}"
        )
        tabs.append(
            f'<button class="server-tab{active}" type="button" data-server="{h(server_id)}">'
            f'{h(name)}<i></i></button>'
        )

        host = item.get("host") or item.get("server") or item.get("endpoint") or "—"
        port = item.get("port") or "—"
        server_port = f"{host}:{port}" if host != "—" and port != "—" else host
        username = item.get("username") or fallback_username
        password = item.get("password") or fallback_password
        psk = item.get("psk")
        uri = str(item.get("uri") or "").strip()
        config = str(item.get("config") or "").strip()
        qr = str(item.get("qr") or "").strip()

        facts = [
            fact_card("Server & Port", server_port),
            fact_card("Username", username),
            fact_card("Password", password),
        ]
        if psk:
            facts.append(fact_card("PSK", psk))

        extra_actions: list[str] = []
        if uri:
            extra_actions.append(copy_button(uri, "کپی لینک"))
            extra_actions.append(
                f'<a class="action-btn" href="{h(uri)}" target="_blank" rel="noopener noreferrer">باز کردن لینک</a>'
            )

        details = ""
        if config:
            config_id = f"config-{protocol}-{index}"
            filename = f"{protocol}-{index + 1}.conf"
            if protocol == "openvpn":
                filename = f"openvpn-{index + 1}.ovpn"
            elif protocol == "wireguard":
                filename = f"wireguard-{index + 1}.conf"
            details = (
                '<details class="config-drawer">'
                '<summary>کانفیگ سرور</summary>'
                f'<textarea id="{h(config_id)}" readonly dir="ltr">{h(config)}</textarea>'
                '<div class="drawer-actions">'
                f'<button class="action-btn copy-target" type="button" data-target="{h(config_id)}">کپی کانفیگ</button>'
                f'<button class="action-btn download-config" type="button" data-target="{h(config_id)}" data-filename="{h(filename)}">دانلود فایل</button>'
                '</div></details>'
            )

        qr_html = f'<img class="server-qr" src="{h(qr)}" alt="QR">' if qr else ""

        views.append(
            f'<div id="{h(server_id)}" class="server-view{active}">'
            f'<div class="facts-grid">{"".join(facts)}</div>'
            f'<div class="server-footer"><div class="inline-actions">{"".join(extra_actions)}</div>{qr_html}</div>'
            f'{details}'
            '</div>'
        )

    if not items:
        return "", '<div class="empty-state">اطلاعات این پروتکل هنوز آماده نشده است.</div>'
    return "".join(tabs), "".join(views)


def render_protocols(
    payload: dict[str, Any],
    fallback_username: str,
    fallback_password: str,
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
            f'<div><h2>{h(title)}</h2><small>جزئیات اتصال</small></div>'
            f'<div class="server-tabs">{server_tabs}</div>'
            '</div>'
            f'<div class="server-views">{server_views}</div>'
            '</section>'
        )
        pane_index += 1

    if not selector_cards:
        return '<div class="empty-state">پروتکلی برای این اشتراک ثبت نشده است.</div>', ""

    return "".join(selector_cards), "".join(panels)


@router.get("/{token}", response_class=HTMLResponse)
def public_connection_page_v2(token: str, db: Session = Depends(get_db)):
    sub = _subscription_from_share_token(token, db)
    payload = _public_payload(db, sub)
    usage = _usage_payload(db, sub)
    user = db.get(User, sub.user_id)
    branding = db.query(BrandingSettings).first()

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

    protocol_cards, protocol_panels = render_protocols(payload, username, password)

    active_badge = (
        '<span class="status-pill online"><i></i>اشتراک فعال</span>'
        if status == "active"
        else '<span class="status-pill offline"><i></i>اشتراک غیرفعال</span>'
    )

    page = f'''<!doctype html>
<html lang="fa" dir="rtl" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light">
<title>{h(brand_name)} · {h(service_label)}</title>
<style>
:root{{--bg:#05070b;--header:#050609;--surface:#0b1017;--surface-2:#101722;--surface-3:#151e2b;--line:#202a39;--line-soft:#182131;--text:#f4f7fb;--muted:#7e8ba0;--primary:{primary};--secondary:{secondary};--success:#29d37d;--danger:#f05268;--orange:#ff9f43;--shadow:0 22px 70px rgba(0,0,0,.28)}}
*{{box-sizing:border-box}}html{{background:var(--bg)}}body{{margin:0;min-height:100vh;background:var(--bg);color:var(--text);font-family:Tahoma,Arial,sans-serif;-webkit-font-smoothing:antialiased}}button,a,textarea{{font:inherit}}button{{cursor:pointer}}a{{color:inherit;text-decoration:none}}
.topbar{{height:78px;border-bottom:1px solid #171c25;background:rgba(4,6,9,.96);display:flex;align-items:center}}.topbar-inner{{width:min(1400px,94vw);margin:auto;display:flex;align-items:center;justify-content:space-between;gap:24px}}.brand{{display:flex;align-items:center;gap:12px;font-size:20px;font-weight:900;letter-spacing:-.02em}}.brand-mark{{width:42px;height:42px;border-radius:12px;display:grid;place-items:center;background:linear-gradient(145deg,var(--primary),var(--secondary));box-shadow:0 10px 30px color-mix(in srgb,var(--primary) 28%,transparent)}}.profile{{display:flex;align-items:center;gap:12px;direction:rtl}}.profile-avatar{{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;background:linear-gradient(145deg,#8d62ff,#6845e5);font-weight:900}}.profile-copy{{display:grid;gap:2px}}.profile-copy strong{{font-size:12px}}.profile-copy small{{font-size:8px;color:var(--muted)}}.service-name{{font-size:14px;font-weight:900;padding-left:14px;border-left:1px solid #272f3d}}.status-pill{{height:28px;padding:0 11px;border-radius:999px;display:inline-flex;align-items:center;gap:6px;font-size:9px;font-weight:900}}.status-pill i{{width:6px;height:6px;border-radius:50%;background:currentColor}}.status-pill.online{{color:#68e7a7;background:#09281b;border:1px solid #155f3e}}.status-pill.offline{{color:#ff8fa0;background:#2b1016;border:1px solid #66303a}}.theme-btn{{width:38px;height:38px;border:1px solid var(--line);border-radius:11px;background:#111722;color:var(--text)}}
.page{{width:min(1400px,94vw);margin:0 auto;padding:28px 0 60px}}.traffic-card{{position:relative;overflow:hidden;display:grid;grid-template-columns:190px minmax(0,1fr);align-items:center;gap:28px;min-height:160px;padding:18px 28px;border:1px solid #252c45;border-radius:20px;background:radial-gradient(circle at 92% 20%,rgba(103,77,210,.20),transparent 30%),linear-gradient(110deg,#0b0f16,#0d1018 64%,#141329);box-shadow:var(--shadow)}}.traffic-card:after{{content:"";position:absolute;inset:auto 24px 24px 24px;height:4px;border-radius:999px;background:linear-gradient(90deg,rgba(124,58,237,.05),rgba(124,58,237,.22),rgba(41,211,125,.06))}}.traffic-visual{{display:flex;align-items:center;gap:18px}}.donut{{--size:126px;width:var(--size);height:var(--size);border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--orange) calc(var(--percent)*1%),#303444 0);position:relative;box-shadow:inset 0 0 0 1px rgba(255,255,255,.03)}}.donut:before{{content:"";position:absolute;inset:14px;border-radius:50%;background:#0d1119;box-shadow:inset 0 0 0 1px #242b38}}.donut-center{{position:relative;text-align:center;z-index:1}}.donut-center b{{display:block;font-size:26px}}.donut-center small{{display:block;color:var(--muted);font-size:8px;margin-top:3px}}.traffic-title{{min-width:140px}}.traffic-title h2{{margin:0;font-size:18px}}.traffic-title small{{display:inline-flex;margin-top:6px;padding:4px 7px;border-radius:999px;background:#0b3a29;color:#58dfa0;font-size:7px;font-weight:900}}.traffic-stats{{display:grid;grid-template-columns:repeat(5,minmax(100px,1fr));align-items:center;height:92px}}.traffic-stat{{height:64px;padding:0 22px;border-left:1px solid #202632;display:flex;flex-direction:column;justify-content:center}}.traffic-stat:last-child{{border-left:0}}.traffic-stat small{{color:var(--muted);font-size:8px}}.traffic-stat strong{{margin-top:8px;font-size:17px}}
.section-head{{display:flex;justify-content:space-between;align-items:end;margin:28px 0 12px}}.section-head small{{display:block;color:#9a78ff;font-size:8px;font-weight:900;margin-bottom:4px}}.section-head h2{{margin:0;font-size:20px}}.section-head p{{margin:4px 0 0;color:var(--muted);font-size:8px}}.mini-menu{{width:36px;height:36px;border:1px solid #31244f;border-radius:10px;background:#151027;color:#9c7cff;font-size:17px}}.protocol-grid{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px}}.protocol-choice{{position:relative;min-height:122px;padding:14px;border:1px solid var(--line);border-radius:15px;background:linear-gradient(180deg,#0d1219,#0c1118);color:var(--text);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:7px;transition:.18s ease;box-shadow:0 12px 30px rgba(0,0,0,.12)}}.protocol-choice:hover{{transform:translateY(-2px);border-color:#3b4557}}.protocol-choice.active{{border-color:color-mix(in srgb,var(--primary) 78%,#fff 0%);box-shadow:0 0 0 1px color-mix(in srgb,var(--primary) 20%,transparent),0 14px 38px rgba(0,0,0,.2)}}.protocol-choice.active:after{{content:"✓";position:absolute;top:10px;right:10px;width:22px;height:22px;border-radius:50%;display:grid;place-items:center;background:#2196df;color:#fff;font-size:10px}}.protocol-icon{{width:48px;height:48px;border-radius:50%;display:grid;place-items:center;background:var(--protocol-color);color:#fff;font-size:13px;font-weight:900;box-shadow:0 8px 18px color-mix(in srgb,var(--protocol-color) 25%,transparent)}}.protocol-choice b{{font-size:12px}}.protocol-choice small{{font-size:8px;color:var(--muted)}}.protocol-choice em{{font-style:normal;font-size:7px;font-weight:900;color:var(--protocol-color);padding:2px 8px;border-radius:999px;background:color-mix(in srgb,var(--protocol-color) 9%,#0c1118)}}
.protocol-panels{{margin-top:12px}}.protocol-panel{{display:none;border:1px solid var(--line);border-radius:17px;background:#0b1017;overflow:hidden}}.protocol-panel.active{{display:block}}.protocol-panel-head{{min-height:78px;padding:16px 18px;border-bottom:1px solid #1c2430;display:flex;align-items:center;justify-content:space-between;gap:20px}}.protocol-panel-head h2{{margin:0;font-size:16px}}.protocol-panel-head small{{display:block;margin-top:4px;color:var(--muted);font-size:8px}}.server-tabs{{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-start}}.server-tab{{height:34px;min-width:72px;padding:0 13px;border:1px solid #384259;border-radius:9px;background:#121826;color:#9eabc0;font-size:9px;font-weight:900}}.server-tab i{{display:inline-block;width:6px;height:6px;margin-right:7px;border-radius:50%;background:#31d685}}.server-tab.active{{border-color:#7958e9;color:#bcaaff;background:#15112a}}.server-views{{padding:18px}}.server-view{{display:none}}.server-view.active{{display:block}}.facts-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}}.facts-grid:has(.fact-card:nth-child(4)){{grid-template-columns:repeat(4,minmax(0,1fr))}}.fact-card{{position:relative;min-height:108px;padding:18px 16px 14px;border:1px solid #202a38;border-radius:12px;background:#10151d;text-align:center;overflow:hidden}}.fact-card:before{{content:"";position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,transparent,color-mix(in srgb,var(--primary) 48%,transparent),transparent);opacity:.5}}.fact-card small{{display:block;color:#7e8ba0;font-size:7px}}.fact-card strong{{display:block;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin:11px 0 10px;font:700 11px ui-monospace,SFMono-Regular,Consolas,monospace;color:#f7f8fb}}.copy-btn,.action-btn{{height:29px;padding:0 10px;border:1px solid #3b2f64;border-radius:8px;background:#1b1431;color:#bda6ff;font-size:8px;font-weight:900;display:inline-flex;align-items:center;justify-content:center}}.copy-btn:hover,.action-btn:hover{{border-color:#7150d5;background:#241943}}.server-footer{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:10px}}.inline-actions{{display:flex;flex-wrap:wrap;gap:7px}}.server-qr{{width:76px;height:76px;border-radius:10px;background:white;padding:5px}}.config-drawer{{margin-top:10px;padding:10px 12px;border:1px solid #202a38;border-radius:11px;background:#0e141d}}.config-drawer summary{{cursor:pointer;color:#bda6ff;font-size:9px;font-weight:900}}.config-drawer textarea{{width:100%;min-height:130px;margin-top:10px;padding:11px;border:1px solid #253044;border-radius:9px;background:#070b10;color:#d8e1ee;font:9px/1.7 ui-monospace,Consolas,monospace;resize:vertical}}.drawer-actions{{display:flex;gap:7px;margin-top:7px}}.empty-state{{padding:24px;border:1px dashed var(--line);border-radius:13px;color:var(--muted);text-align:center;font-size:10px}}.subscription-tools{{display:flex;justify-content:flex-end;margin-top:10px}}.subscription-link-btn{{height:32px;padding:0 12px;border:1px solid #3b2f64;border-radius:9px;background:#171225;color:#bda6ff;font-size:8px;font-weight:900}}
.toast{{position:fixed;left:50%;bottom:24px;transform:translate(-50%,14px);padding:9px 14px;border:1px solid #2a3342;border-radius:9px;background:#111723;color:#fff;font-size:9px;opacity:0;pointer-events:none;transition:.18s;z-index:99}}.toast.show{{opacity:1;transform:translate(-50%,0)}}
html[data-theme="light"]{{--bg:#f5f7fb;--header:#fff;--surface:#fff;--surface-2:#f8faff;--surface-3:#eef2f8;--line:#dfe5ef;--line-soft:#edf1f6;--text:#182033;--muted:#738098}}html[data-theme="light"] body{{background:#f5f7fb}}html[data-theme="light"] .topbar{{background:#fff;border-color:#e6ebf2}}html[data-theme="light"] .traffic-card{{background:linear-gradient(110deg,#fff,#faf9ff);border-color:#ddd8f2}}html[data-theme="light"] .donut:before{{background:#fff}}html[data-theme="light"] .protocol-choice,html[data-theme="light"] .protocol-panel,html[data-theme="light"] .fact-card,html[data-theme="light"] .config-drawer{{background:#fff}}html[data-theme="light"] .fact-card strong{{color:#182033}}html[data-theme="light"] .config-drawer textarea{{background:#f8faff;color:#182033}}
@media(max-width:1100px){{.traffic-card{{grid-template-columns:1fr}}.traffic-visual{{justify-content:center}}.traffic-stats{{grid-template-columns:repeat(5,1fr);width:100%}}.protocol-grid{{grid-template-columns:repeat(3,1fr)}}.facts-grid,.facts-grid:has(.fact-card:nth-child(4)){{grid-template-columns:repeat(2,1fr)}}}}@media(max-width:760px){{.topbar{{height:auto;padding:12px 0}}.topbar-inner{{align-items:flex-start}}.profile{{flex-wrap:wrap}}.service-name{{border-left:0}}.page{{padding-top:16px}}.traffic-card{{padding:18px}}.traffic-visual{{justify-content:flex-start}}.traffic-stats{{grid-template-columns:repeat(2,1fr);height:auto;gap:6px}}.traffic-stat{{border:1px solid var(--line);border-radius:10px;height:62px;padding:0 12px}}.protocol-grid{{grid-template-columns:repeat(2,1fr)}}.protocol-panel-head{{align-items:flex-start;flex-direction:column}}.server-tabs{{justify-content:flex-start}}.facts-grid,.facts-grid:has(.fact-card:nth-child(4)){{grid-template-columns:1fr}}}}@media(max-width:480px){{.brand span:last-child{{display:none}}.profile-copy{{display:none}}.protocol-grid{{grid-template-columns:1fr 1fr;gap:8px}}.protocol-choice{{min-height:105px}}.traffic-visual{{flex-direction:column}}.donut{{--size:112px}}.server-footer{{align-items:flex-start;flex-direction:column}}}}
</style>
</head>
<body>
<header class="topbar">
  <div class="topbar-inner">
    <div class="brand"><span class="brand-mark">{h(brand_mark)}</span><span>{h(brand_name)}</span><button id="themeBtn" class="theme-btn" type="button">☀</button></div>
    <div class="profile">
      <span class="profile-avatar">{h(avatar)}</span>
      <div class="profile-copy"><strong>{h(customer_name)}</strong><small>حساب کاربری</small></div>
      <span class="service-name">{h(service_label)}</span>
      {active_badge}
    </div>
  </div>
</header>
<main class="page">
  <section class="traffic-card">
    <div class="traffic-visual">
      <div class="donut" style="--percent:{percent:.1f}"><div class="donut-center"><b>{percent:.0f}%</b><small>مصرف شده</small></div></div>
      <div class="traffic-title"><h2>مصرف ترافیک</h2><small>LIVE</small></div>
    </div>
    <div class="traffic-stats">
      <div class="traffic-stat"><small>مصرف‌شده</small><strong>{h(used_label)}</strong></div>
      <div class="traffic-stat"><small>باقی‌مانده</small><strong>{h(remaining_label)}</strong></div>
      <div class="traffic-stat"><small>حجم کل</small><strong>{h(total_label)}</strong></div>
      <div class="traffic-stat"><small>تاریخ شروع</small><strong>{h(start_label)}</strong></div>
      <div class="traffic-stat"><small>تاریخ انقضا</small><strong>{h(expires_label)}</strong></div>
    </div>
  </section>

  <div class="section-head">
    <div><small>پروتکل‌های فعال</small><h2>انتخاب پروتکل</h2><p>یک پروتکل را انتخاب کن تا اطلاعات اتصال نمایش داده شود.</p></div>
    <button class="mini-menu" type="button">☷</button>
  </div>

  <section class="protocol-grid">{protocol_cards}</section>
  <div class="protocol-panels">{protocol_panels}</div>
  <div class="subscription-tools">{copy_button(share_url, "کپی لینک اشتراک")}</div>
</main>
<div id="toast" class="toast">کپی شد</div>
<script>
(function(){{
  var root=document.documentElement;
  var toast=document.getElementById('toast');
  try{{var saved=localStorage.getItem('twinpanel.connect.theme');if(saved)root.dataset.theme=saved;}}catch(e){{}}
  document.getElementById('themeBtn').addEventListener('click',function(){{var next=root.dataset.theme==='light'?'dark':'light';root.dataset.theme=next;try{{localStorage.setItem('twinpanel.connect.theme',next)}}catch(e){{}}}});

  function showToast(text){{toast.textContent=text;toast.classList.add('show');clearTimeout(window.__tpToast);window.__tpToast=setTimeout(function(){{toast.classList.remove('show')}},1200);}}
  function fallbackCopy(text){{var ta=document.createElement('textarea');ta.value=text;ta.setAttribute('readonly','');ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();ta.setSelectionRange(0,ta.value.length);var ok=false;try{{ok=document.execCommand('copy')}}catch(e){{}}ta.remove();return ok;}}
  async function copyText(text){{if(navigator.clipboard&&window.isSecureContext){{try{{await navigator.clipboard.writeText(text);return true}}catch(e){{}}}}return fallbackCopy(text);}}

  document.querySelectorAll('.protocol-choice').forEach(function(btn){{btn.addEventListener('click',function(){{var id=btn.getAttribute('data-protocol');document.querySelectorAll('.protocol-choice').forEach(function(x){{x.classList.remove('active')}});document.querySelectorAll('.protocol-panel').forEach(function(x){{x.classList.remove('active')}});btn.classList.add('active');var pane=document.getElementById(id);if(pane)pane.classList.add('active');}})}});

  document.querySelectorAll('.server-tab').forEach(function(btn){{btn.addEventListener('click',function(){{var panel=btn.closest('.protocol-panel');if(!panel)return;var id=btn.getAttribute('data-server');panel.querySelectorAll('.server-tab').forEach(function(x){{x.classList.remove('active')}});panel.querySelectorAll('.server-view').forEach(function(x){{x.classList.remove('active')}});btn.classList.add('active');var view=document.getElementById(id);if(view)view.classList.add('active');}})}});

  document.addEventListener('click',async function(ev){{
    var copy=ev.target.closest('[data-copy]');
    if(copy){{var ok=await copyText(copy.getAttribute('data-copy')||'');showToast(ok?'کپی شد':'کپی انجام نشد');return;}}
    var targetBtn=ev.target.closest('.copy-target');
    if(targetBtn){{var el=document.getElementById(targetBtn.getAttribute('data-target')||'');if(el){{var ok2=await copyText(el.value||el.textContent||'');showToast(ok2?'کپی شد':'کپی انجام نشد');}}return;}}
    var dl=ev.target.closest('.download-config');
    if(dl){{var el2=document.getElementById(dl.getAttribute('data-target')||'');if(!el2)return;var blob=new Blob([el2.value||el2.textContent||''],{{type:'text/plain;charset=utf-8'}});var url=URL.createObjectURL(blob);var a=document.createElement('a');a.href=url;a.download=dl.getAttribute('data-filename')||'config.txt';document.body.appendChild(a);a.click();a.remove();setTimeout(function(){{URL.revokeObjectURL(url)}},1000);showToast('دانلود آماده شد');}}
  }});
}})();
</script>
</body>
</html>'''
    return HTMLResponse(page)
