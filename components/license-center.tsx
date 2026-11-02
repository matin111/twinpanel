"use client";

import {useEffect,useMemo,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {Shell} from "./ui";

type LicenseState={
  status?:string;
  expires_at?:string|null;
  trial_expires_at?:string|null;
  seconds_remaining?:number|null;
};

type ReleaseStatus={
  current_version?:string;
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

  const statusLabel=useMemo(()=>{
    if(["licensed","license_expiring"].includes(status))return pick("فعال","Active");
    if(["trial_active","trial_expiring"].includes(status))return pick("آزمایشی","Trial");
    if(["license_expired","trial_expired","revoked","suspended"].includes(status))return pick("منقضی","Expired");
    return pick("در انتظار فعال‌سازی","Awaiting activation");
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
      setNotice(pick("لایسنس ثبت شد.","License activated."));
      await load();
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  };

  const infoBox=(label:string,value:string,ltr=false)=><div style={{padding:"12px 14px",border:"1px solid var(--line)",borderRadius:12,background:"var(--surface2)"}}>
    <div style={{fontSize:11,color:"var(--muted)",marginBottom:5}}>{label}</div>
    <div dir={ltr?"ltr":undefined} style={{fontSize:15,fontWeight:800,color:"var(--text)"}}>{value}</div>
  </div>;

  return <Shell active="/admin/license">
    <div className="runtime-modal" onMouseDown={e=>{if(e.target===e.currentTarget)close()}}>
      <button className="runtime-modal-bg" type="button" onClick={close} aria-label={pick("بستن","Close")}/>
      <section className="runtime-modal-card" dir={fa?"rtl":"ltr"} style={{width:"min(560px,calc(100vw - 24px))",gap:14,padding:18}}>
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",gap:12}}>
          <h2 style={{margin:0,fontSize:20,fontWeight:900}}>{pick("لایسنس","License")}</h2>
          <button className="icon-button" type="button" onClick={close} aria-label={pick("بستن","Close")}>×</button>
        </div>

        <div style={{display:"grid",gridTemplateColumns:"repeat(2,minmax(0,1fr))",gap:10}}>
          {infoBox(pick("وضعیت","Status"),statusLabel)}
          {infoBox(pick("تاریخ انقضا","Expires"),formatDate(expiry,locale))}
          {infoBox(pick("زمان باقی‌مانده","Remaining"),remainingText(license.seconds_remaining,fa))}
          {infoBox(pick("نسخه پنل","Panel version"),data?.current_version||"—",true)}
        </div>

        {error&&<div className="runtime-error">{error}</div>}
        {notice&&<div className="runtime-message">{notice}</div>}

        <div style={{display:"grid",gap:8}}>
          <label style={{fontSize:11,color:"var(--muted)"}}>{pick("کلید لایسنس","License key")}</label>
          <div style={{display:"flex",gap:8,alignItems:"stretch"}}>
            <input dir="ltr" value={licenseKey} onChange={e=>setLicenseKey(e.target.value)} placeholder="TP-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX" style={{flex:1,minWidth:0}}/>
            <button className="primary" type="button" disabled={busy||licenseKey.trim().length<8} onClick={()=>void activate()}>{busy?pick("در حال ثبت…","Activating…"):pick("ثبت","Activate")}</button>
          </div>
        </div>
      </section>
    </div>
  </Shell>;
}
