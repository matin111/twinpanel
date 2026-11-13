"use client";

import {useEffect,useMemo,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {Badge,Card,Shell} from "./ui";

type Source="sanaei"|"marzban"|"pasargad"|"eylan";
type AnyRow=Record<string,unknown>;

type DryRunRecord={
  index:number;
  source:Source;
  source_id:unknown;
  username:unknown;
  password?:string|null;
  credentials?:Record<string,unknown>;
  legacy_subscription_url?:unknown;
  traffic_limit_bytes?:number;
  traffic_used_bytes?:number;
  expires_at?:string|null;
  ready_for_future_import:boolean;
  warnings:string[];
};

type DryRunResult={
  dry_run:boolean;
  writes_performed:boolean;
  source:Source;
  summary:{input_records:number;expanded_records:number;ready_records:number;warning_records:number};
  records:DryRunRecord[];
};

type ProvisionResult={
  ok:boolean;
  subscriptions:number;
  nodes:number;
  node_restarts:number;
  errors:Array<{node:string;error:string}>;
};

type BatchImportResult={
  ok:boolean;
  imported:number;
  existing:number;
  subscriptions:number;
  provision:ProvisionResult;
};

type EylanStageResult={
  ok:boolean;
  imported:number;
  existing:number;
  already_imported:number;
  staged:number;
  staged_source_ids:string[];
};

type MigrationProtocolStatus={
  source:Source;
  subscriptions:number;
  fully_provisioned:boolean;
  protocols:Array<{protocol:string;declared:number;configured:number}>;
};

type MigrationOverview={
  source:Source;
  total_imported:number;
  history:Array<{
    id:number; source_id:string; subscription_id:number;
    target_user_id:number|null; account_username:string|null;
    status:string; subscription_status:string; created_at:string|null;
  }>;
};

type DestinationCheck={
  exists:boolean;active:boolean;target_user_id:number;
  display_name:string|null;existing_imports:number;
};

type EylanFinalizeResult={
  ok:boolean;
  subscriptions:number;
  existing_imported:number;
  provision:ProvisionResult;
};

const ALL_MIGRATION_PROTOCOLS=[
  "cisco","openvpn","wireguard","l2tp","v2ray",
  "hysteria2","tuic","anytls","naive","shadowtls",
  "snell","mieru","trusttunnel","amneziawg","sudoku",
] as const;
const ALL_PROTOCOLS_CSV=ALL_MIGRATION_PROTOCOLS.join(",");

const EYLAN_STAGE_CHUNK=50;
const MAX_JSON_BYTES=6*1024*1024;
const PREVIEW_PAGE_SIZE=20;

async function api<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!(init.body instanceof FormData)&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  if(!response.ok){
    let detail=`API error ${response.status}`;
    try{
      const body=await response.json() as {detail?:unknown;message?:unknown};
      if(typeof body.detail==="string")detail=body.detail;
      else if(body.detail&&typeof body.detail==="object"&&"message" in body.detail)detail=String((body.detail as {message?:unknown}).message||detail);
      else if(typeof body.message==="string")detail=body.message;
      else if(Array.isArray(body.detail))detail=body.detail.map(String).join("، ");
    }catch{}
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

function parseRecords(raw:string):AnyRow[]{
  const parsed=JSON.parse(raw) as unknown;
  if(Array.isArray(parsed)){
    if(parsed.length>10000)throw new Error("JSON exceeds the 10,000-record preview limit");
    if(!parsed.every(item=>item&&typeof item==="object"&&!Array.isArray(item)))throw new Error("JSON array must contain objects only");
    return parsed as AnyRow[];
  }
  if(parsed&&typeof parsed==="object")return [parsed as AnyRow];
  throw new Error("JSON must be an object or array of objects");
}

function formatBytes(value:unknown){
  const bytes=Number(value||0);
  if(!Number.isFinite(bytes)||bytes<=0)return "0 B";
  const units=["B","KB","MB","GB","TB"];
  const index=Math.min(Math.floor(Math.log(bytes)/Math.log(1024)),units.length-1);
  return `${(bytes/1024**index).toFixed(index>=3?2:1)} ${units[index]}`;
}

const sourceLabel:Record<Source,string>={sanaei:"سنایی / 3x-ui",marzban:"مرزبان",pasargad:"پاسارگاد",eylan:"ایلان"};

export function MigrationCenterAdmin(){
  const {pick}=useI18n();
  const [source,setSource]=useState<Source>("sanaei");
  const [raw,setRaw]=useState("");
  const [eylanFile,setEylanFile]=useState<File|null>(null);
  const [targetUserId,setTargetUserId]=useState("");
  const protocols=ALL_PROTOCOLS_CSV;
  const [dryRun,setDryRun]=useState<DryRunResult|null>(null);
  const [busy,setBusy]=useState(false);
  const [busyPhase,setBusyPhase]=useState<"preview"|"stage"|"provision"|"import">("preview");
  const [busyProgress,setBusyProgress]=useState<{done:number;total:number}|null>(null);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [migrationStatus,setMigrationStatus]=useState<MigrationProtocolStatus|null>(null);
  const [statusLoading,setStatusLoading]=useState(false);
  const [overview,setOverview]=useState<MigrationOverview|null>(null);
  const [overviewLoading,setOverviewLoading]=useState(false);
  const [targetCheck,setTargetCheck]=useState<DestinationCheck|null>(null);
  const [targetLoading,setTargetLoading]=useState(false);
  const [previewPage,setPreviewPage]=useState(0);
  const [jsonFileName,setJsonFileName]=useState("");
  const [showJsonInput,setShowJsonInput]=useState(false);
  const [showProtocols,setShowProtocols]=useState(false);
  const [showProvisioning,setShowProvisioning]=useState(false);
  const [importSummary,setImportSummary]=useState<{imported:number;existing:number;total:number;provisioned:number}|null>(null);

  const readyRecords=useMemo(()=>dryRun?.records.filter(item=>item.ready_for_future_import)??[],[dryRun]);
  const isEylan=source==="eylan";
  const displayedRecords=useMemo(()=>dryRun?.records.slice(
    previewPage*PREVIEW_PAGE_SIZE,(previewPage+1)*PREVIEW_PAGE_SIZE)??[],
    [dryRun,previewPage]);
  const configuredCount=migrationStatus?.source===source
    ?migrationStatus.protocols.filter(p=>p.configured>0).length:0;
  const configuredTotal=migrationStatus?.source===source
    ?migrationStatus.protocols.reduce((total,p)=>total+p.configured,0):0;

  const fetchOverview=async(current:Source)=>{
    const result=await api<MigrationOverview>(
      `/v1/admin/migration-center/overview?source=${current}&limit=12`);
    if(result.source!==current)throw new Error("Unexpected migration overview source");
    setOverview(result);
  };

  useEffect(()=>{
    let cancelled=false;
    setOverview(null);
    setOverviewLoading(true);
    api<MigrationOverview>(`/v1/admin/migration-center/overview?source=${source}&limit=12`)
      .then(result=>{if(!cancelled&&result.source===source)setOverview(result);})
      .catch(()=>{if(!cancelled)setOverview(null);})
      .finally(()=>{if(!cancelled)setOverviewLoading(false);});
    return ()=>{cancelled=true;};
  },[source]);

  const checkTarget=async()=>{
    const id=Number(targetUserId);
    setTargetCheck(null);
    if(!Number.isSafeInteger(id)||id<=0){
      setError(pick("شناسه کاربر مقصد معتبر نیست.","Enter a valid destination user ID."));
      return null;
    }
    setTargetLoading(true);
    try{
      const result=await api<DestinationCheck>(
        `/v1/admin/migration-center/target-check?source=${source}&target_user_id=${id}`);
      if(result.target_user_id!==id)throw new Error("Destination check mismatch");
      setTargetCheck(result);
      return result;
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
      return null;
    }finally{setTargetLoading(false);}
  };

  const chooseJsonFile=async(file:File|null)=>{
    setDryRun(null);setPreviewPage(0);setImportSummary(null);setError("");setOk("");
    if(!file){setJsonFileName("");return;}
    if(file.size>MAX_JSON_BYTES){
      setError(pick("حجم فایل JSON حداکثر ۶ مگابایت است.","JSON file must be at most 6 MB."));
      return;
    }
    try{
      setRaw(await file.text());
      setJsonFileName(file.name);
      setShowJsonInput(false);
    }catch{setError(pick("خواندن فایل JSON ناموفق بود.","Could not read the JSON file."));}
  };

  const refreshMigrationStatus=async()=>{
    setStatusLoading(true);
    setError("");
    try{
      const result=await api<MigrationProtocolStatus>(`/v1/admin/migration-center/all-protocols/status?source=${source}`);
      setMigrationStatus(result);
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setStatusLoading(false);
    }
  };

  const runDry=async()=>{
    setError("");setOk("");setDryRun(null);
    try{
      setBusyPhase("preview");
      setBusyProgress(null);
      setBusy(true);
      let result:DryRunResult;
      if(isEylan){
        if(!eylanFile)throw new Error(pick("فایل بکاپ ایلان را انتخاب کنید.","Select an Eylan backup file."));
        const form=new FormData();
        form.append("file",eylanFile);
        result=await api<DryRunResult>("/v1/admin/migration-center/eylan/preview",{method:"POST",body:form});
      }else{
        if(new TextEncoder().encode(raw).length>MAX_JSON_BYTES)throw new Error(pick("JSON بیش از ۶ مگابایت است.","JSON exceeds 6 MB."));
        const records=parseRecords(raw);
        result=await api<DryRunResult>("/v1/admin/migration-center/dry-run",{
          method:"POST",
          body:JSON.stringify({source,records}),
        });
      }
      if(!result.dry_run||result.writes_performed!==false||result.source!==source){
        throw new Error(pick("پاسخ پیش‌نمایش معتبر نیست؛ انتقال متوقف شد.","Unsafe preview response; import blocked."));
      }
      setPreviewPage(0);
      setDryRun(result);
      setImportSummary(null);
      setOk(pick("بررسی ایمن انجام شد؛ هیچ تغییری ثبت نشده است.","Safe preview completed without writing any data."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);setBusyProgress(null);}
  };

  const importReady=async()=>{
    setError("");setOk("");
    const userId=Number(targetUserId);
    if(!Number.isInteger(userId)||userId<=0){setError(pick("شناسه کاربر TwinPanel معتبر وارد کنید.","Enter a valid TwinPanel user ID."));return;}
    if(!dryRun||dryRun.source!==source||dryRun.writes_performed!==false||readyRecords.length===0){setError(pick("ابتدا پیش‌نمایش معتبر بگیرید.","Run a valid preview before importing."));return;}
    const target=await checkTarget();
    if(!target||!target.exists||!target.active){
      setError(pick("کاربر مقصد وجود ندارد یا غیرفعال است؛ هیچ انتقالی انجام نشد.","Destination user is missing/inactive; no import was started."));
      return;
    }
    const protocolList=protocols.split(",").map(item=>item.trim().toLowerCase()).filter(Boolean);
    const effectiveProtocols=protocolList.length?protocolList:[...ALL_MIGRATION_PROTOCOLS];
    setImportSummary(null);
    setBusyPhase(isEylan?"stage":"import");
    setBusyProgress({done:0,total:readyRecords.length});
    setBusy(true);
    try{
      if(isEylan){
        if(effectiveProtocols.length!==ALL_MIGRATION_PROTOCOLS.length||!ALL_MIGRATION_PROTOCOLS.every(key=>effectiveProtocols.includes(key)))throw new Error(pick("برای انتقال، هر ۱۵ پروتکل باید انتخاب شده باشند.","Select all 15 protocols for migration."));
        const records=readyRecords.map(item=>({
          source_id:String(item.source_id||""),
          username:String(item.username||""),
          password:String(item.password||""),
          traffic_limit_bytes:Number(item.traffic_limit_bytes||0),
          traffic_used_bytes:Number(item.traffic_used_bytes||0),
          expires_at:item.expires_at||null,
        }));

        let imported=0;
        let existing=0;
        let alreadyImported=0;
        for(let offset=0;offset<records.length;offset+=EYLAN_STAGE_CHUNK){
          const chunk=records.slice(offset,offset+EYLAN_STAGE_CHUNK);
          const staged=await api<EylanStageResult>("/v1/admin/migration-center/eylan/stage",{
            method:"POST",
            body:JSON.stringify({records:chunk,target_user_id:userId,protocols:effectiveProtocols}),
          });
          imported+=staged.imported;
          existing+=staged.existing;
          alreadyImported+=staged.already_imported;
          const done=Math.min(offset+chunk.length,records.length);
          setBusyProgress({done,total:records.length});
          setOk(pick(`در حال انتقال ایلان: ${done} از ${records.length} رکورد در دیتابیس آماده شد...`,`Eylan transfer: ${done} of ${records.length} records staged in the database...`));
        }

        setBusyPhase("provision");
        setBusyProgress(null);
        setOk(pick("رکوردها آماده شدند؛ در حال ساخت یک‌جای V2Ray روی Exitها...","Records staged; provisioning V2Ray once across Exit nodes..."));
        const sourceIds=records.map(item=>item.source_id);
        const finalized=await api<EylanFinalizeResult>("/v1/admin/migration-center/eylan/finalize",{
          method:"POST",
          body:JSON.stringify({source_ids:sourceIds,target_user_id:userId,protocols:effectiveProtocols}),
        });
        setImportSummary({imported,existing,total:records.length,provisioned:Number(finalized.provision.subscriptions||0)});
        await fetchOverview(source).catch(()=>{});
        if(!finalized.ok||!finalized.provision.ok){
          const failedNodes=finalized.provision.errors.map(item=>`${item.node}: ${item.error}`).join(" | ");
          setError(pick(`اطلاعات ایلان Stage شد اما Provision همه نودها کامل نشد. ${failedNodes}`,`Eylan records were staged, but provisioning did not complete on every node. ${failedNodes}`));
        }else{
          setOk(pick(`انتقال ایلان: ${imported} جدید، ${existing} موجود؛ V2Ray اعمال شد (${finalized.provision.node_restarts} ری‌استارت). ساخت ۱۴ پروتکل دیگر هنوز باید تکمیل شود.`,`Eylan import: ${imported} new, ${existing} existing; V2Ray applied (${finalized.provision.node_restarts} Xray restarts). The other 14 protocols are pending provisioning.`));
        }
        return;
      }

      // Preserve source V2Ray UUIDs whenever present, in one Xray batch
      // transaction per chunk. Other records use one atomic DB-only request,
      // so no import ever performs one HTTP round-trip per account.
      const hasPreservedUuid=(record:DryRunRecord)=>{
        const raw=String(record.credentials?.uuid||"").trim();
        return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(raw);
      };
      const preserved=readyRecords.filter(hasPreservedUuid);
      const staged=readyRecords.filter(record=>!hasPreservedUuid(record));
      let imported=0;
      let existing=0;
      let finished=0;
      let v2rayProvisioned=0;
      for(const group of [{records:preserved,route:"/v1/admin/migration-center/import-batch"}, {records:staged,route:"/v1/admin/migration-center/import-staged-batch"}]){
        // Larger V2Ray batches amortize expensive Xray restarts; DB-only
        // groups stay small to avoid long HTTP requests.
        const chunkSize=group.route.endsWith("/import-batch")?250:50;
        for(let offset=0;offset<group.records.length;offset+=chunkSize){
          const chunk=group.records.slice(offset,offset+chunkSize);
          const result=await api<BatchImportResult|{ok:boolean;imported:number;existing:number;remote_provisioning_completed:false}>(group.route,{
            method:"POST",
            body:JSON.stringify({source,records:chunk,target_user_id:userId,protocols:effectiveProtocols}),
          });
          imported+=result.imported;
          existing+=result.existing;
          finished+=chunk.length;
          if("provision" in result){
            v2rayProvisioned+=result.provision.subscriptions;
            if(!result.provision.ok){
              setError(pick("انتقال رکوردها انجام شد اما آماده‌سازی V2Ray بعضی سرورها ناقص است.","Records imported but V2Ray provisioning failed on some nodes."));
            }
          }
          setBusyProgress({done:finished,total:readyRecords.length});
        }
      }
      setImportSummary({imported,existing,total:imported+existing,provisioned:v2rayProvisioned});
      await fetchOverview(source).catch(()=>{});
      setOk(pick(
        `برای ${imported+existing} اشتراک هر ۱۵ پروتکل ثبت شد؛ V2Ray با UUID حفظ‌شده برای ${v2rayProvisioned} اکانت به‌صورت دسته‌ای اجرا شد. ساخت پروتکل‌های دیگر در نودهای آماده هنوز باید تکمیل شود.`,
        `All 15 protocol snapshots registered for ${imported+existing} subscriptions; V2Ray batched with preserved UUID for ${v2rayProvisioned} accounts. Remaining protocols await eligible-node provisioning.`
      ));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);setBusyProgress(null);}
  };

  const busyTitle=busyPhase==="preview"
    ?pick("در حال بررسی فایل بکاپ","Analyzing backup file")
    :busyPhase==="stage"
    ?pick("در حال آماده‌سازی رکوردها","Preparing accounts")
    :busyPhase==="provision"
    ?pick("در حال ساخت اکانت‌ها روی سرورها","Provisioning accounts on servers")
    :pick("در حال انتقال اکانت‌ها","Importing accounts");
  const busyDescription=busyPhase==="preview"
    ?pick("بکاپ در حال خواندن و استخراج اطلاعات است. هنوز تغییری در حساب‌ها ایجاد نشده.","Reading and validating backup data. No accounts have been changed.")
    :busyPhase==="provision"
    ?pick("ساخت و همگام‌سازی روی سرورها ممکن است چند دقیقه طول بکشد.","Provisioning and synchronizing nodes may take several minutes.")
    :pick("رکوردها در حال ثبت و بررسی هستند. صفحه را باز نگه دارید.","Records are being saved and checked. Keep this page open.");
  const progressPercent=busyProgress?.total?Math.round(busyProgress.done/busyProgress.total*100):null;

  return <Shell active="/admin/migration-center"><div className="page">
    <div className="page-head">
      <div>
        <h1>{pick("مرکز انتقال اکانت‌ها","Migration Center")}</h1>
        <small>{pick("انتقال از سنایی، مرزبان، پاسارگاد و ایلان با رجیستری یکسان ۱۵ پروتکل.","Import from Sanaei, Marzban, Pasargad and Eylan with the same 15-protocol registry.")}</small>
      </div>
    </div>

    {busy&&<div role="dialog" aria-modal="true" aria-label={busyTitle} aria-describedby="migration-progress-description" className="tp-migration-overlay" dir="rtl">
      <div className="tp-migration-progress" role="status" aria-live="polite">
        <div className="tp-migration-art" aria-hidden="true">
          <span className="tp-migration-art-ring"/>
          <svg viewBox="0 0 96 96" width="82" height="82" fill="none" aria-hidden="true">
            <rect x="9" y="26" width="28" height="40" rx="7" stroke="currentColor" strokeWidth="3" opacity=".75"/>
            <path d="M18 37h10M18 46h10M18 55h7" stroke="currentColor" strokeWidth="3" strokeLinecap="round"/>
            <rect x="59" y="26" width="28" height="40" rx="7" stroke="currentColor" strokeWidth="3"/>
            <path d="M68 37h10M68 46h10M68 55h7" stroke="currentColor" strokeWidth="3" strokeLinecap="round"/>
            <path d="M40 46h16m-6-6 6 6-6 6" stroke="#38bdf8" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="tp-migration-art-arrow"/>
          </svg>
        </div>
        <div className="tp-migration-kicker">{pick("مرکز انتقال TwinPanel","TwinPanel Migration Center")}</div>
        <h2>{busyTitle}</h2>
        <p id="migration-progress-description">{busyDescription}</p>
        {progressPercent===null
          ?<div className="tp-migration-indeterminate" aria-label={pick("عملیات در حال اجراست","Operation in progress")}><span/></div>
          :<div className="tp-migration-progress-track" role="progressbar" aria-valuenow={progressPercent} aria-valuemin={0} aria-valuemax={100} aria-label={pick("پیشرفت آماده‌سازی","Preparation progress")}>
            <span style={{width:`${progressPercent}%`}}/>
          </div>}
        <div className="tp-migration-progress-meta">
          {progressPercent===null
            ?pick("در حال پردازش...","Processing...")
            :pick(`${busyProgress!.done.toLocaleString("fa-IR")} از ${busyProgress!.total.toLocaleString("fa-IR")} رکورد · ${progressPercent.toLocaleString("fa-IR")}٪`,`${busyProgress!.done} of ${busyProgress!.total} records · ${progressPercent}%`)}
        </div>
        <div className="tp-migration-progress-foot">{pick("تا دریافت نتیجه، این صفحه را نبندید یا رفرش نکنید.","Do not close or refresh this page until a result appears.")}</div>
      </div>
    </div>}
    <style>{`
      .tp-migration-overlay{position:fixed;inset:0;z-index:99999;background:rgba(3,8,23,.76);backdrop-filter:blur(9px);display:flex;align-items:center;justify-content:center;padding:16px}
      .tp-migration-progress{width:min(100%,450px);border:1px solid rgba(87,134,244,.3);border-radius:24px;padding:32px 28px;background:linear-gradient(150deg,#14233d,#0b1426 75%);box-shadow:0 28px 100px rgba(0,0,0,.45);color:#f8fafc;text-align:center;direction:rtl}
      .tp-migration-art{width:116px;height:116px;margin:0 auto 18px;display:grid;place-items:center;position:relative;color:#dbeafe}
      .tp-migration-art-ring{position:absolute;inset:4px;border-radius:50%;border:3px solid rgba(96,165,250,.15);border-top-color:#38bdf8;border-right-color:#6366f1;animation:tp-migration-spin 1.5s linear infinite}
      .tp-migration-art-arrow{animation:tp-migration-pulse 1.1s ease-in-out infinite}
      .tp-migration-kicker{font-size:12px;color:#7dd3fc;font-weight:700;letter-spacing:.02em;margin-bottom:10px}
      .tp-migration-progress h2{font-size:21px;font-weight:800;margin:0 0 11px;color:#fff}
      .tp-migration-progress p{font-size:14px;line-height:1.9;color:#bac9e0;margin:0 0 23px}
      .tp-migration-indeterminate,.tp-migration-progress-track{height:9px;border-radius:50px;background:rgba(148,163,184,.16);overflow:hidden}
      .tp-migration-indeterminate span{display:block;height:100%;width:36%;border-radius:50px;background:linear-gradient(90deg,#3b82f6,#06b6d4);animation:tp-migration-scan 1.3s ease-in-out infinite}
      .tp-migration-progress-track span{display:block;height:100%;background:linear-gradient(90deg,#2563eb,#06b6d4);border-radius:50px;transition:width .3s ease}
      .tp-migration-progress-meta{margin-top:10px;font-size:13px;font-variant-numeric:tabular-nums;color:#bae6fd}
      .tp-migration-progress-foot{border-top:1px solid rgba(148,163,184,.15);margin-top:24px;padding-top:18px;font-size:12px;line-height:1.8;color:#94a3b8}
      @keyframes tp-migration-spin{to{transform:rotate(360deg)}}
      @keyframes tp-migration-scan{0%{transform:translateX(-130%)}50%{transform:translateX(100%)}100%{transform:translateX(330%)}}
      @keyframes tp-migration-pulse{50%{opacity:.25}}
      @media(prefers-reduced-motion:reduce){.tp-migration-art-ring,.tp-migration-indeterminate span,.tp-migration-art-arrow{animation:none}}

      .mig-hero{display:grid;grid-template-columns:minmax(270px,1.05fr) minmax(400px,1.35fr);align-items:center;gap:20px;background:linear-gradient(125deg,rgba(54,113,235,.11),rgba(8,174,195,.04));border:1px solid var(--border,rgba(80,103,150,.2));padding:23px 25px;border-radius:22px;margin-bottom:14px}
      .mig-eyebrow{font-size:11px;font-weight:850;letter-spacing:.08em;color:var(--accent,#527ce9)}
      .mig-hero-copy h2{font-size:22px;font-weight:850;margin:7px 0;color:var(--text,#17233b)}
      .mig-hero-copy p{font-size:12px;line-height:1.9;color:var(--muted,#64748b);margin:0;max-width:480px}
      .mig-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px}
      .mig-stat{background:var(--card,rgba(255,255,255,.84));border:1px solid var(--border,rgba(119,138,169,.18));border-radius:14px;min-height:82px;padding:13px 12px;display:flex;flex-direction:column;justify-content:space-between;gap:8px}
      .mig-stat small{color:var(--muted,#71809a);font-size:10px;line-height:1.6}
      .mig-stat b{font-size:22px;line-height:1;font-variant-numeric:tabular-nums}
      .mig-card-head{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:15px}
      .mig-card-head>div:first-child{display:flex;flex-direction:column;gap:5px}
      .mig-card-head b{font-size:15px;font-weight:800}
      .mig-card-head small,.mig-field>span,.mig-field>label,.mig-input-head small{font-size:12px;color:var(--muted,#64748b);line-height:1.8}
      .mig-actions-inline{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
      .mig-actions-inline button{white-space:nowrap}
      .mig-provision-strip,.mig-chips{display:flex;flex-wrap:wrap;gap:8px}
      .mig-mini-pill{display:inline-flex;align-items:center;gap:5px;border:1px solid var(--border,rgba(97,122,164,.23));border-radius:999px;padding:6px 11px;font-size:11px;background:rgba(102,129,172,.055);overflow-wrap:anywhere}
      .mig-mini-pill b{font-variant-numeric:tabular-nums}
      .mig-protocol-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(115px,1fr));gap:8px;margin-top:14px}
      .mig-protocol{border:1px solid var(--border,rgba(109,132,166,.2));background:rgba(112,138,185,.045);padding:10px;border-radius:12px;display:grid;gap:3px}
      .mig-protocol>span{font-size:12px;font-weight:700}
      .mig-protocol>strong{font-size:17px;font-variant-numeric:tabular-nums}
      .mig-protocol>small{font-size:11px;color:var(--muted,#71809a)}
      .mig-steps{display:flex;gap:6px;flex-wrap:wrap}
      .mig-steps span{font-size:10px;font-weight:750;border:1px solid var(--border,rgba(101,126,157,.25));border-radius:999px;padding:5px 9px;color:var(--muted,#63758e)}
      .mig-form-grid{display:grid;grid-template-columns:minmax(180px,1fr) minmax(240px,1.2fr) minmax(180px,1fr);gap:13px;align-items:start}
      .mig-field{min-width:0;display:flex;flex-direction:column;gap:7px;margin:0}
      .mig-field select,.mig-field input:not([type=file]),.mig-field textarea{width:100%;min-width:0;border:1px solid var(--border,rgba(112,131,168,.3));border-radius:11px;padding:10px 12px;background:var(--input-bg,var(--card,rgba(255,255,255,.85)));color:var(--text,inherit);font:inherit}
      .mig-field textarea{font-family:ui-monospace,Consolas,monospace;line-height:1.6;direction:ltr;text-align:left;resize:vertical;min-height:112px}
      .mig-field input[type=file]{width:100%;font-size:12px;max-width:100%}
      .mig-field input[type=file]::file-selector-button{border:1px solid var(--border,rgba(92,117,160,.22));padding:8px 12px;margin-inline-end:10px;border-radius:9px;background:rgba(80,122,220,.09);color:inherit;cursor:pointer}
      .mig-target-row{display:flex;gap:7px}
      .mig-target-row input{flex:1;min-width:90px}
      .mig-target-row button{white-space:nowrap}
      .mig-target-ok{color:#12805c!important}
      .mig-target-error,.mig-warning-text{color:#d97706!important}
      .mig-protocol-summary{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:5px 10px;border:1px solid var(--border,rgba(110,136,168,.2));border-radius:11px;min-height:43px}
      .mig-protocol-summary span{font-size:12px;font-weight:600}
      .mig-chips{padding-top:5px}
      .mig-chips span{padding:5px 8px;border-radius:8px;background:rgba(74,121,230,.08);font-size:11px}
      .mig-import-source{margin-top:15px;background:rgba(102,136,176,.045);border:1px dashed var(--border,rgba(106,139,175,.27));padding:16px;border-radius:14px;display:flex;flex-direction:column;gap:10px}
      .mig-import-source>small{color:var(--muted,#64748b);line-height:1.8}
      .mig-input-head{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
      .mig-input-head>div{display:flex;flex-direction:column;gap:3px}
      .mig-input-head b{font-size:13px}
      .mig-file-field{max-width:560px}
      .mig-footer-actions{display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap;margin-top:17px}
      .mig-footer-actions>small,.mig-session-note{font-size:11px;line-height:1.9;color:var(--muted,#64748b)}
      .mig-session-note{display:block;margin-top:9px}
      .mig-preview-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-bottom:15px}
      .mig-preview-metrics>div{border:1px solid var(--border,rgba(93,124,164,.2));border-radius:12px;padding:12px;display:flex;flex-direction:column;gap:8px}
      .mig-preview-metrics small{font-size:11px;color:var(--muted,#64748b)}
      .mig-preview-metrics b{font-size:20px;font-variant-numeric:tabular-nums}
      .mig-table-wrap{overflow:auto;border:1px solid var(--border,rgba(104,128,163,.2));border-radius:13px}
      .mig-table{width:100%;min-width:650px;border-collapse:collapse;font-size:12px;text-align:start}
      .mig-table th{background:rgba(90,117,156,.08);color:var(--muted,#5a6d85);font-weight:750}
      .mig-table th,.mig-table td{text-align:start;padding:11px 12px;border-bottom:1px solid var(--border,rgba(97,125,162,.1));overflow-wrap:anywhere}
      .mig-table tbody tr:last-child td{border-bottom:0}
      .mig-table tbody tr:hover{background:rgba(78,115,206,.035)}
      .mig-pagination{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:12px}
      .mig-pagination small{font-size:11px;color:var(--muted,#64748b)}
      .mig-history summary{cursor:pointer;font-size:14px;font-weight:800;display:flex;justify-content:space-between;align-items:center;gap:10px}
      .mig-history-content{margin-top:15px}
      .mig-empty{font-size:12px;color:var(--muted,#64748b);padding:12px}
      .mig-notice{margin-block:12px}
      @media(max-width:1050px){.mig-hero{grid-template-columns:1fr}.mig-form-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.mig-stats{grid-template-columns:repeat(4,minmax(0,1fr))}}
      @media(max-width:690px){.mig-hero{padding:16px}.mig-hero-copy h2{font-size:18px}.mig-stats,.mig-preview-metrics,.mig-form-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.mig-steps{display:none}.mig-footer-actions{align-items:stretch}.mig-footer-actions .mig-actions-inline{width:100%}.mig-footer-actions button{flex:1}}
      @media(max-width:440px){.mig-stats,.mig-preview-metrics,.mig-form-grid{grid-template-columns:1fr 1fr}.mig-field:nth-child(2){grid-column:1/-1}.mig-stat{min-height:68px;padding:10px}.mig-stat b{font-size:19px}.mig-target-row{flex-wrap:wrap}}

    `}</style>

    <div className="mig-hero" dir="rtl">
      <div className="mig-hero-copy">
        <span className="mig-eyebrow">{pick("مدیریت انتقال اشتراک‌ها","SUBSCRIPTION MIGRATION")}</span>
        <h2>{pick("انتقال ایمن اکانت‌ها","Safe account migration")}</h2>
        <p>{pick("بررسی مبدا، تأیید مقصد و انتقال دسته‌ای بدون تغییر اطلاعات کاربران فعلی","Validate the source, verify the destination and transfer accounts in bounded batches.")}</p>
      </div>
      <div className="mig-stats" aria-label={pick("آمار انتقال","Migration statistics")}>
        <div className="mig-stat"><small>{pick("انتقال‌شده از مبدا","Already imported")}</small><b>{overview?.source===source?overview.total_imported.toLocaleString():(overviewLoading?"…":"—")}</b></div>
        <div className="mig-stat"><small>{pick("آماده در پیش‌نمایش","Preview ready")}</small><b>{dryRun?readyRecords.length.toLocaleString():"—"}</b></div>
        <div className="mig-stat"><small>{pick("نیازمند بررسی","Preview warnings")}</small><b>{dryRun?dryRun.summary.warning_records.toLocaleString():"—"}</b></div>
        <div className="mig-stat"><small>{pick("پروتکل با کانفیگ","Configured protocols")}</small><b>{migrationStatus?.source===source?configuredCount+"/15":"—"}</b></div>
      </div>
    </div>

    {error&&<div className="runtime-error mig-notice" role="alert">{error}</div>}
    {ok&&<div className="runtime-success mig-notice" role="status">{ok}</div>}

    <Card>
      <div className="mig-card-head">
        <div><b>{pick("وضعیت آماده‌سازی واقعی","Actual provisioning status")}</b>
          <small>{pick("ثبت در دیتابیس با ساخت کانفیگ روی نودها متفاوت است.","Database snapshots are not the same as usable node configs.")}</small>
        </div>
        <div className="mig-actions-inline">
          <button className="ghost" type="button" onClick={()=>void refreshMigrationStatus()} disabled={statusLoading||busy}>
            {statusLoading?pick("در حال بررسی","Checking"):pick("تازه‌سازی","Refresh")}
          </button>
          <button className="ghost" type="button" onClick={()=>setShowProvisioning(value=>!value)} aria-expanded={showProvisioning}>
            {showProvisioning?pick("بستن جزئیات","Hide details"):pick("جزئیات پروتکل‌ها","Protocol details")}
          </button>
        </div>
      </div>
      <div className="mig-provision-strip">
        <span className="mig-mini-pill">{pick("منبع","Source")}: <b>{sourceLabel[source]}</b></span>
        <span className="mig-mini-pill">{pick("اشتراک منتقل‌شده","Imported subscriptions")}: <b>{migrationStatus?.source===source?migrationStatus.subscriptions:"—"}</b></span>
        <span className="mig-mini-pill">{pick("کانفیگ‌های ثبت‌شده","Configured rows")}: <b>{migrationStatus?.source===source?configuredTotal:"—"}</b></span>
        <span className="mig-mini-pill">{pick("آماده‌سازی کامل","Fully provisioned")}: <b>{migrationStatus?.source===source?(migrationStatus.fully_provisioned?pick("تأیید شده","Verified"):pick("تأیید نشده","Not verified")):"—"}</b></span>
      </div>
      {showProvisioning&&<div className="mig-protocol-grid">
        {(migrationStatus?.source===source?migrationStatus.protocols:ALL_MIGRATION_PROTOCOLS.map(protocol=>({protocol,declared:0,configured:0}))).map(item=>
          <div className="mig-protocol" key={item.protocol}>
            <span>{item.protocol}</span>
            <strong>{migrationStatus?.source===source?item.configured.toLocaleString():"—"}</strong>
            <small>{pick("از","of")} {migrationStatus?.source===source?migrationStatus.subscriptions.toLocaleString():"—"}</small>
          </div>
        )}
      </div>}
    </Card>

    <Card>
      <div className="mig-card-head">
        <div>
          <b>{pick("انتقال جدید","New migration")}</b>
          <small>{pick("سه مرحله: انتخاب مبدا و مقصد، بررسی بدون تغییر، سپس انتقال رکوردهای آماده","Three steps: select, preview without writes, import approved records.")}</small>
        </div>
        <div className="mig-steps" aria-hidden="true">
          <span>01 {pick("انتخاب","Select")}</span><span>02 {pick("بررسی","Preview")}</span><span>03 {pick("انتقال","Import")}</span>
        </div>
      </div>

      <div className="mig-form-grid" dir="rtl">
        <label className="mig-field">
          <span>{pick("پنل مبدا","Source panel")}</span>
          <select value={source} disabled={busy} onChange={event=>{
            const next=event.target.value as Source;
            setSource(next);setDryRun(null);setPreviewPage(0);
            setMigrationStatus(null);setTargetCheck(null);
            setImportSummary(null);setOk("");setError("");
          }}>
            <option value="sanaei">سنایی / 3x-ui</option>
            <option value="marzban">مرزبان</option>
            <option value="pasargad">پاسارگاد</option>
            <option value="eylan">ایلان</option>
          </select>
        </label>
        <div className="mig-field">
          <label htmlFor="migration-target-id">{pick("شناسه کاربر مقصد در TwinPanel","Destination user ID")}</label>
          <div className="mig-target-row">
            <input id="migration-target-id" type="number" min="1" step="1" value={targetUserId}
              disabled={busy||targetLoading} onChange={event=>{
                setTargetUserId(event.target.value);setTargetCheck(null);setImportSummary(null);
              }} placeholder={pick("شناسه کاربر","User ID")}/>
            <button className="ghost" type="button" disabled={busy||targetLoading||!targetUserId}
              onClick={()=>void checkTarget()}>
              {targetLoading?pick("بررسی...","Checking..."):pick("تأیید مقصد","Verify")}
            </button>
          </div>
          {targetCheck&&<small className={targetCheck.exists&&targetCheck.active?"mig-target-ok":"mig-target-error"}>
            {targetCheck.exists&&targetCheck.active
              ?pick("مقصد فعال است: "+(targetCheck.display_name||"")+" · "+targetCheck.existing_imports+" انتقال قبلی از این مبدا",
                    "Active destination: "+(targetCheck.display_name||"")+" · "+targetCheck.existing_imports+" existing imports")
              :pick("این کاربر وجود ندارد یا غیرفعال است.","The user does not exist or is inactive.")}
          </small>}
        </div>
        <div className="mig-field">
          <span>{pick("پروتکل‌های مقصد","Destination protocols")}</span>
          <div className="mig-protocol-summary">
            <span><b>15</b> {pick("پروتکل استاندارد","canonical protocols")}</span>
            <button type="button" className="ghost" onClick={()=>setShowProtocols(v=>!v)} aria-expanded={showProtocols}>
              {showProtocols?pick("بستن","Hide"):pick("نمایش لیست","Show list")}
            </button>
          </div>
          {showProtocols&&<div className="mig-chips">{ALL_MIGRATION_PROTOCOLS.map(key=><span key={key}>{key}</span>)}</div>}
        </div>
      </div>

      {isEylan?
        <div className="mig-import-source">
          <label className="mig-field">
            <span>{pick("فایل بکاپ ایلان","Eylan backup file")}</span>
            <input type="file" disabled={busy} accept=".tar,.tar.gz,.tgz,.zip,application/gzip,application/zip"
              onChange={event=>{setEylanFile(event.target.files?.[0]||null);setDryRun(null);setPreviewPage(0);setImportSummary(null);setOk("");setError("");}}/>
          </label>
          <small>{pick("حجم، مصرف، رمز و تاریخ انقضا منتقل می‌شوند. ساخت کانفیگ پروتکل‌ها پس از ثبت حساب جداگانه ارزیابی می‌شود.","Usage, limits, password and expiry are migrated. Actual protocol provisioning is verified separately.")}</small>
          {eylanFile&&<span className="mig-mini-pill">{eylanFile.name} · {formatBytes(eylanFile.size)}</span>}
        </div>
      :
        <div className="mig-import-source">
          <div className="mig-input-head">
            <div><b>{pick("داده‌های پنل مبدا","Source export")}</b>
              <small>{pick("فایل JSON انتخاب کنید یا داده‌ها را مستقیم وارد کنید.","Choose a JSON file or paste exported records.")}</small>
            </div>
            <button type="button" className="ghost" disabled={busy} onClick={()=>setShowJsonInput(v=>!v)} aria-expanded={showJsonInput}>
              {showJsonInput?pick("بستن ویرایشگر","Close editor"):pick("ورود دستی JSON","Paste JSON")}
            </button>
          </div>
          <label className="mig-field mig-file-field">
            <span>{pick("انتخاب فایل JSON","Choose JSON file")}</span>
            <input type="file" accept=".json,application/json" disabled={busy}
              onChange={event=>void chooseJsonFile(event.target.files?.[0]||null)}/>
          </label>
          {jsonFileName&&<span className="mig-mini-pill">{jsonFileName} · {formatBytes(new TextEncoder().encode(raw).length)}</span>}
          {showJsonInput&&<label className="mig-field mig-editor">
            <span>{pick("JSON خروجی پنل مبدا","Source export JSON")}</span>
            <textarea value={raw} disabled={busy} onChange={event=>{
              setRaw(event.target.value);setJsonFileName("");
              setDryRun(null);setPreviewPage(0);setImportSummary(null);setOk("");setError("");
            }} rows={8} spellCheck={false}
              placeholder={pick("JSON خروجی پنل مبدا را اینجا قرار دهید...","Paste the source-panel export JSON here...")}/>
          </label>}
          {!showJsonInput&&raw.trim()&&!jsonFileName&&<span className="mig-mini-pill">{pick("JSON وارد شده","JSON entered")} · {formatBytes(new TextEncoder().encode(raw).length)}</span>}
        </div>
      }

      <div className="mig-footer-actions">
        <small>{pick("پیش‌نمایش فقط بررسی می‌کند و چیزی در دیتابیس تغییر نمی‌دهد.","Preview makes no database changes.")}</small>
        <div className="mig-actions-inline">
          <button className="ghost" type="button" onClick={()=>void runDry()} disabled={busy||(isEylan?!eylanFile:!raw.trim())}>
            {pick("۱. بررسی بدون انتقال","1. Safe preview")}
          </button>
          <button className="primary" type="button" onClick={()=>void importReady()}
            disabled={busy||targetLoading||readyRecords.length===0||dryRun?.source!==source}>
            {pick("۲. انتقال رکوردهای آماده","2. Import ready records")}
            {readyRecords.length>0?" ("+readyRecords.length.toLocaleString()+")":""}
          </button>
        </div>
      </div>
      <small className="mig-session-note">{pick("نتیجه این عملیات تا رفرش صفحه باقی می‌ماند؛ سابقه ثبت‌شده در بخش پایین قابل بررسی است. بعد از رفرش این نتیجه از صفحه پاک می‌شود.",
        "The current operation result is session-only. Saved history appears below. Import results are shown only for this session and clear on refresh.")}</small>
    </Card>

    {dryRun&&<Card>
      <div className="mig-card-head">
        <div><b>{pick("نتیجه پیش‌نمایش","Preview results")}</b><small>{sourceLabel[dryRun.source]}</small></div>
        <Badge tone={dryRun.summary.warning_records?"warn":"ok"}>{readyRecords.length.toLocaleString()} / {dryRun.summary.expanded_records.toLocaleString()} {pick("آماده","ready")}</Badge>
      </div>
      <div className="mig-preview-metrics">
        <div><small>{pick("ورودی","Input")}</small><b>{dryRun.summary.input_records.toLocaleString()}</b></div>
        <div><small>{pick("استخراج‌شده","Expanded")}</small><b>{dryRun.summary.expanded_records.toLocaleString()}</b></div>
        <div><small>{pick("آماده انتقال","Ready")}</small><b>{dryRun.summary.ready_records.toLocaleString()}</b></div>
        <div><small>{pick("نیازمند بررسی","Warnings")}</small><b>{dryRun.summary.warning_records.toLocaleString()}</b></div>
      </div>
      <div className="mig-table-wrap">
        <table className="mig-table"><thead><tr>
          <th>#</th><th>{pick("نام کاربری","Username")}</th><th>{pick("شناسه مبدا","Source ID")}</th>
          {isEylan&&<><th>{pick("حجم کل","Total")}</th><th>{pick("مصرف","Used")}</th><th>{pick("انقضا","Expiry")}</th></>}
          {!isEylan&&<th>{pick("لینک قبلی","Legacy link")}</th>}
          <th>{pick("وضعیت","Status")}</th>
        </tr></thead><tbody>{displayedRecords.map(item=><tr key={String(item.index)+"-"+String(item.source_id)}>
          <td>{item.index+1}</td>
          <td>{String(item.username||"—")}</td>
          <td>{String(item.source_id||"—")}</td>
          {isEylan&&<><td>{formatBytes(item.traffic_limit_bytes)}</td><td>{formatBytes(item.traffic_used_bytes)}</td><td>{item.expires_at?new Date(item.expires_at).toLocaleString():"—"}</td></>}
          {!isEylan&&<td>{item.legacy_subscription_url?pick("موجود","Present"):"—"}</td>}
          <td>{item.ready_for_future_import?<Badge tone="ok">{pick("آماده","Ready")}</Badge>:
            <span className="mig-warning-text">{item.warnings.join("، ")||pick("بررسی لازم","Review")}</span>}</td>
        </tr>)}</tbody></table>
      </div>
      {dryRun.records.length>PREVIEW_PAGE_SIZE&&
        <div className="mig-pagination">
          <small>{pick("نمایش","Showing")} {previewPage*PREVIEW_PAGE_SIZE+1}–{Math.min((previewPage+1)*PREVIEW_PAGE_SIZE,dryRun.records.length)} {pick("از","of")} {dryRun.records.length}</small>
          <div className="mig-actions-inline">
            <button type="button" className="ghost" disabled={previewPage===0} onClick={()=>setPreviewPage(v=>v-1)}>{pick("قبلی","Previous")}</button>
            <button type="button" className="ghost" disabled={(previewPage+1)*PREVIEW_PAGE_SIZE>=dryRun.records.length} onClick={()=>setPreviewPage(v=>v+1)}>{pick("بعدی","Next")}</button>
          </div>
        </div>}
    </Card>}

    {importSummary&&<Card>
      <div className="mig-card-head"><div><b>{pick("خلاصه عملیات جاری","Current operation summary")}</b>
        <small>{pick("آمار ثبت در دیتابیس؛ وضعیت اتصال سرورها جداگانه ارزیابی می‌شود.","Database import counts; node connectivity is checked separately.")}</small></div></div>
      <div className="mig-preview-metrics">
        <div><small>{pick("کل بررسی‌شده","Processed")}</small><b>{importSummary.total}</b></div>
        <div><small>{pick("اشتراک جدید","New")}</small><b>{importSummary.imported}</b></div>
        <div><small>{pick("قبلاً منتقل‌شده","Existing")}</small><b>{importSummary.existing}</b></div>
        <div><small>{pick("V2Ray آماده‌سازی‌شده","V2Ray provisioned")}</small><b>{importSummary.provisioned}</b></div>
      </div>
    </Card>}

    <Card>
      <details className="mig-history">
        <summary>{pick("سابقه انتقال‌های این مبدا","Recent imports from this source")}
          <span className="mig-mini-pill">{overview?.source===source?overview.total_imported.toLocaleString():(overviewLoading?"…":"—")}</span>
        </summary>
        <div className="mig-history-content">
          <div className="mig-card-head">
            <small>{pick("فقط آخرین ۱۲ مورد؛ بدون نمایش رمز، توکن یا لینک خصوصی","Latest 12 only; no passwords, tokens or private links.")}</small>
            <button type="button" className="ghost" disabled={overviewLoading} onClick={()=>{
              setOverviewLoading(true);
              void fetchOverview(source).catch(reason=>setError(reason instanceof Error?reason.message:String(reason)))
                .finally(()=>setOverviewLoading(false));
            }}>{pick("تازه‌سازی","Refresh")}</button>
          </div>
          {overview?.source===source&&overview.history.length?
          <div className="mig-table-wrap"><table className="mig-table"><thead><tr>
            <th>{pick("نام حساب","Account")}</th><th>{pick("شناسه مبدا","Source ID")}</th>
            <th>{pick("شناسه اشتراک","Subscription")}</th><th>{pick("وضعیت","Status")}</th>
            <th>{pick("زمان","Date")}</th>
          </tr></thead><tbody>{overview.history.map(item=><tr key={item.id}>
            <td>{item.account_username||"—"}</td><td>{item.source_id}</td>
            <td>{item.subscription_id}</td><td>{item.subscription_status}</td>
            <td>{item.created_at?new Date(item.created_at).toLocaleString():"—"}</td>
          </tr>)}</tbody></table></div>
          :<p className="mig-empty">{overviewLoading?pick("در حال دریافت سابقه...","Loading history..."):pick("رکوردی برای نمایش نیست.","No imports to display.")}</p>}
        </div>
      </details>
    </Card>
  </div></Shell>;
}
