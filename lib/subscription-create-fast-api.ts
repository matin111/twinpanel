"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type FastSubscriptionCreatePayload={
  user_id:number;
  plan_id?:number|null;
  node_ids:number[];
  protocols:string[];
  traffic_gb?:number;
  duration_days?:number;
  device_limit?:number;
  username?:string;
  password?:string;
};

export type FastSubscriptionCreateResult={
  ok:boolean;
  queued:boolean;
  message?:string;
};

// admin-create-fast-v1 commits the Subscription before the slower protocol
// provisioning phase. The UI therefore must not stay blocked for that entire
// backend lifecycle. Most importantly, do NOT AbortController.abort() here:
// aborting the browser request only creates a false UI failure while the server
// may still be completing the already-committed Subscription.
export const SUBSCRIPTION_CREATE_UI_DETACH_MS=12_000;

function detailText(detail:unknown){
  if(!detail||typeof detail!=="object")return "";
  const value=detail as {
    message?:unknown;
    unavailable_protocols?:unknown;
    missing_protocols?:unknown;
    provision_errors?:unknown;
    provision_error?:unknown;
  };
  const parts:string[]=[];
  if(typeof value.message==="string"&&value.message.trim())parts.push(value.message.trim());

  if(Array.isArray(value.unavailable_protocols)){
    const names=value.unavailable_protocols
      .map(item=>item&&typeof item==="object"?String((item as {protocol?:unknown}).protocol||""):"")
      .filter(Boolean);
    if(names.length)parts.push(`آماده نیست: ${names.join(", ")}`);
  }

  if(Array.isArray(value.missing_protocols)){
    const names=value.missing_protocols.map(item=>String(item||"")).filter(Boolean);
    if(names.length)parts.push(`کانفیگ ساخته نشد: ${names.join(", ")}`);
  }

  if(Array.isArray(value.provision_errors)){
    const errors=value.provision_errors.slice(0,3).map(item=>{
      if(!item||typeof item!=="object")return String(item||"");
      const row=item as {protocol?:unknown;node?:unknown;error?:unknown};
      return [row.protocol,row.node,row.error].filter(Boolean).map(String).join(" · ");
    }).filter(Boolean);
    if(errors.length)parts.push(errors.join(" | "));
  }

  if(value.provision_error){
    const nested=detailText(value.provision_error);
    if(nested)parts.push(nested);
    else if(typeof value.provision_error==="string")parts.push(value.provision_error);
  }

  return parts.join(" — ");
}

function errorText(payload:unknown,status:number){
  if(payload&&typeof payload==="object"){
    const value=payload as {detail?:unknown;message?:unknown};
    if(typeof value.detail==="string")return value.detail;
    const detail=detailText(value.detail);
    if(detail)return detail;
    if(typeof value.message==="string")return value.message;
  }
  if(typeof payload==="string"&&payload.trim())return payload.trim();
  return `API error ${status}`;
}

async function runCreateRequest(payload:FastSubscriptionCreatePayload):Promise<FastSubscriptionCreateResult>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");

  const response=await fetch(`${API_BASE}/v1/subscriptions/admin-create-fast-v1`,{
    method:"POST",
    cache:"no-store",
    headers:{
      Authorization:`Bearer ${token}`,
      "Content-Type":"application/json",
    },
    body:JSON.stringify(payload),
  });

  const raw=await response.text();
  let body:unknown=null;
  if(raw){
    try{body=JSON.parse(raw);}catch{body=raw;}
  }
  if(!response.ok)throw new Error(errorText(body,response.status));
  return body as FastSubscriptionCreateResult;
}

export async function createSubscriptionFastV1(payload:FastSubscriptionCreatePayload):Promise<FastSubscriptionCreateResult>{
  // Keep the real request alive after the UI detaches. Promise.race attaches
  // handlers to the request promise, so a later backend failure is consumed
  // rather than becoming an unhandled browser rejection.
  const request=runCreateRequest(payload);
  let timer:number|undefined;
  const detached=new Promise<FastSubscriptionCreateResult>(resolve=>{
    timer=globalThis.setTimeout(()=>resolve({
      ok:true,
      queued:true,
      message:"ثبت اولیه انجام شد؛ صدور کانفیگ‌ها در سمت سرور ادامه دارد",
    }),SUBSCRIPTION_CREATE_UI_DETACH_MS);
  });

  try{
    return await Promise.race([request,detached]);
  }finally{
    if(timer!==undefined)globalThis.clearTimeout(timer);
  }
}
