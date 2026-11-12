from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..xray_public_hub_profiles_v48 import (
    apply_xray_public_hub_profiles_v48,
    refine_public_connection_xray_profiles_v48,
)
from .public_connection_hub_refine_v6 import refine_public_connection_hub_html
from .public_connection_mobile_v7 import refine_public_connection_mobile_v7
from .public_connection_hub_v8 import refine_public_connection_hub_v8
from .public_connection_manual_fields_v10 import refine_public_connection_manual_fields_v10
from .public_connection_device_actions_v11 import refine_public_connection_device_actions_v11
from .public_connection_windows_v12 import refine_public_connection_windows_v12
from .public_connection_modern_delivery_v13 import (
    refine_public_connection_modern_delivery_v13,
    router as public_connection_modern_delivery_v13_router,
)
from .public_connection_modern_names_v14 import (
    refine_public_connection_modern_names_v14,
    router as public_connection_modern_names_v14_router,
)
from .public_connection_modern_import_v15 import (
    refine_public_connection_modern_import_v15,
)
from .public_connection_modern_delivery_v16 import (
    refine_public_connection_modern_delivery_v16,
    router as public_connection_modern_delivery_v16_router,
)
# Import V18 before the V16 router is included below. V18 mounts its read-only
# mobile inventory endpoint into the V16 router at import time. The retired V18
# presentation refiner is intentionally not applied to the customer page.
from . import public_connection_mobile_server_inventory_v18 as _public_connection_mobile_server_inventory_v18  # noqa: F401
from .public_connection_protocol_actions_v20 import (
    refine_public_connection_protocol_actions_v20,
)
from .public_connection_canonical_mobile_v26 import (
    refine_public_connection_canonical_mobile_v26,
)
from .public_connection_files_v9 import router as public_connection_files_v9_router
from .public_connection_multilink_v7 import router as public_connection_multilink_v7_router
from . import public_connection_hub_v5 as _public_connection_hub_v5_module
from .public_connection_hub_v5 import public_connection_hub_v5
from .public_connection_live_v4 import public_connection_live
from .public_connection_payload_fast_v1 import public_connection_payload_fast_v1
from .public_connection_qr_deferred_v1 import (
    defer_public_connection_qr,
    router as public_connection_qr_deferred_router,
)


# TWINPANEL_PUBLIC_CONNECT_PAYLOAD_FAST_V1
# Hub V5 still imports the legacy payload symbol for compatibility. Point only
# the Hub module's global lookup at the lightweight page payload so unrelated
# account-delivery endpoints retain their historical QR behavior.
_public_connection_hub_v5_module._public_payload = public_connection_payload_fast_v1


router = APIRouter(
    prefix="/v1/connect",
    tags=["public-connection-hub-live-v5"],
)
router.include_router(public_connection_qr_deferred_router)
router.include_router(public_connection_multilink_v7_router)
router.include_router(public_connection_files_v9_router)
router.include_router(public_connection_modern_delivery_v13_router)
router.include_router(public_connection_modern_names_v14_router)
router.include_router(public_connection_modern_delivery_v16_router)
# The live hub is included by app.main; the legacy hub_v5.router is not.
# Register V78's authenticated live RTT endpoint on the exported router.


