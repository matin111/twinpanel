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

function requestBase(){
  if(typeof window!=="undefined")return window.location.origin;
  return API_BASE;
}

function errorText(payload:unknown,status:number){
  if(typeof payload==="string"&&payload.trim())return payload.trim();
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

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");

  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");

  const response=await fetch(`${requestBase()}${path}`,{
    ...init,
    headers,
    cache:"no-store",
  });

  const raw=await response.text();
  let payload:unknown=null;
  if(raw){try{payload=JSON.parse(raw);}catch{payload=raw;}}
  if(!response.ok)throw new Error(errorText(payload,response.status));
  return payload as T;
}

function sleep(ms:number){
  return new Promise<void>(resolve=>window.setTimeout(resolve,ms));
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
  reconcileXray:(tunnelId:number)=>reconcileXray(tunnelId),
};
