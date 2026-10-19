from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..quota_models import QuotaSession, QuotaUsageEvent
from .account_delivery import _subscription_from_share_token, _usage_payload
from .public_connection_v3 import public_connection_page_v3


router = APIRouter(prefix="/v1/connect", tags=["public-connection-live-v4"])


# Xray StatsService does not expose an authoritative connection-open/close
# stream in the same way ocserv does. Treat a user as live when real Xray
# traffic has changed recently. The quota runtime polls every five seconds, so
# a 30-second window is intentionally wider than one missed poll while still
# expiring quickly after traffic stops.
_XRAY_LIVE_ACTIVITY_SECONDS = 30


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() + "Z"


def _latest(value_a: datetime | None, value_b: datetime | None) -> datetime | None:
    values = [value for value in (value_a, value_b) if value is not None]
    return max(values) if values else None


@router.get("/{token}/live")
def public_connection_live(token: str, db: Session = Depends(get_db)):
    """Small public live-state payload used by the connection delivery page."""
    sub = _subscription_from_share_token(token, db)
    usage = _usage_payload(db, sub)

    active_sessions = int(
        db.query(func.count(QuotaSession.id))
        .filter(
            QuotaSession.subscription_id == sub.id,
            QuotaSession.status == "active",
        )
        .scalar()
        or 0
    )
    last_session_seen = (
        db.query(func.max(QuotaSession.last_seen_at))
        .filter(
            QuotaSession.subscription_id == sub.id,
            QuotaSession.status == "active",
        )
        .scalar()
    )

    # Cisco has authoritative active QuotaSession rows. Xray accounting uses
    # cumulative StatsService counters and intentionally does not leave a fake
    # permanent session open. A positive Xray traffic delta in the recent
    # activity window is therefore the protocol-safe live signal for Xray.
    xray_cutoff = datetime.utcnow() - timedelta(seconds=_XRAY_LIVE_ACTIVITY_SECONDS)
    last_xray_activity = (
        db.query(func.max(QuotaUsageEvent.reported_at))
        .filter(
            QuotaUsageEvent.subscription_id == sub.id,
            QuotaUsageEvent.protocol == "xray",
            QuotaUsageEvent.billable_bytes > 0,
            QuotaUsageEvent.reported_at >= xray_cutoff,
        )
        .scalar()
    )

    connection_online = bool(active_sessions > 0 or last_xray_activity is not None)
    last_connection_seen = _latest(last_session_seen, last_xray_activity)

    status = str(getattr(sub.status, "value", sub.status)).lower()
    return {
        **usage,
        "subscription_status": status,
        "starts_at": _iso_utc(getattr(sub, "starts_at", None)),
        "expires_at": _iso_utc(getattr(sub, "expires_at", None)),
        "active_sessions": active_sessions,
        "connection_online": connection_online,
        "last_session_seen_at": _iso_utc(last_connection_seen),
    }


_LIVE_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_LIVE_V4 */
.page{width:min(1120px,92vw);padding:18px 0 42px}
.traffic{grid-template-columns:178px 1fr;gap:16px;min-height:124px;padding:14px 18px;border-radius:16px;transition:border-color .2s,box-shadow .2s}
.traffic[data-connection="online"]{border-color:color-mix(in srgb,var(--ok) 48%,#252c45);box-shadow:0 0 0 1px color-mix(in srgb,var(--ok) 12%,transparent),0 14px 42px rgba(0,0,0,.18)}
.visual{gap:12px}.donut{width:88px;height:88px;flex-basis:88px}.donut:before{inset:10px}.donut b{font-size:18px}.visual h2{font-size:15px}.stats{grid-template-columns:repeat(5,1fr)}.stat{padding:0 12px}.stat strong{font-size:13px;margin-top:5px}
.section-head{margin:18px 0 9px}.section-head h2{font-size:17px}.protocols{gap:9px}.protocol-choice{min-height:96px;border-radius:13px;gap:5px}.protocol-icon{width:38px;height:38px}.protocol-panel{margin-top:9px}.panel-head{min-height:58px;padding:11px 13px}.server-views{padding:12px}.fact{min-height:82px;padding:12px}.apps{margin-top:15px}.apps-head{padding:12px 14px}.platforms{padding:11px}.app-card{min-height:62px;padding:8px}
.section-head small,.protocol-choice small,.panel-head small,.apps-head small,.platform-title small,.app-card small,.profile-copy small{display:none!important}
.status.connected{color:#7af0b5;background:#0a3322;border:1px solid #1b8053;box-shadow:0 0 0 3px rgba(41,211,125,.08)}
.status.connected i{box-shadow:0 0 0 4px rgba(41,211,125,.12)}
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

    const signature=[u.used_bytes,u.remaining_bytes,u.starts_at,u.expires_at,u.active_sessions,u.connection_online,u.subscription_status].join('|');
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
