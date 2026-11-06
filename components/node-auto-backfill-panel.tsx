"use client";

import {useCallback,useEffect,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

type NodeBackfillStatus={
  node_id:number;
  state:string;
  current_protocol?:string|null;
  stage?:number;
  stages_total?:number;
  processed_pairs?:number;
  successful_batches?:number;
  attempts?:number;
  last_error?:string|null;
  pause_requested?:boolean;
  updated_at?:string|null;
};
const liveStates=new Set(["queued","running","retry"]);

export function NodeAutoBackfillPanel({nodeId}:{nodeId:number}){
  const {pick}=useI18n();
  const [value,setValue]=useState<NodeBackfillStatus|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const load=useCallback(async()=>{
    const token=getCustomerToken();
    if(!token)return;
    const response=await fetch(`${API_BASE}/v1/nodes/${nodeId}/auto-backfill-status`,{
      headers:{Authorization:`Bearer ${token}`},cache:"no-store",
    });
    if(!response.ok)throw new Error(`API ${response.status}`);
    setValue(await response.json() as NodeBackfillStatus);
  },[nodeId]);

  useEffect(()=>{
    setValue(null);setError("");
    void load().catch(()=>{});
    const timer=window.setInterval(()=>void load().catch(()=>{}),12000);
    return()=>window.clearInterval(timer);
  },[load]);

  const action=async(endpoint:string)=>{
    if(busy)return;
    setBusy(true);setError("");
    try{
      const token=getCustomerToken();
      if(!token)throw new Error(pick("ابتدا وارد پنل شوید","Please sign in"));
      const response=await fetch(`${API_BASE}/v1/nodes/${nodeId}/${endpoint}`,{
        method:"POST",headers:{Authorization:`Bearer ${token}`},cache:"no-store",
      });
      if(!response.ok)throw new Error(`API ${response.status}`);
      await load();
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  };

  const running=Boolean(value&&liveStates.has(value.state));
  const stateLabel:Record<string,string>={
    not_queued:pick("شروع نشده","Not started"),
    queued:pick("در صف","Queued"),
    running:pick("در حال ساخت","Provisioning"),
    retry:pick("تلاش مجدد","Retrying"),
    done:pick("تکمیل شده","Complete"),
    paused:pick("متوقف شده","Paused"),
    failed:pick("نیاز به بررسی","Needs attention"),
    cancelled:pick("لغوشده","Cancelled"),
  };
  return <div className="runtime-choice-section" style={{marginBlock:"12px",padding:"12px",border:"1px solid var(--border, #5553)",borderRadius:12}}>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:8}}>
      <strong>{pick("فعال‌سازی خودکار کاربران روی نود","Automatic node activation")}</strong>
      <b>{value?stateLabel[value.state]||value.state:"…"}</b>
    </div>
    <small>{pick(
      "بعد از انتشار نود، اکانت‌های فعال با پروتکل‌های مجازشان در دسته‌های کوچک تکمیل می‌شوند. Restart باعث ازبین‌رفتن صف نمی‌شود؛ V2Ray مستقل مدیریت می‌شود.",
      "Eligible accounts are provisioned in small batches with plan entitlements preserved. Jobs resume after restart; V2Ray is managed separately.",
    )}</small>
    {value?.state!=="not_queued"&&value?<>
      <div className="runtime-info-list" style={{marginTop:8}}>
        <div><span>{pick("مرحله","Stage")}</span><b>{value.current_protocol||"—"} ({value.stage||0}/{value.stages_total||5})</b></div>
        <div><span>{pick("کانفیگ تکمیل‌شده","Completed configs")}</span><b>{Number(value.processed_pairs||0).toLocaleString("fa-IR")}</b></div>
        <div><span>{pick("دسته‌های موفق","Successful batches")}</span><b>{Number(value.successful_batches||0).toLocaleString("fa-IR")}</b></div>
      </div>
      {value.last_error?<small role="status">{pick("آخرین مانع","Last issue")}: {value.last_error}</small>:null}
      {value.pause_requested?<small>{pick("توقف پس از تکمیل دسته جاری","Will pause after current batch")}</small>:null}
    </>:null}
    {error?<div className="runtime-error">{error}</div>:null}
    <div className="action-row" style={{marginTop:8}}>
      <button type="button" className="primary-soft" disabled={busy||running}
        onClick={()=>void action(value?.state==="not_queued"?"publish-all-users":"auto-backfill-start")}>
        {busy?"…":value?.state==="not_queued"?pick("انتشار برای همه و شروع خودکار","Publish to all & start"):
          pick("شروع / تلاش مجدد","Start / retry")}
      </button>
      {running?<button type="button" className="ghost" disabled={busy} onClick={()=>void action("auto-backfill-pause")}>
        {pick("توقف ایمن","Pause safely")}
      </button>:null}
      <button type="button" className="ghost" disabled={busy} onClick={()=>void load().catch(()=>setError("STATUS_FETCH_FAILED"))}>
        {pick("به‌روزرسانی وضعیت","Refresh status")}
      </button>
    </div>
  </div>;
}
