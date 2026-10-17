"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";
import type {AdminUser,RuntimeRow} from "./admin-api";

function errorText(payload:unknown,status:number){
  if(payload&&typeof payload==="object"){
    const item=payload as {detail?:unknown;message?:unknown};
    if(typeof item.detail==="string")return item.detail;
    if(typeof item.message==="string")return item.message;
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

export const legacyAdminApi={
  usersPage:(params:{limit:number;offset:number;q:string;status:"all"|"active"|"inactive"|"subscribed"})=>request<UsersPageResponse>(`/v1/admin/users-page?limit=${encodeURIComponent(String(params.limit))}&offset=${encodeURIComponent(String(params.offset))}&q=${encodeURIComponent(params.q)}&status=${encodeURIComponent(params.status)}`),
  subscriptionsByUser:(userId:number)=>request<RuntimeRow[]>(`/v1/subscriptions/by-user/${userId}`),
  extendSubscription:(id:number,payload:{add_traffic_gb?:number;add_days?:number})=>request<RuntimeRow>(`/v1/subscriptions/${id}/extend`,{method:"PATCH",body:JSON.stringify(payload)}),
  nodeAccess:(id:number)=>request<RuntimeRow>(`/v1/provision/node-access/${id}`),
  saveNodeAccess:(payload:{node_id:number;host:string;port:number;username:string;password:string})=>request<RuntimeRow>("/v1/provision/save-node-access",{method:"POST",body:JSON.stringify(payload)}),
  protocolHealth:(nodeId:number)=>request<RuntimeRow>("/v1/provision/protocol-health",{method:"POST",body:JSON.stringify({node_id:nodeId})}),
  restartProtocol:(nodeId:number,protocol:string)=>request<RuntimeRow>("/v1/provision/restart-protocol",{method:"POST",body:JSON.stringify({node_id:nodeId,protocol})}),
  repairProtocolsSaved:(nodeId:number)=>request<RuntimeRow>("/v1/provision/repair-protocols-saved",{method:"POST",body:JSON.stringify({node_id:nodeId})}),
  upgradeAgent:(nodeId:number)=>request<RuntimeRow>("/v1/provision/upgrade-agent",{method:"POST",body:JSON.stringify({node_id:nodeId})}),
  nodeDomains:()=>request<{ok?:boolean;nodes:RuntimeRow[]}>("/v1/subscriptions/node-domains"),
  updateNodeDomain:(id:number,domain:string)=>request<RuntimeRow>(`/v1/subscriptions/node-domains/${id}`,{method:"PUT",body:JSON.stringify({domain})}),
  installTunnelFabric:(nodeId:number)=>request<RuntimeRow>("/v1/provision/install-fabric",{method:"POST",body:JSON.stringify({node_id:nodeId})}),
  tunnelFabricStatus:(nodeId:number)=>request<RuntimeRow>(`/v1/provision/fabric-status/${nodeId}`)
};