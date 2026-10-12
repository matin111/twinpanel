from __future__ import annotations

import html
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

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


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def protocol_title(value: str) -> str:
    return {
        "cisco": "Cisco / OpenConnect",
        "openvpn": "OpenVPN",
        "wireguard": "WireGuard",
        "l2tp": "L2TP / IPsec",
        "v2ray": "V2Ray / Xray",
        "xray": "V2Ray / Xray",
    }.get(str(value or "").lower(), str(value or "Protocol"))


def field_row(label: str, value: Any, copyable: bool = True) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    copy = (
        f'<button class="copy-btn" type="button" data-copy={h(js(text))}>کپی</button>'
        if copyable
        else ""
    )
    return (
        '<div class="field-row">'
        f'<span>{h(label)}</span>'
        f'<code dir="ltr">{h(text)}</code>'
        f'{copy}'
        '</div>'
    )


def item_html(protocol: str, item: dict[str, Any], index: int) -> str:
    rows: list[str] = []
    labels = {
        "host": "سرور",
        "server": "سرور",
        "port": "پورت",
        "username": "نام کاربری",
        "password": "رمز عبور",
        "psk": "PSK",
        "uri": "لینک",
        "endpoint": "Endpoint",
    }
    for key, label in labels.items():
        if item.get(key) not in (None, ""):
            rows.append(field_row(label, item.get(key)))

    config = str(item.get("config") or "").strip()
    uri = str(item.get("uri") or "").strip()
    qr = str(item.get("qr") or "").strip()

    config_block = ""
    if config:
        filename = f"{protocol}-{index + 1}.conf"
        if protocol == "openvpn":
            filename = f"openvpn-{index + 1}.ovpn"
        elif protocol == "wireguard":
            filename = f"wireguard-{index + 1}.conf"
        config_block = (
            '<div class="config-box">'
            f'<textarea readonly dir="ltr">{h(config)}</textarea>'
            '<div class="config-actions">'
            f'<button type="button" class="copy-btn" data-copy={h(js(config))}>کپی کانفیگ</button>'
            f'<button type="button" class="download-config" data-filename={h(js(filename))} data-content={h(js(config))}>دانلود کانفیگ</button>'
            '</div></div>'
        )

    uri_block = ""
    if uri:
        uri_block = (
            '<div class="uri-actions">'
            f'<button type="button" class="copy-btn" data-copy={h(js(uri))}>کپی لینک</button>'
            f'<a href={h(js(uri))} target="_blank" rel="noopener noreferrer">باز کردن</a>'
            '</div>'
        )

    qr_block = f'<img class="item-qr" src="{h(qr)}" alt="QR">' if qr else ""

    return (
        '<div class="server-item">'
        f'<div class="server-head"><b>سرور {index + 1}</b>{qr_block}</div>'
        f'{"".join(rows)}{uri_block}{config_block}'
        '</div>'
    )


def credentials_html(payload: dict[str, Any]) -> str:
    credentials = payload.get("credentials") or []
    if not isinstance(credentials, list) or not credentials:
        return '<div class="empty">اطلاعات اتصال هنوز آماده نشده است.</div>'

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

        account_rows = []
        if cred.get("username"):
            account_rows.append(field_row("نام کاربری", cred.get("username")))
        password = cred.get("password") or cred.get("secret")
        if password:
            account_rows.append(field_row("رمز عبور", password))

        cards.append(
            '<section class="protocol-card">'
            f'<div class="protocol-head"><div><small>PROTOCOL</small><h2>{h(protocol_title(protocol))}</h2></div><span>{len(items)}</span></div>'
            f'{"".join(account_rows)}'
            f'<div class="server-list">{"".join(item_html(protocol, item if isinstance(item, dict) else {}, idx) for idx, item in enumerate(items))}</div>'
            '</section>'
        )

    return "".join(cards) or '<div class="empty">اطلاعات اتصال هنوز آماده نشده است.</div>'


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
        links = []
        for item in items:
            size = int(item.get("file_size") or 0)
            size_label = f"{size / 1024 / 1024:.1f} MB" if size else ""
            links.append(
                '<a class="download-item" href="{}">'
                '<div><b>{}</b><small>{}</small></div>'
                '<span>{}</span>'
                '</a>'.format(
                    h(item.get("url") or "#"),
                    h(item.get("name") or "Download"),
                    h(item.get("note") or ""),
                    h(size_label or "دانلود"),
                )
            )
        groups.append(
            f'<section class="download-group"><h3>{h(labels[platform])}</h3><div class="download-list">{"".join(links)}</div></section>'
        )
    return "".join(groups) or '<div class="empty">فایل دانلودی توسط مدیر اضافه نشده است.</div>'


