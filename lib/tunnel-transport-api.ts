"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type TunnelTransportName="quic_2027"|"arq_2027"|"kcp_2027"|"tcp_2027"|"kernel_gre"|"ssh_tun"|"backhaul"|"mtunnel"|"gost_tun"|"ssh_relay";
export type TunnelTransportMode="auto"|"manual";
export type TunnelTransportRow={id?:number;tunnel_id?:number;transport?:string;priority?:number;enabled?:boolean;status?:string;latency_ms?:number|null;last_error?:string|null;last_healthy_at?:string|null;[key:string]:unknown};
export type TunnelTransportState={tunnel_id:number;iran_node_id?:number;exit_node_id?:number;mode?:string;preferred_transport?:string|null;active_transport?:string|null;last_switch_at?:string|null;transports?:TunnelTransportRow[];[key:string]:unknown};

type DeepRepairJob={
  ok?:boolean;
  accepted?:boolean;
  reused?:boolean;
  job_id?:string;
  tunnel_id?:number;
  status?:"queued"|"running"|"succeeded"|"failed"|string;
  stage?:string|null;
  result?:Record<string,unknown>|null;
  error?:string|null;
  marker?:string;
};

const TRANSIENT_GET_STATUSES=new Set([502,503,504]);
const TRANSIENT_GET_RETRY_MS=[350,900,1800] as const;
const lastGoodRead=new Map<string,unknown>();

function isHtmlErrorBody(value:string){
  const sample=value.trim().slice(0,1024);
  return /<(?:!doctype|html|head|body|title|center)\b|nginx\//i.test(sample);
}

function isTransientNetworkError(reason:unknown){
  const text=reason instanceof Error?reason.message:String(reason||"");
  return /failed to fetch|networkerror|network request failed|load failed|fetch failed|connection|timeout/i.test(text);
}

function transientStatusText(status:number){
  return `سرویس کنترل تانل موقتاً در دسترس نیست. چند لحظه بعد دوباره تلاش کنید. (${status})`;
}

function networkErrorText(){
  return "ارتباط با سرویس کنترل تانل موقتاً قطع شد. چند لحظه بعد دوباره تلاش کنید.";
}

function errorText(payload:unknown,status:number){
  if(TRANSIENT_GET_STATUSES.has(status))return transientStatusText(status);
  if(typeof payload==="string"&&payload.trim()){
    const text=payload.trim();
    if(isHtmlErrorBody(text))return `خطای ارتباط با سرویس کنترل تانل (${status})`;
    return text;
  }
  if(payload&&typeof payload==="object"){
    const row=payload as {detail?:unknown;message?:unknown};
    if(typeof row.detail==="string")return row.detail;
    if(typeof row.message==="string")return row.message;
    if(row.detail&&typeof row.detail==="object"){
      const detail=row.detail as {message?:unknown;error?:unknown;errors?:unknown};
      const message=typeof detail.message==="string"?detail.message:"";
      const error=typeof detail.error==="string"?detail.error:"";
      const errors=detail.errors&&typeof detail.errors==="object"
        ?Object.entries(detail.errors as Record<string,unknown>).map(([key,value])=>`${key}: ${String(value)}`).join(" | ")
        :"";
      if(message||error||errors)return [message,error,errors].filter(Boolean).join(" — ");
    }
    if(Array.isArray(row.detail))return row.detail.map(item=>typeof item==="object"&&item&&"msg" in item?String((item as {msg:unknown}).msg):String(item)).join("، ");
  }
  return `API error ${status}`;
}