_LIVE_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_HUB_LIVE_V5 */
.traffic[data-connection="online"]{
  border-color:color-mix(in srgb,var(--ok) 45%,var(--line));
  box-shadow:
    0 0 0 1px color-mix(in srgb,var(--ok) 12%,transparent),
    var(--shadow);
}
.status.connected{
  font-size:11px;
  font-weight:900;
  color:var(--ok);
  background:color-mix(in srgb,var(--ok) 10%,transparent);
  border:1px solid color-mix(in srgb,var(--ok) 34%,transparent);
}
.profile:has(.status.connected){border:1px solid color-mix(in srgb,var(--ok) 65%,var(--line));border-radius:12px;padding:7px 10px;background:color-mix(in srgb,var(--ok) 7%,var(--surface));box-shadow:0 0 0 1px color-mix(in srgb,var(--ok) 12%,transparent)}
.traffic .stats{grid-template-columns:repeat(6,minmax(0,1fr));}
@media(max-width:720px){.traffic .stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
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
  const nf=new Intl.NumberFormat('en-US',{maximumFractionDigits:2});
  const gib=1024*1024*1024,mib=1024*1024,kib=1024;
  const byId=id=>document.getElementById(id);
  const used=byId('liveUsed'),remaining=byId('liveRemaining'),total=byId('liveTotal');
  const start=byId('liveStart'),expire=byId('liveExpire'),expiryDays=byId('liveExpiryDays'),percent=byId('livePercent');
  const donut=byId('trafficDonut'),status=byId('liveStatus'),traffic=byId('trafficCard'),deviceLimit=byId('liveDeviceLimit'),deviceActive=byId('liveActiveSessions'),deviceCombined=byId('liveDeviceCombined'),durationMetric=byId('liveDurationMetric');
  let previous='';

  function bytes(value){
    const n=Math.max(0,Number(value||0));
    if(n===0)return '0 MB';
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
  function validityLabel(payload){
    const configured=Math.max(0,Math.trunc(Number(payload.activation_duration_days||0)));
    const unlimited=payload.duration_unlimited===true||(!payload.expires_at&&configured<=0);
    const expiry=payload.expires_at?new Date(payload.expires_at):null;
    const validExpiry=expiry&&!Number.isNaN(expiry.getTime());
    if(validExpiry){
      const remaining=Math.max(0,Math.ceil((expiry.getTime()-Date.now())/86400000));
      return configured>0
        ?nf.format(configured)+' روزه · '+nf.format(remaining)+' روز باقی‌مانده'
        :nf.format(remaining)+' روز باقی‌مانده';
    }
    if(unlimited)return 'مدت نامحدود';
    if(configured>0&&!payload.starts_at)return nf.format(configured)+' روز · شروع با اولین اتصال';
    if(configured>0)return nf.format(configured)+' روز · تاریخ انقضا نامشخص';
    return 'مدت نامحدود';
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
    if(p==='naiveproxy')return'naive';
    return p;
  }
  function paintProtocols(protocols,stats){
    const live=new Set((Array.isArray(protocols)?protocols:[]).map(normalizeProtocol));
    const map=stats&&typeof stats==='object'?stats:{};
    document.querySelectorAll('.protocol-choice').forEach(card=>{
      const key=normalizeProtocol(card.dataset.protocolKey||'');
      if(!key)return;
      const item=map[key]||null;
      const online=item?item.online===true:live.has(key);
      card.classList.toggle('live-online',online);

      // Highlight only countries backed by recent live quota sessions or
      // positive traffic on the corresponding real node. Never infer a
      // country from the user's selected filter.
      const countries=new Set(
        (Array.isArray(item?.online_countries)?item.online_countries:[])
          .map(value=>String(value||'').toUpperCase())
      );
      const panel=document.getElementById(card.dataset.protocol||'');
      if(panel){
        panel.classList.toggle('live-online',online);
        panel.querySelectorAll(
          '.tp80-country-bar button,.tp92-v2-country-bar button,.tp93-country-bar button,.server-tabs button[data-country-code]'
        ).forEach(chip=>{
          const country=String(chip.dataset.tp80Country||chip.dataset.country||chip.dataset.countryCode||'').toUpperCase();
          chip.classList.toggle('live-online',online&&country!=='ALL'&&countries.has(country));
        });
      }

      const badge=card.querySelector('em');
      if(!badge)return;
      if(online)badge.textContent=key==='xray'?'فعال اخیراً':'آنلاین';
      else if(item&&item.presence_available)badge.textContent='آفلاین';
      else badge.textContent='آماده';
    });
  }
  function apply(payload){
    const pct=payload.unlimited?0:Math.max(0,Math.min(100,Number(payload.percent||0)));
    write(used,bytes(payload.used_bytes)+' / '+quota(payload.total_bytes,payload.unlimited));
    write(remaining,quota(payload.remaining_bytes,payload.unlimited));
    write(total,quota(payload.total_bytes,payload.unlimited));
    write(start,date(payload.starts_at));
    write(expire,payload.expires_at?date(payload.expires_at):(payload.duration_unlimited===true||Number(payload.activation_duration_days||0)<=0?'نامحدود':'پس از اولین اتصال'));
    write(expiryDays,validityLabel(payload));
    write(percent,payload.unlimited?'∞':nf.format(pct)+'%');
    const cap=Number(payload.device_limit||0),activeSessions=Math.max(0,Number(payload.active_sessions||0));
    write(deviceLimit,cap===0?'نامحدود':nf.format(cap)+' دستگاه');
    write(deviceActive,nf.format(activeSessions));
    write(deviceCombined,nf.format(activeSessions)+' / '+(cap===0?'∞':nf.format(cap)));
    const configuredDays=Math.max(0,Math.trunc(Number(payload.activation_duration_days||0)));
    const expiryTime=payload.expires_at?new Date(payload.expires_at).getTime():NaN;
    const remainingDays=Number.isFinite(expiryTime)?Math.max(0,Math.ceil((expiryTime-Date.now())/86400000)):0;
    write(durationMetric,Number.isFinite(expiryTime)?nf.format(configuredDays||remainingDays)+' روز':(payload.duration_unlimited===true||configuredDays<=0?'نامحدود':nf.format(configuredDays)+' روز'));
    if(donut)donut.style.setProperty('--pct',String(pct));

    const connected=payload.connection_online===true||Number(payload.active_sessions||0)>0;
    const active=String(payload.subscription_status||'').toLowerCase()==='active';
    if(traffic)traffic.dataset.connection=connected?'online':'idle';
    if(status){
      status.className='status '+(connected?'connected':active?'on':'off');
      status.innerHTML='<i></i>'+(connected?'متصل هستید':active?'اشتراک فعال':'غیرفعال');
    }
    paintProtocols(payload.online_protocols,payload.protocol_stats);

    const protocolSignature=Object.entries(payload.protocol_stats||{})
      .map(([key,item])=>[
        key,
        item?.online,
        item?.presence_available,
        (item?.online_countries||[]).join('|'),
      ].join(':'))
      .sort()
      .join(',');
    const signature=[
      payload.used_bytes,
      payload.remaining_bytes,
      payload.starts_at,
      payload.expires_at,
      payload.activation_duration_days,
      payload.duration_unlimited,
      payload.active_sessions,
      payload.device_limit,
      payload.connection_online,
      (payload.online_protocols||[]).join(','),
      protocolSignature,
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



# TWINPANEL_CONNECTION_APP_LOGIN_AUTHENTICATED_V1
def _add_authenticated_app_login_panel(source: str, subscription_id: int) -> str:
    """Add an app-login card to the actual /v1/connect page, not to the admin modal.

    The public share token never returns app passwords. An existing authenticated
    panel session must authorize a customer/reseller/admin delivery API call.
    """
    card = r"""
<style>
#tp-app-access{margin:16px 0;padding:18px;border:1px solid var(--line,#31394b);
border-radius:18px;background:color-mix(in srgb,var(--surface,#111722) 82%,transparent);
color:var(--text,#f4f7fb);box-shadow:0 8px 32px #0002}
#tp-app-access .tp-app-head{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
#tp-app-access .tp-app-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center;margin-top:10px}
#tp-app-access code{overflow-wrap:anywhere;direction:ltr;text-align:left;display:block;padding:10px;border-radius:9px;background:#080b1455}
#tp-app-access button{cursor:pointer;border:1px solid var(--line,#444);border-radius:10px;padding:9px 14px;background:var(--p,#7455cf);color:white}
#tp-app-access .tp-app-note{font-size:12px;opacity:.8;margin-top:9px}
#tp-app-access [hidden]{display:none!important}
</style>
<section id="tp-app-access" aria-label="ورود به اپ TwinConnect">
 <div class="tp-app-head"><strong>ورود به اپ TwinConnect</strong>
 <button id="tp-app-access-load" type="button">نمایش اطلاعات ورود اپ</button></div>
 <p class="tp-app-note" id="tp-app-access-status">نام کاربری و رمز اپ با اطلاعات VPN متفاوت است.</p>
 <div id="tp-app-access-values" hidden>
  <div class="tp-app-row"><code id="tp-app-access-username"></code><button type="button" data-app-copy="username">کپی نام کاربری</button></div>
  <div class="tp-app-row"><code id="tp-app-access-password"></code><button type="button" data-app-copy="password">کپی رمز</button></div>
  <button id="tp-app-access-copy-all" type="button">کپی هر دو</button>
 </div>
 <form id="tp-app-access-auth" hidden autocomplete="on" style="margin-top:12px;display:grid;gap:9px;max-width:420px">
  <label>ایمیل حساب پنل<input id="tp-app-email" type="email" autocomplete="username" required style="width:100%;padding:10px;border-radius:9px"></label>
  <label>رمز حساب پنل<input id="tp-app-login-password" type="password" autocomplete="current-password" required style="width:100%;padding:10px;border-radius:9px"></label>
  <label id="tp-app-otp-wrap" hidden>کد تأیید دومرحله‌ای<input id="tp-app-otp" inputmode="numeric" autocomplete="one-time-code" style="width:100%;padding:10px;border-radius:9px"></label>
  <button type="submit">تأیید هویت و نمایش اطلاعات اپ</button>
 </form>
</section>
<script>
(() => {
  const sid = __SUBSCRIPTION_ID__;
  const root = document.getElementById("tp-app-access");
  if (!root) return;
  const load = document.getElementById("tp-app-access-load");
  const info = document.getElementById("tp-app-access-status");
  const values = document.getElementById("tp-app-access-values");
  const auth = document.getElementById("tp-app-access-auth");
  const otpWrap = document.getElementById("tp-app-otp-wrap");
  let twoFactorToken = null;
  const username = document.getElementById("tp-app-access-username");
  const password = document.getElementById("tp-app-access-password");
  let credentials = null;
  const getToken = () => {
    try { return sessionStorage.getItem("twinpanel_customer_token") ||
       localStorage.getItem("twinpanel_customer_remember_token"); }
    catch (_) { return null; }
  };
  const showStatus = (message) => { info.textContent = message; };
  async function fetchOwnerDelivery(token) {
    for (const role of ["customer","reseller","admin"]) {
      const response = await fetch("/v1/central-app/" + role + "/subscriptions/" +
        sid + "/app-delivery", {
        method:"POST",headers:{"Authorization":"Bearer " + token},
        cache:"no-store",credentials:"same-origin"
      });
      if (response.ok) return response.json();
      if (response.status === 401) return null;
      if (response.status === 403) {
        const body = await response.json().catch(() => ({}));
        if (body.detail === "CENTRAL_APP_NOT_INCLUDED") throw new Error("APP_DISABLED");
      }
      if (![403,404].includes(response.status)) throw new Error("DELIVERY_FAILED");
    }
    throw new Error("ACCESS_DENIED");
  }
  load.addEventListener("click", async () => {
    const token = getToken();
    if (!token) {
      auth.hidden = false;
      showStatus("برای دریافت رمز اپ، با حساب پنل خود تأیید هویت کنید.");
      return;
    }
    load.disabled = true;
    showStatus("در حال دریافت امن اطلاعات ورود...");
    try {
      const result = await fetchOwnerDelivery(token);
      if (!result) {
        auth.hidden = false;
        showStatus("نشست ورود معتبر نیست؛ با حساب پنل تأیید هویت کنید.");
        return;
      }
      credentials = {username:result.app_username,password:result.app_password};
      username.textContent = credentials.username;
      password.textContent = credentials.password;
      values.hidden = false;
      auth.hidden = true;
      showStatus("اطلاعات ورود مخصوص همین اشتراک");
    } catch (error) {
      showStatus(error.message === "APP_DISABLED" ? "ورود اپ در لایسنس این پنل فعال نیست." :
        error.message === "ACCESS_DENIED" ? "دسترسی به اطلاعات این اشتراک مجاز نیست." :
        "دریافت اطلاعات اپ ممکن نشد. دوباره تلاش کنید.");
    } finally { load.disabled = false; }
  });
  // The Connection page is on a separate subdomain; panel localStorage
  // is intentionally not readable here. Authenticate directly with the
  // panel's same-origin API without persisting credentials or access tokens.
  auth.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = auth.querySelector('button[type="submit"]');
    button.disabled = true;
    const email = document.getElementById("tp-app-email");
    const secret = document.getElementById("tp-app-login-password");
    const otp = document.getElementById("tp-app-otp");
    try {
      let loginResponse;
      if (twoFactorToken) {
        loginResponse = await fetch("/v1/auth/2fa/login/verify", {
          method:"POST",headers:{"Content-Type":"application/json"},
          body:JSON.stringify({two_factor_token:twoFactorToken,code:otp.value}),
          cache:"no-store"
        });
      } else {
        loginResponse = await fetch("/v1/auth/login", {
          method:"POST",headers:{"Content-Type":"application/json"},
          body:JSON.stringify({email:email.value,password:secret.value}),
          cache:"no-store"
        });
      }
      secret.value = "";
      if (!loginResponse.ok) throw new Error("LOGIN_FAILED");
      const login = await loginResponse.json();
      if (login.requires_2fa) {
        twoFactorToken = login.two_factor_token;
        otpWrap.hidden = false;
        showStatus("کد تأیید دومرحله‌ای را وارد کنید.");
        return;
      }
      twoFactorToken = null;
      const result = await fetchOwnerDelivery(login.access_token);
      if (!result) throw new Error("ACCESS_DENIED");
      credentials = {username:result.app_username,password:result.app_password};
      username.textContent = credentials.username;
      password.textContent = credentials.password;
      values.hidden = false;
      auth.hidden = true;
      showStatus("اطلاعات ورود مخصوص همین اشتراک");
    } catch (error) {
      showStatus(error.message === "ACCESS_DENIED" ?
        "این حساب به اشتراک موردنظر دسترسی ندارد." :
        "تأیید هویت یا دریافت اطلاعات انجام نشد؛ اطلاعات را بررسی کنید.");
    } finally { button.disabled = false; }
  });
  root.querySelectorAll("[data-app-copy]").forEach((button) =>
    button.addEventListener("click", () => {
      if (credentials) navigator.clipboard.writeText(credentials[button.dataset.appCopy]).catch(() => {});
    })
  );
  document.getElementById("tp-app-access-copy-all").addEventListener("click", () => {
    if (credentials) navigator.clipboard.writeText("نام کاربری اپ: " +
      credentials.username + "\nرمز اپ: " + credentials.password).catch(() => {});
  });
})();
</script>
""".replace("__SUBSCRIPTION_ID__", str(int(subscription_id)))
    anchor = '<section id="trafficCard"'
    if anchor in source:
        return source.replace(anchor, card + anchor, 1)
    return source.replace("</body>", card + "</body>", 1)

@router.get("/{token}", response_class=HTMLResponse)
def public_connection_hub_live_v5(
    token: str,
    db: Session = Depends(get_db),
):
    """Render the V5 public hub and attach canonical live protocol status."""
    # V48 is idempotent and resolves the final V47 customer profile selector at
    # request time. Install it before Hub V5 renders this response.
    apply_xray_public_hub_profiles_v48()
    with defer_public_connection_qr(token):
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
        '<small>تاریخ اولین اتصال</small><strong>':
            '<small>تاریخ اولین اتصال</small><strong id="liveStart">',
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
        '<div class="stats">',
        '<div class="stats"><div class="stat"><small>اتصال مجاز</small><strong id="liveDeviceLimit">—</strong></div><div class="stat"><small>اتصال فعال</small><strong id="liveActiveSessions">—</strong></div>',
        1,
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
    source = refine_public_connection_mobile_v7(source, token)
    source = refine_public_connection_hub_v8(source)
    source = refine_public_connection_manual_fields_v10(source)
    source = refine_public_connection_device_actions_v11(source)
    source = refine_public_connection_windows_v12(source)
    source = refine_public_connection_modern_delivery_v13(source, token, db)
    source = refine_public_connection_modern_names_v14(source, token, db)
    source = refine_public_connection_modern_import_v15(source, token, db)
    source = refine_public_connection_modern_delivery_v16(source, token, db)
    source = refine_public_connection_protocol_actions_v20(source)
    source = refine_public_connection_xray_profiles_v48(source)
    source = refine_public_connection_canonical_mobile_v26(source)
    # Canonical desktop skin forces a five-column metrics strip. The older
    # template already has five cells; appending two produces wrapped/duplicate
    # rows. Keep exactly the five requested metrics without changing quota data.
    metrics = (
        '<div class="stats">'
        '<div class="stat"><small>دستگاه متصل / مجاز</small><strong id="liveDeviceCombined" dir="ltr">—</strong></div>'
        '<div class="stat"><small>مدت اشتراک</small><strong id="liveDurationMetric">—</strong></div>'
        '<div class="stat"><small>مصرف‌شده</small><strong id="liveUsed">—</strong></div>'
        '<div class="stat"><small>باقی‌مانده</small><strong id="liveRemaining">—</strong></div>'
        '<div class="stat"><small>تاریخ انقضا</small><strong id="liveExpire">—</strong><span id="liveExpiryDays" class="tp-expiry-days" style="display:block;margin-top:5px;font-size:11px;line-height:1.6;color:#b5c7e5;white-space:normal">—</span></div>'
        '</div>'
        # Preserve invisible legacy bindings that the live-refresh JS expects.
        '<span id="liveTotal" hidden></span><span id="liveStart" hidden></span><span id="liveDeviceLimit" hidden></span><span id="liveActiveSessions" hidden></span>'
    )
    source, metric_count = re.subn(
        r'<div class="stats">(?:(?!</section>).)*?</div></section>',
        lambda match: metrics + '</section>',
        source,
        count=1,
        flags=re.DOTALL,
    )
    if metric_count != 1:
        print("TWINPANEL_CONNECTION_METRICS_CANONICAL_NOT_FOUND", flush=True)
    source = source.replace(
        "پروتکل برای این اشتراک غیرفعال است",
        "پروتکل فعال است؛ کانفیگ نیاز به ساخت/Repair دارد",
    )

    # Pre-render canonical DB-backed presence as well as client polling.
    # This avoids showing a stale "اشتراک فعال" badge while scripts load,
    # and also works when a browser extension delays JavaScript.
    try:
        live = public_connection_live(token, db)
        cap = int(live.get("device_limit") or 0)
        sessions = max(int(live.get("active_sessions") or 0), 0)
        source = source.replace(
            '<strong id="liveDeviceCombined" dir="ltr">—</strong>',
            '<strong id="liveDeviceCombined" dir="ltr">' + str(sessions) + ' / ' + (str(cap) if cap else '∞') + '</strong>',
            1,
        )
        valid_days = max(int(live.get("activation_duration_days") or 0), 0)
        # An actual expiry timestamp takes precedence over a stale legacy
        # unlimited override. Never label a finite account as unlimited.
        duration_label = (
            str(valid_days) + ' روز'
            if live.get("expires_at") and valid_days
            else 'تا انقضا'
            if live.get("expires_at")
            else 'نامحدود'
            if live.get("duration_unlimited") is True or valid_days <= 0
            else str(valid_days) + ' روز'
        )
        source = source.replace(
            '<strong id="liveDurationMetric">—</strong>',
            '<strong id="liveDurationMetric">' + duration_label + '</strong>',
            1,
        )
        # The canonical layout replaces the old expiry-days element. Render
        # an initial DB-backed label before the live polling script starts.
        from datetime import datetime, timezone
        import math
        expiry_raw = live.get("expires_at")
        if expiry_raw:
            expiry_dt = datetime.fromisoformat(str(expiry_raw).replace("Z", "+00:00"))
            if expiry_dt.tzinfo is None:
                expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
            left = max(0, math.ceil(
                (expiry_dt - datetime.now(timezone.utc)).total_seconds() / 86400
            ))
            remaining_label = str(left) + " روز باقی‌مانده"
        elif live.get("duration_unlimited") is True or valid_days <= 0:
            remaining_label = "مدت نامحدود"
        elif not live.get("starts_at"):
            remaining_label = str(valid_days) + " روز · شروع با اولین اتصال"
        else:
            remaining_label = str(valid_days) + " روز اعتبار"
        source = re.sub(
            r'(<span id="liveExpiryDays"[^>]*>)[^<]*(</span>)',
            lambda match: match.group(1) + remaining_label + match.group(2),
            source,
            count=1,
        )
        source = source.replace(
            '<strong id="liveActiveSessions">—</strong>',
            '<strong id="liveActiveSessions">' + str(sessions) + '</strong>',
            1,
        )
        connected = live.get("connection_online") is True or sessions > 0
        if connected:
            source = re.sub(
                r'<span id="liveStatus" class="status (?:on|off)">[^<]*<i></i>[^<]*</span>',
                '<span id="liveStatus" class="status connected"><i></i>متصل هستید</span>',
                source, count=1,
            )
    except Exception:
        # Presentation hydration must never block config delivery.
        pass

    # Resolve the subscription using the existing private share-token authority;
    # no app password is rendered or returned to unauthenticated visitors.
    from .account_delivery import _subscription_from_share_token
    sub = _subscription_from_share_token(token, db)
    source = _add_authenticated_app_login_panel(source, int(sub.id))

    return HTMLResponse(
        content=source,
        status_code=base.status_code,
        headers={"Cache-Control": "no-store"},
    )