@router.get("/{token}", response_class=HTMLResponse)
def public_connection_page_v2(token: str, db: Session = Depends(get_db)):
    sub = _subscription_from_share_token(token, db)
    payload = _public_payload(db, sub)
    usage = _usage_payload(db, sub)
    user = db.get(User, sub.user_id)

    status = str(getattr(sub.status, "value", sub.status)).lower()
    share_url = _share_url(db, sub)
    account = payload.get("account") if isinstance(payload.get("account"), dict) else {}
    username = str((account or {}).get("username") or getattr(sub, "account_username", "") or "")
    password = str((account or {}).get("password") or getattr(sub, "account_password_encrypted", "") or "")

    used = float(usage.get("used_gb") or 0)
    total = usage.get("total_gb")
    remaining = usage.get("remaining_gb")
    percent = float(usage.get("percent") or 0)
    expires = sub.expires_at.strftime("%Y/%m/%d") if sub.expires_at else "—"
    customer_name = (getattr(user, "full_name", None) or getattr(user, "email", None) or "کاربر") if user else "کاربر"
    downloads = public_downloads_by_platform(db)

    if status != "active":
        state_banner = '<div class="state-banner bad">این اشتراک در حال حاضر فعال نیست.</div>'
    else:
        state_banner = '<div class="state-banner ok">اشتراک فعال است</div>'

    account_box = (
        '<section class="account-card">'
        '<div class="section-head"><div><small>ACCOUNT</small><h2>اطلاعات حساب</h2></div></div>'
        f'{field_row("نام کاربری", username)}'
        f'{field_row("رمز عبور", password)}'
        f'{field_row("لینک اشتراک", share_url)}'
        '</section>'
    )

    page = f'''<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light">
<title>اتصال سرویس #{sub.id}</title>
<style>
:root{{--bg:#070b14;--surface:#0d1423;--surface2:#111b2e;--line:#22304a;--text:#f4f7ff;--muted:#8896b3;--purple:#8b5cf6;--purple2:#6d28d9;--green:#22c55e;--red:#ef4444}}
*{{box-sizing:border-box}}html{{background:var(--bg)}}body{{margin:0;background:radial-gradient(circle at 80% -10%,rgba(124,58,237,.18),transparent 28%),var(--bg);color:var(--text);font-family:Tahoma,Arial,sans-serif;min-height:100vh}}button,a{{font:inherit}}a{{color:inherit;text-decoration:none}}.wrap{{width:min(1120px,94vw);margin:auto;padding:28px 0 60px}}.top{{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:22px}}.brand{{display:flex;align-items:center;gap:10px;font-weight:900}}.brand-mark{{width:38px;height:38px;border-radius:13px;background:linear-gradient(135deg,var(--purple),var(--purple2));display:grid;place-items:center;box-shadow:0 12px 30px rgba(109,40,217,.3)}}.theme{{width:40px;height:40px;border:1px solid var(--line);background:var(--surface);border-radius:12px;color:var(--text);cursor:pointer}}.hero{{display:grid;grid-template-columns:1fr auto;gap:22px;align-items:center;padding:26px;border:1px solid rgba(139,92,246,.28);border-radius:24px;background:linear-gradient(135deg,rgba(124,58,237,.13),rgba(13,20,35,.96));margin-bottom:18px}}.hero h1{{margin:0 0 8px;font-size:30px}}.hero p{{margin:0;color:var(--muted);font-size:13px}}.hero-stats{{display:grid;grid-template-columns:repeat(3,110px);gap:8px}}.hero-stats span{{padding:13px;border:1px solid var(--line);border-radius:14px;background:rgba(8,13,24,.55);text-align:center}}.hero-stats b{{display:block;font-size:18px}}.hero-stats small{{color:var(--muted);font-size:9px}}.state-banner{{padding:11px 14px;border-radius:12px;margin-bottom:16px;font-size:12px;font-weight:900}}.state-banner.ok{{background:rgba(34,197,94,.09);border:1px solid rgba(34,197,94,.25);color:#86efac}}.state-banner.bad{{background:rgba(239,68,68,.09);border:1px solid rgba(239,68,68,.25);color:#fca5a5}}.grid{{display:grid;grid-template-columns:360px minmax(0,1fr);gap:16px;align-items:start}}.account-card,.protocol-card,.downloads{{border:1px solid var(--line);background:linear-gradient(180deg,var(--surface),rgba(10,16,28,.98));border-radius:20px;padding:18px}}.account-card{{position:sticky;top:16px}}.section-head,.protocol-head{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:14px}}.section-head small,.protocol-head small{{color:#a78bfa;font-size:9px;font-weight:900;letter-spacing:.12em}}.section-head h2,.protocol-head h2{{margin:4px 0 0;font-size:18px}}.protocol-head>span{{min-width:32px;height:32px;border-radius:10px;background:rgba(124,58,237,.13);display:grid;place-items:center;color:#c4b5fd}}.field-row{{display:grid;grid-template-columns:82px minmax(0,1fr) auto;align-items:center;gap:8px;padding:9px 0;border-bottom:1px dashed var(--line)}}.field-row>span{{color:var(--muted);font-size:10px}}.field-row code{{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text);font-family:ui-monospace,Consolas,monospace;font-size:11px}}.copy-btn,.download-config,.uri-actions a{{height:34px;padding:0 11px;border:1px solid var(--line);border-radius:9px;background:var(--surface2);color:var(--text);cursor:pointer;font-size:10px}}.copy-btn:hover,.download-config:hover,.uri-actions a:hover{{border-color:rgba(139,92,246,.65)}}.protocols{{display:grid;gap:14px}}.server-list{{display:grid;gap:10px}}.server-item{{padding:13px;border:1px solid var(--line);border-radius:14px;background:var(--surface2)}}.server-head{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:6px}}.server-head b{{font-size:11px}}.item-qr{{width:72px;height:72px;background:#fff;border-radius:10px;padding:4px}}.config-box{{margin-top:10px}}.config-box textarea{{width:100%;min-height:110px;resize:vertical;padding:10px;border:1px solid var(--line);border-radius:10px;background:#080d17;color:#dbeafe;font:10px/1.7 ui-monospace,Consolas,monospace}}.config-actions,.uri-actions{{display:flex;gap:7px;margin-top:7px}}.uri-actions a{{display:inline-flex;align-items:center}}.downloads{{margin-top:16px}}.downloads-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}.download-group{{padding:12px;border:1px solid var(--line);border-radius:14px;background:var(--surface2)}}.download-group h3{{margin:0 0 10px;font-size:13px}}.download-list{{display:grid;gap:7px}}.download-item{{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px;border:1px solid var(--line);border-radius:11px;background:rgba(6,10,18,.45)}}.download-item b{{display:block;font-size:10px}}.download-item small{{display:block;margin-top:3px;color:var(--muted);font-size:8px}}.download-item>span{{color:#c4b5fd;font-size:9px;white-space:nowrap}}.empty{{padding:18px;border:1px dashed var(--line);border-radius:13px;color:var(--muted);text-align:center;font-size:11px}}
html[data-theme="light"]{{--bg:#f6f8fd;--surface:#fff;--surface2:#f8faff;--line:#dfe7f4;--text:#15203c;--muted:#71809f}}html[data-theme="light"] body{{background:radial-gradient(circle at 80% -10%,rgba(124,58,237,.10),transparent 28%),var(--bg)}}html[data-theme="light"] .config-box textarea{{background:#f7f9fd;color:#15203c}}
@media(max-width:900px){{.grid{{grid-template-columns:1fr}}.account-card{{position:static}}.hero{{grid-template-columns:1fr}}.hero-stats{{grid-template-columns:repeat(3,1fr)}}}}@media(max-width:620px){{.wrap{{width:min(94vw,540px);padding-top:16px}}.hero{{padding:18px;border-radius:18px}}.hero h1{{font-size:23px}}.hero-stats{{gap:5px}}.hero-stats span{{padding:9px 6px}}.downloads-grid{{grid-template-columns:1fr}}.field-row{{grid-template-columns:1fr auto}}.field-row>span{{grid-column:1/-1}}.field-row code{{white-space:normal;word-break:break-all}}}}
</style>
</head>
<body>
<div class="wrap">
  <header class="top"><div class="brand"><span class="brand-mark">T</span><span>TwinPanel</span></div><button id="themeBtn" class="theme" type="button">◐</button></header>
  <section class="hero"><div><h1>سرویس #{sub.id}</h1><p>{h(customer_name)} · انقضا {h(expires)}</p></div><div class="hero-stats"><span><b>{h(f'{used:.1f} GB')}</b><small>مصرف</small></span><span><b>{h('∞' if total is None else f'{float(total or 0):.1f} GB')}</b><small>حجم کل</small></span><span><b>{h('∞' if remaining is None else f'{float(remaining or 0):.1f} GB')}</b><small>باقی‌مانده</small></span></div></section>
  {state_banner}
  <div class="grid">
    {account_box}
    <div class="protocols">{credentials_html(payload)}</div>
  </div>
  <section class="downloads"><div class="section-head"><div><small>DOWNLOADS</small><h2>دانلود برنامه‌ها</h2></div></div><div class="downloads-grid">{downloads_html(downloads)}</div></section>
</div>
<script>
(function(){{
  var root=document.documentElement;
  var saved='';try{{saved=localStorage.getItem('twinpanel.connect.theme')||''}}catch(e){{}}
  if(saved)root.dataset.theme=saved;
  document.getElementById('themeBtn').addEventListener('click',function(){{var next=root.dataset.theme==='light'?'dark':'light';root.dataset.theme=next;try{{localStorage.setItem('twinpanel.connect.theme',next)}}catch(e){{}}}});

  function fallbackCopy(text){{
    var ta=document.createElement('textarea');ta.value=text;ta.setAttribute('readonly','');ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();ta.setSelectionRange(0,ta.value.length);var ok=false;try{{ok=document.execCommand('copy')}}catch(e){{}}document.body.removeChild(ta);return ok;
  }}
  async function copyText(text){{
    if(navigator.clipboard && window.isSecureContext){{try{{await navigator.clipboard.writeText(text);return true}}catch(e){{}}}}
    return fallbackCopy(text);
  }}
  document.addEventListener('click',async function(ev){{
    var copy=ev.target.closest('[data-copy]');
    if(copy){{var text='';try{{text=JSON.parse(copy.getAttribute('data-copy'))}}catch(e){{text=copy.getAttribute('data-copy')||''}}var old=copy.textContent;var ok=await copyText(text);copy.textContent=ok?'✓ کپی شد':'کپی نشد';setTimeout(function(){{copy.textContent=old}},1200);return;}}
    var dl=ev.target.closest('.download-config');
    if(dl){{var content='',filename='config.txt';try{{content=JSON.parse(dl.getAttribute('data-content'));filename=JSON.parse(dl.getAttribute('data-filename'))}}catch(e){{}}var blob=new Blob([content],{{type:'text/plain;charset=utf-8'}});var url=URL.createObjectURL(blob);var a=document.createElement('a');a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(function(){{URL.revokeObjectURL(url)}},1000);}}
  }});
}})();
</script>
</body></html>'''
    return HTMLResponse(page)
