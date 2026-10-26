from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import SubscriptionProtocol
from ..quota_models import QuotaCursor, QuotaSession, QuotaUsageEvent
from ..services.modern_quota_runtime_v257 import capability_payload
from .account_delivery import _subscription_from_share_token, _usage_payload
from .public_connection_v3 import public_connection_page_v3


router = APIRouter(prefix="/v1/connect", tags=["public-connection-live-v4"])


_LIVE_ACTIVITY_SECONDS = 30


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() + "Z"


def _latest(value_a: datetime | None, value_b: datetime | None) -> datetime | None:
    values = [value for value in (value_a, value_b) if value is not None]
    return max(values) if values else None


def _earliest(value_a: datetime | None, value_b: datetime | None) -> datetime | None:
    values = [value for value in (value_a, value_b) if value is not None]
    return min(values) if values else None


def _normalized_protocol(value: str | None) -> str:
    protocol = str(value or "").strip().lower()
    if protocol == "v2ray":
        return "xray"
    if protocol in {"openconnect", "ocserv", "anyconnect"}:
        return "cisco"
    if protocol == "naiveproxy":
        return "naive"
    return protocol


def _protocol_stats(
    db: Session,
    *,
    subscription_id: int,
    online_protocols: set[str],
    activity_cutoff: datetime,
) -> dict[str, dict]:
    selected = {
        _normalized_protocol(row[0])
        for row in (
            db.query(SubscriptionProtocol.protocol)
            .filter(SubscriptionProtocol.subscription_id == int(subscription_id))
            .all()
        )
        if _normalized_protocol(row[0])
    }

    session_rows = (
        db.query(
            QuotaSession.protocol,
            func.min(QuotaSession.started_at),
            func.max(QuotaSession.last_seen_at),
        )
        .filter(QuotaSession.subscription_id == int(subscription_id))
        .group_by(QuotaSession.protocol)
        .all()
    )
    session_meta: dict[str, dict] = {}
    for raw_protocol, first_seen, last_seen in session_rows:
        key = _normalized_protocol(raw_protocol)
        if not key:
            continue
        item = session_meta.setdefault(
            key,
            {"first": None, "last": None},
        )
        item["first"] = _earliest(item["first"], first_seen)
        item["last"] = _latest(item["last"], last_seen)
        selected.add(key)

    active_rows = (
        db.query(
            QuotaSession.protocol,
            func.count(QuotaSession.id),
            func.max(QuotaSession.last_seen_at),
        )
        .filter(
            QuotaSession.subscription_id == int(subscription_id),
            QuotaSession.status == "active",
            QuotaSession.last_seen_at >= activity_cutoff,
        )
        .group_by(QuotaSession.protocol)
        .all()
    )
    active_meta: dict[str, dict] = {}
    for raw_protocol, count, last_seen in active_rows:
        key = _normalized_protocol(raw_protocol)
        if not key:
            continue
        bucket = active_meta.setdefault(key, {"count": 0, "last": None})
        bucket["count"] += int(count or 0)
        bucket["last"] = _latest(bucket["last"], last_seen)
        selected.add(key)

    usage_rows = (
        db.query(
            QuotaUsageEvent.protocol,
            func.coalesce(func.sum(QuotaUsageEvent.accepted_bytes), 0),
            func.min(QuotaUsageEvent.reported_at),
            func.max(QuotaUsageEvent.reported_at),
            func.count(QuotaUsageEvent.id),
        )
        .filter(
            QuotaUsageEvent.subscription_id == int(subscription_id),
            QuotaUsageEvent.accepted_bytes > 0,
        )
        .group_by(QuotaUsageEvent.protocol)
        .all()
    )
    usage_meta: dict[str, dict] = {}
    for raw_protocol, used, first_seen, last_seen, event_count in usage_rows:
        key = _normalized_protocol(raw_protocol)
        if not key:
            continue
        bucket = usage_meta.setdefault(
            key,
            {"used": 0, "first": None, "last": None, "events": 0},
        )
        bucket["used"] += int(used or 0)
        bucket["first"] = _earliest(bucket["first"], first_seen)
        bucket["last"] = _latest(bucket["last"], last_seen)
        bucket["events"] += int(event_count or 0)
        selected.add(key)

    cursor_rows = (
        db.query(
            QuotaCursor.protocol,
            func.min(QuotaCursor.updated_at),
        )
        .filter(QuotaCursor.subscription_id == int(subscription_id))
        .group_by(QuotaCursor.protocol)
        .all()
    )
    cursor_meta: dict[str, datetime | None] = {}
    for raw_protocol, started_at in cursor_rows:
        key = _normalized_protocol(raw_protocol)
        if not key:
            continue
        cursor_meta[key] = _earliest(cursor_meta.get(key), started_at)
        selected.add(key)

    capabilities = capability_payload()
    stats: dict[str, dict] = {}
    for key in sorted(selected):
        session = session_meta.get(key, {})
        active = active_meta.get(key, {})
        usage = usage_meta.get(key, {})
        capability = capabilities.get(key, {})

        has_usage_events = int(usage.get("events") or 0) > 0
        traffic_supported = bool(capability.get("traffic")) or has_usage_events
        presence_supported = (
            bool(capability.get("presence"))
            or key in session_meta
            or has_usage_events
        )

        first_connected = _earliest(
            session.get("first"),
            usage.get("first"),
        )
        last_activity = _latest(
            session.get("last"),
            usage.get("last"),
        )
        last_activity = _latest(last_activity, active.get("last"))

        stats[key] = {
            "protocol": key,
            "online": key in online_protocols,
            "active_sessions": int(active.get("count") or 0),
            "presence_available": presence_supported,
            "traffic_accounting_available": traffic_supported,
            "used_bytes": int(usage.get("used") or 0) if traffic_supported else None,
            "first_connected_at": _iso_utc(first_connected),
            "last_activity_at": _iso_utc(last_activity),
            "accounting_since": _iso_utc(cursor_meta.get(key)),
        }

    return stats