function requestBase(){
  // Admin tunnel control must always use the same TwinPanel origin in the
  // browser. This guarantees that /v1 goes through the built-in Next proxy
  // instead of accidentally targeting a stale/public API base configured at
  // build time. SSR retains API_BASE for compatibility.
  if(typeof window!=="undefined")return window.location.origin;
  return API_BASE;
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
      response=await fetch(`${requestBase()}${path}`,{...init,headers,cache:"no-store"});
    }catch(reason){
      const canRetry=method==="GET"&&isTransientNetworkError(reason)&&attempt<TRANSIENT_GET_RETRY_MS.length;
      if(canRetry){
        await sleep(TRANSIENT_GET_RETRY_MS[attempt]);
        continue;
      }

      if(method==="GET"&&isTransientNetworkError(reason)&&lastGoodRead.has(path)){
        return lastGoodRead.get(path) as T;
      }

      if(isTransientNetworkError(reason))throw new Error(networkErrorText());
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

    if(response.status===204)return undefined as T;
    const raw=await response.text();
    let payload:unknown=null;
    if(raw){try{payload=JSON.parse(raw);}catch{payload=raw;}}
    if(!response.ok)throw new Error(errorText(payload,response.status));

    if(method==="GET")lastGoodRead.set(path,payload);
    else lastGoodRead.clear();

    return payload as T;
  }

  if(method==="GET"&&lastGoodRead.has(path))return lastGoodRead.get(path) as T;
  throw new Error(networkErrorText());
}

async function managedDeepRepairJob(id:number):Promise<Record<string,unknown>>{
  const started=await request<DeepRepairJob>(`/v1/tunnels/${id}/managed-deep-repair-job`,{method:"POST"});
  const jobId=String(started.job_id||"").trim();
  if(!jobId)throw new Error("Deep repair job was not created.");

  if(started.status==="succeeded"&&started.result)return started.result;
  if(started.status==="failed")throw new Error(started.error||"Deep repair job failed.");

  // V34: each poll is a short request. The browser/Next/FastAPI socket is no
  // longer held open while MTunnel/TP2027/SSH installers run for minutes.
  const deadline=Date.now()+15*60*1000;
  let lastStage=String(started.stage||started.status||"queued");

  while(Date.now()<deadline){
    await sleep(2000);
    const job=await request<DeepRepairJob>(`/v1/tunnels/${id}/managed-deep-repair-job/${encodeURIComponent(jobId)}`);
    lastStage=String(job.stage||job.status||lastStage);

    if(job.status==="succeeded"){
      if(!job.result)throw new Error("Deep repair completed without a result.");
      return job.result;
    }

    if(job.status==="failed"){
      throw new Error(job.error||`Deep repair failed at ${lastStage}.`);
    }
  }

  throw new Error(`Deep repair is still running (${lastStage}). Refresh later and run diagnosis again.`);
}

export const tunnelTransportApi={
  transports:(id:number)=>request<TunnelTransportState>(`/v1/tunnels/${id}/transports`),
  setMode:(id:number,payload:{mode:TunnelTransportMode;transport?:TunnelTransportName})=>request<TunnelTransportState>(`/v1/tunnels/${id}/transport-mode`,{method:"POST",body:JSON.stringify(payload)}),
  managedDiagnose:(id:number)=>request<Record<string,unknown>>(`/v1/tunnels/${id}/managed-diagnose`),
  managedRepair:(id:number)=>request<Record<string,unknown>>(`/v1/tunnels/${id}/managed-repair`,{method:"POST"}),
  managedDeepDiagnose:(id:number)=>request<Record<string,unknown>>(`/v1/tunnels/${id}/managed-deep-diagnose`),
  managedDeepRepair:(id:number)=>managedDeepRepairJob(id),
  installDeepDiagnosticsAgent:(id:number)=>request<Record<string,unknown>>(`/v1/tunnels/${id}/managed-deep-agent-install`,{method:"POST"}),
  installSsh:(id:number)=>request<Record<string,unknown>>(`/v1/tunnels/${id}/ssh/install`,{method:"POST"}),
  installBackhaul:(id:number)=>request<Record<string,unknown>>(`/v1/tunnels/${id}/backhaul/install`,{method:"POST"}),
  backhaulStatus:(id:number)=>request<Record<string,unknown>>(`/v1/tunnels/${id}/backhaul/status`),
  installMtunnel:(id:number)=>request<Record<string,unknown>>(`/v1/tunnels/${id}/mtunnel/install`,{method:"POST"}),
  repairMtunnel:(id:number)=>request<Record<string,unknown>>(`/v1/tunnels/${id}/mtunnel/repair`,{method:"POST"}),
  mtunnelHealth:(id:number)=>request<Record<string,unknown>>(`/v1/tunnels/${id}/mtunnel/health`),
  health:(id:number)=>request<Record<string,unknown>>(`/v1/tunnels/${id}/health`)
};
