"use client";

import {useEffect,useMemo,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {Badge,Card,Shell} from "./ui";

type LicenseState={
  status?:string;
  installation_id?:string;
  validation?:string;
  validation_error?:string;
  validated_at?:string;
  edition?:string;
  release_channel?:string;
  expires_at?:string|null;
  trial_started_at?:string|null;
  trial_expires_at?:string|null;
  seconds_remaining?:number|null;
  offline_grace_seconds_remaining?:number|null;
  features?:string[];
  enforced?:boolean;
  renewal_bot_url?:string;
};

type ReleaseStatus={
  current_version?:string;
  latest_version?:string;
  channel?:string;
  license?:LicenseState;
};

type Tone="ok"|"warn"|"bad"|"violet";

const ACTIVE_STATES=new Set(["trial_active","trial_expiring","licensed","license_expiring"]);
const BAD_STATES=new Set(["trial_expired","license_expired","suspended","revoked"]);

class LicenseRequestError extends Error{
  status:number;
  constructor(message:string,status:number){
    super(message);
    this.name="LicenseRequestError";
    this.status=status;
  }
}

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  const raw=await response.text();
  let payload:unknown=null;
  if(raw){
    try{payload=JSON.parse(raw);}catch{payload=raw;}
  }
  if(!response.ok){
    const detail=payload&&typeof payload==="object"&&"detail" in payload
      ?String((payload as {detail:unknown}).detail)
      :`API error ${response.status}`;
    throw new LicenseRequestError(detail,response.status);
  }
  return payload as T;
}

function formatDate(value:string|undefined|null,locale:string){
  if(!value)return "—";
  const date=new Date(value);
  if(Number.isNaN(date.getTime()))return "—";
  try{return new Intl.DateTimeFormat(locale,{dateStyle:"medium",timeStyle:"short"}).format(date);}catch{return date.toLocaleString();}
}

function remainingText(seconds:number|undefined|null,fa:boolean){
  if(seconds==null||!Number.isFinite(Number(seconds)))return "—";
  const value=Math.max(0,Number(seconds));
  const days=Math.floor(value/86400);
  const hours=Math.floor((value%86400)/3600);
  const minutes=Math.floor((value%3600)/60);
  if(days>0)return fa?`${days.toLocaleString("fa-IR")} روز و ${hours.toLocaleString("fa-IR")} ساعت`:`${days}d ${hours}h`;
  if(hours>0)return fa?`${hours.toLocaleString("fa-IR")} ساعت و ${minutes.toLocaleString("fa-IR")} دقیقه`:`${hours}h ${minutes}m`;
  return fa?`${minutes.toLocaleString("fa-IR")} دقیقه`:`${minutes}m`;
}

function shortId(value:string|undefined){
  const raw=String(value||"").trim();
  if(!raw)return "—";
  if(raw.length<=22)return raw;
  return `${raw.slice(0,10)}…${raw.slice(-8)}`;
}

