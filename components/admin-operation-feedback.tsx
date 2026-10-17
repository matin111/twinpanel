"use client";

import {useEffect,useMemo,useRef,useState} from "react";
import {useI18n} from "../lib/i18n";

type OperationKind="node-provision"|"tunnel-create"|"subscription-create";
type ActivityState={
  id:number;
  kind:OperationKind;
  status:"pending"|"success"|"error";
  startedAt:number;
  httpStatus?:number;
};

const operationFor=(pathname:string,method:string):OperationKind|null=>{
  const verb=method.toUpperCase();
  if(verb!=="POST")return null;
  if(pathname==="/v1/provision/install")return "node-provision";
  if(pathname==="/v1/tunnels/create-managed")return "tunnel-create";
  if(pathname==="/v1/subscriptions/admin-create-v2")return "subscription-create";
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
        if(sequenceRef.current===id){
          setActivity({
            id,
            kind,
            status:response.ok?"success":"error",
            startedAt,
            httpStatus:response.status,
          });
          clearTimerRef.current=window.setTimeout(()=>{
            setActivity(current=>current?.id===id?null:current);
            clearTimerRef.current=null;
          },response.ok?4500:8000);
        }
        return response;
      }catch(error){
        if(sequenceRef.current===id){
          setActivity({id,kind,status:"error",startedAt});
          clearTimerRef.current=window.setTimeout(()=>{
            setActivity(current=>current?.id===id?null:current);
            clearTimerRef.current=null;
          },8000);
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
    if(activity.kind==="node-provision"){
      return activity.status==="pending"
        ?pick("در حال نصب و راه‌اندازی نود و پروتکل‌ها…","Installing and provisioning the node and protocols…")
        :activity.status==="success"
          ?pick("نصب نود با موفقیت پاسخ گرفت.","Node provisioning completed successfully.")
          :pick("نصب نود با خطا متوقف شد.","Node provisioning failed.");
    }
    if(activity.kind==="tunnel-create"){
      return activity.status==="pending"
        ?pick("در حال ساخت تانل و بررسی مسیرهای ارتباطی…","Creating the tunnel and validating transport paths…")
        :activity.status==="success"
          ?pick("ساخت تانل با موفقیت پاسخ گرفت.","Tunnel creation completed successfully.")
          :pick("ساخت تانل با خطا متوقف شد.","Tunnel creation failed.");
    }
    return activity.status==="pending"
      ?pick("در حال ساخت اشتراک و صدور اکانت…","Creating the subscription and provisioning the account…")
      :activity.status==="success"
        ?pick("اشتراک با موفقیت ساخته شد.","Subscription created successfully.")
        :pick("ساخت اشتراک با خطا متوقف شد.","Subscription creation failed.");
  },[activity,pick]);

  if(!activity)return null;

  const elapsed=Math.max(0,Math.floor((clock-activity.startedAt)/1000));
  const detail=activity.status==="pending"
    ?pick(
      `درخواست ارسال شده و عملیات در سرور در حال اجراست. صفحه را نبندید. زمان سپری‌شده: ${elapsed.toLocaleString("fa-IR")} ثانیه`,
      `The request was accepted and is still running on the server. Keep this page open. Elapsed: ${elapsed}s`,
    )
    :activity.status==="success"
      ?pick("لیست صفحه به‌صورت خودکار بروزرسانی می‌شود.","The page list will refresh automatically.")
      :pick(
        `پاسخ عملیات ناموفق بود${activity.httpStatus?` (HTTP ${activity.httpStatus})`:""}. جزئیات خطا در همان صفحه نمایش داده می‌شود.`,
        `The operation failed${activity.httpStatus?` (HTTP ${activity.httpStatus})`:""}. The detailed error remains visible on the page.`,
      );

  const toneClass=activity.status==="pending"?"runtime-warning":activity.status==="success"?"runtime-success":"runtime-error";

  return <div
    role="status"
    aria-live="polite"
    aria-atomic="true"
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
