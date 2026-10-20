"use client";

import {useEffect,useMemo,useRef,useState} from "react";
import {useI18n} from "../lib/i18n";

type OperationKind=
  |"node-provision"
  |"node-access"
  |"node-health"
  |"node-restart"
  |"node-repair"
  |"agent-upgrade"
  |"fabric-install"
  |"fabric-status"
  |"xray-domain-save"
  |"xray-domain-prepare"
  |"tunnel-create"
  |"subscription-create";

type ActivityState={
  id:number;
  kind:OperationKind;
  status:"pending"|"success"|"error";
  startedAt:number;
  httpStatus?:number;
  message?:string;
};

const operationFor=(pathname:string,method:string):OperationKind|null=>{
  const verb=method.toUpperCase();

  if(verb==="POST"&&pathname==="/v1/provision/install")return "node-provision";
  if(verb==="POST"&&pathname==="/v1/provision/save-node-access")return "node-access";
  if(verb==="POST"&&pathname==="/v1/provision/protocol-health")return "node-health";
  if(verb==="POST"&&pathname==="/v1/provision/restart-protocol")return "node-restart";
  if(verb==="POST"&&pathname==="/v1/provision/repair-protocols-saved")return "node-repair";
  if(verb==="POST"&&pathname==="/v1/provision/upgrade-agent")return "agent-upgrade";
  if(verb==="POST"&&pathname==="/v1/provision/install-fabric")return "fabric-install";
  if(verb==="GET"&&/^\/v1\/provision\/fabric-status\/\d+$/.test(pathname))return "fabric-status";
  if(verb==="PUT"&&/^\/v1\/xray-modern-admin\/nodes\/\d+\/xray-domain$/.test(pathname))return "xray-domain-save";
  if(verb==="POST"&&/^\/v1\/xray-modern-admin\/nodes\/\d+\/xray-domain\/prepare$/.test(pathname))return "xray-domain-prepare";
  if(verb==="POST"&&pathname==="/v1/tunnels/create-managed")return "tunnel-create";
  if(verb==="POST"&&pathname==="/v1/subscriptions/admin-create-v2")return "subscription-create";
  return null;
};

function requestMeta(input:RequestInfo|URL,init?:RequestInit){
  const method=String(init?.method||(typeof Request!=="undefined"&&input instanceof Request?input.method:"GET")||"GET").toUpperCase();
  const raw=typeof input==="string"?input:input instanceof URL?input.toString():input.url;
  try{
    return {method,pathname:new URL(raw,window.location.origin).pathname};
  }catch{
    return {method,pathname:""};
  }
}

function responseOutcome(payload:unknown){
  if(!payload||typeof payload!=="object")return {ok:undefined as boolean|undefined,message:""};
  const row=payload as Record<string,unknown>;
  const ok=typeof row.ok==="boolean"?row.ok:undefined;
  let message="";

  if(typeof row.detail==="string")message=row.detail;
  else if(typeof row.message==="string")message=row.message;

  if(!message&&Array.isArray(row.failed_protocols)&&row.failed_protocols.length){
    message=`Failed protocols: ${row.failed_protocols.map(String).join(", ")}`;
  }

  return {ok,message};
}

