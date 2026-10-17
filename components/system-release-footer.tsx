"use client";

import {useEffect,useMemo,useRef,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

const UPDATE_RELOAD_KEY="twinpanel-update-reload-pending-v1";

type LicenseState={
  status?:string;
  seconds_remaining?:number|null;
  enforced?:boolean;
  validation?:string;
};

type UpdateState={
  state?:string;
  target_version?:string;
  error?:string;
  delivery?:string;
  elapsed_seconds?:number;
  download_bytes?:number;
};

type ReleaseStatus={
  current_version:string;
  latest_version:string;
  update_available:boolean;
  github_url:string;
  license:LicenseState;
  update:UpdateState;
};

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  const raw=await response.text();
  let payload:unknown=null;
  if(raw){try{payload=JSON.parse(raw);}catch{payload=raw;}}
  if(!response.ok){
    const detail=payload&&typeof payload==="object"&&"detail" in payload?String((payload as {detail:unknown}).detail):`API error ${response.status}`;
    throw new Error(detail);
  }
  return payload as T;
}

function remainingText(seconds:number|undefined|null,fa:boolean){
  if(seconds==null||!Number.isFinite(Number(seconds)))return "";
  const value=Math.max(0,Number(seconds));
  const days=Math.floor(value/86400);
  const hours=Math.floor((value%86400)/3600);
  if(days>0)return fa?`${days.toLocaleString("fa-IR")} روز`:`${days}d`;
  return fa?`${hours.toLocaleString("fa-IR")} ساعت`:`${hours}h`;
}

function updatePendingInSession(){
  try{
    return typeof window!=="undefined"&&window.sessionStorage.getItem(UPDATE_RELOAD_KEY)==="1";
  }catch{
    return false;
  }
}

