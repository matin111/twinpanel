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
      const message=typeof detail.message==="string"?detail.message:"";
      const errors=detail.errors&&typeof detail.errors==="object"
        ?Object.entries(detail.errors as Record<string,unknown>).map(([key,value])=>`${key}: ${String(value)}`).join(" | ")
        :"";
      if(message||errors)return [message,errors].filter(Boolean).join(" — ");
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

async function requestWithTimeout<T>(path:string,init:RequestInit={},timeoutMs=120000):Promise<T>{
  const controller=new AbortController();
  const timer=window.setTimeout(()=>controller.abort(),timeoutMs);
  try{
    return await request<T>(path,{...init,signal:controller.signal});
  }catch(error){
    if(controller.signal.aborted){
      throw new Error(`زمان اجرای عملیات تمام شد (${Math.round(timeoutMs/1000)} ثانیه): ${path}`);
    }
    throw error;
  }finally{
    window.clearTimeout(timer);
  }
}

function routeMissing(error:unknown){
  const message=error instanceof Error?error.message:String(error);
  return /(not found|method not allowed|api error 404|api error 405)/i.test(message);
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
export type ManagedTunnelCreateResponse={
  ok:boolean;
  operational?:boolean;
  complete:boolean;
  tp2027_complete?:boolean;
  full_complete?:boolean;
  tunnel:AdminTunnel;
  active_transport:string|null;
  installed:string[];
  errors:Record<string,string>;
  transports?:RuntimeRow[];
};

type ManagedInstallCache={installed:string[];errors:Record<string,string>};
const managedInstallCache=new Map<number,ManagedInstallCache>();

// Compatibility cache for older tunnel screens. New V18 screens call
// createManagedTunnel() directly and do not run the legacy three-install flow.
const managedAutoCreateCache=new Set<number>();

async function managedTransportResult(id:number,name:"mtunnel"|"backhaul"|"ssh_tun"){
  const cached=managedInstallCache.get(id);
  if(!cached)return null;

  if(name==="ssh_tun")managedInstallCache.delete(id);

  if(cached.installed.includes(name)){
    return {ok:true,managed:true,transport:name,status:"online"} as RuntimeRow;
  }

  throw new Error(cached.errors[name]||`${name} نصب نشد`);
}

export const legacyControlApi={
  dashboard:()=>request<DashboardSummary&RuntimeRow>("/v1/admin/dashboard-summary"),
  systemHealth:()=>request<SystemHealth>("/v1/admin/system-health"),
  coreProtocols:()=>request<CoreProtocolsResponse>("/v1/admin/core-protocols"),
  restartCoreProtocol:(protocol:string)=>request<RuntimeRow>(`/v1/admin/core-protocols/${encodeURIComponent(protocol)}/restart`,{method:"POST"}),
  restartAllCoreProtocols:()=>request<RuntimeRow>("/v1/admin/core-protocols/restart-all",{method:"POST"}),
  securityOverview:()=>request<RuntimeRow>("/v1/admin/security/overview"),

  nodes:()=>request<AdminNode[]>("/v1/nodes"),
  tunnels:()=>request<AdminTunnel[]>("/v1/tunnels"),

  createManagedTunnel:async(payload:{iran_node_id:number;exit_node_id:number;transport:string;priority:number;is_active:boolean})=>{
    const body=JSON.stringify({...payload,is_active:true});
    try{
      return await requestWithTimeout<ManagedTunnelCreateResponse>("/v1/tunnels/create-managed",{method:"POST",body},360000);
    }catch(error){
      if(!routeMissing(error))throw error;
      return null;
    }
  },
  registerTunnel:async(payload:{iran_node_id:number;exit_node_id:number;transport:string;priority:number;is_active:boolean})=>{
    const body=JSON.stringify({...payload,is_active:true});

    try{
      const managed=await requestWithTimeout<ManagedTunnelCreateResponse>("/v1/tunnels/create-managed",{method:"POST",body},360000);
      const tunnelId=Number(managed.tunnel?.id||0);
      if(tunnelId){
        managedInstallCache.set(tunnelId,{
          installed:Array.isArray(managed.installed)?managed.installed:[],
          errors:managed.errors&&typeof managed.errors==="object"?managed.errors:{},
        });
        managedAutoCreateCache.add(tunnelId);
      }
      return managed.tunnel;
    }catch(error){
      if(!routeMissing(error))throw error;
    }

    try{
      return await request<AdminTunnel>("/v1/tunnels/register",{method:"POST",body});
    }catch(error){
      if(!routeMissing(error))throw error;
      return request<AdminTunnel>("/v1/tunnels",{method:"POST",body});
    }
  },
  updateTunnel:(id:number,payload:RuntimeRow)=>request<AdminTunnel>(`/v1/tunnels/${id}`,{method:"PATCH",body:JSON.stringify(payload)}),
  toggleTunnel:(id:number)=>request<AdminTunnel>(`/v1/tunnels/${id}/toggle`,{method:"POST"}),
  deleteTunnel:(id:number)=>request<RuntimeRow>(`/v1/tunnels/${id}`,{method:"DELETE"}),
  prepareTunnel:(id:number)=>requestWithTimeout<AdminTunnel>(`/v1/tunnels/${id}/prepare`,{method:"POST"},150000),
  tunnelHealth:(id:number)=>request<RuntimeRow>(`/v1/tunnels/${id}/health`),
  tunnelTransports:(id:number)=>request<TunnelTransportsResponse>(`/v1/tunnels/${id}/transports`),
  setTunnelTransportMode:async(id:number,payload:{mode:string;transport?:string|null})=>{
    if(
      managedAutoCreateCache.has(id)
      && payload.mode==="manual"
      && ["mtunnel","backhaul","ssh_tun"].includes(String(payload.transport||""))
    ){
      managedAutoCreateCache.delete(id);
      return request<RuntimeRow>(`/v1/tunnels/${id}/transport-mode`,{
        method:"POST",
        body:JSON.stringify({mode:"auto",transport:null}),
      });
    }

    managedAutoCreateCache.delete(id);
    return request<RuntimeRow>(`/v1/tunnels/${id}/transport-mode`,{method:"POST",body:JSON.stringify(payload)});
  },
  installSshTunnel:async(id:number)=>{
    const managed=await managedTransportResult(id,"ssh_tun");
    return managed||requestWithTimeout<RuntimeRow>(`/v1/tunnels/${id}/ssh/install`,{method:"POST"},150000);
  },
  installMtunnel:async(id:number)=>{
    const managed=await managedTransportResult(id,"mtunnel");
    return managed||requestWithTimeout<RuntimeRow>(`/v1/tunnels/${id}/mtunnel/install`,{method:"POST"},150000);
  },
  repairMtunnel:(id:number)=>requestWithTimeout<RuntimeRow>(`/v1/tunnels/${id}/mtunnel/repair`,{method:"POST"},150000),
  mtunnelHealth:(id:number)=>request<RuntimeRow>(`/v1/tunnels/${id}/mtunnel/health`),
  installBackhaul:async(id:number)=>{
    const managed=await managedTransportResult(id,"backhaul");
    return managed||requestWithTimeout<RuntimeRow>(`/v1/tunnels/${id}/backhaul/install`,{method:"POST"},75000);
  },
  backhaulStatus:(id:number)=>request<RuntimeRow>(`/v1/tunnels/${id}/backhaul/status`)
};
