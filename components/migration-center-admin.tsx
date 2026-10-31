"use client";

import {useEffect,useMemo,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {Badge,Card,Shell} from "./ui";

type Source="sanaei"|"marzban"|"pasargad";
type AnyRow=Record<string,unknown>;

type DryRunRecord={
  index:number;
  source:Source;
  source_id:unknown;
  username:unknown;
  credentials:Record<string,unknown>;
  legacy_subscription_url:unknown;
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

type ImportHistoryItem={
  id:number;
  source:Source;
  source_id:string;
  subscription_id:number;
  user_id:number|null;
  account_username:string|null;
  subscription_status:string;
  legacy_url:string|null;
  legacy_token:string|null;
  status:string;
  created_at:string|null;
};

type BatchImportResult={
  ok:boolean;
  imported:number;
  existing:number;
  subscriptions:number;
  provision:{
    ok:boolean;
    subscriptions:number;
    nodes:number;
    node_restarts:number;
    errors:Array<{node:string;error:string}>;
  };
};

async function api<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  if(!response.ok){
    let detail=`API error ${response.status}`;
    try{
      const body=await response.json() as {detail?:unknown;message?:unknown};
      if(typeof body.detail==="string")detail=body.detail;
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
    if(!parsed.every(item=>item&&typeof item==="object"&&!Array.isArray(item)))throw new Error("JSON array must contain objects only");
    return parsed as AnyRow[];
  }
  if(parsed&&typeof parsed==="object")return [parsed as AnyRow];
  throw new Error("JSON must be an object or array of objects");
}

const sourceLabel:Record<Source,string>={sanaei:"سنایی / 3x-ui",marzban:"مرزبان",pasargad:"پاسارگاد"};

export function MigrationCenterAdmin(){
  const {pick}=useI18n();
  const [source,setSource]=useState<Source>("sanaei");
  const [raw,setRaw]=useState("");
  const [targetUserId,setTargetUserId]=useState("");
  const [protocols,setProtocols]=useState("v2ray");
  const [dryRun,setDryRun]=useState<DryRunResult|null>(null);
  const [history,setHistory]=useState<ImportHistoryItem[]>([]);
  const [busy,setBusy]=useState(false);
  const [loadingHistory,setLoadingHistory]=useState(true);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const readyRecords=useMemo(()=>dryRun?.records.filter(item=>item.ready_for_future_import)??[],[dryRun]);

  const loadHistory=async()=>{
    setLoadingHistory(true);
    try{
      const result=await api<{count:number;items:ImportHistoryItem[]}>("/v1/admin/migration-center/imports");
      setHistory(result.items||[]);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setLoadingHistory(false);}
  };

  useEffect(()=>{void loadHistory();},[]);

  const runDry=async()=>{
    setError("");setOk("");setDryRun(null);
    try{
      const records=parseRecords(raw);
      setBusy(true);
      const result=await api<DryRunResult>("/v1/admin/migration-center/dry-run",{
        method:"POST",
        body:JSON.stringify({source,records}),
      });
      setDryRun(result);
      setOk(pick("بررسی انجام شد؛ هنوز هیچ تغییری در دیتابیس ثبت نشده است.","Dry-run completed; no database writes were performed."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const importReady=async()=>{
    setError("");setOk("");
    const userId=Number(targetUserId);
    if(!Number.isInteger(userId)||userId<=0){setError(pick("شناسه کاربر TwinPanel معتبر وارد کنید.","Enter a valid TwinPanel user ID."));return;}
    if(!dryRun||readyRecords.length===0){setError(pick("ابتدا Dry-run بگیرید و رکورد آماده داشته باشید.","Run a dry-run first and make sure at least one record is ready."));return;}
    const protocolList=protocols.split(",").map(item=>item.trim().toLowerCase()).filter(Boolean);
    const effectiveProtocols=protocolList.length?protocolList:["v2ray"];
    setBusy(true);
    try{
      if(effectiveProtocols.length===1&&effectiveProtocols[0]==="v2ray"){
        const result=await api<BatchImportResult>("/v1/admin/migration-center/import-batch",{
          method:"POST",
          body:JSON.stringify({
            source,
            records:readyRecords,
            target_user_id:userId,
            protocols:["v2ray"],
          }),
        });

        if(!result.ok||!result.provision.ok){
          const failedNodes=result.provision.errors.map(item=>`${item.node}: ${item.error}`).join(" | ");
          setError(pick(
            `انتقال دیتابیس انجام شد اما Provision بعضی نودها کامل نشد. ${failedNodes}`,
            `Database import completed, but provisioning did not complete on every node. ${failedNodes}`,
          ));
        }else{
          setOk(pick(
            `انتقال و ساخت روی نودها تمام شد: ${result.imported} رکورد جدید، ${result.existing} رکورد موجود، ${result.provision.node_restarts} ری‌استارت Xray.`,
            `Import and node provisioning finished: ${result.imported} new, ${result.existing} existing, ${result.provision.node_restarts} Xray restarts.`,
          ));
        }
        await loadHistory();
        return;
      }

      let imported=0;
      let existing=0;
      for(const record of readyRecords){
        const result=await api<{imported:boolean;idempotent:boolean}>("/v1/admin/migration-center/import",{
          method:"POST",
          body:JSON.stringify({
            source,
            record,
            target_user_id:userId,
            protocols:effectiveProtocols,
          }),
        });
        if(result.imported)imported+=1;
        else if(result.idempotent)existing+=1;
      }
      setOk(pick(`انتقال تمام شد: ${imported} رکورد جدید، ${existing} رکورد از قبل موجود.`,`Import finished: ${imported} new, ${existing} already imported.`));
      await loadHistory();
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  return <Shell active="/admin/migration-center"><div className="page">
    <div className="page-head">
      <div>
        <h1>{pick("مرکز انتقال اکانت‌ها","Migration Center")}</h1>
        <small>{pick("انتقال کنترل‌شده از سنایی، مرزبان و پاسارگاد با حفظ اطلاعات فعلی اکانت.","Controlled import from Sanaei, Marzban and Pasargad while preserving existing account material.")}</small>
      </div>
      <button className="ghost" onClick={()=>void loadHistory()} disabled={loadingHistory||busy}>{pick("بازخوانی","Reload")}</button>
    </div>

    {error&&<div className="runtime-error">{error}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}

    <Card>
      <div className="card-head">
        <div><b>{pick("وضعیت انتقال‌های قبلی","Previous imports")}</b><small>{pick("رکوردهایی که واقعاً وارد TwinPanel شده‌اند","Records already imported into TwinPanel")}</small></div>
        <Badge tone="violet">{history.length}</Badge>
      </div>
      {loadingHistory?<div className="runtime-loading">{pick("در حال دریافت...","Loading...")}</div>:history.length===0?
        <p>{pick("هنوز هیچ انتقال ثبت‌شده‌ای وجود ندارد.","No imports have been recorded yet.")}</p>:
        <div style={{overflowX:"auto"}}><table style={{width:"100%"}}><thead><tr>
          <th>{pick("منبع","Source")}</th><th>{pick("اکانت","Account")}</th><th>{pick("کاربر TwinPanel","TwinPanel user")}</th><th>{pick("اشتراک","Subscription")}</th><th>{pick("وضعیت","Status")}</th>
        </tr></thead><tbody>{history.map(item=><tr key={item.id}>
          <td>{sourceLabel[item.source]||item.source}</td>
          <td>{item.account_username||item.source_id}</td>
          <td>#{item.user_id??"—"}</td>
          <td>#{item.subscription_id}</td>
          <td><Badge tone={item.subscription_status==="active"?"ok":"warn"}>{item.subscription_status}</Badge></td>
        </tr>)}</tbody></table></div>}
    </Card>

    <Card>
      <div className="card-head"><div><b>{pick("انتقال جدید","New import")}</b><small>{pick("ابتدا Dry-run؛ سپس فقط رکوردهای آماده را Import کنید.","Dry-run first, then import only ready records.")}</small></div></div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))",gap:12}}>
        <label><span>{pick("پنل مبدا","Source panel")}</span><select value={source} onChange={event=>{setSource(event.target.value as Source);setDryRun(null);}} style={{width:"100%"}}>
          <option value="sanaei">سنایی / 3x-ui</option><option value="marzban">مرزبان</option><option value="pasargad">پاسارگاد</option>
        </select></label>
        <label><span>{pick("شناسه کاربر مقصد در TwinPanel","Target TwinPanel user ID")}</span><input type="number" min="1" value={targetUserId} onChange={event=>setTargetUserId(event.target.value)} placeholder="17" style={{width:"100%"}}/></label>
        <label><span>{pick("پروتکل‌ها","Protocols")}</span><input value={protocols} onChange={event=>setProtocols(event.target.value)} placeholder="v2ray,hysteria2" style={{width:"100%"}}/></label>
      </div>
      <p><small>{pick("نکته: Backend فعلی رکورد واردشده را به یک User موجود TwinPanel متصل می‌کند؛ ساخت خودکار User جدید و اتصال مستقیم به API پنل مبدا هنوز جزو این مرحله نیست.","Note: the current backend attaches imported records to an existing TwinPanel user. Automatic user creation and direct source-panel API sync are not part of this phase yet.")}</small></p>
      <label><span>{pick("JSON خروجی پنل مبدا","Source export JSON")}</span><textarea value={raw} onChange={event=>setRaw(event.target.value)} rows={14} spellCheck={false} placeholder={pick("JSON خروجی سنایی/مرزبان/پاسارگاد را اینجا قرار دهید...","Paste the Sanaei/Marzban/Pasargad export JSON here...")} style={{width:"100%",fontFamily:"monospace"}}/></label>
      <div className="action-row">
        <button className="ghost" onClick={()=>void runDry()} disabled={busy||!raw.trim()}>{pick("بررسی بدون انتقال","Dry-run")}</button>
        <button className="primary" onClick={()=>void importReady()} disabled={busy||readyRecords.length===0}>{pick("انتقال رکوردهای آماده","Import ready records")}</button>
      </div>
    </Card>

    {dryRun&&<Card>
      <div className="card-head"><div><b>{pick("نتیجه بررسی","Dry-run result")}</b><small>{sourceLabel[dryRun.source]}</small></div><Badge tone={dryRun.summary.warning_records?"warn":"ok"}>{dryRun.summary.ready_records}/{dryRun.summary.expanded_records} {pick("آماده","ready")}</Badge></div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(140px,1fr))",gap:10,marginBottom:12}}>
        <div><small>{pick("ورودی","Input")}</small><b style={{display:"block"}}>{dryRun.summary.input_records}</b></div>
        <div><small>{pick("رکورد استخراج‌شده","Expanded")}</small><b style={{display:"block"}}>{dryRun.summary.expanded_records}</b></div>
        <div><small>{pick("آماده انتقال","Ready")}</small><b style={{display:"block"}}>{dryRun.summary.ready_records}</b></div>
        <div><small>{pick("نیازمند بررسی","Warnings")}</small><b style={{display:"block"}}>{dryRun.summary.warning_records}</b></div>
      </div>
      <div style={{overflowX:"auto"}}><table style={{width:"100%"}}><thead><tr><th>#</th><th>{pick("نام کاربری","Username")}</th><th>{pick("شناسه مبدا","Source ID")}</th><th>{pick("لینک قدیمی","Legacy link")}</th><th>{pick("نتیجه","Result")}</th></tr></thead><tbody>{dryRun.records.map(item=><tr key={`${item.index}-${String(item.source_id)}`}>
        <td>{item.index+1}</td><td>{String(item.username||"—")}</td><td>{String(item.source_id||"—")}</td><td>{item.legacy_subscription_url?pick("موجود","Present"):"—"}</td><td>{item.ready_for_future_import?<Badge tone="ok">{pick("آماده","Ready")}</Badge>:<span>{item.warnings.join(", ")}</span>}</td>
      </tr>)}</tbody></table></div>
    </Card>}
  </div></Shell>;
}
