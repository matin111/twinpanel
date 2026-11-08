"use client";

import {FormEvent,useEffect,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {parityApi,type ProvisionInstallPayload} from "../lib/admin-parity-api";
import {useI18n} from "../lib/i18n";
import {NodeCountryPicker,isSupportedNodeCountry,normalizeNodeCountry} from "./node-country-picker";

type NodeDraft={host:string;port:number;username:string;password:string;name:string;node_type:"iran"|"exit";country_code:string;capacity_users:number;};
const defaultDraft:NodeDraft={host:"",port:22,username:"root",password:"",name:"",node_type:"exit",country_code:"DE",capacity_users:1000};
const NO_PROTOCOLS={install_cisco:false,cisco_port:443,install_openvpn:false,openvpn_port:1194,openvpn_transport:"udp" as const,install_wireguard:false,wireguard_port:51820,install_l2tp:false,install_v2ray:false,xray_port:8443};
const EXIT_BASE_PROTOCOLS={...NO_PROTOCOLS,install_cisco:true,install_openvpn:true,install_wireguard:true,install_l2tp:true};
function payloadOf(draft:NodeDraft):ProvisionInstallPayload{return {...draft,country_code:draft.node_type==="iran"?"IR":normalizeNodeCountry(draft.country_code),...(draft.node_type==="exit"?EXIT_BASE_PROTOCOLS:NO_PROTOCOLS)};}

type NodeInstallJob={
  job_id:string;node_name:string;node_id:number|null;
  state:"queued"|"running"|"waiting_backfill"|"completed"|"failed"|"interrupted";
  stage:string;installed_protocols:number|null;expected_protocols:number|null;
  users_assigned:number|null;backfill_pending:boolean;error_code:string|null;
  updated_at:string;
};
type BackfillJobs={queued:boolean;completed_pairs:number;families:Array<{protocol:string;state:string;completed_pairs:number}>};
const NODE_JOB_STORAGE="twinpanel-last-node-install-v1";
// The backend persists stable codes, never raw SSH stderr or private details.
const NODE_INSTALL_FAILURE_GUIDANCE:Record<string,[string,string]>={
  NODE_OS_RELEASE_UNREADABLE:[
    "SSH وصل شد، اما سیستم‌عامل از /etc/os-release یا مسیر جایگزین قابل شناسایی نیست. فایل‌های سیستم‌عامل نود را بررسی کنید؛ نصب هنوز شروع نشده است.",
    "SSH succeeded, but the node OS cannot be identified from os-release or fallback. Inspect OS metadata; installation has not started.",
  ],
  NODE_OS_UNSUPPORTED:[
    "سیستم‌عامل این سرور پشتیبانی نمی‌شود؛ برای نصب نود، Ubuntu یا Debian لازم است.",
    "Unsupported node OS; Ubuntu or Debian is required.",
  ],
  NODE_OS_PREFLIGHT_COMMAND_FAILED:[
    "SSH برقرار شد، اما فرمان فقط‌خواندنی بررسی سیستم‌عامل اجرا نشد. دسترسی شل و فایل‌های OS را بررسی کنید.",
    "SSH connected, but the read-only OS check could not run. Check the remote shell and OS metadata.",
  ],
  NODE_OS_PREFLIGHT_TIMEOUT:[
    "سرور هنگام بررسی سیستم‌عامل پاسخ نداد؛ وضعیت SSH و بار سرور را بررسی کنید.",
    "Node OS preflight timed out. Inspect SSH responsiveness and server load.",
  ],
  NODE_HOST_ALREADY_REGISTERED:[
    "این IP قبلاً به نود فعالی در پنل اختصاص یافته است. برای جلوگیری از آسیب به نود ایران یا سایر کاربران، نصب تکراری مسدود شد.",
    "This IP already belongs to an active panel node. Reinstallation is blocked to protect the existing Iran/Exit service.",
  ],
  NODE_NAME_ALREADY_REGISTERED:[
    "نودی با همین نام از قبل فعال است؛ نام متفاوتی انتخاب کنید.",
    "An active node already has this name. Choose another name.",
  ],
  NODE_SSH_OR_OS_REJECTED:[
    "بررسی SSH یا سیستم‌عامل سرور رد شد. از «تست اتصال» برای دیدن مشکل استفاده کنید.",
    "SSH or node OS check was rejected. Use Test Connection to inspect it.",
  ],
  NODE_REMOTE_PREFLIGHT_REJECTED:[
    "سرور در بررسی اولیه مجاز به نصب جدید نبود؛ سرویس‌های موجود نباید بازنویسی شوند.",
    "Remote safety preflight rejected the install to protect existing services.",
  ],
  NODE_INSTALL_REMOTE_COMMAND_FAILED:[
    "فرمان نصب روی سرور ناموفق بود. سرویس‌های فعلی را حذف نکنید؛ لاگ نصب نود باید بررسی شود.",
    "A remote installation command failed. Keep existing services intact and inspect the node installation log.",
  ],
};

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
      ["verified_ready","تأیید سلامت سرویس‌ها","Services verified healthy"],
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
        <small>{failed?pick("نصب کامل تأیید نشده است","Installation is not confirmed"):waiting?pick("کاربران به نود منتسب شده‌اند؛ اعمال کانفیگ‌ها هنوز در صف مرکزی است","Accounts are assigned; configuration application is still queued centrally"):finished?pick("نصب به پایان رسید؛ وضعیت نمایش نود و کانفیگ‌های آماده را بررسی کنید","Installation is complete; check node publication and ready configurations"):pick("وضعیت مراحل مستقیماً از سرور خوانده می‌شود","Stages are read directly from the server")}</small>
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
    {job?.error_code?<div className="runtime-warning">
      {pick("کد وضعیت","Status code")}: <code dir="ltr">{job.error_code}</code>
      {NODE_INSTALL_FAILURE_GUIDANCE[job.error_code]?<p>{pick(...NODE_INSTALL_FAILURE_GUIDANCE[job.error_code])}</p>:null}
    </div>:null}
    {error?<div className="runtime-warning">{error}</div>:null}
    {job?.state==="interrupted"?<div className="runtime-warning">{pick("به‌روزرسانی این کار متوقف شده؛ وضعیت واقعی نود را بررسی کنید. فرایند را خودکار موفق فرض نکنید.","Job updates are stale. Verify the node before retrying; completion cannot be assumed.")}</div>:null}
    <small>{pick("این نمایش از داده‌های واقعی API استفاده می‌کند؛ حرکت نوار به معنی درصد پیشرفت نیست.","Stages come from the API. The moving indicator is not a percent-complete estimate.")}</small>
  </div>;
}