@router.get("/{token}/live")
async def public_connection_live(token: str, db: Session = Depends(get_db)):
    """Public canonical live state and per-protocol accounting summary.

    This request path is deliberately DB-only. Runtime I/O (including WG/AWG
    peer snapshots) belongs to the Modern Accounting collector, which writes
    canonical QuotaSession/QuotaUsageEvent state in the background. Keeping
    SSH/runtime probes out of the 3-second browser poll prevents request piles,
    lock contention and long-held DB sessions without changing billing data.
    """

    sub = _subscription_from_share_token(token, db)
    usage = _usage_payload(db, sub)
    activity_cutoff = datetime.utcnow() - timedelta(seconds=_LIVE_ACTIVITY_SECONDS)

    active_session_rows = (
        db.query(
            QuotaSession.protocol,
            func.max(QuotaSession.last_seen_at),
            func.count(QuotaSession.id),
        )
        .filter(
            QuotaSession.subscription_id == sub.id,
            QuotaSession.status == "active",
            QuotaSession.last_seen_at >= activity_cutoff,
        )
        .group_by(QuotaSession.protocol)
        .all()
    )

    online_protocols: set[str] = set()
    last_session_seen: datetime | None = None
    active_sessions = 0
    for raw_protocol, seen_at, count in active_session_rows:
        protocol = _normalized_protocol(raw_protocol)
        if protocol:
            online_protocols.add(protocol)
        last_session_seen = _latest(last_session_seen, seen_at)
        active_sessions += int(count or 0)

    recent_activity_rows = (
        db.query(QuotaUsageEvent.protocol, func.max(QuotaUsageEvent.reported_at))
        .filter(
            QuotaUsageEvent.subscription_id == sub.id,
            QuotaUsageEvent.accepted_bytes > 0,
            QuotaUsageEvent.reported_at >= activity_cutoff,
        )
        .group_by(QuotaUsageEvent.protocol)
        .all()
    )
    last_counter_activity: datetime | None = None
    for raw_protocol, reported_at in recent_activity_rows:
        protocol = _normalized_protocol(raw_protocol)
        if protocol:
            online_protocols.add(protocol)
        last_counter_activity = _latest(last_counter_activity, reported_at)

    connection_online = bool(online_protocols)
    last_connection_seen = _latest(last_session_seen, last_counter_activity)

    protocol_stats = _protocol_stats(
        db,
        subscription_id=int(sub.id),
        online_protocols=online_protocols,
        activity_cutoff=activity_cutoff,
    )

    status = str(getattr(sub.status, "value", sub.status)).lower()
    return {
        **usage,
        "subscription_status": status,
        "starts_at": _iso_utc(getattr(sub, "starts_at", None)),
        "expires_at": _iso_utc(getattr(sub, "expires_at", None)),
        "active_sessions": active_sessions,
        "connection_online": connection_online,
        "online_protocols": sorted(online_protocols),
        "last_session_seen_at": _iso_utc(last_connection_seen),
        "protocol_stats": protocol_stats,
    }