export function SystemReleaseFooter(){
  const {pick,lang}=useI18n();
  const [data,setData]=useState<ReleaseStatus|null>(null);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [licenseOpen,setLicenseOpen]=useState(false);
  const [licenseKey,setLicenseKey]=useState("");
  const [reloading,setReloading]=useState(false);
  const initialVersionRef=useRef("");
  const reloadTimerRef=useRef<number|null>(null);

  const updateState=String(data?.update?.state||"");
  const updateBusy=useMemo(()=>[
    "queued",
    "resolving",
    "fetching",
    "downloading",
    "verifying",
    "backup",
    "extracting",
    "building",
    "python-dependencies",
    "restarting",
    "rollback",
  ].includes(updateState),[updateState]);

  const load=async(check=false)=>{
    try{
      const result=await request<ReleaseStatus>(check?"/v1/admin/system/release/check":"/v1/admin/system/release/status",check?{method:"POST"}:{});
      if(!initialVersionRef.current)initialVersionRef.current=String(result.current_version||"").trim();
      setData(result);setError("");
    }catch(reason){
      // During an in-place update the API is intentionally restarted. Nginx may
      // briefly return 502/connection errors while the new release activates.
      // Keep the last known progress on screen instead of presenting that
      // expected restart window as a failed update.
      if(updatePendingInSession())return;
      setError(reason instanceof Error?reason.message:String(reason));
    }
  };

  useEffect(()=>{
    let alive=true;
    const checkNow=()=>{
      if(!alive||document.visibilityState!=="visible")return;
      void load(true);
    };
    const refreshStatus=()=>{
      if(!alive||document.visibilityState!=="visible")return;
      void load(false);
    };

    checkNow();
    const statusTimer=window.setInterval(refreshStatus,5000);
    const checkTimer=window.setInterval(checkNow,300000);
    window.addEventListener("focus",checkNow);
    document.addEventListener("visibilitychange",checkNow);

    return()=>{
      alive=false;
      window.clearInterval(statusTimer);
      window.clearInterval(checkTimer);
      window.removeEventListener("focus",checkNow);
      document.removeEventListener("visibilitychange",checkNow);
    };
  },[]);

  useEffect(()=>{
    if(!updateBusy)return;
    const timer=window.setInterval(()=>{
      if(document.visibilityState==="visible")void load(false);
    },2000);
    return()=>window.clearInterval(timer);
  },[updateBusy]);

  useEffect(()=>{
    if(!data)return;

    if(updateState==="failed"){
      try{window.sessionStorage.removeItem(UPDATE_RELOAD_KEY);}catch{}
      const detail=String(data.update?.error||"").trim();
      if(detail)setError(detail);
      return;
    }

    const current=String(data.current_version||"").trim();
    const target=String(data.update?.target_version||"").trim();
    const completed=updateState==="completed"&&Boolean(target)&&current===target;
    if(!completed||reloading)return;

    let startedHere=false;
    try{startedHere=window.sessionStorage.getItem(UPDATE_RELOAD_KEY)==="1";}catch{}
    const versionChanged=Boolean(initialVersionRef.current&&initialVersionRef.current!==current);
    if(!startedHere&&!versionChanged)return;

    try{window.sessionStorage.removeItem(UPDATE_RELOAD_KEY);}catch{}
    setReloading(true);
    if(reloadTimerRef.current!==null)window.clearTimeout(reloadTimerRef.current);
    reloadTimerRef.current=window.setTimeout(()=>window.location.reload(),700);
  },[data,reloading,updateState]);

  useEffect(()=>()=>{
    if(reloadTimerRef.current!==null)window.clearTimeout(reloadTimerRef.current);
  },[]);

  const licenseStatus=String(data?.license?.status||"");
  const remaining=remainingText(data?.license?.seconds_remaining,lang==="fa");
  const needsLicense=["trial_expired","license_expired","revoked","suspended"].includes(licenseStatus);

  const updateProgress=useMemo(()=>{
    const fa=lang==="fa";
    const labels:Record<string,string>={
      queued:fa?"در صف بروزرسانی…":"Queued…",
      resolving:fa?"در حال آماده‌سازی…":"Preparing…",
      fetching:fa?"در حال دریافت نسخه…":"Fetching release…",
      downloading:fa?"در حال دانلود نسخه…":"Downloading…",
      verifying:fa?"در حال بررسی نسخه…":"Verifying…",
      backup:fa?"در حال ساخت بکاپ…":"Creating backup…",
      extracting:fa?"در حال آماده‌سازی فایل‌ها…":"Preparing files…",
      building:fa?"در حال آماده‌سازی اجرا…":"Preparing runtime…",
      "python-dependencies":fa?"در حال بروزرسانی وابستگی‌ها…":"Updating dependencies…",
      restarting:fa?"در حال فعال‌سازی نسخه…":"Activating release…",
      rollback:fa?"در حال بازگردانی نسخه قبلی…":"Rolling back…",
    };
    return labels[updateState]||pick("در حال بروزرسانی…","Updating…");
  },[lang,updateState,pick]);

  const startUpdate=async()=>{
    if(busy||updateBusy||reloading)return;
    if(!window.confirm(pick("بروزرسانی پنل شروع شود؟ قبل از تغییر نسخه، بکاپ خودکار ساخته می‌شود.","Start the panel update? A backup is created before the release is changed.")))return;
    setBusy("update");setError("");
    try{
      try{window.sessionStorage.setItem(UPDATE_RELOAD_KEY,"1");}catch{}
      await request("/v1/admin/system/update",{method:"POST"});
      await load(false);
      window.setTimeout(()=>void load(false),1500);
    }catch(reason){
      try{window.sessionStorage.removeItem(UPDATE_RELOAD_KEY);}catch{}
      setError(reason instanceof Error?reason.message:String(reason));
    }
    finally{setBusy("");}
  };

  const activate=async()=>{
    if(busy||licenseKey.trim().length<8)return;
    setBusy("license");setError("");
    try{
      await request("/v1/admin/system/license/activate",{method:"POST",body:JSON.stringify({license_key:licenseKey.trim()})});
      setLicenseKey("");setLicenseOpen(false);await load(true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  if(!data)return <div className="system-release-footer"><span>{pick("نسخه پنل","Panel version")}</span><b>…</b></div>;

  return <>
    <div className={`system-release-footer ${data.update_available?"has-update":""}`}>
      <div className="system-release-version">
        <span>{pick("TwinPanel","TwinPanel")}</span>
        <a href={data.github_url||"https://github.com/matin111/twinpanel"} target="_blank" rel="noreferrer">v{data.current_version}</a>
      </div>

      <div className="system-release-license">
        <span className={`license-dot ${needsLicense?"bad":licenseStatus.startsWith("trial")?"warn":"ok"}`}/>
        <span>{licenseStatus||pick("لایسنس","License")}{remaining?` · ${remaining}`:""}</span>
        <button type="button" onClick={()=>setLicenseOpen(true)}>{pick("لایسنس","License")}</button>
      </div>

      {reloading&&<button className="system-update-button" type="button" disabled>{pick("بروزرسانی کامل شد؛ در حال تازه‌سازی…","Update complete; refreshing…")}</button>}
      {!reloading&&data.update_available&&<button className="system-update-button" type="button" disabled={busy==="update"||updateBusy} onClick={()=>void startUpdate()}>
        {updateBusy?updateProgress:pick(`بروزرسانی به ${data.latest_version}`,`Update to ${data.latest_version}`)}
      </button>}

      {!reloading&&!data.update_available&&<button className="system-check-button" type="button" disabled={Boolean(busy)} onClick={()=>void load(true)}>{pick("بررسی بروزرسانی","Check update")}</button>}
      {error&&<small className="system-release-error">{error}</small>}
    </div>

    {licenseOpen&&<div className="system-license-modal" role="dialog" aria-modal="true">
      <button className="system-license-backdrop" type="button" aria-label={pick("بستن","Close")} onClick={()=>setLicenseOpen(false)}/>
      <div className="system-license-card">
        <div className="system-license-head"><div><b>{pick("فعال‌سازی لایسنس","License activation")}</b><small>{pick("کلید خریداری‌شده را وارد کنید. فعال‌سازی روی همین نصب انجام می‌شود.","Enter your purchased key. Activation upgrades this installation in place.")}</small></div><button type="button" onClick={()=>setLicenseOpen(false)}>×</button></div>
        <input dir="ltr" value={licenseKey} onChange={event=>setLicenseKey(event.target.value)} placeholder="TP-XXXX-XXXX-XXXX" autoComplete="off"/>
        <div className="system-license-actions"><button type="button" className="ghost" onClick={()=>setLicenseOpen(false)}>{pick("انصراف","Cancel")}</button><button type="button" className="primary" disabled={busy==="license"||licenseKey.trim().length<8} onClick={()=>void activate()}>{busy==="license"?"…":pick("فعال‌سازی","Activate")}</button></div>
      </div>
    </div>}
  </>;
}
