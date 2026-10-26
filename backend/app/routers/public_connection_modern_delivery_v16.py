from __future__ import annotations

import copy
import html
import json
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..amneziawg_live_telemetry_v221 import subscription_amneziawg_live
from ..database import get_db
from ..models import SubscriptionProtocol
from ..quota_models import QuotaSession, QuotaUsageEvent
from ..wireguard_live_telemetry_v97 import subscription_wireguard_live
from .account_delivery import _public_payload, _subscription_from_share_token
from .public_connection_modern_delivery_v13 import (
    MODERN_PROTOCOLS,
    _items,
    _ready_modern_item,
    _status_value,
)
from .public_connection_modern_import_v15 import KARING_126_PROTOCOLS, _outbound
from .public_connection_modern_names_v14 import _download_stem, _profile_name


router = APIRouter(tags=["public-connection-modern-delivery-v16"])


_V16_MARKER = "TWINPANEL_PUBLIC_MODERN_DELIVERY_V16"
_PROTOCOL_STATS_MARKER = "TWINPANEL_PUBLIC_PROTOCOL_STATS_V257"
_LIVE_ACTIVITY_SECONDS = 45


def _h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _normalized_protocol(value: str | None) -> str:
    protocol = str(value or "").strip().lower()
    if protocol == "v2ray":
        return "xray"
    if protocol in {"openconnect", "ocserv", "anyconnect"}:
        return "cisco"
    return protocol


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() + "Z"


def _latest(value_a: datetime | None, value_b: datetime | None) -> datetime | None:
    values = [value for value in (value_a, value_b) if value is not None]
    return max(values) if values else None


def _base_protocol_stats(db: Session, sub: Any) -> dict[str, dict[str, Any]]:
    """Build protocol-level display stats strictly from canonical quota rows."""
    selected = {
        _normalized_protocol(row[0])
        for row in (
            db.query(SubscriptionProtocol.protocol)
            .filter(SubscriptionProtocol.subscription_id == int(sub.id))
            .all()
        )
        if _normalized_protocol(row[0])
    }

    payload = _public_payload(db, sub)
    credentials = payload.get("credentials") if isinstance(payload, dict) else []
    for credential in credentials if isinstance(credentials, list) else []:
        if not isinstance(credential, dict):
            continue
        protocol = _normalized_protocol(credential.get("protocol"))
        if protocol:
            selected.add(protocol)

    starts_at = _iso_utc(getattr(sub, "starts_at", None))
    expires_at = _iso_utc(getattr(sub, "expires_at", None))
    stats: dict[str, dict[str, Any]] = {
        protocol: {
            "protocol": protocol,
            "used_bytes": 0,
            "active_sessions": 0,
            "online": False,
            "last_seen_at": None,
            "starts_at": starts_at,
            "expires_at": expires_at,
            "has_accounting": False,
        }
        for protocol in sorted(selected)
    }

    usage_rows = (
        db.query(
            QuotaUsageEvent.protocol,
            func.coalesce(func.sum(QuotaUsageEvent.accepted_bytes), 0),
            func.max(QuotaUsageEvent.reported_at),
        )
        .filter(QuotaUsageEvent.subscription_id == int(sub.id))
        .group_by(QuotaUsageEvent.protocol)
        .all()
    )
    cutoff = datetime.utcnow() - timedelta(seconds=_LIVE_ACTIVITY_SECONDS)
    for raw_protocol, accepted_bytes, reported_at in usage_rows:
        protocol = _normalized_protocol(raw_protocol)
        if not protocol:
            continue
        row = stats.setdefault(
            protocol,
            {
                "protocol": protocol,
                "used_bytes": 0,
                "active_sessions": 0,
                "online": False,
                "last_seen_at": None,
                "starts_at": starts_at,
                "expires_at": expires_at,
                "has_accounting": False,
            },
        )
        row["used_bytes"] = max(int(accepted_bytes or 0), 0)
        row["has_accounting"] = True
        if reported_at is not None:
            row["last_seen_at"] = _iso_utc(reported_at)
            if reported_at >= cutoff:
                row["online"] = True

    session_rows = (
        db.query(
            QuotaSession.protocol,
            func.count(QuotaSession.id),
            func.max(QuotaSession.last_seen_at),
        )
        .filter(
            QuotaSession.subscription_id == int(sub.id),
            QuotaSession.status == "active",
        )
        .group_by(QuotaSession.protocol)
        .all()
    )
    for raw_protocol, active_sessions, last_seen_at in session_rows:
        protocol = _normalized_protocol(raw_protocol)
        if not protocol:
            continue
        row = stats.setdefault(
            protocol,
            {
                "protocol": protocol,
                "used_bytes": 0,
                "active_sessions": 0,
                "online": False,
                "last_seen_at": None,
                "starts_at": starts_at,
                "expires_at": expires_at,
                "has_accounting": False,
            },
        )
        row["active_sessions"] = int(active_sessions or 0)
        row["has_accounting"] = True
        if last_seen_at is not None:
            current = None
            if row.get("last_seen_at"):
                try:
                    current = datetime.fromisoformat(str(row["last_seen_at"]).removesuffix("Z"))
                except ValueError:
                    current = None
            latest = _latest(current, last_seen_at)
            row["last_seen_at"] = _iso_utc(latest)
            if last_seen_at >= cutoff:
                row["online"] = True

    return stats


