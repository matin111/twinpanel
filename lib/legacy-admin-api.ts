"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";
import type {AdminUser,RuntimeRow} from "./admin-api";

function errorText(payload:unknown,status:number){
  if(payload&&typeof payload==="object"){
    const item=payload as {detail?:unknown;message?:unknown};
    if(typeof item.detail==="string")return item.detail;
    if(typeof item.message==="string")return item.message;
    if(item.detail&&typeof item.detail==="object"&&"message" in item.detail){
      const message=(item.detail as {message?:unknown}).message;
      if(typeof message==="string")return message;
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
  if(!response.ok){let payload:unknown=null;try{payload=await response.json();}catch{}throw new Error(errorText(payload,response.status));}
  if(response.status===204)return undefined as T;
  return response.json() as Promise<T>;
}

export type UsersPageResponse={
  items:Array<AdminUser&RuntimeRow>;
  total:number;
  limit:number;
  offset:number;
  summary:{total_users:number;active_users:number;inactive_users:number;subscribed_users:number};
};

export type ClassicProtocolKey="cisco"|"openvpn"|"wireguard"|"l2tp"|"v2ray";
export type EnsureClassicProtocolPayload={
  node_id:number;
  protocol:ClassicProtocolKey;
  port?:number;
  transport?:"udp"|"tcp";
};
export type ClassicProtocolInventoryRow={
  protocol:ClassicProtocolKey;
  enabled:boolean;
  operator_disabled?:boolean;
  port:number|null;
  port_text:string;
  transport:string;
  service?:string|null;
  status:string;
  last_error?:string|null;
  checked_at?:string|null;
};
export type ClassicProtocolInventoryNode={
  id:number;
  name:string;
  public_ip:string;
  public_domain?:string|null;
  status:string;
  protocols:ClassicProtocolInventoryRow[];
};
export type ClassicProtocolInventoryResponse={
  ok:boolean;
  nodes:ClassicProtocolInventoryNode[];
};

export const legacyAdminApi={
  usersPage:(params:{limit:number;offset:number;q:string;status:"all"|"active"|"inactive"|"subscribed"})=>request<UsersPageResponse>(`/v1/admin/users-page?limit=${encodeURIComponent(String(params.limit))}&offset=${encodeURIComponent(String(params.offset))}&q=${encodeURIComponent(params.q)}&status=${encodeURIComponent(params.status)}`),
  subscriptionsByUser:(userId:number)=>request<RuntimeRow[]>(`/v1/subscriptions/by-user/${userId}`),
  resetSubscriptionUsage:(id:number)=>request<{ok:boolean;reset_usage:boolean}>(`/v1/subscriptions/${id}/extend`,{method:"PATCH",body:JSON.stringify({add_traffic_gb:0,add_days:0,reset_usage:true,reset_date:false})}),
  reserveSubscriptionRenewal:(id:number,payload:{traffic_gb:number;duration_days:number;plan_id?:number;mode?:"legacy"|"custom"|"plan"})=>request<{ok:boolean;renewal_id:number;status:string}>(`/v1/subscriptions/${id}/reserve-renewal`,{method:"POST",body:JSON.stringify(payload)}),
  subscriptionHistory:(id:number)=>request<{events:Array<{id:number;type:string;source:string;actor:string;details:Record<string,unknown>;created_at:string}>;renewals:Array<{id:number;plan:string;traffic_bytes:number;duration_days:number;status:string;created_at:string;activated_at?:string|null;can_cancel:boolean;amount_toman?:number|null;source:string}>;queued:Array<{id:number;plan:string;traffic_bytes:number;duration_days:number;status:string;created_at:string}>}>(`/v1/subscriptions/${id}/history`),
  cancelReservedRenewal:(id:number,renewalId:number)=>request<{ok:boolean}>(`/v1/subscriptions/${id}/reserve-renewal/${renewalId}`,{method:"DELETE"}),
  retryReservedRenewal:(id:number,renewalId:number)=>request<{ok:boolean;status:string}>(`/v1/subscriptions/${id}/reserve-renewal/${renewalId}/retry`,{method:"POST"}),
  nodeAccess:(id:number)=>request<RuntimeRow>(`/v1/provision/node-access/${id}`),
  saveNodeAccess:(payload:{node_id:number;host:string;port:number;username:string;password:string})=>request<RuntimeRow>("/v1/provision/save-node-access",{method:"POST",body:JSON.stringify(payload)}),
  classicProtocols:()=>request<ClassicProtocolInventoryResponse>("/v1/provision/classic-protocols"),
  protocolHealth:(nodeId:number,protocol?:ClassicProtocolKey)=>request<RuntimeRow>("/v1/provision/classic-protocol-health",{method:"POST",body:JSON.stringify({node_id:nodeId,...(protocol?{protocol}:{})})}),
  classicPortCheck:(payload:EnsureClassicProtocolPayload)=>request<{ok:boolean;available:boolean;checked_ports:number[];conflicts:Array<{port:number;transport:string}>;note?:string|null}>("/v1/provision/classic-port-check",{method:"POST",body:JSON.stringify(payload)}),
  ensureClassicProtocol:(payload:EnsureClassicProtocolPayload)=>request<RuntimeRow>("/v1/provision/ensure-classic-protocol",{method:"POST",body:JSON.stringify(payload)}),
  restartProtocol:(nodeId:number,protocol:string)=>request<RuntimeRow>("/v1/provision/classic-restart-protocol",{method:"POST",body:JSON.stringify({node_id:nodeId,protocol})}),
  repairProtocolsSaved:(nodeId:number)=>request<RuntimeRow>("/v1/provision/repair-protocols-saved",{method:"POST",body:JSON.stringify({node_id:nodeId})}),
  upgradeAgent:(nodeId:number)=>request<RuntimeRow>("/v1/provision/upgrade-agent",{method:"POST",body:JSON.stringify({node_id:nodeId})}),
  nodeDomains:()=>request<{ok?:boolean;nodes:RuntimeRow[]}>("/v1/subscriptions/node-domains"),
  updateNodeDomain:(id:number,domain:string)=>request<RuntimeRow>(`/v1/subscriptions/node-domains/${id}`,{method:"PUT",body:JSON.stringify({domain})}),
  installTunnelFabric:(nodeId:number)=>request<RuntimeRow>("/v1/provision/install-fabric",{method:"POST",body:JSON.stringify({node_id:nodeId})}),
  tunnelFabricStatus:(nodeId:number)=>request<RuntimeRow>(`/v1/provision/fabric-status/${nodeId}`)
};