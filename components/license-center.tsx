"use client";

import {useEffect,useState} from "react";
import {useRouter} from "next/navigation";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

type LicenseState={
  status?:string;
  expires_at?:string|null;
  trial_expires_at?:string|null;
  renewal_bot_url?:string;
};
type ReleaseStatus={license?:LicenseState};

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
  if(!response.ok){throw new Error(payload?.detail||`API error ${response.status}`)}
  return payload as T;
}

function formatDate(value:string|undefined|null,locale:string){
  if(!value)return "—";
  const date=new Date(value);
  if(Number.isNaN(date.getTime()))return "—";
  try{return new Intl.DateTimeFormat(locale,{year:"numeric",month:"long",day:"numeric"}).format(date)}catch{return date.toLocaleDateString()}
}

export function LicenseCenter(){
  const {pick,lang}=useI18n();
  const router=useRouter();
  const [data,setData]=useState<ReleaseStatus|null>(null);
  const [licenseKey,setLicenseKey]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const license=data?.license||{};
  const expiry=license.expires_at||license.trial_expires_at;
  const renewalBot=String(license.renewal_bot_url||"").trim();

  const load=async()=>{
    try{setError("");setData(await request<ReleaseStatus>("/v1/admin/system/release/status"))}
    catch(e){setError(e instanceof Error?e.message:String(e))}
  };
  useEffect(()=>{void load()},[]);

  const activate=async()=>{
    const key=licenseKey.trim();
    if(key.length<8||busy)return;
    setBusy(true);setError("");
    try{
      await request("/v1/admin/system/license/activate",{method:"POST",body:JSON.stringify({license_key:key})});
      await load();
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  };

  return <div className="fixed inset-0 z-[140] flex items-center justify-center bg-black/55 p-4 backdrop-blur-md">
    <div className="w-full max-w-xl overflow-hidden rounded-[28px] border border-white/10 bg-[#0b0d14]/95 shadow-[0_30px_100px_rgba(0,0,0,.55)]">
      <div className="flex items-center justify-between border-b border-white/10 px-6 py-5">
        <div className="text-xl font-black">{pick("لایسنس","License")}</div>
        <button onClick={()=>router.push("/admin")} className="grid h-10 w-10 place-items-center rounded-xl border border-white/10 bg-white/5 text-xl hover:bg-white/10">×</button>
      </div>

      <div className="space-y-5 p-6">
        <div className="rounded-2xl border border-violet-400/20 bg-gradient-to-br from-violet-500/10 to-transparent p-5">
          <div className="mb-2 text-xs text-white/45">{pick("کلید لایسنس","License key")}</div>
          <input
            dir="ltr"
            value={licenseKey}
            onChange={e=>setLicenseKey(e.target.value)}
            placeholder="TP-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX"
            className="w-full rounded-2xl border border-white/10 bg-black/25 px-4 py-4 text-left font-mono text-sm outline-none ring-0 focus:border-violet-400/60"
          />
          <button disabled={busy||licenseKey.trim().length<8} onClick={()=>void activate()} className="mt-3 w-full rounded-2xl bg-violet-600 px-4 py-3.5 font-black text-white disabled:opacity-50">
            {busy?"…":pick("ثبت لایسنس","Activate")}
          </button>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="rounded-2xl border border-white/10 bg-white/[.035] p-5">
            <div className="mb-2 text-xs text-white/40">{pick("تاریخ انقضا","Expires")}</div>
            <div className="text-lg font-black">{formatDate(expiry,lang==="fa"?"fa-IR":"en-US")}</div>
          </div>

          <div className="rounded-2xl border border-emerald-400/15 bg-emerald-500/[.06] p-5">
            <div className="mb-3 text-xs text-white/40">{pick("تمدید لایسنس","Renew license")}</div>
            {renewalBot?
              <a href={renewalBot} target="_blank" rel="noreferrer" className="block rounded-xl bg-emerald-500 px-4 py-3 text-center font-black text-black">
                {pick("باز کردن ربات تمدید","Open renewal bot")}
              </a>
              :<div className="rounded-xl border border-white/10 px-4 py-3 text-center text-sm text-white/35">—</div>}
          </div>
        </div>

        {error&&<div className="rounded-2xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>}
      </div>
    </div>
  </div>;
}
