"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type TunnelTransportName="ssh_tun"|"backhaul"|"mtunnel";
export type ModernTransportName="kernel_gre"|"gost_tun"|"amneziawg"|"netrix";
export type TunnelTransportMode="auto"|"manual";
export type TunnelTransportRow={
  id?:number;
  tunnel_id?:number;
  transport?:string;
  priority?:number;
  enabled?:boolean;
  status?:string;
  latency_ms?:number|null;
  last_error?:string|null;
  last_healthy_at?:string|null;
  label?:string;
  family?:string;
  canary?:boolean;
  selectable?:boolean;
  runtime?:Record<string,unknown>;
  [key:string]:unknown;
};
export type TunnelTransportState={
  tunnel_id:number;
  iran_node_id?:number;
  exit_node_id?:number;
  mode?:string;
  preferred_transport?:string|null;
  active_transport?:string|null;
  last_switch_at?:string|null;
  transports?:TunnelTransportRow[];
  [key:string]:unknown;
};
export type ModernTransportState={
  ok?:boolean;
  tunnel_id:number;
  active_transport?:string|null;
  production_default?:string;
  transports?:TunnelTransportRow[];
  [key:string]:unknown;
};

function errorText(payload:unknown,status:number){
  if(payload&&typeof payload==="object"){
    const row=payload as {detail?:unknown;message?:unknown};
    if(typeof row.detail==="string")return row.detail;
    if(typeof row.message==="string")return row.message;
    if(row.detail&&typeof row.detail==="object"&&!Array.isArray(row.detail)){
      const detail=row.detail as {message?:unknown;transport?:unknown;error?:unknown};
      const parts=[detail.message,detail.transport,detail.error].filter(value=>value!==undefined&&value!==null&&String(value).trim()).map(String);
      if(parts.length)return parts.join(" — ");
    }
    if(Array.isArray(row.detail))return row.detail.map(item=>typeof item==="object"&&item&&"msg" in item?String((item as {msg:unknown}).msg):String(item)).join("، ");
  }
  return `API error ${status}`;
}

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  if(!response.ok){let payload:unknown=null;try{payload=await response.json();}catch{}throw new Error(errorText(payload,response.status));}
  if(response.status===204)return undefined as T;
  return response.json() as Promise<T>;
}

export const tunnelTransportApi={
  transports:(id:number)=>request<TunnelTransportState>(`/v1/tunnels/${id}/transports`),
  modernTransports:(id:number)=>request<ModernTransportState>(`/v1/tunnels/${id}/modern-transports`),
  modernCatalog:()=>request<Record<string,unknown>>("/v1/tunnels/transport-catalog"),
  installModern:(id:number,name:ModernTransportName)=>request<Record<string,unknown>>(`/v1/tunnels/${id}/modern-transports/${encodeURIComponent(name)}/install`,{method:"POST"}),
  removeModern:(id:number,name:ModernTransportName)=>request<Record<string,unknown>>(`/v1/tunnels/${id}/modern-transports/${encodeURIComponent(name)}`,{method:"DELETE"}),
  setMode:(id:number,payload:{mode:TunnelTransportMode;transport?:TunnelTransportName})=>request<TunnelTransportState>(`/v1/tunnels/${id}/transport-mode`,{method:"POST",body:JSON.stringify(payload)}),
  installSsh:(id:number)=>request<Record<string,unknown>>(`/v1/tunnels/${id}/ssh/install`,{method:"POST"}),
  installBackhaul:(id:number)=>request<Record<string,unknown>>(`/v1/tunnels/${id}/backhaul/install`,{method:"POST"}),
  backhaulStatus:(id:number)=>request<Record<string,unknown>>(`/v1/tunnels/${id}/backhaul/status`),
  installMtunnel:(id:number)=>request<Record<string,unknown>>(`/v1/tunnels/${id}/mtunnel/install`,{method:"POST"}),
  repairMtunnel:(id:number)=>request<Record<string,unknown>>(`/v1/tunnels/${id}/mtunnel/repair`,{method:"POST"}),
  mtunnelHealth:(id:number)=>request<Record<string,unknown>>(`/v1/tunnels/${id}/mtunnel/health`),
  health:(id:number)=>request<Record<string,unknown>>(`/v1/tunnels/${id}/health`)
};
