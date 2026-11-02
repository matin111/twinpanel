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
  validated_at?:string;
  expires_at?:string|null;
  trial_expires_at?:string|null;
  seconds_remaining?:number|null;
  renewal_bot_url?:string;
};

type ReleaseStatus={
  current_version?:string;
  latest_version?:string;
  channel?:string;
  license?:LicenseState;
};

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  const raw=await response.text();
  let payload:any=null;
  if(raw){try{payload=JSON.parse(raw)}catch{payload=raw}}
  if(!response.ok)throw new Error(payload?.detail||`API error ${response.status}`);
  return payload as T;
}

function formatDate(value:string|undefined|null,locale:string){
  if(!value)return "—";
  const date=new Date(value);
  if(Number.isNaN(date.getTime()))return "—";
  try{return new Intl.DateTimeFormat(locale,{dateStyle:"medium"}).format(date)}catch{return date.toLocaleDateString()}
}

function remainingText(seconds:number|undefined|null,fa:boolean){
  if(seconds==null||!Number.isFinite(Number(seconds)))return "—";
  const value=Math.max(0,Number(seconds));
  const days=Math.floor(value/86400);
  const hours=Math.floor((value%86400)/3600);
  if(days>0)return fa?`${days.toLocaleString("fa-IR")} روز و ${hours.toLocaleString("fa-IR")} ساعت`:`${days}d ${hours}h`;
  return fa?`${hours.toLocaleString("fa-IR")} ساعت`:`${hours}h`;
}