export function AdminOperationFeedback(){
  const {pick}=useI18n();
  const [activity,setActivity]=useState<ActivityState|null>(null);
  const [clock,setClock]=useState(()=>Date.now());
  const sequenceRef=useRef(0);
  const clearTimerRef=useRef<number|null>(null);

  useEffect(()=>{
    if(!activity||activity.status!=="pending")return;
    setClock(Date.now());
    const timer=window.setInterval(()=>setClock(Date.now()),1000);
    return()=>window.clearInterval(timer);
  },[activity?.id,activity?.status]);

  useEffect(()=>{
    const originalFetch=window.fetch.bind(window);

    const wrappedFetch:typeof window.fetch=async(input,init)=>{
      const meta=requestMeta(input,init);
      const kind=operationFor(meta.pathname,meta.method);
      if(!kind)return originalFetch(input,init);

      if(clearTimerRef.current!==null){
        window.clearTimeout(clearTimerRef.current);
        clearTimerRef.current=null;
      }

      const id=++sequenceRef.current;
      const startedAt=Date.now();
      setClock(startedAt);
      setActivity({id,kind,status:"pending",startedAt});

      try{
        const response=await originalFetch(input,init);
        let payload:unknown=null;
        try{
          const type=response.headers.get("content-type")||"";
          if(type.includes("application/json"))payload=await response.clone().json();
        }catch{}

        const outcome=responseOutcome(payload);
        const success=response.ok&&outcome.ok!==false;

        if(sequenceRef.current===id){
          setActivity({
            id,
            kind,
            status:success?"success":"error",
            startedAt,
            httpStatus:response.status,
            message:outcome.message||undefined,
          });
          clearTimerRef.current=window.setTimeout(()=>{
            setActivity(current=>current?.id===id?null:current);
            clearTimerRef.current=null;
          },success?5500:10000);
        }
        return response;
      }catch(error){
        if(sequenceRef.current===id){
          setActivity({
            id,
            kind,
            status:"error",
            startedAt,
            message:error instanceof Error?error.message:String(error),
          });
          clearTimerRef.current=window.setTimeout(()=>{
            setActivity(current=>current?.id===id?null:current);
            clearTimerRef.current=null;
          },10000);
        }
        throw error;
      }
    };

    window.fetch=wrappedFetch;
    return()=>{
      if(window.fetch===wrappedFetch)window.fetch=originalFetch;
      if(clearTimerRef.current!==null){
        window.clearTimeout(clearTimerRef.current);
        clearTimerRef.current=null;
      }
    };
  },[]);

  const label=useMemo(()=>{
    if(!activity)return "";

    const statusLabel=(pending:string,success:string,error:string)=>
      activity.status==="pending"?pending:activity.status==="success"?success:error;

    if(activity.kind==="node-provision")return statusLabel(
      pick("در حال نصب و راه‌اندازی نود و پروتکل‌ها…","Installing and provisioning the node and protocols…"),
      pick("نصب نود با موفقیت پاسخ گرفت.","Node provisioning completed successfully."),
      pick("نصب نود با خطا متوقف شد.","Node provisioning failed."),
    );
    if(activity.kind==="node-access")return statusLabel(
      pick("در حال ثبت دسترسی امن سرور…","Saving secure server access…"),
      pick("دسترسی امن سرور با موفقیت ثبت شد.","Secure server access was saved successfully."),
      pick("ثبت دسترسی امن سرور با خطا متوقف شد.","Saving secure server access failed."),
    );
    if(activity.kind==="node-health")return statusLabel(
      pick("در حال بررسی سلامت سرویس‌های نود…","Checking node service health…"),
      pick("بررسی سلامت سرویس‌ها کامل شد.","Service health check completed."),
      pick("بررسی سلامت سرویس‌ها مشکل پیدا کرد.","Service health check reported a problem."),
    );
    if(activity.kind==="node-restart")return statusLabel(
      pick("در حال ریستارت و بررسی سرویس انتخاب‌شده…","Restarting and checking the selected service…"),
      pick("ریستارت سرویس با موفقیت پاسخ گرفت.","Service restart completed successfully."),
      pick("ریستارت سرویس با خطا متوقف شد.","Service restart failed."),
    );
    if(activity.kind==="node-repair")return statusLabel(
      pick("در حال تعمیر و همگام‌سازی پروتکل‌های نود…","Repairing and reconciling node protocols…"),
      pick("تعمیر پروتکل‌های نود کامل شد.","Node protocol repair completed."),
      pick("تعمیر پروتکل‌های نود کامل نشد.","Node protocol repair did not complete successfully."),
    );
    if(activity.kind==="agent-upgrade")return statusLabel(
      pick("در حال ارتقای Agent نود…","Upgrading the node Agent…"),
      pick("ارتقای Agent نود کامل شد.","Node Agent upgrade completed."),
      pick("ارتقای Agent نود با خطا متوقف شد.","Node Agent upgrade failed."),
    );
    if(activity.kind==="fabric-install")return statusLabel(
      pick("در حال آماده‌سازی Tunnel Fabric نود…","Preparing the node Tunnel Fabric…"),
      pick("Tunnel Fabric نود آماده شد.","Node Tunnel Fabric is ready."),
      pick("آماده‌سازی Tunnel Fabric با خطا متوقف شد.","Tunnel Fabric preparation failed."),
    );
    if(activity.kind==="fabric-status")return statusLabel(
      pick("در حال دریافت وضعیت Tunnel Fabric…","Loading Tunnel Fabric status…"),
      pick("وضعیت Tunnel Fabric دریافت شد.","Tunnel Fabric status loaded."),
      pick("Tunnel Fabric در وضعیت آماده نیست.","Tunnel Fabric is not ready."),
    );
    if(activity.kind==="xray-domain-save")return statusLabel(
      pick("در حال ذخیره دامنه Xray…","Saving the Xray domain…"),
      pick("دامنه Xray ذخیره شد.","Xray domain saved."),
      pick("ذخیره دامنه Xray ناموفق بود.","Saving the Xray domain failed."),
    );
    if(activity.kind==="xray-domain-prepare")return statusLabel(
      pick("در حال آماده‌سازی SSL دامنه Xray…","Preparing TLS for the Xray domain…"),
      pick("SSL دامنه Xray آماده شد.","Xray domain TLS is ready."),
      pick("آماده‌سازی SSL دامنه Xray کامل نشد.","Xray domain TLS preparation did not complete."),
    );
    if(activity.kind==="tunnel-create")return statusLabel(
      pick("در حال ساخت تانل و بررسی مسیرهای ارتباطی…","Creating the tunnel and validating transport paths…"),
      pick("ساخت تانل با موفقیت پاسخ گرفت.","Tunnel creation completed successfully."),
      pick("ساخت تانل با خطا متوقف شد.","Tunnel creation failed."),
    );
    return statusLabel(
      pick("در حال ساخت اشتراک و صدور اکانت…","Creating the subscription and provisioning the account…"),
      pick("اشتراک با موفقیت ساخته شد.","Subscription created successfully."),
      pick("ساخت اشتراک با خطا متوقف شد.","Subscription creation failed."),
    );
  },[activity,pick]);

  if(!activity)return null;

  const elapsed=Math.max(0,Math.floor((clock-activity.startedAt)/1000));
  const detail=activity.status==="pending"
    ?pick(
      `درخواست ارسال شده و عملیات در سرور در حال اجراست. صفحه را نبندید. زمان سپری‌شده: ${elapsed.toLocaleString("fa-IR")} ثانیه`,
      `The request was accepted and is still running on the server. Keep this page open. Elapsed: ${elapsed}s`,
    )
    :activity.status==="success"
      ?activity.message||pick("عملیات پایان یافت و اطلاعات صفحه در حال بروزرسانی است.","The operation finished and the page data is refreshing.")
      :activity.message
        ?`${activity.message}${activity.httpStatus?` (HTTP ${activity.httpStatus})`:""}`
        :pick(
          `پاسخ عملیات ناموفق بود${activity.httpStatus?` (HTTP ${activity.httpStatus})`:""}.`,
          `The operation failed${activity.httpStatus?` (HTTP ${activity.httpStatus})`:""}.`,
        );

  const toneClass=activity.status==="pending"?"runtime-warning":activity.status==="success"?"runtime-success":"runtime-error";

  return <div
    role="status"
    aria-live="polite"
    aria-atomic="true"
    aria-busy={activity.status==="pending"}
    style={{
      position:"fixed",
      insetInlineStart:24,
      bottom:24,
      zIndex:12000,
      width:"min(520px, calc(100vw - 48px))",
      pointerEvents:"none",
    }}
  >
    <div className={toneClass} style={{boxShadow:"0 18px 48px rgba(0,0,0,.28)",pointerEvents:"auto"}}>
      <div style={{display:"flex",gap:10,alignItems:"flex-start"}}>
        <span aria-hidden="true" style={{fontSize:20,lineHeight:1.4}}>{activity.status==="pending"?"⏳":activity.status==="success"?"✓":"!"}</span>
        <div style={{display:"grid",gap:4}}>
          <b>{label}</b>
          <small>{detail}</small>
        </div>
      </div>
    </div>
  </div>;
}