_LIVE_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_LIVE_V4 */
.page{width:min(1120px,92vw);padding:18px 0 42px}
.traffic{grid-template-columns:178px 1fr;gap:16px;min-height:124px;padding:14px 18px;border-radius:16px;transition:border-color .2s,box-shadow .2s}
.traffic[data-connection="online"]{border-color:color-mix(in srgb,var(--ok) 48%,#252c45);box-shadow:0 0 0 1px color-mix(in srgb,var(--ok) 12%,transparent),0 14px 42px rgba(0,0,0,.18)}
.visual{gap:12px}.donut{width:88px;height:88px;flex-basis:88px}.donut:before{inset:10px}.donut b{font-size:18px}.visual h2{font-size:15px}.stats{grid-template-columns:repeat(5,1fr)}.stat{padding:0 12px}.stat strong{font-size:13px;margin-top:5px}
.section-head{margin:18px 0 9px}.section-head h2{font-size:17px}.protocols{gap:9px}.protocol-choice{min-height:96px;border-radius:13px;gap:5px;transition:border-color .2s,box-shadow .2s,background .2s}.protocol-icon{width:38px;height:38px}.protocol-panel{margin-top:9px}.panel-head{min-height:58px;padding:11px 13px}.server-views{padding:12px}.fact{min-height:82px;padding:12px}.apps{margin-top:15px}.apps-head{padding:12px 14px}.platforms{padding:11px}.app-card{min-height:62px;padding:8px}
.section-head small,.protocol-choice small,.panel-head small,.apps-head small,.platform-title small,.app-card small,.profile-copy small{display:none!important}
.status.connected{color:#7af0b5;background:#0a3322;border:1px solid #1b8053;box-shadow:0 0 0 3px rgba(41,211,125,.08)}
.status.connected i{box-shadow:0 0 0 4px rgba(41,211,125,.12)}
.protocol-choice.live-online,.protocol-choice.live-online.active{border-color:#29d37d!important;box-shadow:0 0 0 1px rgba(41,211,125,.38),0 0 24px rgba(41,211,125,.14)!important;background:linear-gradient(180deg,rgba(41,211,125,.07),rgba(41,211,125,.02))!important}
.protocol-choice.live-online em{color:#7af0b5!important;background:#0a3322!important;border-color:#1b8053!important}
.live-flash{animation:liveFlash .45s ease}@keyframes liveFlash{0%{opacity:.48}100%{opacity:1}}
@media(max-width:760px){.page{width:min(94vw,680px)}.traffic{grid-template-columns:1fr;padding:13px}.stats{grid-template-columns:repeat(2,1fr)}.stat{padding:10px}.protocol-choice{min-height:90px}}
"""


_LIVE_SCRIPT = r"""
<script>
(function(){
  const token=__TOKEN__;
  const endpoint='/v1/connect/'+encodeURIComponent(token)+'/live';
  const nf=new Intl.NumberFormat('fa-IR',{maximumFractionDigits:2});
  const gib=1024*1024*1024, mib=1024*1024, kib=1024;
  const byId=(id)=>document.getElementById(id);
  const used=byId('liveUsed'),remaining=byId('liveRemaining'),total=byId('liveTotal');
  const start=byId('liveStart'),expire=byId('liveExpire'),percent=byId('livePercent');
  const donut=byId('trafficDonut'),status=byId('liveStatus'),traffic=byId('trafficCard');
  let previous='';

  function bytes(value){
    const n=Math.max(0,Number(value||0));
    if(n===0)return '۰ MB';
    if(n<mib)return nf.format(n/kib)+' KB';
    if(n<gib)return nf.format(n/mib)+' MB';
    return nf.format(n/gib)+' GB';
  }
  function quota(value,unlimited){return unlimited?'∞':bytes(value);}
  function date(value){
    if(!value)return '—';
    const d=new Date(value);if(Number.isNaN(d.getTime()))return '—';
    const p=(v)=>String(v).padStart(2,'0');
    return d.getUTCFullYear()+'/'+p(d.getUTCMonth()+1)+'/'+p(d.getUTCDate());
  }
  function flash(el){if(!el)return;el.classList.remove('live-flash');void el.offsetWidth;el.classList.add('live-flash');}
  function write(el,value){if(!el||el.textContent===value)return;el.textContent=value;flash(el);}
  function cardProtocol(card){
    const text=(card.querySelector('b')?.textContent||'').toLowerCase();
    if(text.includes('cisco')||text.includes('anyconnect')||text.includes('openconnect'))return 'cisco';
    if(text.includes('openvpn'))return 'openvpn';
    if(text.includes('amneziawg'))return 'amneziawg';
    if(text.includes('wireguard'))return 'wireguard';
    if(text.includes('l2tp'))return 'l2tp';
    if(text.includes('v2ray')||text.includes('xray'))return 'xray';
    if(text.includes('hysteria2'))return 'hysteria2';
    if(text.includes('tuic'))return 'tuic';
    if(text.includes('anytls'))return 'anytls';
    if(text.includes('naive'))return 'naive';
    if(text.includes('shadowtls'))return 'shadowtls';
    if(text.includes('snell'))return 'snell';
    if(text.includes('mieru'))return 'mieru';
    if(text.includes('trusttunnel'))return 'trusttunnel';
    if(text.includes('sudoku'))return 'sudoku';
    return '';
  }
  function paintProtocols(protocols){
    const live=new Set((Array.isArray(protocols)?protocols:[]).map(v=>String(v||'').toLowerCase()==='v2ray'?'xray':String(v||'').toLowerCase()));
    document.querySelectorAll('.protocol-choice').forEach(card=>{
      card.classList.toggle('live-online',live.has(cardProtocol(card)));
    });
  }
  function apply(u){
    const pct=u.unlimited?0:Math.max(0,Math.min(100,Number(u.percent||0)));
    write(used,bytes(u.used_bytes));
    write(remaining,quota(u.remaining_bytes,u.unlimited));
    write(total,quota(u.total_bytes,u.unlimited));
    write(start,date(u.starts_at));
    write(expire,date(u.expires_at));
    write(percent,u.unlimited?'∞':nf.format(pct)+'%');
    if(donut)donut.style.setProperty('--pct',String(pct));

    const connected=(u.connection_online===true)||Number(u.active_sessions||0)>0;
    if(traffic)traffic.dataset.connection=connected?'online':'idle';
    if(status){
      const active=String(u.subscription_status||'')==='active';
      status.className='status '+(connected?'connected':active?'on':'off');
      status.innerHTML='<i></i>'+(connected?'متصل':active?'اشتراک فعال':'غیرفعال');
    }
    paintProtocols(u.online_protocols);

    const signature=[u.used_bytes,u.remaining_bytes,u.starts_at,u.expires_at,u.active_sessions,u.connection_online,(u.online_protocols||[]).join(','),u.subscription_status].join('|');
    if(previous&&signature!==previous&&traffic)flash(traffic);
    previous=signature;
  }
  async function refresh(){
    try{
      const response=await fetch(endpoint,{cache:'no-store',headers:{'Accept':'application/json'}});
      if(!response.ok)return;
      apply(await response.json());
    }catch(_error){}
  }
  refresh();
  const timer=setInterval(refresh,3000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
  window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});
})();
</script>
"""


@router.get("/{token}", response_class=HTMLResponse)
def public_connection_page_live_v4(token: str, db: Session = Depends(get_db)):
    """Keep the V3 design, add compact density and real live state polling."""
    sub = _subscription_from_share_token(token, db)
    base = public_connection_page_v3(token, db)
    source = base.body.decode(getattr(base, "charset", None) or "utf-8")

    source = re.sub(
        r'<section class="traffic">',
        '<section id="trafficCard" class="traffic">',
        source,
        count=1,
    )
    source = re.sub(
        r'<div class="donut" style="--pct:([^"]*)">',
        lambda match: f'<div id="trafficDonut" class="donut" style="--pct:{match.group(1)}">',
        source,
        count=1,
    )
    source = re.sub(
        r'(<div id="trafficDonut"[^>]*><div><b)(>)([^<]*)(</b>)',
        lambda match: f'{match.group(1)} id="livePercent"{match.group(2)}{match.group(3)}{match.group(4)}',
        source,
        count=1,
    )

    replacements = {
        '<small>مصرف‌شده</small><strong>': '<small>مصرف‌شده</small><strong id="liveUsed">',
        '<small>باقی‌مانده</small><strong>': '<small>باقی‌مانده</small><strong id="liveRemaining">',
        '<small>حجم کل</small><strong>': '<small>حجم کل</small><strong id="liveTotal">',
        '<small>تاریخ شروع</small><strong>': '<small>تاریخ شروع</small><strong id="liveStart">',
        '<small>تاریخ انقضا</small><strong>': '<small>تاریخ انقضا</small><strong id="liveExpire">',
    }
    for old, new in replacements.items():
        source = source.replace(old, new, 1)

    source = re.sub(
        r'<span class="status (on|off)">',
        lambda match: f'<span id="liveStatus" class="status {match.group(1)}">',
        source,
        count=1,
    )

    if getattr(sub, "starts_at", None) is None:
        source = re.sub(
            r'(<strong id="liveStart">)[^<]*(</strong>)',
            lambda match: f'{match.group(1)}—{match.group(2)}',
            source,
            count=1,
        )
    if getattr(sub, "expires_at", None) is None:
        source = re.sub(
            r'(<strong id="liveExpire">)[^<]*(</strong>)',
            lambda match: f'{match.group(1)}—{match.group(2)}',
            source,
            count=1,
        )

    source = source.replace("</style>", _LIVE_CSS + "\n</style>", 1)
    script = _LIVE_SCRIPT.replace("__TOKEN__", json.dumps(str(token), ensure_ascii=True))
    source = source.replace("</body>", script + "\n</body>", 1)

    return HTMLResponse(
        content=source,
        status_code=base.status_code,
        headers={"Cache-Control": "no-store"},
    )
