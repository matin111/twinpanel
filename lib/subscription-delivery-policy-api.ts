"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type DeliveryCapability={
  protocol:string;
  title:string;
  catalog_present:boolean;
  runtime_ready:boolean;
  account_delivery_ready:boolean;
  quota_enforcement_ready:boolean;
  identity_scope:string;
  revocation_scope:string;
  direct_supported:boolean;
  tunnel_supported:boolean;
  formats:string[];
  reason:string|null;
};

export type DeliveryTunnel={
  id:number;
  iran_node_id:number;
  exit_node_id:number;
  status:string;
  priority:number;
  is_active:boolean;
};

export type DeliveryInfrastructureNode={
  id:number;
  name:string;
  country_code?:string|null;
  public_ip?:string|null;
  public_domain?:string|null;
  show_to_users:boolean;
  status:string;
  protocols:Array<{protocol:string;status:string;port?:number|null;transport?:string|null}>;
  tunnels:DeliveryTunnel[];
};

export type DeliveryTarget={
  node_id:number;
  name:string;
  country_code?:string|null;
  public_ip?:string|null;
  public_domain?:string|null;
  show_to_users:boolean;
  runtime_status:string;
  enabled:boolean;
  direct_enabled:boolean;
  tunnel_enabled:boolean;
  tunnel_id:number|null;
  tunnel?:DeliveryTunnel|null;
  priority:number;
};

export type DeliveryPolicy={
  subscription_id:number;
  mode:"legacy"|"explicit";
  schema_version:number;
  legacy_behavior:string|null;
  protocols:string[];
  targets:DeliveryTarget[];
  capabilities:DeliveryCapability[];
  infrastructure:DeliveryInfrastructureNode[];
  share_code_stable:boolean;
};

export type DeliveryPolicyInput={
  protocols:string[];
  targets:Array<{
    node_id:number;
    enabled:boolean;
    direct_enabled:boolean;
    tunnel_enabled:boolean;
    tunnel_id:number|null;
    priority:number;
  }>;
};

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body)headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  const raw=await response.text();
  let payload:unknown=null;
  if(raw){try{payload=JSON.parse(raw);}catch{payload=raw;}}
  if(!response.ok){
    if(payload&&typeof payload==="object"&&"detail" in payload){
      const detail=(payload as {detail:unknown}).detail;
      if(typeof detail==="string")throw new Error(detail);
      if(detail&&typeof detail==="object"&&"message" in detail){
        const message=String((detail as {message:unknown}).message||"");
        const protocols=(detail as {protocols?:Record<string,string>}).protocols;
        throw new Error(protocols?`${message}: ${Object.keys(protocols).join("، ")}`:message);
      }
    }
    throw new Error(`API error ${response.status}`);
  }
  return payload as T;
}

export const subscriptionDeliveryPolicyApi={
  get:(subscriptionId:number)=>request<DeliveryPolicy>(`/v1/subscriptions/${subscriptionId}/delivery-policy`),
  save:(subscriptionId:number,payload:DeliveryPolicyInput)=>request<DeliveryPolicy>(`/v1/subscriptions/${subscriptionId}/delivery-policy`,{method:"PUT",body:JSON.stringify(payload)}),
  reconcile:(subscriptionId:number)=>request<{ok:boolean;created_pairs?:unknown[];reused_pairs?:unknown[];errors?:unknown[];quota_sync_ok?:boolean;secrets_redacted?:boolean}>(`/v1/subscriptions/${subscriptionId}/delivery-reconcile`,{method:"POST"}),
};
