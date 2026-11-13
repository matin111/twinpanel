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
    `}</style>
    <Card>
      <div className="card-head">
        <div><b>{pick("وضعیت واقعی ۱۵ پروتکل","15-protocol provisioning status")}</b>
          <small>{pick("پروتکل ثبت‌شده با کانفیگ قابل استفاده تفاوت دارد؛ وضعیت را به‌صورت دستی تازه‌سازی کنید.","A selected protocol is not necessarily provisioned. Refresh this status on demand.")}</small>
        </div>
        <button className="ghost" onClick={()=>void refreshMigrationStatus()} disabled={statusLoading||busy}>
          {statusLoading?pick("در حال بررسی...","Checking..."):pick("بررسی وضعیت اتصال","Check provisioning")}
        </button>
      </div>
      {migrationStatus&&migrationStatus.source===source&&
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(135px,1fr))",gap:9}}>
          {migrationStatus.protocols.map(item=><div key={item.protocol} style={{padding:10,border:"1px solid var(--border,#28354a)",borderRadius:10}}>
            <small>{item.protocol}</small>
            <b style={{display:"block",marginTop:4}}>{item.configured.toLocaleString("fa-IR")} / {migrationStatus.subscriptions.toLocaleString("fa-IR")}</b>
          </div>)}
        </div>}
    </Card>

    {error&&<div className="runtime-error">{error}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}

    <Card>
      <div className="card-head"><div><b>{pick("انتقال جدید","New import")}</b><small>{pick("ابتدا Preview؛ سپس فقط رکوردهای آماده را Import کنید. نتیجه انتقال فقط در همین نشست نمایش داده می‌شود؛ بعد از رفرش این نتیجه از صفحه پاک می‌شود.","Preview first, then import only ready records. Import results are shown only for this session and clear on refresh.")}</small></div></div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))",gap:12}}>
        <label><span>{pick("پنل مبدا","Source panel")}</span><select value={source} onChange={event=>{const next=event.target.value as Source;setSource(next);setDryRun(null);setOk("");setError("");}} style={{width:"100%"}}>
          <option value="sanaei">سنایی / 3x-ui</option><option value="marzban">مرزبان</option><option value="pasargad">پاسارگاد</option><option value="eylan">ایلان</option>
        </select></label>
        <label><span>{pick("شناسه کاربر مقصد در TwinPanel","Target TwinPanel user ID")}</span><input type="number" min="1" value={targetUserId} onChange={event=>setTargetUserId(event.target.value)} placeholder="17" style={{width:"100%"}}/></label>
        <label><span>{pick("پروتکل‌ها","Protocols")}</span><input value={protocols} readOnly aria-label={pick("۱۵ پروتکل انتقال","15 migration protocols")} placeholder={ALL_PROTOCOLS_CSV} style={{width:"100%"}}/></label>
      </div>

      {isEylan?<>
        <p><small>{pick("بکاپ ایلان مستقیم خوانده می‌شود؛ فقط نام کاربری، رمز، حجم کل، مصرف واقعی (دانلود + آپلود) و تاریخ انقضا منتقل می‌شود. UUID و کانفیگ قدیمی منتقل نمی‌شود. برای بکاپ‌های بزرگ، ساخت رکوردها خودکار در بسته‌های کوچک انجام می‌شود تا Gateway Timeout رخ ندهد.","The Eylan backup is read directly; only username, password, total traffic, actual usage (download + upload), and expiry are imported. Old UUIDs and configs are not preserved. Large backups are staged automatically in small chunks to avoid gateway timeouts.")}</small></p>
        <label><span>{pick("فایل بکاپ ایلان","Eylan backup file")}</span><input type="file" accept=".tar,.tar.gz,.tgz,.zip,application/gzip,application/zip" onChange={event=>{setEylanFile(event.target.files?.[0]||null);setDryRun(null);}} style={{width:"100%"}}/></label>
        {eylanFile&&<small>{eylanFile.name}</small>}
      </>:<>
        <p><small>{pick("Backend رکورد واردشده را به یک User موجود TwinPanel متصل می‌کند.","The backend attaches imported records to an existing TwinPanel user.")}</small></p>
        <label><span>{pick("JSON خروجی پنل مبدا","Source export JSON")}</span><textarea value={raw} onChange={event=>setRaw(event.target.value)} rows={14} spellCheck={false} placeholder={pick("JSON خروجی پنل مبدا را اینجا قرار دهید...","Paste the source-panel export JSON here...")} style={{width:"100%",fontFamily:"monospace"}}/></label>
      </>}

      <div className="action-row">
        <button className="ghost" onClick={()=>void runDry()} disabled={busy||(isEylan?!eylanFile:!raw.trim())}>{pick("بررسی بدون انتقال","Preview / Dry-run")}</button>
        <button className="primary" onClick={()=>void importReady()} disabled={busy||readyRecords.length===0}>{pick("انتقال رکوردهای آماده","Import ready records")}</button>
      </div>
    </Card>

    {dryRun&&<Card>
      <div className="card-head"><div><b>{pick("نتیجه بررسی","Preview result")}</b><small>{sourceLabel[dryRun.source]}</small></div><Badge tone={dryRun.summary.warning_records?"warn":"ok"}>{dryRun.summary.ready_records}/{dryRun.summary.expanded_records} {pick("آماده","ready")}</Badge></div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(140px,1fr))",gap:10,marginBottom:12}}>
        <div><small>{pick("ورودی","Input")}</small><b style={{display:"block"}}>{dryRun.summary.input_records}</b></div><div><small>{pick("رکورد استخراج‌شده","Expanded")}</small><b style={{display:"block"}}>{dryRun.summary.expanded_records}</b></div><div><small>{pick("آماده انتقال","Ready")}</small><b style={{display:"block"}}>{dryRun.summary.ready_records}</b></div><div><small>{pick("نیازمند بررسی","Warnings")}</small><b style={{display:"block"}}>{dryRun.summary.warning_records}</b></div>
      </div>
      <div style={{overflowX:"auto"}}><table style={{width:"100%"}}><thead><tr><th>#</th><th>{pick("نام کاربری","Username")}</th><th>{pick("شناسه مبدا","Source ID")}</th>{isEylan&&<><th>{pick("رمز","Password")}</th><th>{pick("حجم کل","Total")}</th><th>{pick("مصرف","Used")}</th><th>{pick("انقضا","Expiry")}</th></>} {!isEylan&&<th>{pick("لینک قدیمی","Legacy link")}</th>}<th>{pick("نتیجه","Result")}</th></tr></thead><tbody>{dryRun.records.map(item=><tr key={`${item.index}-${String(item.source_id)}`}>
        <td>{item.index+1}</td><td>{String(item.username||"—")}</td><td>{String(item.source_id||"—")}</td>
        {isEylan&&<><td>{item.password?pick("موجود","Set"):"—"}</td><td>{formatBytes(item.traffic_limit_bytes)}</td><td>{formatBytes(item.traffic_used_bytes)}</td><td>{item.expires_at?new Date(item.expires_at).toLocaleString():"—"}</td></>}
        {!isEylan&&<td>{item.legacy_subscription_url?pick("موجود","Present"):"—"}</td>}
        <td>{item.ready_for_future_import?<Badge tone="ok">{pick("آماده","Ready")}</Badge>:<span>{item.warnings.join(", ")}</span>}</td>
      </tr>)}</tbody></table></div>
    </Card>}
  </div></Shell>;
}
