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


def protocol_title(value: str) -> str:
    return {
        "cisco": "Cisco / OpenConnect",
        "openvpn": "OpenVPN",
        "wireguard": "WireGuard",
        "l2tp": "L2TP / IPsec",
        "v2ray": "V2Ray / Xray",
        "xray": "V2Ray / Xray",
    }.get(str(value or "").lower(), str(value or "Protocol"))


def copy_row(label: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return (
        '<div class="info-row">'
        f'<span>{h(label)}</span>'
        f'<code dir="ltr" title="{h(text)}">{h(text)}</code>'
        f'<button type="button" class="copy-btn" data-copy="{h(text)}">کپی</button>'
        '</div>'
    )


def server_card(protocol: str, item: dict[str, Any], index: int) -> str:
    host = str(item.get("host") or item.get("server") or item.get("endpoint") or "—")
    port = str(item.get("port") or "—")
    psk = str(item.get("psk") or "").strip()
    uri = str(item.get("uri") or "").strip()
    config = str(item.get("config") or "").strip()
    qr = str(item.get("qr") or "").strip()

    facts = [
        f'<div class="fact"><small>آدرس سرور</small><b dir="ltr" title="{h(host)}">{h(host)}</b></div>',
        f'<div class="fact port"><small>پورت</small><b dir="ltr">{h(port)}</b></div>',
    ]
    if psk:
        facts.append(f'<div class="fact"><small>PSK</small><b dir="ltr" title="{h(psk)}">{h(psk)}</b></div>')

    actions: list[str] = []
    actions.append(f'<button class="mini-btn copy-btn" type="button" data-copy="{h(host)}">کپی سرور</button>')
    if uri:
        actions.append(f'<button class="mini-btn copy-btn" type="button" data-copy="{h(uri)}">کپی لینک</button>')
        actions.append(f'<a class="mini-btn" href="{h(uri)}" target="_blank" rel="noopener noreferrer">باز کردن</a>')

    config_html = ""
    if config:
        cid = f"cfg-{protocol}-{index}"
        filename = f"{protocol}-{index + 1}.conf"
        if protocol == "openvpn":
            filename = f"openvpn-{index + 1}.ovpn"
        elif protocol == "wireguard":
            filename = f"wireguard-{index + 1}.conf"
        config_html = (
            '<details class="config-details">'
            '<summary>کانفیگ سرور</summary>'
            f'<textarea id="{h(cid)}" readonly dir="ltr">{h(config)}</textarea>'
            '<div class="config-actions">'
            f'<button type="button" class="mini-btn copy-target" data-target="{h(cid)}">کپی کانفیگ</button>'
            f'<button type="button" class="mini-btn download-config" data-target="{h(cid)}" data-filename="{h(filename)}">دانلود فایل</button>'
            '</div>'
            '</details>'
        )

    qr_html = f'<img class="server-qr" src="{h(qr)}" alt="QR">' if qr else ""

    return (
        '<article class="server-card">'
        f'<div class="server-title"><span>{index + 1}</span><b>سرور {index + 1}</b></div>'
        f'<div class="facts">{"".join(facts)}</div>'
        f'{qr_html}'
        f'<div class="server-actions">{"".join(actions)}</div>'
        f'{config_html}'
        '</article>'
    )


def credentials_html(payload: dict[str, Any]) -> str:
    credentials = payload.get("credentials") or []
    if not isinstance(credentials, list):
        credentials = []

    cards: list[str] = []
    for cred in credentials:
        if not isinstance(cred, dict):
            continue
        protocol = str(cred.get("protocol") or "").lower()
        items = cred.get("items") or []
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            items = []

        servers = "".join(
            server_card(protocol, item if isinstance(item, dict) else {}, idx)
            for idx, item in enumerate(items)
        ) or '<div class="empty">برای این پروتکل هنوز سروری آماده نشده است.</div>'

        cards.append(
            '<section class="protocol-card">'
            '<div class="protocol-head">'
            f'<div><small>PROTOCOL</small><h2>{h(protocol_title(protocol))}</h2></div>'
            f'<span>{len(items)} سرور</span>'
            '</div>'
            f'<div class="server-grid">{servers}</div>'
            '</section>'
        )

    return "".join(cards) or '<div class="empty">اطلاعات اتصال هنوز آماده نشده است.</div>'


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
    password = str((account or {}).get("password") or "")

    used = float(usage.get("used_gb") or 0)
    total = usage.get("total_gb")
    remaining = usage.get("remaining_gb")
    percent = max(0.0, min(100.0, float(usage.get("percent") or 0)))
    expires = sub.expires_at.strftime("%Y/%m/%d") if sub.expires_at else "—"
    customer_name = (getattr(user, "full_name", None) or getattr(user, "email", None) or "کاربر") if user else "کاربر"

    total_label = "∞" if total is None else f"{float(total or 0):.1f} GB"
    remaining_label = "∞" if remaining is None else f"{float(remaining or 0):.1f} GB"

    state_banner = (
        '<div class="state-banner ok"><i></i>اشتراک فعال است</div>'
        if status == "active"
        else '<div class="state-banner bad"><i></i>اشتراک در حال حاضر فعال نیست</div>'
    )

    account_box = (
        '<section class="account-card">'
        '<div class="section-head"><div><small>ACCOUNT</small><h2>اطلاعات حساب</h2></div></div>'
        f'{copy_row("نام کاربری", username)}'
        f'{copy_row("رمز عبور", password)}'
        f'{copy_row("لینک اشتراک", share_url)}'
        '</section>'
    )

    page = f'''<!doctype html>
<html lang="fa" dir="rtl" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light">
<title>{h(brand_name)} · سرویس #{sub.id}</title>
<style>
:root{{--bg:#080b13;--surface:#0f1626;--surface2:#121c2f;--surface3:#17243a;--line:#263553;--text:#f5f7ff;--muted:#8997b3;--primary:{primary};--secondary:{secondary};--green:#22c55e;--red:#ef4444;--shadow:0 20px 55px rgba(0,0,0,.2)}}
*{{box-sizing:border-box}}html{{background:var(--bg)}}body{{margin:0;min-height:100vh;background:radial-gradient(circle at 80% -8%,color-mix(in srgb,var(--primary) 17%,transparent),transparent 30%),var(--bg);color:var(--text);font-family:Tahoma,Arial,sans-serif;-webkit-font-smoothing:antialiased}}button,a,textarea{{font:inherit}}button{{cursor:pointer}}a{{color:inherit;text-decoration:none}}.wrap{{width:min(1160px,94vw);margin:auto;padding:24px 0 54px}}.topbar{{height:52px;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}}.brand{{display:flex;align-items:center;gap:10px;font-weight:900}}.brand-mark{{width:38px;height:38px;border-radius:13px;display:grid;place-items:center;background:linear-gradient(135deg,var(--primary),var(--secondary));box-shadow:0 10px 28px color-mix(in srgb,var(--primary) 30%,transparent)}}.theme-btn{{width:40px;height:40px;border:1px solid var(--line);border-radius:12px;background:var(--surface);color:var(--text)}}
.hero{{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:20px;padding:24px;border:1px solid color-mix(in srgb,var(--primary) 30%,var(--line));border-radius:24px;background:linear-gradient(135deg,color-mix(in srgb,var(--primary) 14%,var(--surface)),var(--surface));box-shadow:var(--shadow)}}.hero h1{{margin:0 0 7px;font-size:30px}}.hero p{{margin:0;color:var(--muted);font-size:11px}}.usage-track{{height:5px;margin-top:13px;border-radius:999px;background:var(--surface3);overflow:hidden}}.usage-track i{{display:block;width:{percent:.1f}%;height:100%;background:linear-gradient(90deg,var(--primary),#a78bfa);border-radius:inherit}}.hero-stats{{display:grid;grid-template-columns:repeat(3,106px);gap:8px}}.hero-stat{{padding:12px 8px;border:1px solid var(--line);border-radius:14px;background:rgba(8,13,24,.48);text-align:center}}.hero-stat b{{display:block;font-size:17px}}.hero-stat small{{display:block;margin-top:4px;color:var(--muted);font-size:8px}}.state-banner{{display:flex;align-items:center;gap:8px;margin:12px 0;padding:10px 13px;border-radius:12px;font-size:10px;font-weight:900}}.state-banner i{{width:7px;height:7px;border-radius:50%;background:currentColor}}.state-banner.ok{{color:#86efac;background:rgba(34,197,94,.07);border:1px solid rgba(34,197,94,.21)}}.state-banner.bad{{color:#fca5a5;background:rgba(239,68,68,.07);border:1px solid rgba(239,68,68,.21)}}
.main-grid{{display:grid;grid-template-columns:330px minmax(0,1fr);gap:14px;align-items:start}}.account-card,.protocol-card{{border:1px solid var(--line);border-radius:19px;background:linear-gradient(180deg,var(--surface),color-mix(in srgb,var(--surface) 95%,#000));box-shadow:var(--shadow)}}.account-card{{position:sticky;top:14px;padding:17px}}.section-head,.protocol-head{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px}}.section-head small,.protocol-head small{{color:#b79cff;font-size:8px;font-weight:900;letter-spacing:.15em}}.section-head h2,.protocol-head h2{{margin:4px 0 0;font-size:17px}}.protocol-head>span{{padding:6px 9px;border-radius:999px;background:color-mix(in srgb,var(--primary) 12%,var(--surface2));color:#c4b5fd;font-size:8px}}.info-row{{display:grid;grid-template-columns:72px minmax(0,1fr) auto;align-items:center;gap:7px;min-height:45px;border-bottom:1px dashed var(--line)}}.info-row:last-child{{border-bottom:0}}.info-row>span{{color:var(--muted);font-size:8px}}.info-row code{{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font:10px ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--text)}}.copy-btn,.mini-btn{{height:31px;padding:0 10px;border:1px solid var(--line);border-radius:8px;background:var(--surface3);color:var(--text);font-size:9px}}.copy-btn:hover,.mini-btn:hover{{border-color:color-mix(in srgb,var(--primary) 72%,var(--line));background:color-mix(in srgb,var(--primary) 10%,var(--surface3))}}
.protocols{{display:grid;gap:12px}}.protocol-card{{padding:16px}}.server-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}}.server-card{{position:relative;display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:9px;align-items:center;padding:11px;border:1px solid var(--line);border-radius:13px;background:var(--surface2)}}.server-title{{display:flex;align-items:center;gap:6px;min-width:72px}}.server-title span{{width:24px;height:24px;border-radius:8px;display:grid;place-items:center;background:color-mix(in srgb,var(--primary) 13%,var(--surface3));color:#c4b5fd;font-size:8px}}.server-title b{{font-size:9px;white-space:nowrap}}.facts{{display:grid;grid-template-columns:minmax(0,1fr) 64px;gap:7px;min-width:0}}.fact{{min-width:0;padding:7px 8px;border:1px solid color-mix(in srgb,var(--line) 80%,transparent);border-radius:9px;background:color-mix(in srgb,var(--surface3) 58%,transparent)}}.fact small{{display:block;color:var(--muted);font-size:7px}}.fact b{{display:block;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font:9px ui-monospace,SFMono-Regular,Consolas,monospace}}.server-qr{{width:46px;height:46px;padding:3px;border-radius:8px;background:#fff}}.server-actions{{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:5px}}.config-details{{grid-column:1/-1;border-top:1px dashed var(--line);padding-top:7px}}.config-details summary{{cursor:pointer;color:#c4b5fd;font-size:8px;font-weight:900}}.config-details textarea{{width:100%;min-height:105px;margin-top:7px;padding:9px;border:1px solid var(--line);border-radius:9px;background:#080d17;color:#dbeafe;font:9px/1.6 ui-monospace,Consolas,monospace;resize:vertical}}.config-actions{{display:flex;gap:6px;margin-top:6px}}.empty{{padding:18px;border:1px dashed var(--line);border-radius:12px;color:var(--muted);text-align:center;font-size:10px}}.toast{{position:fixed;left:50%;bottom:24px;transform:translate(-50%,12px);padding:9px 14px;border:1px solid var(--line);border-radius:10px;background:#111827;color:#fff;font-size:9px;opacity:0;pointer-events:none;transition:.18s;z-index:30}}.toast.show{{opacity:1;transform:translate(-50%,0)}}
html[data-theme="light"]{{--bg:#f6f8fd;--surface:#fff;--surface2:#f8faff;--surface3:#eef3fb;--line:#dfe7f4;--text:#15203c;--muted:#71809f}}html[data-theme="light"] body{{background:radial-gradient(circle at 80% -8%,color-mix(in srgb,var(--primary) 10%,transparent),transparent 30%),var(--bg)}}html[data-theme="light"] .config-details textarea{{background:#f7f9fd;color:#15203c}}
@media(max-width:900px){{.main-grid{{grid-template-columns:1fr}}.account-card{{position:static}}.server-grid{{grid-template-columns:1fr}}.hero{{grid-template-columns:1fr}}.hero-stats{{grid-template-columns:repeat(3,1fr)}}}}@media(max-width:560px){{.wrap{{width:94vw;padding-top:12px}}.hero{{padding:17px;border-radius:18px}}.hero h1{{font-size:23px}}.hero-stats{{gap:5px}}.hero-stat{{padding:9px 4px}}.hero-stat b{{font-size:12px}}.info-row{{grid-template-columns:1fr auto}}.info-row>span{{grid-column:1/-1}}.server-card{{grid-template-columns:1fr auto}}.server-title{{grid-column:1}}.server-qr{{grid-column:2;grid-row:1/3}}.facts{{grid-column:1;grid-template-columns:minmax(0,1fr) 62px}}.server-actions{{grid-column:1/-1}}}}
</style>
</head>
<body>
<div class="wrap">
  <header class="topbar"><div class="brand"><span class="brand-mark">{h(brand_mark)}</span><span>{h(brand_name)}</span></div><button id="themeBtn" class="theme-btn" type="button">◐</button></header>
  <section class="hero">
    <div><h1>سرویس #{sub.id}</h1><p>{h(customer_name)} · انقضا {h(expires)}</p><div class="usage-track"><i></i></div></div>
    <div class="hero-stats"><div class="hero-stat"><b>{h(f'{used:.1f} GB')}</b><small>مصرف</small></div><div class="hero-stat"><b>{h(total_label)}</b><small>حجم کل</small></div><div class="hero-stat"><b>{h(remaining_label)}</b><small>باقی‌مانده</small></div></div>
  </section>
  {state_banner}
  <div class="main-grid">
    {account_box}
    <div class="protocols">{credentials_html(payload)}</div>
  </div>
</div>
<div id="toast" class="toast">کپی شد</div>
<script>
(function(){{
  var root=document.documentElement,toast=document.getElementById('toast');
  try{{var saved=localStorage.getItem('twinpanel.connect.theme');if(saved)root.dataset.theme=saved}}catch(e){{}}
  document.getElementById('themeBtn').addEventListener('click',function(){{var next=root.dataset.theme==='light'?'dark':'light';root.dataset.theme=next;try{{localStorage.setItem('twinpanel.connect.theme',next)}}catch(e){{}}}});
  function showToast(text){{toast.textContent=text;toast.classList.add('show');clearTimeout(window.__tpToast);window.__tpToast=setTimeout(function(){{toast.classList.remove('show')}},1200)}}
  function fallbackCopy(text){{var ta=document.createElement('textarea');ta.value=text;ta.setAttribute('readonly','');ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();ta.setSelectionRange(0,ta.value.length);var ok=false;try{{ok=document.execCommand('copy')}}catch(e){{}}ta.remove();return ok}}
  async function copyText(text){{if(navigator.clipboard&&window.isSecureContext){{try{{await navigator.clipboard.writeText(text);return true}}catch(e){{}}}}return fallbackCopy(text)}}
  document.addEventListener('click',async function(ev){{
    var c=ev.target.closest('[data-copy]');
    if(c){{var ok=await copyText(c.getAttribute('data-copy')||'');showToast(ok?'کپی شد':'کپی انجام نشد');return}}
    var ct=ev.target.closest('.copy-target');
    if(ct){{var el=document.getElementById(ct.getAttribute('data-target')||'');if(el){{var ok2=await copyText(el.value||el.textContent||'');showToast(ok2?'کپی شد':'کپی انجام نشد')}}return}}
    var dl=ev.target.closest('.download-config');
    if(dl){{var el2=document.getElementById(dl.getAttribute('data-target')||'');if(!el2)return;var blob=new Blob([el2.value||el2.textContent||''],{{type:'text/plain;charset=utf-8'}});var url=URL.createObjectURL(blob);var a=document.createElement('a');a.href=url;a.download=dl.getAttribute('data-filename')||'config.txt';document.body.appendChild(a);a.click();a.remove();setTimeout(function(){{URL.revokeObjectURL(url)}},1000);showToast('دانلود آماده شد')}}
  }})
}})();
</script>
</body>
</html>'''
    return HTMLResponse(page)
