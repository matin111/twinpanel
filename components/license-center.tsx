"use client";

import {useEffect,useMemo,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {Badge,Shell} from "./ui";

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

  const close=()=>{
    if(typeof window==="undefined")return;
    if(window.history.length>1)window.history.back();
    else window.location.href="/admin";
  };

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

  const statItems=[
    {icon:"✓",label:pick("وضعیت","Status"),value:statusMeta.label,meta:status},
    {icon:"◷",label:pick("باقی‌مانده","Remaining"),value:remainingText(license.seconds_remaining,fa),meta:formatDate(expiry,locale)},
    {icon:"◆",label:pick("نسخه پنل","Panel version"),value:data?.current_version||"—",meta:data?.channel||"—",ltr:true},
    {icon:"◉",label:pick("اعتبارسنجی","Validation"),value:license.validation||"—",meta:formatDate(license.validated_at,locale)}
  ];

  return <Shell active="/admin/license">
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/45 p-4 backdrop-blur-[3px]" onMouseDown={e=>{if(e.target===e.currentTarget)close()}}>
      <section dir={fa?"rtl":"ltr"} className="w-full max-w-5xl overflow-hidden rounded-[28px] border border-slate-200/80 bg-white shadow-2xl dark:border-white/10 dark:bg-[#111827]">
        <div className="flex items-start justify-between gap-4 border-b border-slate-200/80 px-5 py-4 dark:border-white/10 sm:px-6">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-black text-slate-900 dark:text-white sm:text-2xl">{pick("مرکز لایسنس","License Center")}</h1>
              <Badge tone={statusMeta.tone}>{statusMeta.label}</Badge>
            </div>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{pick("مدیریت فعال‌سازی، اعتبار و تمدید لایسنس همین نصب","Manage activation, validity and renewal for this installation")}</p>
          </div>
          <button type="button" onClick={close} className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-slate-200 bg-slate-50 text-xl text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white" aria-label={pick("بستن","Close")}>×</button>
        </div>

        <div className="max-h-[82vh] overflow-y-auto p-5 sm:p-6">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {statItems.map(item=><div key={item.label} className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 dark:border-white/10 dark:bg-white/[.035]">
              <div className="flex items-start gap-3">
                <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-violet-500/10 font-black text-violet-600 dark:text-violet-300">{item.icon}</div>
                <div className="min-w-0">
                  <div className="text-xs font-bold text-slate-400">{item.label}</div>
                  <div dir={item.ltr?"ltr":undefined} className="mt-1 truncate text-base font-black text-slate-900 dark:text-white">{item.value}</div>
                  <div className="mt-1 truncate text-[11px] text-slate-400">{item.meta}</div>
                </div>
              </div>
            </div>)}
          </div>

          {error&&<div className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-200"><b className="ms-2">{pick("خطا:","Error:")}</b>{error}</div>}
          {notice&&<div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-200">{notice}</div>}

          <div className="mt-4 grid gap-4 lg:grid-cols-[1.45fr_.75fr]">
            <div className="rounded-2xl border border-slate-200 p-4 dark:border-white/10 sm:p-5">
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-base font-black text-slate-900 dark:text-white">{pick("فعال‌سازی لایسنس","Activate license")}</h2>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{pick("کلید صادرشده را وارد کنید؛ اعتبار روی همین نصب بررسی می‌شود.","Enter the issued key; validation is bound to this installation.")}</p>
                </div>
                <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-violet-500/10 text-violet-600 dark:text-violet-300">⌁</div>
              </div>

              <div className="flex flex-col gap-3 sm:flex-row">
                <input dir="ltr" value={licenseKey} onChange={e=>setLicenseKey(e.target.value)} placeholder="TP-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX" className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 font-mono text-sm text-slate-900 outline-none transition focus:border-violet-400 dark:border-white/10 dark:bg-black/10 dark:text-white" />
                <button className="primary whitespace-nowrap px-5" disabled={busy||licenseKey.trim().length<8} onClick={()=>void activate()}>{busy?pick("در حال ثبت…","Activating…"):pick("ثبت لایسنس","Activate")}</button>
              </div>

              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl bg-slate-50 px-4 py-3 dark:bg-white/[.035]">
                  <div className="text-[11px] text-slate-400">{pick("شناسه نصب","Installation ID")}</div>
                  <div className="mt-1 truncate font-mono text-xs text-slate-700 dark:text-slate-300" dir="ltr">{license.installation_id||"—"}</div>
                </div>
                <div className="rounded-xl bg-slate-50 px-4 py-3 dark:bg-white/[.035]">
                  <div className="text-[11px] text-slate-400">{pick("تاریخ انقضا","Expires")}</div>
                  <div className="mt-1 text-sm font-bold text-slate-700 dark:text-slate-200">{formatDate(expiry,locale)}</div>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <div className="rounded-2xl border border-slate-200 p-4 dark:border-white/10">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h3 className="font-black text-slate-900 dark:text-white">{pick("تمدید لایسنس","Renew license")}</h3>
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{pick("خرید یا تمدید از ربات رسمی","Purchase or renew via the official bot")}</p>
                  </div>
                  <span className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-300">↗</span>
                </div>
                {renewalBot?<a href={renewalBot} target="_blank" rel="noreferrer" className="mt-4 block rounded-xl bg-emerald-500 px-4 py-2.5 text-center text-sm font-black text-black transition hover:brightness-105">{pick("باز کردن ربات تمدید","Open renewal bot")}</a>:<div className="mt-4 rounded-xl bg-slate-50 px-4 py-2.5 text-center text-xs text-slate-400 dark:bg-white/[.035]">{pick("لینک تمدید تنظیم نشده","Renewal link not configured")}</div>}
              </div>

              <div className="rounded-2xl border border-slate-200 p-4 dark:border-white/10">
                <div className="flex items-center gap-3">
                  <span className="grid h-9 w-9 place-items-center rounded-xl bg-sky-500/10 text-sky-600 dark:text-sky-300">⛓</span>
                  <div>
                    <h3 className="text-sm font-black text-slate-900 dark:text-white">{pick("تأیید پرداخت زنجیره‌ای","On-chain verification")}</h3>
                    <p className="text-[11px] text-slate-400">{pick("بدون API Key پولی اجباری","No mandatory paid API key")}</p>
                  </div>
                </div>
                <p className="mt-3 text-xs leading-6 text-slate-500 dark:text-slate-400">{pick("بررسی پرداخت با هش تراکنش، مقصد، مبلغ و تأییدهای شبکه انجام می‌شود.","Payments are verified from transaction hash, destination, amount and network confirmations.")}</p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  </Shell>;
}
