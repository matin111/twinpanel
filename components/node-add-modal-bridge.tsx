"use client";

import {FormEvent,useEffect,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {parityApi,type ProvisionInstallPayload} from "../lib/admin-parity-api";
import {useI18n} from "../lib/i18n";

type NodeDraft={host:string;port:number;username:string;password:string;name:string;node_type:"iran"|"exit";country_code:string;capacity_users:number;};
const defaultDraft:NodeDraft={host:"",port:22,username:"root",password:"",name:"",node_type:"exit",country_code:"DE",capacity_users:1000};
const NO_PROTOCOLS={install_cisco:false,cisco_port:443,install_openvpn:false,openvpn_port:1194,openvpn_transport:"udp" as const,install_wireguard:false,wireguard_port:51820,install_l2tp:false,install_v2ray:false,xray_port:8443};
function payloadOf(draft:NodeDraft):ProvisionInstallPayload{return {...draft,country_code:draft.node_type==="iran"?"IR":draft.country_code.trim().toUpperCase(),...NO_PROTOCOLS};}

type NodeInstallJob={
  job_id:string;node_name:string;node_id:number|null;
  state:"queued"|"running"|"waiting_backfill"|"completed"|"failed"|"interrupted";
  stage:string;installed_protocols:number|null;expected_protocols:number|null;
  users_assigned:number|null;backfill_pending:boolean;error_code:string|null;
  updated_at:string;
};
type BackfillJobs={queued:boolean;completed_pairs:number;families:Array<{protocol:string;state:string;completed_pairs:number}>};
const NODE_JOB_STORAGE="twinpanel-last-node-install-v1";

function NodeInstallProgress({job,error}:{job:NodeInstallJob|null;error:string}){
  const {pick}=useI18n();
  const [backfill,setBackfill]=useState<BackfillJobs|null>(null);
  useEffect(()=>{
    if(!job?.node_id||!job.backfill_pending)return;
    let active=true;
    const refresh=async()=>{
      const token=getCustomerToken();
      if(!token)return;
      try{
        const r=await fetch(API_BASE+"/v1/nodes/"+job.node_id+"/backfill-status",{
          cache:"no-store",headers:{Authorization:"Bearer "+token},
        });
        if(r.ok&&active)setBackfill(await r.json() as BackfillJobs);
      }catch{/* A transient outage must not fabricate progress. */}
    };
    void refresh();
    const timer=window.setInterval(()=>void refresh(),10000);
    return()=>{active=false;window.clearInterval(timer);};
  },[job?.node_id,job?.backfill_pending]);

  const phases:[string,string,string][]=[
    ["queued","درخواست ثبت شد","Request accepted"],
    ["installing_base","نصب زیرساخت پایه و سرویس‌ها","Installing core services"],
    ...(job?.expected_protocols?[
      ["installing_xray","آماده‌سازی Xray","Preparing Xray"],
      ["installing_modern","نصب پروتکل‌های مدرن","Installing modern protocols"],
      ["enrolling_users","ثبت اکانت‌ها در مدیریت مرکزی","Enrolling accounts"],
    ] as [string,string,string][]:[]),
  ];
  const index=phases.findIndex(([key])=>key===job?.stage);
  const finished=job?.state==="completed";
  const failed=job?.state==="failed"||job?.state==="interrupted";
  const waiting=job?.state==="waiting_backfill";
  const pending=job?.state==="queued"||job?.state==="running"||!job;
  return <div className="node-install-progress" aria-live="polite" aria-busy={pending}>
    <div className="node-install-progress-head">
      <div className={"node-install-orb "+(failed?"is-failed":finished?"is-done":"is-working")} aria-hidden="true">◉</div>
      <div>
        <b>{job?.node_name||pick("آماده‌سازی سرور","Preparing server")}</b>
        <small>{failed?pick("نصب کامل تأیید نشده است","Installation is not confirmed"):waiting?pick("کاربران به نود منتسب شده‌اند؛ اعمال کانفیگ‌ها هنوز در صف مرکزی است","Accounts are assigned; configuration application is still queued centrally"):finished?pick("مرحله نصب تأیید شد","Installation stage verified"):pick("وضعیت مراحل مستقیماً از سرور خوانده می‌شود","Stages are read directly from the server")}</small>
      </div>
    </div>
    <div className={"node-install-running-line "+(pending?"is-active":"")} aria-hidden="true"><span/></div>
    <div className="node-install-steps">
      {phases.map(([key,fa,en],i)=>{
        const done=finished||waiting||index>i;
        const current=index===i&&!finished&&!failed;
        return <div key={key} className={"node-install-step "+(done?"is-done":current?"is-current":"")}>
          <span className="node-install-step-icon">{done?"✓":current?"●":(i+1).toLocaleString("fa-IR")}</span>
          <span>{pick(fa,en)}</span>
          {current?<small>{pick("در حال اجرا","In progress")}</small>:done?<small>{pick("انجام شد","Done")}</small>:null}
        </div>;
      })}
    </div>
    {job?.installed_protocols!==null&&job?.installed_protocols!==undefined&&job?.expected_protocols!==null&&job?.expected_protocols!==undefined?<div className="node-install-count">{pick("پروتکل‌های گزارش‌شده","Protocols reported")}: <b>{job.installed_protocols.toLocaleString("fa-IR")} / {job.expected_protocols.toLocaleString("fa-IR")}</b></div>:null}
    {job?.users_assigned!==null&&job?.users_assigned!==undefined?<div className="node-install-count">{pick("کل اکانت‌های منتسب به نود","Total accounts assigned to node")}: <b>{job.users_assigned.toLocaleString("fa-IR")}</b></div>:null}
    {job?.backfill_pending?<div className="node-install-count">{pick("جفت‌کانفیگ‌های پردازش‌شده در صف موجود","Processed credential pairs in existing queue")}: <b>{backfill?backfill.completed_pairs.toLocaleString("fa-IR"):"—"}</b> {backfill?.queued?<span className="node-install-live-tag">{pick("صف فعال","Queue active")}</span>:null}</div>:null}
    {job?.error_code?<div className="runtime-warning">{pick("کد وضعیت","Status code")}: <code dir="ltr">{job.error_code}</code></div>:null}
    {error?<div className="runtime-warning">{error}</div>:null}
    {job?.state==="interrupted"?<div className="runtime-warning">{pick("به‌روزرسانی این کار متوقف شده؛ وضعیت واقعی نود را بررسی کنید. فرایند را خودکار موفق فرض نکنید.","Job updates are stale. Verify the node before retrying; completion cannot be assumed.")}</div>:null}
    <small>{pick("این نمایش از داده‌های واقعی API استفاده می‌کند؛ حرکت نوار به معنی درصد پیشرفت نیست.","Stages come from the API. The moving indicator is not a percent-complete estimate.")}</small>
  </div>;
}

export function NodeAddModalBridge(){
  const {pick}=useI18n();
  const [open,setOpen]=useState(false);
  const [draft,setDraft]=useState<NodeDraft>(defaultDraft);
  const [publishToAll,setPublishToAll]=useState(false);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [jobId,setJobId]=useState("");
  const [job,setJob]=useState<NodeInstallJob|null>(null);
  const [jobError,setJobError]=useState("");


  useEffect(()=>{
    const onClick=(event:MouseEvent)=>{
      const target=event.target as HTMLElement|null;
      const anchor=target?.closest?.('a[href="/admin/provision"]') as HTMLAnchorElement|null;
      if(!anchor)return;
      event.preventDefault();setError("");setOk("");setOpen(true);
    };
    document.addEventListener("click",onClick,true);
    return()=>document.removeEventListener("click",onClick,true);
  },[]);

  useEffect(()=>{
    try{
      const saved=window.localStorage.getItem(NODE_JOB_STORAGE);
      if(saved&&/^[0-9a-f-]{36}$/i.test(saved))setJobId(saved);
    }catch{/* Storage is optional. */}
  },[]);

  useEffect(()=>{
    if(!jobId)return;
    let active=true;
    const poll=async()=>{
      const token=getCustomerToken();
      if(!token)return;
      try{
        const r=await fetch(API_BASE+"/v1/nodes/install-jobs/"+encodeURIComponent(jobId),{
          cache:"no-store",headers:{Authorization:"Bearer "+token},
        });
        if(!r.ok)throw new Error("Status HTTP "+r.status);
        const value=await r.json() as NodeInstallJob;
        if(active){setJob(value);setJobError("");}
      }catch(reason){
        if(active)setJobError(reason instanceof Error?reason.message:String(reason));
      }
    };
    void poll();
    const timer=window.setInterval(()=>void poll(),3500);
    return()=>{active=false;window.clearInterval(timer);};
  },[jobId]);

  const resetInstall=()=>{
    try{window.localStorage.removeItem(NODE_JOB_STORAGE);}catch{}
    setJobId("");setJob(null);setJobError("");setError("");setOk("");
    setDraft(defaultDraft);setPublishToAll(false);setOpen(true);
  };

  const test=async()=>{
    if(busy)return;
    setBusy("test");setError("");setOk("");
    try{await parityApi.provisionTest({host:draft.host.trim(),port:draft.port,username:draft.username.trim()||"root",password:draft.password});setOk(pick("اتصال SSH و سیستم‌عامل سرور تایید شد.","SSH connection and server OS verified."));}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const submit=async(event:FormEvent)=>{
    event.preventDefault();if(busy)return;
    const token=getCustomerToken();
    if(!token){setError("AUTH_REQUIRED");return;}
    const payload={...payloadOf({...draft,host:draft.host.trim(),username:draft.username.trim()||"root",name:draft.name.trim()}),publish_to_all_users:draft.node_type==="exit"?publishToAll:false};
    setBusy("register");setError("");setOk("");
    try{
      const response=await fetch(`${API_BASE}/v1/nodes/install-background-v1`,{
        method:"POST",cache:"no-store",
        headers:{Authorization:`Bearer ${token}`,"Content-Type":"application/json"},
        body:JSON.stringify(payload),
      });
      const raw=await response.text();
      if(!response.ok)throw new Error(raw||`API error ${response.status}`);
      const accepted=JSON.parse(raw) as {job_id?:string};
      if(!accepted.job_id)throw new Error("Install job ID missing from API response");
      try{window.localStorage.setItem(NODE_JOB_STORAGE,accepted.job_id);}catch{}
      setJob(null);setJobError("");setJobId(accepted.job_id);
      setDraft(current=>({...current,password:""}));
      setOk("");
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setBusy("");
    }
  };

  return <>
    {!open&&jobId?<button className="node-install-reopen" type="button" onClick={()=>setOpen(true)}>{pick("مشاهده مراحل افزودن نود","View server installation stages")} · {job?.node_name||pick("در حال دریافت وضعیت","Loading status")}{job?.state==="running"?" ●":""}</button>:null}
    {!open&&ok?<div className="runtime-success" style={{marginBottom:12}}>{ok}</div>:null}
    {!open&&error?<div className="runtime-error" style={{marginBottom:12}}>{error}</div>:null}
    {open?<div className="runtime-modal" role="dialog" aria-modal="true">
    <button type="button" className="runtime-modal-bg" aria-label="close" onClick={()=>setOpen(false)}/>
    <div className="runtime-modal-card" style={{width:"min(760px,100%)"}}>
      <div className="card-head"><div><b>{pick("افزودن سرور","Add server")}</b><small>{pick("ثبت نود، SSH و زیرساخت پایه","Node registration, SSH and base infrastructure")}</small></div><button type="button" className="icon-button" onClick={()=>setOpen(false)}>×</button></div>
      {error?<div className="runtime-error">{error}</div>:null}
      {ok?<div className="runtime-success">{ok}</div>:null}
      {jobId?<div>
        <NodeInstallProgress job={job} error={jobError}/>
        <div className="action-row" style={{marginTop:16}}>
          <button className="primary-soft" type="button" onClick={()=>setOpen(false)}>{pick("بستن و ادامه در پس‌زمینه","Close; keep processing")}</button>
          <button className="ghost" type="button" onClick={resetInstall}>{pick("افزودن سرور دیگر","Add another server")}</button>
        </div>
      </div>:<form onSubmit={submit}>
        <div className="setting-grid">
          <label className="field"><span>{pick("نام سرور","Server name")}</span><input required value={draft.name} onChange={e=>setDraft(v=>({...v,name:e.target.value}))}/></label>
          <label className="field"><span>IP / Host</span><input required dir="ltr" value={draft.host} onChange={e=>setDraft(v=>({...v,host:e.target.value}))}/></label>
          <label className="field"><span>{pick("نوع نود","Node type")}</span><select value={draft.node_type} onChange={e=>setDraft(v=>{const node_type=e.target.value as "iran"|"exit";return {...v,node_type,country_code:node_type==="iran"?"IR":v.country_code==="IR"?"DE":v.country_code};})}><option value="iran">Iran</option><option value="exit">Exit</option></select></label>
          <label className="field"><span>{pick("کشور","Country")}</span><input dir="ltr" maxLength={2} value={draft.country_code} onChange={e=>setDraft(v=>({...v,country_code:e.target.value.toUpperCase()}))}/></label>
          <label className="field"><span>SSH Port</span><input type="number" min={1} max={65535} value={draft.port} onChange={e=>setDraft(v=>({...v,port:Number(e.target.value)||22}))}/></label>
          <label className="field"><span>SSH Username</span><input dir="ltr" value={draft.username} onChange={e=>setDraft(v=>({...v,username:e.target.value}))}/></label>
          <label className="field"><span>SSH Password</span><input type="password" autoComplete="new-password" required value={draft.password} onChange={e=>setDraft(v=>({...v,password:e.target.value}))}/></label>
          <label className="field"><span>{pick("ظرفیت کاربر","User capacity")}</span><input type="number" min={1} value={draft.capacity_users} onChange={e=>setDraft(v=>({...v,capacity_users:Number(e.target.value)||1}))}/></label>
        </div>
        {draft.node_type==="exit"?<div className="runtime-choice-section"><label className="toggle module-toggle"><span>{pick("نمایش برای همه کاربران سایت","Show for all site users")}</span><input type="checkbox" checked={publishToAll} onChange={e=>setPublishToAll(e.target.checked)}/><i/></label><small>{pick("با فعال‌کردن این گزینه، نود فقط به اشتراک‌های فعال قبلی که منقضی نشده‌اند و حجم دارند اضافه می‌شود. برای خریداران جدید، نود را جداگانه در پلن اقتصادی یا ویژه انتخاب کنید. کانفیگ‌های ناقص کاربران قبلی به‌صورت خودکار در صف پایدار ساخته می‌شوند و پیشرفت از مدیریت نود قابل مشاهده است.","When enabled, the node is assigned to eligible existing active subscriptions only. Select it separately in Economy/Premium plans for new purchases. Missing existing-account credentials are automatically queued and tracked under node management.")}</small></div>:null}
        <div className="runtime-warning">{pick("پروتکل‌ها بعد از ثبت از صفحه «پروتکل‌ها» مدیریت می‌شوند. برای Exit، Xray baseline به‌صورت خودکار آماده می‌شود.","Protocols are managed from Protocols after registration. Exit nodes automatically receive the Xray baseline.")}</div>
        <div className="action-row"><button type="button" className="ghost" disabled={Boolean(busy)||!draft.host||!draft.password} onClick={()=>void test()}>{busy==="test"?"…":pick("تست SSH","Test SSH")}</button><button className="primary" disabled={Boolean(busy)||!draft.host||!draft.password||!draft.name}>{busy==="register"?pick("در حال ثبت...","Registering..."):pick("ثبت و آماده‌سازی سرور","Register & prepare server")}</button></div>
      </form>}
    </div>
  </div>:null}
  </>;
}