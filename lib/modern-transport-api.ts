"use client";

import {getCustomerToken} from "./customer-api";

export type SmartTransportName=
  |"tp27_fast"
  |"spoof_wg"
  |"tp27_masque"
  |"tp27_tcp_direct"
  |"kernel_gre"
  |"gost_tun"
  |"amneziawg"
  |"netrix";

export type SmartTransportBenchmark={
  measured_at_epoch?:number;
  download_mbps?:number;
  upload_mbps?:number;
  weighted_mbps?:number;
  download_weight?:number;
  upload_weight?:number;
  streams?:number;
  source?:string;
};

export type SpoofWGConfiguration={
  iran_spoof_ip?:string;
  exit_spoof_ip?:string;
  send_transport?:string;
  recv_transport?:string;
  xdp?:boolean;
  configured?:boolean;
};

export type SmartTransportCandidate={
  transport:SmartTransportName;
  label?:string;
  family?:string;
  iran_profile?:string;
  description?:string;
  enabled?:boolean;
  status?:string;
  latency_ms?:number|null;
  last_error?:string|null;
  last_healthy_at?:string|null;
  auto_managed?:boolean;
  qualified?:boolean;
  selectable?:boolean;
  stable_seconds?:number;
  required_stable_seconds?:number;
  auto_block_reason?:string|null;
  quarantine_until_epoch?:number|null;
  benchmark?:SmartTransportBenchmark|null;
  benchmark_fresh?:boolean;
  benchmark_age_seconds?:number|null;
  runtime?:Record<string,unknown>;
  configuration?:SpoofWGConfiguration;
  configured?:boolean;
  configuration_required?:boolean;
  auto_install?:boolean;
  upstream_version?:string;
  xdp?:boolean;
  [key:string]:unknown;
};

export type SmartTransportState={
  ok?:boolean;
  tunnel_id:number;
  mode?:string;
  active_transport?:string|null;
  preferred_transport?:string|null;
  production_default?:string;
  promotion_policy?:string;
  transports:SmartTransportCandidate[];
};

function requestBase(){
  if(typeof window!=="undefined")return window.location.origin;
  return "";
}

function errorText(payload:unknown,status:number){
  if(typeof payload==="string"&&payload.trim())return payload.trim();
  if(payload&&typeof payload==="object"){
    const value=payload as {detail?:unknown;message?:unknown};
    if(typeof value.message==="string")return value.message;
    if(typeof value.detail==="string")return value.detail;
    if(value.detail&&typeof value.detail==="object"){
      const detail=value.detail as {message?:unknown;error?:unknown};
      return [detail.message,detail.error].filter(Boolean).map(String).join(" — ")||`API error ${status}`;
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
  const response=await fetch(`${requestBase()}${path}`,{...init,headers,cache:"no-store"});
  const raw=await response.text();
  let payload:unknown=null;
  if(raw){try{payload=JSON.parse(raw);}catch{payload=raw;}}
  if(!response.ok)throw new Error(errorText(payload,response.status));
  return payload as T;
}

export const modernTransportApi={
  state:(tunnelId:number)=>request<SmartTransportState>(`/v1/tunnels/${tunnelId}/modern-transports`),
  install:(tunnelId:number,transport:SmartTransportName)=>request<Record<string,unknown>>(`/v1/tunnels/${tunnelId}/modern-transports/${encodeURIComponent(transport)}/install`,{method:"POST"}),
  remove:(tunnelId:number,transport:SmartTransportName)=>request<Record<string,unknown>>(`/v1/tunnels/${tunnelId}/modern-transports/${encodeURIComponent(transport)}`,{method:"DELETE"}),
  configureSpoof:(tunnelId:number,configuration:{iran_spoof_ip:string;exit_spoof_ip:string})=>request<Record<string,unknown>>(`/v1/tunnels/${tunnelId}/modern-transports/spoof_wg/config`,{method:"PUT",body:JSON.stringify(configuration)}),
  setMode:(tunnelId:number,mode:"auto"|"manual",transport?:string)=>{
    if(mode==="manual"&&transport){
      return request<Record<string,unknown>>(`/v1/tunnels/${tunnelId}/modern-transports/${encodeURIComponent(transport)}/select-manual`,{method:"POST"});
    }
    return request<Record<string,unknown>>(`/v1/tunnels/${tunnelId}/transport-mode`,{method:"POST",body:JSON.stringify({mode})});
  },
};