def _resolve_delivery_content(
    protocol: str,
    item: dict[str, Any],
    profile_name: str,
) -> tuple[str, str, str] | None:
    """Return (content, extension, media_type) without inventing protocol data.

    Raw generated config always wins. This is especially important for Naive,
    where the full JSON contains the managed CA trust material. If raw config is
    absent, use the canonical share URI already stored by Account Delivery. As a
    final lossless fallback, serialize the canonical outbound that Account
    Delivery already exposes; never synthesize protocol-specific fields here.
    """
    protocol = str(protocol or "").strip().lower()
    config = str(item.get("config") or "").strip()
    config_format = str(item.get("config_format") or "").strip().lower()

    if config:
        if config_format in {"sing-box", "mieru-json", "sudoku-json"}:
            return config, "json", "application/json"
        if protocol == "amneziawg" or config_format in {
            "amneziawg",
            "amneziawg-conf",
        }:
            return config, "conf", "text/plain"
        return config, "txt", "text/plain"

    uri = str(item.get("uri") or "").strip()
    if uri:
        return uri, "txt", "text/plain"

    outbound = _outbound(item)
    if not isinstance(outbound, dict):
        return None

    node = copy.deepcopy(outbound)
    node["tag"] = str(profile_name or "TwinPanel").strip() or "TwinPanel"
    content = json.dumps(
        {"outbounds": [node]},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return content, "json", "application/json"


def _replace_unsupported_karing_button(
    source: str,
    *,
    protocol: str,
    config_path: str,
) -> str:
    """Replace stale V13 one-click Karing actions for the 1.2.26-only cohort."""
    if protocol not in KARING_126_PROTOCOLS:
        return source

    escaped_path = _h(config_path)
    pattern = re.compile(
        r'<button class="primary-btn v13-karing-import" type="button" '
        r'data-config-path="'
        + re.escape(escaped_path)
        + r'"(?: data-config-name="[^"]*")?[^>]*>'
        r'افزودن مستقیم به Karing</button>'
    )
    replacement = (
        f'<a class="primary-btn tp-v16-safe-download" href="{escaped_path}">'
        'دانلود کانفیگ</a>'
    )
    return pattern.sub(replacement, source, count=1)


@router.get("/{token}/protocol-stats-v257")
async def public_protocol_stats_v257(
    token: str,
    db: Session = Depends(get_db),
):
    """Return truthful per-protocol usage/date/live state for the public hub."""
    sub = _subscription_from_share_token(token, db)
    stats = _base_protocol_stats(db, sub)

    wireguard_online, wireguard_seen = await subscription_wireguard_live(db, sub)
    wireguard = stats.get("wireguard")
    if wireguard is not None and wireguard_online:
        wireguard["online"] = True
        if wireguard_seen is not None:
            wireguard["last_seen_at"] = _iso_utc(wireguard_seen)

    amneziawg_online, amneziawg_seen = await subscription_amneziawg_live(db, sub)
    amneziawg = stats.get("amneziawg")
    if amneziawg is not None and amneziawg_online:
        amneziawg["online"] = True
        if amneziawg_seen is not None:
            amneziawg["last_seen_at"] = _iso_utc(amneziawg_seen)

    return {
        "ok": True,
        "subscription_status": _status_value(sub),
        "protocols": stats,
    }


@router.get("/{token}/modern-config-v16/{protocol}/{node_id}")
def public_modern_config_v16(
    token: str,
    protocol: str,
    node_id: int,
    db: Session = Depends(get_db),
):
    protocol = str(protocol or "").strip().lower()
    if protocol not in MODERN_PROTOCOLS:
        raise HTTPException(status_code=404, detail="پروتکل پشتیبانی نمی‌شود")

    sub = _subscription_from_share_token(token, db)
    item = _ready_modern_item(token, protocol, node_id, db)
    profile_name = _profile_name(sub, protocol, item)
    resolved = _resolve_delivery_content(protocol, item, profile_name)
    if resolved is None:
        raise HTTPException(
            status_code=409,
            detail="برای این سرور هنوز کانفیگ قابل تحویل ساخته نشده است",
        )

    content, extension, media_type = resolved
    stem = _download_stem(sub, protocol, item)
    filename = f"{stem}.{extension}"

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


_PROTOCOL_STATS_CSS = r"""
/* TWINPANEL_PUBLIC_PROTOCOL_STATS_V257 */
.protocol-choice{min-height:112px}
.protocol-choice .tp-v257-protocol-stats{display:grid;gap:2px;margin-top:4px;font-size:7px;line-height:1.45;color:var(--muted);font-weight:700}
.protocol-choice .tp-v257-protocol-stats span{display:block;white-space:nowrap}
.protocol-choice.tp-v257-online em{color:var(--ok);border-color:color-mix(in srgb,var(--ok) 34%,transparent);background:color-mix(in srgb,var(--ok) 8%,transparent)}
.protocol-choice.tp-v257-offline em{color:var(--muted);border-color:var(--line);background:transparent}
.protocol-choice.v13-pending .tp-v257-protocol-stats{opacity:.75}
@media(max-width:760px){.protocol-choice{min-height:108px}.protocol-choice .tp-v257-protocol-stats{font-size:7.5px}}
"""


_PROTOCOL_STATS_SCRIPT = r"""
<script>
(function(){
  const token=__TOKEN__;
  const endpoint='/v1/connect/'+encodeURIComponent(token)+'/protocol-stats-v257';
  const nf=new Intl.NumberFormat('fa-IR',{maximumFractionDigits:2});
  const gib=1024*1024*1024,mib=1024*1024,kib=1024;

  function normalizeProtocol(value){
    const p=String(value||'').trim().toLowerCase();
    if(p==='v2ray')return'xray';
    if(p==='openconnect'||p==='ocserv'||p==='anyconnect')return'cisco';
    return p;
  }
  function bytes(value){
    const n=Math.max(0,Number(value||0));
    if(n===0)return'۰ MB';
    if(n<mib)return nf.format(n/kib)+' KB';
    if(n<gib)return nf.format(n/mib)+' MB';
    return nf.format(n/gib)+' GB';
  }
  function date(value){
    if(!value)return'—';
    const d=new Date(value);
    if(Number.isNaN(d.getTime()))return'—';
    const p=v=>String(v).padStart(2,'0');
    return d.getUTCFullYear()+'/'+p(d.getUTCMonth()+1)+'/'+p(d.getUTCDate());
  }
  function ensureMeta(card){
    let meta=card.querySelector('.tp-v257-protocol-stats');
    if(meta)return meta;
    meta=document.createElement('span');
    meta.className='tp-v257-protocol-stats';
    meta.innerHTML='<span data-role="usage">مصرف —</span><span data-role="dates">شروع — · پایان —</span>';
    const text=card.querySelector('.protocol-text');
    if(text)text.appendChild(meta);
    return meta;
  }
  function apply(payload){
    const stats=(payload&&payload.protocols&&typeof payload.protocols==='object')?payload.protocols:{};
    document.querySelectorAll('.protocol-choice[data-protocol-key]').forEach(card=>{
      const key=normalizeProtocol(card.dataset.protocolKey||'');
      const row=stats[key]||null;
      const meta=ensureMeta(card);
      const usage=meta.querySelector('[data-role="usage"]');
      const dates=meta.querySelector('[data-role="dates"]');
      const badge=card.querySelector('em');
      const pending=card.classList.contains('v13-pending');
      const online=Boolean(row&&row.online===true);

      card.classList.toggle('tp-v257-online',online);
      card.classList.toggle('tp-v257-offline',Boolean(row)&&!online&&!pending);
      if(usage)usage.textContent='مصرف '+(row?bytes(row.used_bytes):'—');
      if(dates)dates.textContent='شروع '+date(row&&row.starts_at)+' · پایان '+date(row&&row.expires_at);
      if(badge&&!pending)badge.textContent=online?'آنلاین':'آفلاین';
      if(row&&row.last_seen_at)card.title='آخرین فعالیت: '+new Date(row.last_seen_at).toLocaleString('fa-IR');
    });
  }
  async function refresh(){
    try{
      const response=await fetch(endpoint,{cache:'no-store',headers:{Accept:'application/json'}});
      if(!response.ok)return;
      apply(await response.json());
    }catch(_error){}
  }
  refresh();
  const timer=setInterval(refresh,4000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
  window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});
})();
</script>
"""


def refine_public_connection_modern_delivery_v16(
    source: str,
    token: str,
    db: Session,
) -> str:
    """Repair Modern downloads and attach truthful protocol-level live stats."""
    if _V16_MARKER in source:
        return source

    sub = _subscription_from_share_token(token, db)
    if _status_value(sub) != "active":
        return source

    payload = _public_payload(db, sub)
    credentials = payload.get("credentials") if isinstance(payload, dict) else []
    token_part = quote(str(token), safe="")

    for cred in credentials if isinstance(credentials, list) else []:
        if not isinstance(cred, dict):
            continue
        protocol = str(cred.get("protocol") or "").strip().lower()
        if protocol not in MODERN_PROTOCOLS:
            continue

        for item in _items(cred):
            try:
                node_id = int(item.get("node_id") or 0)
            except (TypeError, ValueError):
                node_id = 0
            if node_id <= 0:
                continue

            profile_name = _profile_name(sub, protocol, item)
            resolved = _resolve_delivery_content(protocol, item, profile_name)
            if resolved is None:
                continue

            old_path = (
                f"/v1/connect/{token_part}/modern-config-v14/"
                f"{quote(protocol, safe='')}/{node_id}"
            )
            current_path = old_path

            # V14 is already correct when the canonical raw config exists. Only
            # move genuinely broken downloads to V16, preserving healthy paths.
            if not str(item.get("config") or "").strip():
                new_path = (
                    f"/v1/connect/{token_part}/modern-config-v16/"
                    f"{quote(protocol, safe='')}/{node_id}"
                )
                source = source.replace(_h(old_path), _h(new_path))
                current_path = new_path

            # Karing 1.2.25 must never be advertised as one-click capable for
            # Snell/Sudoku/TrustTunnel. V15 already supplies a copy action; the
            # old V13 button becomes a real download instead.
            source = _replace_unsupported_karing_button(
                source,
                protocol=protocol,
                config_path=current_path,
            )

    if _PROTOCOL_STATS_MARKER not in source:
        source = source.replace("</style>", _PROTOCOL_STATS_CSS + "\n</style>", 1)
        stats_script = _PROTOCOL_STATS_SCRIPT.replace(
            "__TOKEN__",
            json.dumps(str(token), ensure_ascii=True),
        )
        source = source.replace("</body>", stats_script + "\n</body>", 1)

    source = source.replace(
        "</body>",
        f"<!-- {_V16_MARKER} -->\n<!-- {_PROTOCOL_STATS_MARKER} -->\n</body>",
        1,
    )
    return source