export function LicenseCenter(){
  const {pick,lang}=useI18n();
  const fa=lang==="fa";
  const locale=fa?"fa-IR":"en-US";
  const [data,setData]=useState<ReleaseStatus|null>(null);
  const [licenseKey,setLicenseKey]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const license=data?.license||{};
  const status=String(license.status||"unknown");
  const expiry=license.expires_at||license.trial_expires_at;
  const renewalBot=String(license.renewal_bot_url||"").trim();

  const statusMeta=useMemo(()=>{
    const active=new Set(["licensed","license_expiring","trial_active","trial_expiring"]);
    const bad=new Set(["license_expired","trial_expired","revoked","suspended"]);
    return {
      tone:active.has(status)?(status.includes("expiring")?"warn":"ok"):bad.has(status)?"bad":"violet" as "ok"|"warn"|"bad"|"violet",
      label:active.has(status)
        ?pick(status.includes("trial")?"آزمایشی فعال":"لایسنس فعال",status.includes("trial")?"Trial active":"License active")
        :bad.has(status)
          ?pick("نیازمند تمدید","Renewal required")
          :pick("در انتظار فعال‌سازی","Awaiting activation")
    };
  },[status,pick]);

  const load=async()=>{
    try{
      setError("");
      setData(await request<ReleaseStatus>("/v1/admin/system/release/status"));
    }catch(e){setError(e instanceof Error?e.message:String(e))}
  };

  useEffect(()=>{void load()},[]);

  const activate=async()=>{
    const key=licenseKey.trim();
    if(key.length<8||busy)return;
    setBusy(true);setError("");setNotice("");
    try{
      await request("/v1/admin/system/license/activate",{method:"POST",body:JSON.stringify({license_key:key})});
      setLicenseKey("");
      setNotice(pick("لایسنس با موفقیت ثبت شد.","License activated successfully."));
      await load();
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  };

  return <Shell active="/admin/license">
    <div className="page">
      <div className="page-head">
        <div>
          <h1>{pick("مرکز لایسنس","License Center")}</h1>
          <p>{pick("فعال‌سازی، وضعیت اعتبار و تمدید لایسنس این نصب.","Activate, inspect and renew the license for this installation.")}</p>
        </div>
        <Badge tone={statusMeta.tone}>{statusMeta.label}</Badge>
      </div>

      <div className="stats-grid">
        <Card className="stat"><span className="stat-icon">✓</span><div><small>{pick("وضعیت","Status")}</small><b>{statusMeta.label}</b><em>{status}</em></div></Card>
        <Card className="stat"><span className="stat-icon">◷</span><div><small>{pick("زمان باقی‌مانده","Remaining")}</small><b>{remainingText(license.seconds_remaining,fa)}</b><em>{formatDate(expiry,locale)}</em></div></Card>
        <Card className="stat"><span className="stat-icon">◆</span><div><small>{pick("نسخه پنل","Panel version")}</small><b dir="ltr">{data?.current_version||"—"}</b><em>{data?.channel||"—"}</em></div></Card>
        <Card className="stat"><span className="stat-icon">◉</span><div><small>{pick("اعتبارسنجی","Validation")}</small><b>{license.validation||"—"}</b><em>{formatDate(license.validated_at,locale)}</em></div></Card>
      </div>

      {error&&<div className="notice danger"><b>{pick("خطا","Error")}</b><span>{error}</span></div>}
      {notice&&<div className="notice success"><b>{pick("انجام شد","Completed")}</b><span>{notice}</span></div>}

      <div className="grid gap-4 lg:grid-cols-[1.35fr_.65fr]">
        <Card>
          <div className="mb-5 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-black">{pick("فعال‌سازی لایسنس","Activate license")}</h2>
              <p className="mt-1 text-sm opacity-60">{pick("کلید صادرشده را وارد کنید؛ اعتبار روی همین نصب بررسی می‌شود.","Enter the issued key; validation is bound to this installation.")}</p>
            </div>
            <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-violet-500/10 text-xl">⌁</div>
          </div>

          <div className="rounded-2xl border border-violet-400/15 bg-violet-500/[.04] p-4">
            <label className="mb-2 block text-xs font-bold opacity-55">{pick("کلید لایسنس","License key")}</label>
            <div className="flex flex-col gap-3 sm:flex-row">
              <input
                dir="ltr"
                value={licenseKey}
                onChange={e=>setLicenseKey(e.target.value)}
                placeholder="TP-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX"
                className="min-w-0 flex-1 rounded-xl border border-white/10 bg-black/10 px-4 py-3 font-mono text-sm outline-none focus:border-violet-400/60"
              />
              <button className="primary whitespace-nowrap" disabled={busy||licenseKey.trim().length<8} onClick={()=>void activate()}>
                {busy?pick("در حال ثبت…","Activating…"):pick("ثبت لایسنس","Activate")}
              </button>
            </div>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl border border-white/10 bg-white/[.025] p-4">
              <div className="text-xs opacity-45">{pick("شناسه نصب","Installation ID")}</div>
              <div className="mt-2 truncate font-mono text-sm" dir="ltr">{license.installation_id||"—"}</div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/[.025] p-4">
              <div className="text-xs opacity-45">{pick("تاریخ انقضا","Expires")}</div>
              <div className="mt-2 font-bold">{formatDate(expiry,locale)}</div>
            </div>
          </div>
        </Card>

        <div className="space-y-4">
          <Card>
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-black">{pick("تمدید لایسنس","Renew license")}</h2>
                <p className="mt-1 text-xs opacity-55">{pick("برای خرید یا تمدید وارد ربات رسمی شوید.","Open the official renewal bot to purchase or renew.")}</p>
              </div>
              <div className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-500/10">↗</div>
            </div>
            {renewalBot?
              <a href={renewalBot} target="_blank" rel="noreferrer" className="block rounded-xl bg-emerald-500 px-4 py-3 text-center font-black text-black transition hover:brightness-105">
                {pick("باز کردن ربات تمدید","Open renewal bot")}
              </a>
              :<div className="rounded-xl border border-white/10 px-4 py-3 text-center text-sm opacity-40">{pick("لینک تمدید تنظیم نشده","Renewal link not configured")}</div>}
          </Card>

          <Card>
            <div className="mb-3 flex items-center gap-3">
              <div className="grid h-10 w-10 place-items-center rounded-xl bg-sky-500/10">⛓</div>
              <div>
                <h3 className="font-black">{pick("تأیید پرداخت زنجیره‌ای","On-chain verification")}</h3>
                <p className="text-xs opacity-55">{pick("بدون API Key اجباری","No mandatory API key")}</p>
              </div>
            </div>
            <p className="text-sm leading-7 opacity-70">{pick("تأیید تراکنش‌های کریپتو با هش تراکنش، مقصد، مبلغ و کانفرم شبکه انجام می‌شود و مسیر اصلی از RPC عمومی شبکه استفاده می‌کند.","Crypto transactions are verified from the transaction hash, destination, amount and network confirmations; the primary path uses public network RPC endpoints.")}</p>
          </Card>
        </div>
      </div>
    </div>
  </Shell>;
}