export function NodeAddModalBridge(){
  const {pick}=useI18n();
  const [open,setOpen]=useState(false);
  const [draft,setDraft]=useState<NodeDraft>(defaultDraft);
  const [publishToAll,setPublishToAll]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [jobId,setJobId]=useState("");
  const [job,setJob]=useState<NodeInstallJob|null>(null);
  const [jobError,setJobError]=useState("");
  // Failed installs do not retain the original publish preference. Require
  // an explicit fresh choice rather than exposing a node automatically.
  const [publishAfterRepair,setPublishAfterRepair]=useState(false);


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
    setDraft(defaultDraft);setPublishToAll(true);setPublishAfterRepair(false);setOpen(true);
  };

  const test=async()=>{
    if(busy)return;
    setBusy("test");setError("");setOk("");
    try{await parityApi.provisionTest({host:draft.host.trim(),port:draft.port,username:draft.username.trim()||"root",password:draft.password});setOk(pick("اتصال SSH و سیستم‌عامل سرور تایید شد.","SSH connection and server OS verified."));}
    catch(reason){
      const detail=reason instanceof Error?reason.message:String(reason);
      const guidance=NODE_INSTALL_FAILURE_GUIDANCE[detail];
      setError(guidance?pick(...guidance):detail);
    }
    finally{setBusy("");}
  };

  const submit=async(event:FormEvent)=>{
    event.preventDefault();if(busy)return;
    if(!isSupportedNodeCountry(draft.node_type==="iran"?"IR":draft.country_code)){
      setError(pick("لطفاً کشور معتبر را از فهرست انتخاب کنید.","Please select a valid country from the list."));return;
    }
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
      if(!response.ok){
        let detail="";
        try{const parsed=JSON.parse(raw) as {detail?:string};detail=String(parsed.detail||"");}catch{}
        const guidance=NODE_INSTALL_FAILURE_GUIDANCE[detail];
        throw new Error(guidance?pick(...guidance):(raw||`API error ${response.status}`));
      }
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

  const repairFailedCisco=async()=>{
    if(busy||!job?.node_id||!jobId)return;
    const token=getCustomerToken();
    if(!token){setError("AUTH_REQUIRED");return;}
    setBusy("repair");setError("");setOk("");setJobError("");
    try{
      const response=await fetch(API_BASE+"/v1/nodes/"+job.node_id+"/central-stage/repair-cisco",{
        method:"POST",cache:"no-store",
        headers:{Authorization:"Bearer "+token,"Content-Type":"application/json"},
        body:JSON.stringify({publish_to_all_users:publishAfterRepair}),
      });
      const raw=await response.text();
      if(!response.ok)throw new Error(raw||"Cisco repair HTTP "+response.status);
      const result=JSON.parse(raw) as {job_id?:string;queued?:boolean};
      if(!result.queued||result.job_id!==jobId)throw new Error("CISCO_REPAIR_JOB_MISMATCH");
      setJob(current=>current?{...current,state:"running",stage:"installing_base",error_code:null}:current);
      setOk(pick("ترمیم Cisco در بک‌اند شروع شد؛ ۱۵ پروتکل سالم تغییر نمی‌کنند.","Cisco-only background repair started; the other 15 services remain unchanged."));
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{setBusy("");}
  };

  return <>

    <style>{`
      .tp-add-node-modal .tp-add-node-card{width:min(720px,calc(100vw - 24px))!important;padding:0!important;
        border:1px solid #2c4268!important;border-radius:21px!important;
        background:linear-gradient(165deg,#131e33 0%,#0e1627 100%)!important;
        box-shadow:0 30px 80px rgba(0,0,0,.53)!important;overflow-y:auto!important;overflow-x:hidden!important}
      .tp-add-node-card>.card-head{position:sticky;top:0;z-index:15;padding:19px 22px!important;margin:0!important;
        border-bottom:1px solid rgba(136,165,218,.16)!important;
        background:linear-gradient(115deg,#152a4b,#111c31)!important}
      .tp-add-node-card>.card-head b{font-size:17px!important;font-weight:850!important;color:#f0f5ff!important}
      .tp-add-node-card>.card-head small{color:#9db1d2!important;display:block;margin-top:5px;font-size:12px}
      .tp-add-node-card>.card-head>.icon-button{border-radius:10px!important;background:#1e304d!important;color:#d7e7ff!important}
      .tp-add-node-card form{padding:16px 22px 20px;display:flex;flex-direction:column;gap:14px}
      .tp-node-section-title{display:flex;align-items:center;gap:9px;color:#e3edff;font-size:13px;font-weight:850;letter-spacing:.05px}
      .tp-node-section-number{width:25px;height:25px;display:grid;place-items:center;background:#284b81;color:#9fcbff;
        border-radius:8px;flex:none;font:800 12px ui-monospace,monospace}
      .tp-node-section-note{margin-inline-start:auto;font-size:11px;font-weight:500;color:#829bbd}
      .tp-add-node-card .tp-node-form-grid{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;
        gap:12px 14px!important;margin:0!important}
      .tp-add-node-card .tp-node-form-grid>.field{min-width:0;display:flex!important;flex-direction:column;gap:6px!important;margin:0!important}
      .tp-add-node-card .tp-node-form-grid>.field>span{font-size:12px!important;color:#a9b9d2!important;font-weight:700}
      .tp-add-node-card .tp-node-form-grid>.field>input,.tp-add-node-card .tp-node-form-grid>.field>select{
        width:100%!important;min-height:44px!important;height:44px!important;padding:0 12px!important;
        border:1px solid #304360!important;border-radius:11px!important;background:#121d30!important;color:#eff5ff!important;
        box-shadow:none!important;outline:none!important;font-size:13px!important;box-sizing:border-box}
      .tp-add-node-card .tp-node-form-grid>.field>input:focus,.tp-add-node-card .tp-node-form-grid>.field>select:focus{
        border-color:#4788f5!important;box-shadow:0 0 0 3px rgba(58,120,237,.13)!important}
      .tp-add-node-card .tp-node-separator{border:0;border-top:1px solid rgba(146,168,204,.14);margin:1px 0 0}
      .tp-add-node-card form .runtime-choice-section{padding:11px 13px!important;border-radius:12px!important;
        background:rgba(31,49,78,.55)!important;border:1px solid rgba(128,157,205,.18)!important}
      .tp-add-node-card form .runtime-warning{border-radius:11px!important;font-size:11px!important;line-height:1.7!important;
        padding:10px 12px!important;margin:0!important}
      .tp-add-node-card form>.action-row{position:sticky;bottom:-20px;z-index:12;display:flex;flex-wrap:wrap;
        gap:10px!important;padding:13px 0 0!important;margin:0!important;
        border-top:1px solid rgba(146,168,204,.18);background:#0e1627!important}
      .tp-add-node-card form>.action-row button{border-radius:11px!important;min-height:42px!important}
      .tp-add-node-card form>.action-row .primary{background:linear-gradient(110deg,#2566dc,#108fcb)!important;
        box-shadow:0 6px 18px rgba(23,99,212,.2)!important}
      html[data-theme="light"] .tp-add-node-modal .tp-add-node-card{background:#fff!important;border-color:#dae2ec!important}
      html[data-theme="light"] .tp-add-node-card>.card-head{background:linear-gradient(110deg,#edf5ff,#fff)!important}
      html[data-theme="light"] .tp-add-node-card>.card-head b{color:#233653!important}
      html[data-theme="light"] .tp-node-section-title{color:#243b59}
      html[data-theme="light"] .tp-add-node-card .tp-node-form-grid>.field>input,
      html[data-theme="light"] .tp-add-node-card .tp-node-form-grid>.field>select{background:#f8faff!important;color:#1f3456!important}
      html[data-theme="light"] .tp-add-node-card form>.action-row{background:#fff!important}
      @media(max-width:640px){
        .tp-add-node-card form{padding:13px!important}
        .tp-add-node-card>.card-head{padding:15px!important}
        .tp-add-node-card .tp-node-form-grid{grid-template-columns:minmax(0,1fr)!important}
        .tp-node-section-note{display:none}
        .tp-add-node-card form>.action-row button{flex:1;min-width:120px}
      }
    `}</style>

    {!open&&jobId?<button className="node-install-reopen" type="button" onClick={()=>setOpen(true)}>{pick("مشاهده مراحل افزودن نود","View server installation stages")} · {job?.node_name||pick("در حال دریافت وضعیت","Loading status")}{job?.state==="running"?" ●":""}</button>:null}
    {!open&&ok?<div className="runtime-success" style={{marginBottom:12}}>{ok}</div>:null}
    {!open&&error?<div className="runtime-error" style={{marginBottom:12}}>{error}</div>:null}
    {open?<div className="runtime-modal tp-add-node-modal" role="dialog" aria-modal="true">
    <button type="button" className="runtime-modal-bg" aria-label="close" onClick={()=>setOpen(false)}/>
    <div className="runtime-modal-card tp-add-node-card">
      <div className="card-head"><div><b>{pick("افزودن سرور","Add server")}</b><small>{pick("ثبت نود، SSH و زیرساخت پایه","Node registration, SSH and base infrastructure")}</small></div><button type="button" className="icon-button" onClick={()=>setOpen(false)}>×</button></div>
      {error?<div className="runtime-error">{error}</div>:null}
      {ok?<div className="runtime-success">{ok}</div>:null}
      {jobId?<div>
        <NodeInstallProgress job={job} error={jobError}/>
        {job?.state==="failed"&&["PROTOCOL_SETUP_INCOMPLETE","CISCO_REPAIR_FAILED"].includes(job.error_code||"")&&job.node_id?
          <div className="runtime-choice-section">
            <div className="runtime-warning">{pick("نصب یک پروتکل ناقص مانده است. فقط Cisco را ترمیم کن؛ ۱۵ پروتکل سالم دوباره نصب نمی‌شوند.","One protocol is incomplete. Repair only Cisco; do not reinstall the 15 healthy protocols.")}</div>
            <label className="toggle module-toggle"><span>{pick("بعد از تأیید همه ۱۶ پروتکل، نود برای کاربران مجاز نمایش داده شود","Publish to eligible users after all 16 services pass health checks")}</span><input type="checkbox" checked={publishAfterRepair} onChange={e=>setPublishAfterRepair(e.target.checked)}/><i/></label>
            <button className="primary-soft" type="button" disabled={Boolean(busy)} onClick={()=>void repairFailedCisco()}>{busy==="repair"?pick("در حال شروع ترمیم...","Starting repair..."):pick("ترمیم Cisco و ادامه نصب همین نود","Repair Cisco and resume this node")}</button>
          </div>:null}
        <div className="action-row" style={{marginTop:16}}>
          <button className="primary-soft" type="button" onClick={()=>setOpen(false)}>{pick("بستن و ادامه در پس‌زمینه","Close; keep processing")}</button>
          <button className="ghost" type="button" onClick={resetInstall}>{pick("افزودن سرور دیگر","Add another server")}</button>
        </div>
      </div>:<form onSubmit={submit}>
        <div className="tp-node-section-title"><span className="tp-node-section-number">01</span>{pick("مشخصات سرور","Server details")}<small className="tp-node-section-note">{pick("نام، میزبان و موقعیت","Identity & location")}</small></div>
        <div className="setting-grid tp-node-form-grid">
          <label className="field"><span>{pick("نام سرور","Server name")}</span><input required value={draft.name} onChange={e=>setDraft(v=>({...v,name:e.target.value}))}/></label>
          <label className="field"><span>IP / Host</span><input required dir="ltr" value={draft.host} onChange={e=>setDraft(v=>({...v,host:e.target.value}))}/></label>
          <label className="field"><span>{pick("نوع نود","Node type")}</span><select value={draft.node_type} onChange={e=>setDraft(v=>{const node_type=e.target.value as "iran"|"exit";return {...v,node_type,country_code:node_type==="iran"?"IR":v.country_code==="IR"?"DE":v.country_code};})}><option value="iran">Iran</option><option value="exit">Exit</option></select></label>
          <div className="field"><NodeCountryPicker label={pick("کشور و پرچم سرور","Server country & flag")} value={draft.node_type==="iran"?"IR":draft.country_code} disabled={draft.node_type==="iran"} onChange={country_code=>setDraft(v=>({...v,country_code}))} language={pick("fa","en") as "fa"|"en"}/></div>
        </div>
        <hr className="tp-node-separator"/>
        <div className="tp-node-section-title"><span className="tp-node-section-number">02</span>{pick("دسترسی و ظرفیت","Access & capacity")}<small className="tp-node-section-note">{pick("اطلاعات SSH سرور","SSH credentials")}</small></div>
        <div className="setting-grid tp-node-form-grid">
          <label className="field"><span>SSH Port</span><input type="number" min={1} max={65535} value={draft.port} onChange={e=>setDraft(v=>({...v,port:Number(e.target.value)||22}))}/></label>
          <label className="field"><span>SSH Username</span><input dir="ltr" value={draft.username} onChange={e=>setDraft(v=>({...v,username:e.target.value}))}/></label>
          <label className="field"><span>SSH Password</span><input type="password" autoComplete="new-password" required value={draft.password} onChange={e=>setDraft(v=>({...v,password:e.target.value}))}/></label>
          <label className="field"><span>{pick("ظرفیت کاربر","User capacity")}</span><input type="number" min={1} value={draft.capacity_users} onChange={e=>setDraft(v=>({...v,capacity_users:Number(e.target.value)||1}))}/></label>
        </div>
        {draft.node_type==="exit"?<div className="runtime-choice-section"><label className="toggle module-toggle"><span>{pick("نمایش برای همه کاربران سایت","Show for all site users")}</span><input type="checkbox" checked={publishToAll} onChange={e=>setPublishToAll(e.target.checked)}/><i/></label><small>{pick("با فعال‌کردن این گزینه، نود فقط به اشتراک‌های فعال قبلی که منقضی نشده‌اند و حجم دارند اضافه می‌شود. برای خریداران جدید، نود را جداگانه در پلن اقتصادی یا ویژه انتخاب کنید. پس از تأیید سلامت ۱۶ پروتکل، نود و عضویت کاربران فعال بلافاصله نمایش داده می‌شود؛ کانفیگ‌های آماده به‌تدریج قابل دریافت‌اند و بقیه در بک‌اند تکمیل می‌شوند.","When enabled, the node is assigned to eligible existing active subscriptions only. Select it separately in Economy/Premium plans for new purchases. Once all 16 live listeners are verified, the node becomes visible immediately. Ready configs are delivered progressively while the backend syncs the rest.")}</small></div>:null}
        <div className="runtime-warning">{pick("سرور خروجی ابتدا سلامت ۱۶ پروتکل را بررسی می‌کند؛ سپس کاربران فعال گروهی ثبت و نود نمایش داده می‌شود. ساخت کانفیگ‌ها در بک‌اند ادامه دارد، بدون اینکه افزودن سرور منتظر آن بماند.","Exit nodes verify all 16 protocols, then enroll active users in bulk and become visible immediately. Credential generation continues separately in the backend.")}</div>
        <div className="action-row"><button type="button" className="ghost" disabled={Boolean(busy)||!draft.host||!draft.password} onClick={()=>void test()}>{busy==="test"?"…":pick("تست SSH","Test SSH")}</button><button className="primary" disabled={Boolean(busy)||!draft.host||!draft.password||!draft.name}>{busy==="register"?pick("در حال ثبت...","Registering..."):pick("ثبت و آماده‌سازی سرور","Register & prepare server")}</button></div>
      </form>}
    </div>
  </div>:null}
  </>;
}