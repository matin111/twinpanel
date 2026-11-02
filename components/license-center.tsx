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
  renewal_bot_url?:string|null;
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

function botName(url:string){
  try{
    const parsed=new URL(url);
    const part=parsed.pathname.replace(/^\/+/,"");
    return part?`@${part}`:"Telegram";
  }catch{return "Telegram"}
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

  const infoBox=(label:string,value:string,ltr=false,accent="124,92,255")=><div style={{padding:"14px",border:"1px solid rgba(124,92,255,.14)",borderRadius:16,background:`linear-gradient(135deg,rgba(${accent},.08),rgba(${accent},.025))`,boxShadow:"inset 0 1px 0 rgba(255,255,255,.04)"}}>
    <div style={{fontSize:10,color:"var(--muted)",marginBottom:7,fontWeight:700}}>{label}</div>
    <div dir={ltr?"ltr":undefined} style={{fontSize:16,fontWeight:900,color:"var(--text)",whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{value}</div>
  </div>;

  return <Shell active="/admin/license">
    <div className="runtime-modal">
      <button className="runtime-modal-bg" type="button" onClick={close} aria-label={pick("بستن","Close")}/>
      <section className="runtime-modal-card" dir={fa?"rtl":"ltr"} style={{width:"min(620px,calc(100vw - 24px))",gap:14,padding:18,borderRadius:24,background:"linear-gradient(180deg,var(--surface),color-mix(in srgb,var(--surface) 94%,#6c3cff 6%))",boxShadow:"0 28px 90px rgba(20,18,40,.34),inset 0 1px 0 rgba(255,255,255,.06)"}}>
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",gap:12}}>
          <div style={{display:"flex",alignItems:"center",gap:10}}>
            <div style={{width:42,height:42,borderRadius:14,display:"grid",placeItems:"center",background:"linear-gradient(135deg,#6c3cff,#8b5cf6)",color:"#fff",fontWeight:900,boxShadow:"0 10px 28px rgba(108,60,255,.28)"}}>TP</div>
            <div>
              <h2 style={{margin:0,fontSize:20,fontWeight:950}}>{pick("لایسنس","License")}</h2>
              <div style={{marginTop:2,fontSize:11,color:"var(--muted)"}}>{pick("TwinPanel Control","TwinPanel Control")}</div>
            </div>
          </div>
          <div style={{display:"flex",alignItems:"center",gap:8}}>
            <span style={{padding:"6px 10px",borderRadius:999,fontSize:11,fontWeight:800,background:statusLabel===pick("منقضی","Expired")?"rgba(240,106,120,.12)":"rgba(53,201,139,.12)",color:statusLabel===pick("منقضی","Expired")?"#d85163":"#26976a"}}>{statusLabel}</span>
            <button className="icon-button" type="button" onClick={close} aria-label={pick("بستن","Close")}>×</button>
          </div>
        </div>

        <div style={{display:"grid",gridTemplateColumns:"repeat(2,minmax(0,1fr))",gap:10}}>
          {infoBox(pick("تاریخ انقضا","Expires"),formatDate(expiry,locale),false,"124,92,255")}
          {infoBox(pick("زمان باقی‌مانده","Remaining"),remainingText(license.seconds_remaining,fa),false,"36,180,126")}
          {infoBox(pick("نسخه پنل","Panel version"),data?.current_version||"—",true,"52,152,219")}
          {infoBox(pick("وضعیت","Status"),statusLabel,false,"245,158,11")}
        </div>

        {renewalBot&&<a href={renewalBot} target="_blank" rel="noreferrer" style={{display:"flex",alignItems:"center",justifyContent:"space-between",gap:12,padding:"13px 14px",borderRadius:16,border:"1px solid rgba(41,182,246,.18)",background:"linear-gradient(135deg,rgba(41,182,246,.10),rgba(41,182,246,.025))",color:"var(--text)",textDecoration:"none"}}>
          <div style={{display:"flex",alignItems:"center",gap:10,minWidth:0}}>
            <div style={{width:38,height:38,borderRadius:12,display:"grid",placeItems:"center",background:"#229ED9",color:"white",fontWeight:900}}>TG</div>
            <div style={{minWidth:0}}>
              <div style={{fontSize:11,color:"var(--muted)"}}>{pick("ربات تمدید","Renewal bot")}</div>
              <div dir="ltr" style={{fontSize:14,fontWeight:900,whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{botName(renewalBot)}</div>
            </div>
          </div>
          <div style={{fontSize:20,color:"#229ED9"}}>↗</div>
        </a>}

        {error&&<div className="runtime-error">{error}</div>}
        {notice&&<div className="runtime-message">{notice}</div>}

        <div style={{display:"grid",gap:8,paddingTop:2}}>
          <label style={{fontSize:11,color:"var(--muted)",fontWeight:700}}>{pick("کلید لایسنس","License key")}</label>
          <div style={{display:"flex",gap:8,alignItems:"stretch"}}>
            <input dir="ltr" value={licenseKey} onChange={e=>setLicenseKey(e.target.value)} placeholder="TP-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX" style={{flex:1,minWidth:0,borderRadius:13}}/>
            <button className="primary" type="button" disabled={busy||licenseKey.trim().length<8} onClick={()=>void activate()} style={{borderRadius:13,paddingInline:18}}>{busy?pick("در حال ثبت…","Activating…"):pick("ثبت","Activate")}</button>
          </div>
        </div>
      </section>
    </div>
  </Shell>;
}
