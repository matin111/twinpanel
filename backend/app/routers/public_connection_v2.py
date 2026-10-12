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
from .download_assets import public_downloads_by_platform


router = APIRouter(prefix="/v1/connect", tags=["public-connection-v2"])


def h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def protocol_title(value: str) -> str:
    return {
        "cisco": "Cisco / OpenConnect",
        "openvpn": "OpenVPN",
        "wireguard": "WireGuard",
        "l2tp": "L2TP / IPsec",
        "v2ray": "V2Ray / Xray",
        "xray": "V2Ray / Xray",
    }.get(str(value or "").lower(), str(value or "Protocol"))


def safe_color(value: Any, fallback: str) -> str:
    value = str(value or "").strip()
    return value if re.fullmatch(r"#[0-9A-Fa-f]{6}", value) else fallback


def field_row(label: str, value: Any, *, mono: bool = True) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    direction = ' dir="ltr"' if mono else ""
    return (
        '<div class="field-row">'
        f'<span>{h(label)}</span>'
        f'<code{direction} title="{h(text)}">{h(text)}</code>'
        f'<button class="copy-btn" type="button" data-copy="{h(text)}">کپی</button>'
        '</div>'
    )


def server_item_html(protocol: str, item: dict[str, Any], index: int) -> str:
    host = item.get("host") or item.get("server") or item.get("endpoint") or "—"
    port = item.get("port") or "—"
    psk = item.get("psk")
    uri = str(item.get("uri") or "").strip()
    config = str(item.get("config") or "").strip()
    qr = str(item.get("qr") or "").strip()

    compact = (
        '<div class="server-facts">'
        f'<div><small>سرور</small><b dir="ltr">{h(host)}</b></div>'
        f'<div><small>پورت</small><b dir="ltr">{h(port)}</b></div>'
        + (f'<div><small>PSK</small><b dir="ltr">{h(psk)}</b></div>' if psk else "")
        + '</div>'
    )

    actions: list[str] = []
    if uri:
        actions.append(f'<button type="button" class="soft copy-btn" data-copy="{h(uri)}">کپی لینک</button>')
        actions.append(f'<a class="soft" href="{h(uri)}" target="_blank" rel="noopener noreferrer">باز کردن</a>')

    details = ""
    if config:
        config_id = f"cfg-{h(protocol)}-{index}"
        filename = f"{protocol}-{index + 1}.conf"
        if protocol == "openvpn":
            filename = f"openvpn-{index + 1}.ovpn"
        elif protocol == "wireguard":
            filename = f"wireguard-{index + 1}.conf"
        details = (
            '<details class="config-details">'
            '<summary>کانفیگ این سرور</summary>'
            f'<textarea id="{config_id}" readonly dir="ltr">{h(config)}</textarea>'
            '<div class="config-actions">'
            f'<button type="button" class="soft copy-target" data-target="{config_id}">کپی کانفیگ</button>'
            f'<button type="button" class="soft download-config" data-target="{config_id}" data-filename="{h(filename)}">دانلود فایل</button>'
            '</div></details>'
        )

    qr_html = f'<img class="server-qr" src="{h(qr)}" alt="QR">' if qr else ""

    return (
        '<article class="server-row">'
        f'<div class="server-index"><span>{index + 1}</span><b>سرور {index + 1}</b></div>'
        f'{compact}'
        f'<div class="server-actions">{"".join(actions)}</div>'
        f'{qr_html}'
        f'{details}'
        '</article>'
    )


def credentials_tabs_html(payload: dict[str, Any]) -> tuple[str, str]:
    credentials = payload.get("credentials") or []
    if not isinstance(credentials, list):
        credentials = []

    tabs: list[str] = []
    panes: list[str] = []
    pane_index = 0

    for cred in credentials:
        if not isinstance(cred, dict):
            continue
        protocol = str(cred.get("protocol") or "").lower()
        items = cred.get("items") or []
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            items = []

        pane_id = f"protocol-{pane_index}"
        active = " active" if pane_index == 0 else ""
        tabs.append(
            f'<button class="protocol-tab{active}" type="button" data-pane="{pane_id}">'
            f'<span>{h(protocol_title(protocol))}</span><small>{len(items)} سرور</small>'
            '</button>'
        )

        rows = "".join(
            server_item_html(protocol, item if isinstance(item, dict) else {}, idx)
            for idx, item in enumerate(items)
        ) or '<div class="empty">برای این پروتکل هنوز سروری آماده نشده است.</div>'

        panes.append(
            f'<section id="{pane_id}" class="protocol-pane{active}">'
            f'<div class="protocol-pane-head"><div><small>PROTOCOL</small><h2>{h(protocol_title(protocol))}</h2></div><span>{len(items)} سرور</span></div>'
            f'<div class="server-list">{rows}</div>'
            '</section>'
        )
        pane_index += 1

    if not tabs:
        return "", '<div class="empty">اطلاعات اتصال هنوز آماده نشده است.</div>'
    return "".join(tabs), "".join(panes)


