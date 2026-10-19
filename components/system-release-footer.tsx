"use client";

import {useEffect,useMemo,useRef,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

const UPDATE_RELOAD_KEY="twinpanel-update-reload-pending-v4";
const RELEASE_CHECK_STAMP_KEY="twinpanel-release-check-at-v2";
const RELEASE_NOTICE_KEY="twinpanel-release-update-available-v1";
const RELEASE_EVENT="twinpanel:release-status";
const UPDATE_RECOVERY_MS=5*60*1000;
const TRANSIENT_API_GRACE_MS=60*1000;
const RELEASE_CHECK_INTERVAL_MS=2*60*1000;
const STATUS_POLL_MS=15*1000;
const ACTIVE_STATUS_POLL_MS=1500;

type LicenseState={
  status?:string;
  seconds_remaining?:number|null;
  enforced?:boolean;
  validation?:string;
};

type UpdateState={
  state?:string;
  target_version?:string;
  previous_version?:string;
  active_version?:string;
  error?:string;
  delivery?:string;
  elapsed_seconds?:number;
  download_bytes?:number;
  stage_seconds?:Record<string,number>;
};

type ReleaseNotes={fa?:string;en?:string;[key:string]:string|undefined};

type ReleaseStatus={
  current_version:string;
  latest_version:string;
  update_available:boolean;
  channel?:string;
  released_at?:string|null;
  release_notes?:ReleaseNotes;
  manifest_error?:string|null;
  github_url:string;
  license:LicenseState;
  update:UpdateState;
};

type RecoveryMarker={
  expires_at:number;
  target_version?:string;
  reload_from?:string;
};

type UpdateStage={
  key:string;
  fa:string;
  en:string;
};

const UPDATE_STAGES:UpdateStage[]=[
  {key:"manifest",fa:"بررسی نسخه",en:"Resolve release"},
  {key:"download",fa:"دریافت بسته",en:"Download package"},
  {key:"verify",fa:"اعتبارسنجی",en:"Verify package"},
  {key:"backup",fa:"بکاپ ایمن",en:"Safe backup"},
  {key:"extract",fa:"آماده‌سازی فایل‌ها",en:"Prepare files"},
  {key:"runtime",fa:"آماده‌سازی Runtime",en:"Prepare runtime"},
  {key:"restart",fa:"فعال‌سازی سرویس‌ها",en:"Activate services"},
  {key:"health",fa:"بررسی سلامت",en:"Health verification"},
];

class ReleaseRequestError extends Error{
  status:number;
  constructor(message:string,status:number){
    super(message);
    this.name="ReleaseRequestError";
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
  if(raw){try{payload=JSON.parse(raw);}catch{payload=raw;}}
  if(!response.ok){
    const detail=payload&&typeof payload==="object"&&"detail" in payload?String((payload as {detail:unknown}).detail):`API error ${response.status}`;
    throw new ReleaseRequestError(detail,response.status);
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

function formatBytes(value:number|undefined,fa:boolean){
  const bytes=Number(value)||0;
  if(bytes<=0)return "";
  const units=fa?["بایت","کیلوبایت","مگابایت","گیگابایت"]:["B","KB","MB","GB"];
  let size=bytes;
  let index=0;
  while(size>=1024&&index<units.length-1){size/=1024;index+=1;}
  return `${size.toLocaleString(fa?"fa-IR":"en-US",{maximumFractionDigits:index===0?0:1})} ${units[index]}`;
}

function formatDuration(value:number|undefined,fa:boolean){
  const seconds=Math.max(0,Number(value)||0);
  if(!seconds)return "";
  if(seconds<60)return fa?`${Math.round(seconds).toLocaleString("fa-IR")} ثانیه`:`${Math.round(seconds)}s`;
  const minutes=Math.floor(seconds/60);
  const remain=Math.round(seconds%60);
  return fa?`${minutes.toLocaleString("fa-IR")} دقیقه ${remain.toLocaleString("fa-IR")} ثانیه`:`${minutes}m ${remain}s`;
}

function formatReleaseDate(value:string|undefined|null,fa:boolean){
  if(!value)return "—";
  const date=new Date(value);
  if(Number.isNaN(date.getTime()))return "—";
  try{
    return new Intl.DateTimeFormat(fa?"fa-IR":"en-US",{dateStyle:"medium",timeStyle:"short"}).format(date);
  }catch{return date.toLocaleString();}
}

function readRecoveryMarker():RecoveryMarker|null{
  try{
    if(typeof window==="undefined")return null;
    const raw=window.sessionStorage.getItem(UPDATE_RELOAD_KEY);
    if(!raw)return null;
    const parsed=JSON.parse(raw) as Partial<RecoveryMarker>;
    const expires=Number(parsed.expires_at)||0;
    if(expires<=Date.now()){
      window.sessionStorage.removeItem(UPDATE_RELOAD_KEY);
      return null;
    }
    return {
      expires_at:expires,
      target_version:String(parsed.target_version||"").trim()||undefined,
      reload_from:String(parsed.reload_from||"").trim()||undefined,
    };
  }catch{return null;}
}

function writeRecoveryMarker(marker:RecoveryMarker){
  try{window.sessionStorage.setItem(UPDATE_RELOAD_KEY,JSON.stringify(marker));}catch{}
}

function setRecoveryMarker(targetVersion?:string){
  writeRecoveryMarker({
    expires_at:Date.now()+UPDATE_RECOVERY_MS,
    target_version:String(targetVersion||"").trim()||undefined,
  });
}

function markRecoveryReloadRequested(pageInstance:string){
  const marker=readRecoveryMarker();
  if(!marker)return;
  writeRecoveryMarker({...marker,reload_from:pageInstance});
}

function clearRecoveryMarker(){
  try{window.sessionStorage.removeItem(UPDATE_RELOAD_KEY);}catch{}
}

function claimBackgroundReleaseCheck(){
  try{
    if(typeof window==="undefined")return true;
    const now=Date.now();
    const last=Number(window.localStorage.getItem(RELEASE_CHECK_STAMP_KEY))||0;
    if(now-last<RELEASE_CHECK_INTERVAL_MS)return false;
    window.localStorage.setItem(RELEASE_CHECK_STAMP_KEY,String(now));
  }catch{}
  return true;
}

function broadcastReleaseStatus(result:ReleaseStatus){
  try{
    if(typeof window==="undefined")return;
    const available=Boolean(result.update_available);
    window.localStorage.setItem(RELEASE_NOTICE_KEY,available?"1":"0");
    window.dispatchEvent(new CustomEvent(RELEASE_EVENT,{detail:{updateAvailable:available,latestVersion:result.latest_version,currentVersion:result.current_version}}));
  }catch{}
}

function isTransientReleaseError(reason:unknown){
  if(reason instanceof ReleaseRequestError)return [502,503,504].includes(reason.status);
  const text=reason instanceof Error?reason.message:String(reason||"");
  return /failed to fetch|networkerror|network request failed|load failed|connection|fetch failed/i.test(text);
}

function humanizeUpdateError(raw:string,fa:boolean){
  const value=String(raw||"").trim();
  if(!value)return fa?"بروزرسانی کامل نشد.":"The update did not complete.";
  if(value.startsWith("POST_UPDATE_HEALTH_VERSION_FAILED:")){
    const services=value.split(":")[1]||"api,web";
    return fa?`نسخه جدید فعال شد اما بررسی سلامت ${services} در زمان تعیین‌شده کامل نشد.`:`The new release was activated, but the ${services} health check did not converge in time.`;
  }
  if(value.includes("SYSTEMD_START_FAILED")||value.includes("UPDATER_START_FAILED"))return fa?"سرویس بروزرسانی شروع نشد. وضعیت systemd را بررسی کنید.":"The updater service could not start. Check systemd status.";
  if(value.includes("LICENSE_REQUIRED_FOR_UPDATE"))return fa?"برای دریافت بروزرسانی، وضعیت لایسنس باید فعال باشد.":"An active license is required to install this update.";
  if(value.includes("MANIFEST_UNREACHABLE"))return fa?"سرور نسخه‌ها در دسترس نیست. چند لحظه بعد دوباره بررسی کنید.":"The release service is unreachable. Try checking again shortly.";
  return value;
}

function stateStageIndex(state:string){
  const value=String(state||"");
  if(["queued","resolving","fetching"].includes(value))return 0;
  if(value==="downloading")return 1;
  if(value==="verifying")return 2;
  if(value==="backup")return 3;
  if(value==="extracting")return 4;
  if(["building","python-dependencies"].includes(value))return 5;
  if(value==="restarting")return 6;
  if(value==="completed")return 8;
  return -1;
}

export function SystemReleaseFooter(){
  const {pick,lang}=useI18n();
  const fa=lang==="fa";
  const [data,setData]=useState<ReleaseStatus|null>(null);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [checking,setChecking]=useState(false);
  const [updateOpen,setUpdateOpen]=useState(false);
  const [licenseOpen,setLicenseOpen]=useState(false);
  const [licenseKey,setLicenseKey]=useState("");
  const [reloading,setReloading]=useState(false);
  const initialVersionRef=useRef("");
  const reloadTimerRef=useRef<number|null>(null);
  const transientSinceRef=useRef<number|null>(null);
  const loadInFlightRef=useRef<{status:boolean;check:boolean}>({status:false,check:false});
  const pageInstanceRef=useRef("");

  if(!pageInstanceRef.current){
    pageInstanceRef.current=`release-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }

  const updateState=String(data?.update?.state||"");
  const updateBusy=useMemo(()=>[
    "queued","resolving","fetching","downloading","verifying","backup","extracting","building","python-dependencies","restarting","rollback",
  ].includes(updateState),[updateState]);

  const load=async(check=false)=>{
    const lane=check?"check":"status";
    if(loadInFlightRef.current[lane])return;
    loadInFlightRef.current[lane]=true;
    if(check)setChecking(true);

    try{
      const result=await request<ReleaseStatus>(check?"/v1/admin/system/release/check":"/v1/admin/system/release/status",check?{method:"POST"}:{});
      if(!initialVersionRef.current)initialVersionRef.current=String(result.current_version||"").trim();
      transientSinceRef.current=null;
      setData(result);
      setError("");
      broadcastReleaseStatus(result);

      const marker=readRecoveryMarker();
      const current=String(result.current_version||"").trim();
      const target=String(result.update?.target_version||marker?.target_version||"").trim();
      const completed=String(result.update?.state||"")==="completed"&&Boolean(target)&&current===target;
      if(marker&&completed&&marker.reload_from&&marker.reload_from!==pageInstanceRef.current)clearRecoveryMarker();
    }catch(reason){
      if(isTransientReleaseError(reason)){
        const marker=readRecoveryMarker();
        const started=transientSinceRef.current??Date.now();
        transientSinceRef.current=started;
        setError("");
        if(marker||Date.now()-started<TRANSIENT_API_GRACE_MS)return;
        setError(pick("ارتباط با سرویس پنل طولانی‌تر از حد انتظار قطع است. دوباره وضعیت را بررسی کنید.","Panel service is taking longer than expected to reconnect. Check status again."));
        return;
      }
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      loadInFlightRef.current[lane]=false;
      if(check)setChecking(false);
    }
  };

  useEffect(()=>{
    let alive=true;
    const refreshStatus=()=>{
      if(!alive||document.visibilityState!=="visible")return;
      void load(false);
    };
    const maybeCheckLatest=()=>{
      if(!alive||document.visibilityState!=="visible")return;
      if(claimBackgroundReleaseCheck())void load(true);
    };

    refreshStatus();
    const backgroundKick=window.setTimeout(maybeCheckLatest,1200);
    const statusTimer=window.setInterval(refreshStatus,STATUS_POLL_MS);
    const checkTimer=window.setInterval(maybeCheckLatest,RELEASE_CHECK_INTERVAL_MS);
    window.addEventListener("focus",refreshStatus);
    document.addEventListener("visibilitychange",refreshStatus);

    if(readRecoveryMarker())setUpdateOpen(true);

    return()=>{
      alive=false;
      window.clearTimeout(backgroundKick);
      window.clearInterval(statusTimer);
      window.clearInterval(checkTimer);
      window.removeEventListener("focus",refreshStatus);
      document.removeEventListener("visibilitychange",refreshStatus);
    };
  },[]);

  useEffect(()=>{
    if(!updateBusy)return;
    setUpdateOpen(true);
    const timer=window.setInterval(()=>{
      if(document.visibilityState==="visible")void load(false);
    },ACTIVE_STATUS_POLL_MS);
    return()=>window.clearInterval(timer);
  },[updateBusy]);

  useEffect(()=>{
    if(!data)return;
    if(updateState==="failed"){
      clearRecoveryMarker();
      const detail=String(data.update?.error||"").trim();
      if(detail)setError(detail);
      setUpdateOpen(true);
      return;
    }

    const current=String(data.current_version||"").trim();
    const target=String(data.update?.target_version||"").trim();
    const completed=updateState==="completed"&&Boolean(target)&&current===target;
    if(!completed||reloading)return;

    const marker=readRecoveryMarker();
    const startedHere=Boolean(marker);
    const versionChanged=Boolean(initialVersionRef.current&&initialVersionRef.current!==current);
    if(!startedHere&&!versionChanged)return;

    setUpdateOpen(true);
    if(marker)markRecoveryReloadRequested(pageInstanceRef.current);
    setReloading(true);
    if(reloadTimerRef.current!==null)window.clearTimeout(reloadTimerRef.current);
    reloadTimerRef.current=window.setTimeout(()=>window.location.reload(),2200);
  },[data,reloading,updateState]);

  useEffect(()=>()=>{
    if(reloadTimerRef.current!==null)window.clearTimeout(reloadTimerRef.current);
  },[]);

  const licenseStatus=String(data?.license?.status||"");
  const remaining=remainingText(data?.license?.seconds_remaining,fa);
  const needsLicense=["trial_expired","license_expired","revoked","suspended"].includes(licenseStatus);
  const currentVersion=String(data?.current_version||"—");
  const latestVersion=String(data?.latest_version||currentVersion);
  const targetVersion=String(data?.update?.target_version||latestVersion||"—");
  const releaseNotes=String(data?.release_notes?.[fa?"fa":"en"]||data?.release_notes?.fa||data?.release_notes?.en||"").trim();
  const displayError=humanizeUpdateError(error||String(data?.update?.error||""),fa);
  const stageIndex=stateStageIndex(updateState);
  const progressPercent=updateState==="completed"?100:updateBusy?Math.max(6,Math.min(94,Math.round(((Math.max(stageIndex,0)+.55)/UPDATE_STAGES.length)*100))):0;
  const downloaded=formatBytes(data?.update?.download_bytes,fa);
  const elapsed=formatDuration(data?.update?.elapsed_seconds,fa);
  const updateFailed=updateState==="failed";
  const updateCompleted=updateState==="completed"&&String(data?.update?.target_version||"")===currentVersion;

  const openUpdateCenter=()=>{
    setUpdateOpen(true);
    setError("");
    void load(true);
  };

  const startUpdate=async()=>{
    if(busy||updateBusy||reloading||!data?.update_available)return;
    setBusy("update");
    setError("");
    setUpdateOpen(true);
    const expectedTarget=String(data.latest_version||"").trim();
    setRecoveryMarker(expectedTarget);
    try{
      await request("/v1/admin/system/update",{method:"POST"});
      await load(false);
      window.setTimeout(()=>void load(false),900);
    }catch(reason){
      if(isTransientReleaseError(reason)){
        setError("");
        window.setTimeout(()=>void load(false),900);
      }else{
        clearRecoveryMarker();
        setError(reason instanceof Error?reason.message:String(reason));
      }
    }finally{setBusy("");}
  };

  const activate=async()=>{
    if(busy||licenseKey.trim().length<8)return;
    setBusy("license");setError("");
    try{
      await request("/v1/admin/system/license/activate",{method:"POST",body:JSON.stringify({license_key:licenseKey.trim()})});
      setLicenseKey("");setLicenseOpen(false);await load(false);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  if(!data)return <div className="system-release-footer is-loading"><span className="release-skeleton"/><span className="release-skeleton short"/></div>;

  return <>
    <div className={`system-release-footer ${data.update_available?"has-update":""}`}>
      <button className="system-release-summary" type="button" onClick={openUpdateCenter}>
        <span className="system-release-summary-icon" aria-hidden="true">↻</span>
        <span className="system-release-summary-copy">
          <b>{pick("مرکز بروزرسانی","Update Center")}</b>
          <small dir="ltr">v{currentVersion}</small>
        </span>
        {data.update_available?<span className="system-release-new-badge">{pick("نسخه جدید","New")}</span>:<span className="system-release-ready-dot" aria-hidden="true"/>}
      </button>

      <div className="system-release-license">
        <span className={`license-dot ${needsLicense?"bad":licenseStatus.startsWith("trial")?"warn":"ok"}`}/>
        <span>{licenseStatus||pick("لایسنس","License")}{remaining?` · ${remaining}`:""}</span>
        <button type="button" onClick={()=>setLicenseOpen(true)}>{pick("مدیریت","Manage")}</button>
      </div>

      <button className={`system-update-launch ${data.update_available?"primary":""}`} type="button" onClick={openUpdateCenter}>
        {updateBusy?pick("مشاهده روند بروزرسانی","View update progress"):data.update_available?pick(`بروزرسانی ${latestVersion}`,`Update ${latestVersion}`):pick("بررسی بروزرسانی","Check for updates")}
      </button>
    </div>

    {updateOpen&&<div className="system-update-modal" role="dialog" aria-modal="true" aria-labelledby="system-update-title">
      <button className="system-update-backdrop" type="button" aria-label={pick("بستن","Close")} onClick={()=>{if(!reloading)setUpdateOpen(false);}}/>
      <section className="system-update-card" dir={fa?"rtl":"ltr"}>
        <header className="system-update-head">
          <div className="system-update-title-wrap">
            <span className={`system-update-orb ${data.update_available||updateBusy?"active":""}`} aria-hidden="true">↻</span>
            <div>
              <div className="system-update-eyebrow">{pick("سیستم و نگهداری","System & Maintenance")}</div>
              <h2 id="system-update-title">{pick("مرکز بروزرسانی TwinPanel","TwinPanel Update Center")}</h2>
              <p>{updateBusy?pick("نسخه جدید در حال اعمال است؛ وضعیت سرویس‌ها به‌صورت زنده بررسی می‌شود.","The new release is being applied and service health is monitored live."):pick("نسخه، تغییرات و سلامت بروزرسانی را از یکجا مدیریت کنید.","Manage release checks, changes, and update health in one place.")}</p>
            </div>
          </div>
          <button className="system-update-close" type="button" disabled={reloading} onClick={()=>setUpdateOpen(false)} aria-label={pick("بستن","Close")}>×</button>
        </header>

        <div className="system-update-version-grid">
          <article>
            <span>{pick("نسخه فعلی","Current version")}</span>
            <strong dir="ltr">v{currentVersion}</strong>
            <small>{pick("در حال اجرا","Running")}</small>
          </article>
          <span className="system-update-version-arrow" aria-hidden="true">←</span>
          <article className={data.update_available?"target":""}>
            <span>{pick("آخرین نسخه","Latest version")}</span>
            <strong dir="ltr">v{latestVersion}</strong>
            <small>{data.update_available?pick("آماده نصب","Ready to install"):pick("به‌روز است","Up to date")}</small>
          </article>
        </div>

        <div className="system-update-meta">
          <span><i aria-hidden="true">◈</i><em>{pick("کانال انتشار","Channel")}</em><b>{String(data.channel||"stable").toUpperCase()}</b></span>
          <span><i aria-hidden="true">◷</i><em>{pick("انتشار","Released")}</em><b>{formatReleaseDate(data.released_at,fa)}</b></span>
          <span><i aria-hidden="true">⌁</i><em>{pick("روش دریافت","Delivery")}</em><b>{String(data.update?.delivery||"Prebuilt")}</b></span>
        </div>

        {(updateBusy||updateCompleted||updateFailed)&&<div className={`system-update-progress-panel ${updateFailed?"failed":updateCompleted?"completed":""}`}>
          <div className="system-update-progress-head">
            <div>
              <span>{updateFailed?pick("بروزرسانی کامل نشد","Update did not complete"):updateCompleted?pick("بروزرسانی با موفقیت انجام شد","Update completed successfully"):pick(`در حال بروزرسانی به ${targetVersion}`,`Updating to ${targetVersion}`)}</span>
              <small>{elapsed?pick(`زمان سپری‌شده: ${elapsed}`,`Elapsed: ${elapsed}`):updateBusy?pick("پنل ممکن است هنگام راه‌اندازی مجدد چند لحظه پاسخ ندهد.","The panel may briefly reconnect while services restart."):""}</small>
            </div>
            <strong>{updateFailed?"!":`${progressPercent.toLocaleString(fa?"fa-IR":"en-US")}%`}</strong>
          </div>
          <div className="system-update-progress-track"><span style={{width:`${progressPercent}%`}}/></div>
          <div className="system-update-steps">
            {UPDATE_STAGES.map((stage,index)=>{
              const done=updateCompleted||stageIndex>index;
              const active=updateBusy&&stageIndex===index;
              const failed=updateFailed&&index===Math.max(0,stageIndex);
              return <div className={`${done?"done":""} ${active?"active":""} ${failed?"failed":""}`.trim()} key={stage.key}>
                <span className="system-update-step-mark">{done?"✓":failed?"!":index+1}</span>
                <small>{fa?stage.fa:stage.en}</small>
              </div>;
            })}
          </div>
          {(downloaded||elapsed)&&<div className="system-update-runtime-stats">
            {downloaded&&<span>{pick("دریافت‌شده","Downloaded")} <b>{downloaded}</b></span>}
            {elapsed&&<span>{pick("زمان کل","Total time")} <b>{elapsed}</b></span>}
          </div>}
        </div>}

        {updateFailed&&<div className="system-update-alert error">
          <span aria-hidden="true">!</span>
          <div><b>{pick("بروزرسانی کامل نشد","Update did not complete")}</b><p>{displayError}</p>{String(data.update?.error||error||"")&&<details><summary>{pick("جزئیات فنی","Technical details")}</summary><code dir="ltr">{String(data.update?.error||error)}</code></details>}</div>
        </div>}

        {!updateFailed&&error&&<div className="system-update-alert error"><span aria-hidden="true">!</span><div><b>{pick("بررسی ناموفق بود","Check failed")}</b><p>{displayError}</p></div></div>}

        {data.manifest_error&&!error&&<div className="system-update-alert warn"><span aria-hidden="true">i</span><div><b>{pick("آخرین وضعیت نسخه در دسترس نیست","Latest release status is unavailable")}</b><p>{pick("اطلاعات ذخیره‌شده نمایش داده می‌شود. بررسی دوباره را بزنید.","Cached information is shown. Run the check again.")}</p></div></div>}

        {releaseNotes&&<div className="system-update-notes">
          <div className="system-update-section-title"><span>{pick("تغییرات این نسخه","What’s new")}</span><small dir="ltr">{latestVersion}</small></div>
          <p>{releaseNotes}</p>
        </div>}

        {!releaseNotes&&!updateBusy&&<div className="system-update-notes compact">
          <div className="system-update-section-title"><span>{pick("وضعیت نسخه","Release status")}</span></div>
          <p>{data.update_available?pick("نسخه جدید آماده دریافت است. قبل از فعال‌سازی، بکاپ خودکار ساخته می‌شود.","A newer release is ready. An automatic backup is created before activation."):pick("این نصب روی آخرین نسخه عمومی قرار دارد.","This installation is on the latest public release.")}</p>
        </div>}

        <footer className="system-update-actions">
          <div className="system-update-actions-secondary">
            <button className="ghost" type="button" disabled={checking||updateBusy||reloading} onClick={()=>void load(true)}>{checking?<><span className="system-update-spinner"/> {pick("در حال بررسی…","Checking…")}</>:pick("بررسی دوباره","Check again")}</button>
            {data.github_url&&<a href={data.github_url} target="_blank" rel="noreferrer">{pick("مشاهده GitHub","View GitHub")}</a>}
          </div>
          <div className="system-update-actions-primary">
            {!updateBusy&&!reloading&&<button className="ghost" type="button" onClick={()=>setUpdateOpen(false)}>{pick("بستن","Close")}</button>}
            {data.update_available&&!updateBusy&&!reloading&&<button className="primary" type="button" disabled={busy==="update"||checking} onClick={()=>void startUpdate()}>{busy==="update"?pick("در حال شروع…","Starting…"):pick(`شروع بروزرسانی به ${latestVersion}`,`Update to ${latestVersion}`)}</button>}
            {updateBusy&&<button className="primary" type="button" disabled><span className="system-update-spinner"/> {pick("بروزرسانی در حال انجام است","Update in progress")}</button>}
            {reloading&&<button className="success" type="button" disabled>✓ {pick("انجام شد؛ در حال تازه‌سازی","Done; refreshing")}</button>}
          </div>
        </footer>
      </section>
    </div>}

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
