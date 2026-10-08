"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";
import type {AdminNode,AdminTunnel,DashboardSummary,RuntimeRow} from "./admin-api";

function errorText(payload:unknown,status:number){
  if(typeof payload==="string"&&payload.trim())return payload.trim();
  if(payload&&typeof payload==="object"){
    const item=payload as {detail?:unknown;message?:unknown};
    if(typeof item.detail==="string")return item.detail;
    if(typeof item.message==="string")return item.message;
    if(item.detail&&typeof item.detail==="object"){
      const detail=item.detail as {message?:unknown;errors?:unknown};
      if(typeof detail.message==="string")return detail.message;
    }
    if(Array.isArray(item.detail))return item.detail.map(x=>typeof x==="object"&&x&&"msg" in x?String((x as {msg:unknown}).msg):String(x)).join("، ");
  }
  return `API error ${status}`;
}

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type")&&!(init.body instanceof FormData))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  if(response.status===204)return undefined as T;
  const raw=await response.text();
  let payload:unknown=null;
  if(raw){try{payload=JSON.parse(raw);}catch{payload=raw;}}
  if(!response.ok)throw new Error(errorText(payload,response.status));
  return payload as T;
}

export type SystemHealth=RuntimeRow&{
  hostname?:string;
  state?:string;
  cpu?:RuntimeRow;
  memory?:RuntimeRow;
  disk?:RuntimeRow;
  network?:RuntimeRow;
  services?:Record<string,RuntimeRow>;
  active_connections?:number;
  uptime_seconds?:number;
};

export type CoreProtocolsResponse={ok?:boolean;protocols:Record<string,RuntimeRow>};
export type TunnelTransportsResponse=RuntimeRow&{transports?:RuntimeRow[]};

export const legacyControlApi={
  dashboard:()=>request<DashboardSummary&RuntimeRow>("/v1/admin/dashboard-summary"),
  systemHealth:()=>request<SystemHealth>("/v1/admin/system-health"),
  coreProtocols:()=>request<CoreProtocolsResponse>("/v1/admin/core-protocols"),
  restartCoreProtocol:(protocol:string)=>request<RuntimeRow>(`/v1/admin/core-protocols/${encodeURIComponent(protocol)}/restart`,{method:"POST"}),
  restartAllCoreProtocols:()=>request<RuntimeRow>("/v1/admin/core-protocols/restart-all",{method:"POST"}),
  securityOverview:()=>request<RuntimeRow>("/v1/admin/security/overview"),

  nodes:()=>request<AdminNode[]>("/v1/nodes"),
  tunnels:()=>request<AdminTunnel[]>("/v1/tunnels"),

  registerTunnel:(payload:{iran_node_id:number;exit_node_id:number;transport:string;priority:number;is_active:boolean})=>request<AdminTunnel>("/v1/tunnels/register",{method:"POST",body:JSON.stringify(payload)}),
  updateTunnel:(id:number,payload:RuntimeRow)=>request<AdminTunnel>(`/v1/tunnels/${id}`,{method:"PATCH",body:JSON.stringify(payload)}),
  toggleTunnel:(id:number)=>request<AdminTunnel>(`/v1/tunnels/${id}/toggle`,{method:"POST"}),
  deleteTunnel:(id:number)=>request<RuntimeRow>(`/v1/tunnels/${id}`,{method:"DELETE"}),
  prepareTunnel:(id:number)=>request<AdminTunnel>(`/v1/tunnels/${id}/prepare`,{method:"POST"}),
  tunnelHealth:(id:number)=>request<RuntimeRow>(`/v1/tunnels/${id}/health`),
  tunnelTransports:(id:number)=>request<TunnelTransportsResponse>(`/v1/tunnels/${id}/transports`),
  setTunnelTransportMode:(id:number,payload:{mode:string;transport?:string|null})=>request<RuntimeRow>(`/v1/tunnels/${id}/transport-mode`,{method:"POST",body:JSON.stringify(payload)}),
  installSshTunnel:(id:number)=>request<RuntimeRow>(`/v1/tunnels/${id}/ssh/install`,{method:"POST"}),
  installMtunnel:(id:number)=>request<RuntimeRow>(`/v1/tunnels/${id}/mtunnel/install`,{method:"POST"}),
  repairMtunnel:(id:number)=>request<RuntimeRow>(`/v1/tunnels/${id}/mtunnel/repair`,{method:"POST"}),
  mtunnelHealth:(id:number)=>request<RuntimeRow>(`/v1/tunnels/${id}/mtunnel/health`),
  installBackhaul:(id:number)=>request<RuntimeRow>(`/v1/tunnels/${id}/backhaul/install`,{method:"POST"}),
  backhaulStatus:(id:number)=>request<RuntimeRow>(`/v1/tunnels/${id}/backhaul/status`)
};