export function LicenseCenter(){
  const {pick,lang}=useI18n();
  const fa=lang==="fa";
  const locale=fa?"fa-IR":"en-US";
  const [data,setData]=useState<ReleaseStatus|null>(null);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [licenseKey,setLicenseKey]=useState("");
  const license=data?.license||{};
  const status=String(license.status||"unknown");

  const tone:Tone=useMemo(()=>{
    if(ACTIVE_STATES.has(status))return status.includes("expiring")?"warn":"ok";
    if(BAD_STATES.has(status))return "bad";
    return "violet";
  },[status]);

  const statusText=useMemo(()=>{
    const map:Record<string,[string,string]>={
      trial_active:["آزمایشی فعال","Trial active"],
      trial_expiring:["آزمایشی رو به پایان","Trial expiring"],
      trial_expired:["آزمایشی منقضی","Trial expired"],
      licensed:["لایسنس فعال","Licensed"],
      license_expiring:["لایسنس رو به پایان","License expiring"],
      license_expired:["لایسنس منقضی","License expired"],
      suspended:["تعلیق‌شده","Suspended"],
      revoked:["لغوشده","Revoked"],
      unconfigured:["هنوز فعال نشده","Not activated yet"],
      license_api_missing:["سرور لایسنس تنظیم نشده","License server not configured"],
      unknown:["نامشخص","Unknown"],
    };
    const item=map[status]||map.unknown;
    return pick(item[0],item[1]);
  },[status,pick]);

  const validationText=useMemo(()=>{
    const value=String(license.validation||"none");
    const map:Record<string,[string,string]>={
      online:["آنلاین و تأییدشده","Online / verified"],
      offline_grace:["مهلت آفلاین","Offline grace"],
      offline_cache:["اعتبارسنجی آفلاین","Offline cache"],
      server_unreachable:["سرور لایسنس در دسترس نیست","License server unreachable"],
      none:["هنوز اعتبارسنجی نشده","Not validated yet"],
    };
    const item=map[value]||[value,value];
    return pick(item[0],item[1]);
  },[license.validation,pick]);

  const load=async()=>{
    try{
      setError("");
      const result=await request<ReleaseStatus>("/v1/admin/system/release/status");
      setData(result);
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }
  };

  useEffect(()=>{void load();},[]);

  const run=async(action:"validate"|"trial"|"activate")=>{
    if(busy)return;
    setBusy(action);
    setError("");
    setNotice("");
    try{
      const path=`/v1/admin/system/license/${action}`;
      const init:RequestInit={method:"POST"};
      if(action==="activate"){
        const key=licenseKey.trim();
        if(key.length<8)throw new Error("LICENSE_KEY_INVALID");
        init.body=JSON.stringify({license_key:key});
      }
      await request<LicenseState>(path,init);
      if(action==="activate")setLicenseKey("");
      setNotice(action==="trial"
        ?pick("دوره آزمایشی با موفقیت ثبت/بازیابی شد.","Trial entitlement was created/recovered successfully.")
        :action==="activate"
          ?pick("لایسنس با موفقیت روی همین نصب فعال شد.","The license was activated on this installation.")
          :pick("وضعیت لایسنس از سرور بروزرسانی شد.","License status was refreshed from the server."));
      await load();
    }catch(reason){
      const raw=reason instanceof Error?reason.message:String(reason);
      const friendly=raw.includes("LICENSE_API_NOT_CONFIGURED")
        ?pick("آدرس سرور لایسنس هنوز روی این نصب تنظیم نشده است.","The license server URL is not configured on this installation.")
        :raw.includes("LICENSE_PUBLIC_KEY_MISSING")
          ?pick("کلید عمومی اعتبارسنجی لایسنس روی سرور نصب نشده است.","The license verification public key is missing on the server.")
          :raw.includes("LICENSE_KEY_INVALID")
            ?pick("کلید لایسنس معتبر نیست.","The license key is invalid.")
            :raw;
      setError(friendly);
    }finally{
      setBusy("");
    }
  };

  const canStartTrial=status==="unconfigured"||status==="unknown";
  const remaining=remainingText(license.seconds_remaining,fa);
  const expiry=license.trial_expires_at||license.expires_at;
  const features=Array.isArray(license.features)?license.features:[];
  const renewalBot=String(license.renewal_bot_url||"").trim();

  return <Shell active="/admin/license">
    <div className="page">
      <div className="page-head">
        <div>
          <h1>{pick("مرکز لایسنس","License Center")}</h1>
          <p>{pick("مدیریت دوره آزمایشی، فعال‌سازی لایسنس و وضعیت اعتبارسنجی این نصب.","Manage trial access, paid activation and validation for this installation.")}</p>
        </div>
        <button type="button" className="primary" disabled={busy==="validate"} onClick={()=>void run("validate")}>{busy==="validate"?"…":pick("اعتبارسنجی مجدد","Validate now")}</button>
      </div>

      {error&&<div className="notice danger"><b>{pick("خطا","Error")}</b><span>{error}</span></div>}
      {notice&&<div className="notice success"><b>{pick("انجام شد","Completed")}</b><span>{notice}</span></div>}

      <div className="stats-grid">
        <Card className="stat"><span className="stat-icon">◉</span><div><small>{pick("وضعیت","Status")}</small><b>{statusText}</b><Badge tone={tone}>{status}</Badge></div></Card>
        <Card className="stat"><span className="stat-icon">◷</span><div><small>{pick("زمان باقی‌مانده","Remaining")}</small><b>{remaining}</b><em>{formatDate(expiry,locale)}</em></div></Card>
        <Card className="stat"><span className="stat-icon">✓</span><div><small>{pick("اعتبارسنجی","Validation")}</small><b>{validationText}</b><em>{formatDate(license.validated_at,locale)}</em></div></Card>
        <Card className="stat"><span className="stat-icon">◆</span><div><small>{pick("نسخه / کانال","Version / channel")}</small><b dir="ltr">{data?.current_version||"—"}</b><em>{license.release_channel||data?.channel||"—"}</em></div></Card>
      </div>

      <div className="grid two">
        <Card>
          <div className="section-head"><div><h2>{pick("مشخصات این نصب","Installation identity")}</h2><p>{pick("این شناسه برای اتصال Trial و لایسنس به همین سرور استفاده می‌شود.","This identity binds trial and paid entitlements to this server.")}</p></div></div>
          <div className="detail-list">
            <div><span>{pick("Installation ID","Installation ID")}</span><code dir="ltr" title={license.installation_id||""}>{shortId(license.installation_id)}</code></div>
            <div><span>{pick("Edition","Edition")}</span><b>{license.edition||"standard"}</b></div>
            <div><span>{pick("اجرای محدودیت","Enforcement")}</span><Badge tone={license.enforced?"ok":"warn"}>{license.enforced?pick("فعال","Enabled"):pick("غیرفعال","Disabled")}</Badge></div>
            <div><span>{pick("وضعیت ارتباط","Vendor connection")}</span><b>{validationText}</b></div>
            {license.offline_grace_seconds_remaining!=null&&<div><span>{pick("مهلت آفلاین باقی‌مانده","Offline grace remaining")}</span><b>{remainingText(license.offline_grace_seconds_remaining,fa)}</b></div>}
          </div>
        </Card>

        <Card>
          <div className="section-head"><div><h2>{pick("فعال‌سازی لایسنس","Activate paid license")}</h2><p>{pick("کلید خریداری‌شده را وارد کنید. کاربران، نودها و تنظیمات فعلی بدون تغییر می‌مانند.","Enter a purchased key. Existing users, nodes and configuration remain untouched.")}</p></div></div>
          <label className="field"><span>{pick("کد لایسنس","License key")}</span><input dir="ltr" autoComplete="off" value={licenseKey} onChange={event=>setLicenseKey(event.target.value)} placeholder="TP-XXXX-XXXX-XXXX"/></label>
          <div className="row-actions">
            <button type="button" className="primary" disabled={busy==="activate"||licenseKey.trim().length<8} onClick={()=>void run("activate")}>{busy==="activate"?"…":pick("ثبت و فعال‌سازی لایسنس","Save & activate license")}</button>
            {canStartTrial&&<button type="button" disabled={busy==="trial"} onClick={()=>void run("trial")}>{busy==="trial"?"…":pick("شروع / بازیابی ۷ روز آزمایشی","Start / recover 7-day trial")}</button>}
          </div>
          <small>{pick("کد لایسنس در رابط کاربری نمایش یا ذخیره نمی‌شود؛ Backend آن را فقط برای فعال‌سازی به سرور لایسنس ارسال می‌کند.","The license key is not displayed or persisted by the UI; the backend only forwards it to the license service for activation.")}</small>
        </Card>
      </div>

      {renewalBot&&<Card>
        <div className="section-head"><div><h2>{pick("خرید و تمدید لایسنس","Buy / renew license")}</h2><p>{pick("این لینک فقط در بخش مدیریت نمایش داده می‌شود و برای کاربران عادی قابل مشاهده نیست.","This link is visible only in the admin area and is never exposed to regular users.")}</p></div></div>
        <div className="row-actions">
          <a className="primary" href={renewalBot} target="_blank" rel="noreferrer">{pick("باز کردن ربات خرید و تمدید","Open purchase / renewal bot")}</a>
        </div>
      </Card>}

      <Card>
        <div className="section-head"><div><h2>{pick("سیاست دسترسی","Access policy")}</h2><p>{pick("قطع موقت سرور لایسنس نباید VPN کاربران را قطع کند.","A temporary license-server outage must not interrupt existing VPN traffic.")}</p></div></div>
        <div className="detail-list">
          <div><span>{pick("Trial فعال","Active trial")}</span><b>{pick("تمام امکانات مدیریت فعال است","Full management enabled")}</b></div>
          <div><span>{pick("Grace آفلاین","Offline grace")}</span><b>{pick("سرویس کاربران ادامه دارد؛ اعتبارسنجی بعداً تکرار می‌شود","User service continues; validation retries later")}</b></div>
          <div><span>{pick("Expired / Revoked","Expired / Revoked")}</span><b>{pick("ورود، فعال‌سازی لایسنس، بکاپ و عیب‌یابی در دسترس می‌ماند","Login, licensing, backup and diagnostics remain available")}</b></div>
        </div>
        {features.length>0&&<div className="chips">{features.map(item=><span className="chip" key={item}>{item}</span>)}</div>}
      </Card>
    </div>
  </Shell>;
}
