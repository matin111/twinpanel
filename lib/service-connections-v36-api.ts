"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type HighSpeedRouteResult={
  ok?:boolean;
  tunnel_id?:number;
  mode?:string;
  route_ready?:boolean;
  active_transport?:string;
  status?:string;
  latency_ms?:number|null;
  selection_basis?:string;
  message?:string;
  candidates?:Array<{
    transport?:string;
    priority?:number;
    latency_ms?:number|null;
    effective_mbps?:number|null;
  }>;
};

export type RealEgressRepairResult={
  ok?:boolean;
  tunnel_id?:number;
  mode?:string;
  active_transport?:string;
  status?:string;
  latency_ms?:number|null;
  exit_interface?:string|null;
  message?:string;
  selected?:{
    transport?:string;
    ok?:boolean;
    loss_pct?:number|null;
    latency_ms?:number|null;
    public_ip?:string|null;
    error?:string|null;
  }|null;
  verification?:Array<{
    transport?:string;
    ok?:boolean;
    loss_pct?:number|null;
    latency_ms?:number|null;
    public_ip?:string|null;
    error?:string|null;
  }>;
};

export type XrayReconcileJob={
  job_id?:string;
  exit_node_id?:number;
  status?:"queued"|"running"|"succeeded"|"completed_with_errors"|"failed"|string;
  processed?:number;
  total?:number;
  migrated?:number;
  skipped?:number;
  errors?:Array<{subscription_id?:number;error?:string}>;
  result?:{
    ok?:boolean;
    exit_node_id?:number;
    total?:number;
    migrated?:number;
    skipped?:number;
    errors?:Array<{subscription_id?:number;error?:string}>;
  }|null;
  error?:string|null;
};

const TRANSIENT_GET_STATUSES=new Set([502,503,504]);
const TRANSIENT_GET_RETRY_MS=[350,900,1800] as const;
const lastGoodRead=new Map<string,unknown>();

function requestBase(){
  if(typeof window!=="undefined")return window.location.origin;
  return API_BASE;
}

function isHtmlErrorBody(value:string){
  const sample=value.trim().slice(0,1024);
  return /<(?:!doctype|html|head|body|title|center)\b|nginx\//i.test(sample);
}

function isTransientNetworkError(reason:unknown){
  const text=reason instanceof Error?reason.message:String(reason||"");
  return /failed to fetch|networkerror|network request failed|load failed|fetch failed|connection|timeout/i.test(text);
}

function errorText(payload:unknown,status:number){
  if(TRANSIENT_GET_STATUSES.has(status))return `سرویس مسیرهای تانل موقتاً در دسترس نیست. چند لحظه بعد دوباره تلاش کنید. (${status})`;
  if(typeof payload==="string"&&payload.trim()){
    const text=payload.trim();
    if(isHtmlErrorBody(text))return `خطای ارتباط با سرویس مسیرهای تانل (${status})`;
    return text;
  }
  if(payload&&typeof payload==="object"){
    const row=payload as {detail?:unknown;message?:unknown};
    if(typeof row.detail==="string")return row.detail;
    if(typeof row.message==="string")return row.message;
    if(row.detail&&typeof row.detail==="object"){
      const detail=row.detail as {message?:unknown;error?:unknown};
      const message=typeof detail.message==="string"?detail.message:"";
      const error=typeof detail.error==="string"?detail.error:"";
      if(message||error)return [message,error].filter(Boolean).join(" — ");
    }
  }
  return `API error ${status}`;
}

function sleep(ms:number){
  return new Promise<void>(resolve=>globalThis.setTimeout(resolve,ms));
}

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");

  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");

  const method=String(init.method||"GET").toUpperCase();
  const maxAttempts=method==="GET"?TRANSIENT_GET_RETRY_MS.length+1:1;

  for(let attempt=0;attempt<maxAttempts;attempt+=1){
    let response:Response;

    try{
      response=await fetch(`${requestBase()}${path}`,{
        ...init,
        headers,
        cache:"no-store",
      });
    }catch(reason){
      const canRetry=method==="GET"&&isTransientNetworkError(reason)&&attempt<TRANSIENT_GET_RETRY_MS.length;
      if(canRetry){
        await sleep(TRANSIENT_GET_RETRY_MS[attempt]);
        continue;
      }
      if(method==="GET"&&isTransientNetworkError(reason)&&lastGoodRead.has(path)){
        return lastGoodRead.get(path) as T;
      }
      if(isTransientNetworkError(reason))throw new Error("ارتباط با سرویس مسیرهای تانل موقتاً قطع شد. چند لحظه بعد دوباره تلاش کنید.");
      throw reason;
    }

    if(method==="GET"&&TRANSIENT_GET_STATUSES.has(response.status)){
      if(attempt<TRANSIENT_GET_RETRY_MS.length){
        try{await response.body?.cancel();}catch{}
        await sleep(TRANSIENT_GET_RETRY_MS[attempt]);
        continue;
      }
      if(lastGoodRead.has(path)){
        try{await response.body?.cancel();}catch{}
        return lastGoodRead.get(path) as T;
      }
    }

    const raw=await response.text();
    let payload:unknown=null;
    if(raw){try{payload=JSON.parse(raw);}catch{payload=raw;}}
    if(!response.ok)throw new Error(errorText(payload,response.status));

    if(method==="GET")lastGoodRead.set(path,payload);
    else lastGoodRead.clear();

    return payload as T;
  }

  if(method==="GET"&&lastGoodRead.has(path))return lastGoodRead.get(path) as T;
  throw new Error("ارتباط با سرویس مسیرهای تانل موقتاً قطع شد. چند لحظه بعد دوباره تلاش کنید.");
}

async function reconcileXray(tunnelId:number):Promise<XrayReconcileJob>{
  const started=await request<XrayReconcileJob>(
    `/v1/tunnels/${tunnelId}/service-connections/xray-reconcile-job`,
    {method:"POST"},
  );

  const jobId=String(started.job_id||"").trim();
  if(!jobId)throw new Error("Xray reconciliation job was not created.");

  const deadline=Date.now()+10*60*1000;

  while(Date.now()<deadline){
    const current=await request<XrayReconcileJob>(
      `/v1/tunnels/${tunnelId}/service-connections/xray-reconcile-job/${encodeURIComponent(jobId)}`,
    );

    if(current.status==="succeeded"||current.status==="completed_with_errors"){
      return current;
    }

    if(current.status==="failed"){
      throw new Error(current.error||"Xray reconciliation failed.");
    }

    await sleep(2000);
  }

  throw new Error("Xray reconciliation is still running. Refresh this panel shortly.");
}

export const serviceConnectionsV36Api={
  highSpeedAuto:(tunnelId:number)=>request<HighSpeedRouteResult>(
    `/v1/tunnels/${tunnelId}/service-connections/high-speed-auto`,
    {method:"POST"},
  ),
  repairRealEgress:(tunnelId:number)=>request<RealEgressRepairResult>(
    `/v1/tunnels/${tunnelId}/service-connections/repair-real-egress`,
    {method:"POST"},
  ),
  reconcileXray:(tunnelId:number)=>reconcileXray(tunnelId),
};