def downloads_html(downloads: dict[str, list[dict]]) -> str:
    labels = {
        "android": "Android",
        "ios": "iPhone / iPad",
        "windows": "Windows",
        "macos": "macOS",
        "linux": "Linux",
    }
    groups: list[str] = []
    for platform in ("android", "ios", "windows", "macos", "linux"):
        items = downloads.get(platform) or []
        if not items:
            continue
        links: list[str] = []
        for item in items:
            size = int(item.get("file_size") or 0)
            size_label = f"{size / 1024 / 1024:.1f} MB" if size else "دانلود"
            links.append(
                '<a class="download-item" href="{}">'
                '<div><b>{}</b><small>{}</small></div>'
                '<span>{}</span>'
                '</a>'.format(
                    h(item.get("url") or "#"),
                    h(item.get("name") or "Download"),
                    h(item.get("note") or ""),
                    h(size_label),
                )
            )
        groups.append(
            f'<section class="download-group"><h3>{h(labels[platform])}</h3><div class="download-list">{"".join(links)}</div></section>'
        )
    return "".join(groups) or '<div class="empty">هنوز فایل دانلودی توسط مدیر اضافه نشده است.</div>'


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
    share_url = _share_url(db, sub)
    account = payload.get("account") if isinstance(payload.get("account"), dict) else {}
    username = str((account or {}).get("username") or getattr(sub, "account_username", "") or "")
    # Never expose the encrypted database value as a password.
    password = str((account or {}).get("password") or "")

    used = float(usage.get("used_gb") or 0)
    total = usage.get("total_gb")
    remaining = usage.get("remaining_gb")
    percent = max(0.0, min(100.0, float(usage.get("percent") or 0)))
    expires = sub.expires_at.strftime("%Y/%m/%d") if sub.expires_at else "—"
    customer_name = (getattr(user, "full_name", None) or getattr(user, "email", None) or "کاربر") if user else "کاربر"
    downloads = public_downloads_by_platform(db)
    tabs_html, panes_html = credentials_tabs_html(payload)

    state_banner = (
        '<div class="state-banner ok"><span></span>اشتراک فعال است</div>'
        if status == "active"
        else '<div class="state-banner bad"><span></span>اشتراک در حال حاضر فعال نیست</div>'
    )

    account_box = (
        '<section class="account-card">'
        '<div class="card-title"><div><small>ACCOUNT</small><h2>اطلاعات حساب</h2></div></div>'
        '<div class="account-fields">'
        f'{field_row("نام کاربری", username)}'
        f'{field_row("رمز عبور", password)}'
        f'{field_row("لینک اشتراک", share_url)}'
        '</div></section>'
    )

    total_label = "∞" if total is None else f"{float(total or 0):.1f} GB"
    remaining_label = "∞" if remaining is None else f"{float(remaining or 0):.1f} GB"

    page = f'''<!doctype html>
<html lang="fa" dir="rtl" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light">
<title>{h(brand_name)} · اشتراک #{sub.id}</title>
<style>
:root{{--bg:#070b14;--surface:#0d1423;--surface2:#111a2b;--surface3:#151f33;--line:#22304a;--text:#f4f7ff;--muted:#8997b4;--primary:{primary};--secondary:{secondary};--green:#22c55e;--red:#ef4444;--shadow:0 20px 60px rgba(0,0,0,.18)}}
*{{box-sizing:border-box}}html{{background:var(--bg)}}body{{margin:0;min-height:100vh;background:radial-gradient(circle at 82% -12%,color-mix(in srgb,var(--primary) 18%,transparent),transparent 30%),var(--bg);color:var(--text);font-family:Tahoma,Arial,sans-serif;-webkit-font-smoothing:antialiased}}button,a,input,textarea{{font:inherit}}button{{cursor:pointer}}a{{color:inherit;text-decoration:none}}.wrap{{width:min(1180px,94vw);margin:auto;padding:24px 0 56px}}.topbar{{height:54px;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}}.brand{{display:flex;align-items:center;gap:10px;font-size:14px;font-weight:900}}.brand-mark{{width:36px;height:36px;display:grid;place-items:center;border-radius:12px;background:linear-gradient(135deg,var(--primary),var(--secondary));color:#fff;box-shadow:0 10px 26px color-mix(in srgb,var(--primary) 28%,transparent)}}.theme-btn{{width:38px;height:38px;border:1px solid var(--line);border-radius:11px;background:var(--surface);color:var(--text)}}
.hero{{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:22px;padding:24px;border:1px solid color-mix(in srgb,var(--primary) 28%,var(--line));border-radius:22px;background:linear-gradient(135deg,color-mix(in srgb,var(--primary) 13%,var(--surface)),var(--surface));box-shadow:var(--shadow)}}.hero-copy small{{display:block;color:#b9a5ff;font-size:9px;font-weight:900;letter-spacing:.14em}}.hero-copy h1{{margin:5px 0 6px;font-size:28px}}.hero-copy p{{margin:0;color:var(--muted);font-size:11px}}.hero-stats{{display:grid;grid-template-columns:repeat(3,105px);gap:8px}}.hero-stat{{padding:12px 8px;border:1px solid var(--line);border-radius:13px;background:color-mix(in srgb,var(--surface2) 86%,transparent);text-align:center}}.hero-stat b{{display:block;font-size:16px}}.hero-stat small{{display:block;margin-top:4px;color:var(--muted);font-size:8px}}.usage-track{{height:5px;border-radius:999px;background:var(--surface3);overflow:hidden;margin-top:12px}}.usage-track i{{display:block;height:100%;width:{percent:.1f}%;background:linear-gradient(90deg,var(--primary),#a78bfa);border-radius:inherit}}.state-banner{{display:flex;align-items:center;gap:8px;margin:12px 0;padding:9px 12px;border-radius:11px;font-size:10px;font-weight:900}}.state-banner span{{width:7px;height:7px;border-radius:50%;background:currentColor}}.state-banner.ok{{color:#86efac;background:rgba(34,197,94,.07);border:1px solid rgba(34,197,94,.20)}}.state-banner.bad{{color:#fca5a5;background:rgba(239,68,68,.07);border:1px solid rgba(239,68,68,.20)}}
.account-card,.connection-card,.downloads-card{{border:1px solid var(--line);border-radius:18px;background:linear-gradient(180deg,var(--surface),color-mix(in srgb,var(--surface) 94%,#000));box-shadow:var(--shadow)}}.account-card{{padding:16px;margin-bottom:12px}}.card-title,.connection-head{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}}.card-title small,.connection-head small,.protocol-pane-head small{{color:#a78bfa;font-size:8px;font-weight:900;letter-spacing:.14em}}.card-title h2,.connection-head h2,.protocol-pane-head h2{{margin:3px 0 0;font-size:16px}}.account-fields{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}}.field-row{{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:8px;min-height:46px;padding:7px 9px;border:1px solid var(--line);border-radius:11px;background:var(--surface2)}}.field-row>span{{font-size:8px;color:var(--muted);white-space:nowrap}}.field-row code{{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font:10px ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--text)}}.copy-btn,.soft{{height:31px;padding:0 10px;border:1px solid var(--line);border-radius:8px;background:var(--surface3);color:var(--text);font-size:9px}}.copy-btn:hover,.soft:hover{{border-color:color-mix(in srgb,var(--primary) 70%,var(--line));background:color-mix(in srgb,var(--primary) 9%,var(--surface3))}}
.connection-card{{padding:16px}}.protocol-tabs{{display:flex;gap:7px;overflow:auto;padding:2px 0 10px;scrollbar-width:thin}}.protocol-tab{{min-width:max-content;padding:9px 12px;border:1px solid var(--line);border-radius:10px;background:var(--surface2);color:var(--muted);text-align:right}}.protocol-tab span{{display:block;font-size:10px;font-weight:900}}.protocol-tab small{{display:block;margin-top:3px;font-size:7px;color:inherit}}.protocol-tab.active{{border-color:color-mix(in srgb,var(--primary) 62%,var(--line));background:color-mix(in srgb,var(--primary) 12%,var(--surface2));color:var(--text)}}.protocol-pane{{display:none}}.protocol-pane.active{{display:block}}.protocol-pane-head{{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px 0 11px}}.protocol-pane-head>span{{padding:5px 9px;border-radius:999px;background:color-mix(in srgb,var(--primary) 11%,var(--surface2));color:#c4b5fd;font-size:8px}}.server-list{{display:grid;gap:8px}}.server-row{{position:relative;display:grid;grid-template-columns:100px minmax(0,1fr) auto auto;align-items:center;gap:10px;padding:11px;border:1px solid var(--line);border-radius:12px;background:var(--surface2)}}.server-index{{display:flex;align-items:center;gap:7px}}.server-index span{{width:25px;height:25px;display:grid;place-items:center;border-radius:8px;background:color-mix(in srgb,var(--primary) 13%,var(--surface3));color:#c4b5fd;font-size:9px}}.server-index b{{font-size:9px;white-space:nowrap}}.server-facts{{display:flex;align-items:center;gap:18px;min-width:0}}.server-facts>div{{min-width:95px}}.server-facts small{{display:block;color:var(--muted);font-size:7px}}.server-facts b{{display:block;margin-top:2px;font:10px ui-monospace,SFMono-Regular,Consolas,monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.server-actions{{display:flex;gap:5px}}.server-qr{{width:48px;height:48px;padding:3px;border-radius:8px;background:#fff}}.config-details{{grid-column:1/-1;margin-top:2px;border-top:1px dashed var(--line);padding-top:8px}}.config-details summary{{cursor:pointer;color:#c4b5fd;font-size:9px;font-weight:900}}.config-details textarea{{width:100%;min-height:120px;margin-top:8px;padding:10px;border:1px solid var(--line);border-radius:9px;background:#080d17;color:#dbeafe;font:9px/1.65 ui-monospace,Consolas,monospace;resize:vertical}}.config-actions{{display:flex;gap:6px;margin-top:6px}}.empty{{padding:18px;border:1px dashed var(--line);border-radius:12px;color:var(--muted);text-align:center;font-size:10px}}
.downloads-card{{margin-top:12px;padding:16px}}.downloads-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}}.download-group{{padding:11px;border:1px solid var(--line);border-radius:12px;background:var(--surface2)}}.download-group h3{{margin:0 0 8px;font-size:11px}}.download-list{{display:grid;gap:6px}}.download-item{{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 9px;border:1px solid var(--line);border-radius:9px;background:var(--surface)}}.download-item b{{display:block;font-size:9px}}.download-item small{{display:block;margin-top:2px;color:var(--muted);font-size:7px}}.download-item>span{{color:#c4b5fd;font-size:8px;white-space:nowrap}}
.toast{{position:fixed;left:50%;bottom:24px;transform:translate(-50%,15px);padding:9px 14px;border:1px solid var(--line);border-radius:10px;background:#111827;color:#fff;font-size:9px;opacity:0;pointer-events:none;transition:.18s;z-index:20}}.toast.show{{opacity:1;transform:translate(-50%,0)}}
html[data-theme="light"]{{--bg:#f6f8fd;--surface:#fff;--surface2:#f8faff;--surface3:#eef3fb;--line:#dfe7f4;--text:#15203c;--muted:#71809f}}html[data-theme="light"] body{{background:radial-gradient(circle at 82% -12%,color-mix(in srgb,var(--primary) 10%,transparent),transparent 30%),var(--bg)}}html[data-theme="light"] .config-details textarea{{background:#f7f9fd;color:#15203c}}html[data-theme="light"] .toast{{background:#15203c;color:#fff}}
@media(max-width:860px){{.hero{{grid-template-columns:1fr}}.hero-stats{{grid-template-columns:repeat(3,1fr)}}.account-fields{{grid-template-columns:1fr}}.server-row{{grid-template-columns:90px minmax(0,1fr) auto}}.server-qr{{grid-column:3;grid-row:1}}.server-actions{{grid-column:1/-1}}.downloads-grid{{grid-template-columns:1fr}}}}@media(max-width:560px){{.wrap{{width:94vw;padding-top:12px}}.hero{{padding:17px;border-radius:17px}}.hero-copy h1{{font-size:22px}}.hero-stats{{gap:5px}}.hero-stat{{padding:9px 4px}}.hero-stat b{{font-size:12px}}.server-row{{grid-template-columns:1fr auto}}.server-index{{grid-column:1}}.server-qr{{grid-column:2;grid-row:1/3}}.server-facts{{grid-column:1;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}}.server-facts>div{{min-width:0}}.server-actions{{grid-column:1/-1;flex-wrap:wrap}}.server-actions>*{{flex:1;justify-content:center;text-align:center}}}}
</style>
</head>
<body>
<div class="wrap">
  <header class="topbar"><div class="brand"><span class="brand-mark">{h(brand_mark)}</span><span>{h(brand_name)}</span></div><button id="themeBtn" class="theme-btn" type="button">◐</button></header>
  <section class="hero">
    <div class="hero-copy"><small>SUBSCRIPTION</small><h1>اشتراک #{sub.id}</h1><p>{h(customer_name)} · انقضا {h(expires)}</p><div class="usage-track"><i></i></div></div>
    <div class="hero-stats"><div class="hero-stat"><b>{h(f'{used:.1f} GB')}</b><small>مصرف</small></div><div class="hero-stat"><b>{h(total_label)}</b><small>حجم کل</small></div><div class="hero-stat"><b>{h(remaining_label)}</b><small>باقی‌مانده</small></div></div>
  </section>
  {state_banner}
  {account_box}
  <section class="connection-card"><div class="connection-head"><div><small>CONNECTION</small><h2>اتصال و کانفیگ</h2></div></div><div class="protocol-tabs">{tabs_html}</div><div class="protocol-panes">{panes_html}</div></section>
  <section class="downloads-card"><div class="card-title"><div><small>DOWNLOADS</small><h2>برنامه‌های اتصال</h2></div></div><div class="downloads-grid">{downloads_html(downloads)}</div></section>
</div>
<div id="toast" class="toast">کپی شد</div>
<script>
(function(){{
  var root=document.documentElement, toast=document.getElementById('toast');
  try{{var saved=localStorage.getItem('twinpanel.connect.theme');if(saved)root.dataset.theme=saved}}catch(e){{}}
  document.getElementById('themeBtn').addEventListener('click',function(){{var next=root.dataset.theme==='light'?'dark':'light';root.dataset.theme=next;try{{localStorage.setItem('twinpanel.connect.theme',next)}}catch(e){{}}}});

  function showToast(text){{toast.textContent=text;toast.classList.add('show');clearTimeout(window.__tpToast);window.__tpToast=setTimeout(function(){{toast.classList.remove('show')}},1200)}}
  function fallbackCopy(text){{var ta=document.createElement('textarea');ta.value=text;ta.setAttribute('readonly','');ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();ta.setSelectionRange(0,ta.value.length);var ok=false;try{{ok=document.execCommand('copy')}}catch(e){{}}ta.remove();return ok}}
  async function copyText(text){{if(navigator.clipboard&&window.isSecureContext){{try{{await navigator.clipboard.writeText(text);return true}}catch(e){{}}}}return fallbackCopy(text)}}

  document.querySelectorAll('.protocol-tab').forEach(function(btn){{btn.addEventListener('click',function(){{var id=btn.getAttribute('data-pane');document.querySelectorAll('.protocol-tab').forEach(function(x){{x.classList.remove('active')}});document.querySelectorAll('.protocol-pane').forEach(function(x){{x.classList.remove('active')}});btn.classList.add('active');var pane=document.getElementById(id);if(pane)pane.classList.add('active')}})}});

  document.addEventListener('click',async function(ev){{
    var copy=ev.target.closest('[data-copy]');
    if(copy){{var ok=await copyText(copy.getAttribute('data-copy')||'');showToast(ok?'کپی شد':'کپی نشد');return}}
    var targetCopy=ev.target.closest('.copy-target');
    if(targetCopy){{var node=document.getElementById(targetCopy.getAttribute('data-target')||'');var ok2=node?await copyText(node.value||node.textContent||''):false;showToast(ok2?'کپی شد':'کپی نشد');return}}
    var dl=ev.target.closest('.download-config');
    if(dl){{var node2=document.getElementById(dl.getAttribute('data-target')||'');if(!node2)return;var blob=new Blob([node2.value||node2.textContent||''],{{type:'text/plain;charset=utf-8'}});var url=URL.createObjectURL(blob);var a=document.createElement('a');a.href=url;a.download=dl.getAttribute('data-filename')||'config.txt';document.body.appendChild(a);a.click();a.remove();setTimeout(function(){{URL.revokeObjectURL(url)}},1000)}}
  }});
}})();
</script>
</body></html>'''
    return HTMLResponse(page)
