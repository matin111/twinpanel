from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..database import get_db
from .public_connection_hub_refine_v6 import refine_public_connection_hub_html
from .public_connection_hub_v5 import public_connection_hub_v5


router = APIRouter(
    prefix="/v1/connect",
    tags=["public-connection-hub-live-v5"],
)


_LIVE_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_HUB_LIVE_V5 */
.traffic[data-connection="online"]{
  border-color:color-mix(in srgb,var(--ok) 45%,var(--line));
  box-shadow:
    0 0 0 1px color-mix(in srgb,var(--ok) 12%,transparent),
    var(--shadow);
}
.status.connected{
  color:var(--ok);
  background:color-mix(in srgb,var(--ok) 10%,transparent);
  border:1px solid color-mix(in srgb,var(--ok) 34%,transparent);
}
.protocol-choice.live-online,
.protocol-choice.live-online.active{
  border-color:var(--ok);
  box-shadow:0 0 0 1px color-mix(in srgb,var(--ok) 24%,transparent);
}
.protocol-choice.live-online em{
  color:var(--ok);
  border-color:color-mix(in srgb,var(--ok) 32%,transparent);
  background:color-mix(in srgb,var(--ok) 8%,transparent);
}
.live-flash{animation:hubLiveFlash .4s ease}
@keyframes hubLiveFlash{0%{opacity:.55}100%{opacity:1}}
"""


_LIVE_SCRIPT = r"""
<script>
(function(){
  const token=__TOKEN__;
  const endpoint='/v1/connect/'+encodeURIComponent(token)+'/live';
  const nf=new Intl.NumberFormat('fa-IR',{maximumFractionDigits:2});
  const gib=1024*1024*1024,mib=1024*1024,kib=1024;
  const byId=id=>document.getElementById(id);
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
    const d=new Date(value);
    if(Number.isNaN(d.getTime()))return '—';
    const p=v=>String(v).padStart(2,'0');
    return d.getUTCFullYear()+'/'+p(d.getUTCMonth()+1)+'/'+p(d.getUTCDate());
  }
  function flash(el){
    if(!el)return;
    el.classList.remove('live-flash');
    void el.offsetWidth;
    el.classList.add('live-flash');
  }
  function write(el,value){
    if(!el||el.textContent===value)return;
    el.textContent=value;
    flash(el);
  }
  function normalizeProtocol(value){
    const p=String(value||'').trim().toLowerCase();
    if(p==='v2ray')return'xray';
    if(p==='openconnect'||p==='ocserv'||p==='anyconnect')return'cisco';
    return p;
  }
  function paintProtocols(protocols){
    const live=new Set((Array.isArray(protocols)?protocols:[]).map(normalizeProtocol));
    document.querySelectorAll('.protocol-choice').forEach(card=>{
      const key=normalizeProtocol(card.dataset.protocolKey||'');
      card.classList.toggle('live-online',Boolean(key)&&live.has(key));
    });
  }
  function apply(payload){
    const pct=payload.unlimited?0:Math.max(0,Math.min(100,Number(payload.percent||0)));
    write(used,bytes(payload.used_bytes));
    write(remaining,quota(payload.remaining_bytes,payload.unlimited));
    write(total,quota(payload.total_bytes,payload.unlimited));
    write(start,date(payload.starts_at));
    write(expire,date(payload.expires_at));
    write(percent,payload.unlimited?'∞':nf.format(pct)+'%');
    if(donut)donut.style.setProperty('--pct',String(pct));

    const connected=payload.connection_online===true||Number(payload.active_sessions||0)>0;
    const active=String(payload.subscription_status||'').toLowerCase()==='active';
    if(traffic)traffic.dataset.connection=connected?'online':'idle';
    if(status){
      status.className='status '+(connected?'connected':active?'on':'off');
      status.innerHTML='<i></i>'+(connected?'متصل':active?'اشتراک فعال':'غیرفعال');
    }
    paintProtocols(payload.online_protocols);

    const signature=[
      payload.used_bytes,
      payload.remaining_bytes,
      payload.starts_at,
      payload.expires_at,
      payload.active_sessions,
      payload.connection_online,
      (payload.online_protocols||[]).join(','),
      payload.subscription_status,
    ].join('|');
    if(previous&&signature!==previous&&traffic)flash(traffic);
    previous=signature;
  }
  async function refresh(){
    try{
      const response=await fetch(endpoint,{cache:'no-store',headers:{Accept:'application/json'}});
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
def public_connection_hub_live_v5(
    token: str,
    db: Session = Depends(get_db),
):
    """Render the V5 public hub and attach the existing V4 live-state API."""
    base = public_connection_hub_v5(token, db)
    source = base.body.decode(getattr(base, "charset", None) or "utf-8")

    source = source.replace(
        '<section class="traffic">',
        '<section id="trafficCard" class="traffic">',
        1,
    )
    source = re.sub(
        r'<div class="donut" style="--pct:([^"]*)">',
        lambda match: (
            '<div id="trafficDonut" class="donut" '
            f'style="--pct:{match.group(1)}">'
        ),
        source,
        count=1,
    )
    source = re.sub(
        r'(<div id="trafficDonut"[^>]*><div><b)(>)([^<]*)(</b>)',
        lambda match: (
            f'{match.group(1)} id="livePercent"'
            f'{match.group(2)}{match.group(3)}{match.group(4)}'
        ),
        source,
        count=1,
    )

    replacements = {
        '<small>مصرف‌شده</small><strong>':
            '<small>مصرف‌شده</small><strong id="liveUsed">',
        '<small>باقی‌مانده</small><strong>':
            '<small>باقی‌مانده</small><strong id="liveRemaining">',
        '<small>حجم کل</small><strong>':
            '<small>حجم کل</small><strong id="liveTotal">',
        '<small>تاریخ شروع</small><strong>':
            '<small>تاریخ شروع</small><strong id="liveStart">',
        '<small>تاریخ انقضا</small><strong>':
            '<small>تاریخ انقضا</small><strong id="liveExpire">',
    }
    for old, new in replacements.items():
        source = source.replace(old, new, 1)

    source = re.sub(
        r'<span class="status (on|off)">',
        lambda match: (
            f'<span id="liveStatus" class="status {match.group(1)}">'
        ),
        source,
        count=1,
    )

    source = source.replace(
        "</style>",
        _LIVE_CSS + "\n</style>",
        1,
    )
    script = _LIVE_SCRIPT.replace(
        "__TOKEN__",
        json.dumps(str(token), ensure_ascii=True),
    )
    source = source.replace(
        "</body>",
        script + "\n</body>",
        1,
    )
    source = refine_public_connection_hub_html(source)

    return HTMLResponse(
        content=source,
        status_code=base.status_code,
        headers={"Cache-Control": "no-store"},
    )
