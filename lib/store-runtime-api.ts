"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type StorePlan={
  id:number;
  name:string;
  description:string|null;
  category?:string|null;
  subscription_type?:string|null;
  sort_order?:number;
  duration_days:number;
  traffic_gb:number;
  device_limit:number;
  price_toman:number;
  is_active:boolean;
  enable_cisco:boolean;
  enable_openvpn:boolean;
  enable_wireguard:boolean;
  enable_l2tp:boolean;
  enable_v2ray:boolean;
  protocols?:string[];
};

export type StoreOrderResult={
  id:number;
  user_id:number;
  plan_id:number;
  amount_toman:number;
  protocols:string[];
  status:string;
  payment_method:string|null;
  payment_reference:string|null;
  subscription_id:number|null;
  error:string|null;
  created_at:string;
};

function detail(payload:unknown,status:number){
  if(payload&&typeof payload==="object"){
    const row=payload as {detail?:unknown;message?:unknown};
    if(typeof row.detail==="string")return row.detail;
    if(typeof row.message==="string")return row.message;
    if(Array.isArray(row.detail))return row.detail.map(x=>typeof x==="object"&&x&&"msg" in x?String((x as {msg:unknown}).msg):String(x)).join("، ");
  }
  return `API error ${status}`;
}

async function request<T>(path:string,init:RequestInit={},token?:string|null):Promise<T>{
  const headers=new Headers(init.headers);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  if(token)headers.set("Authorization",`Bearer ${token}`);
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  if(!response.ok){let payload:unknown=null;try{payload=await response.json();}catch{}throw new Error(detail(payload,response.status));}
  if(response.status===204)return undefined as T;
  return response.json() as Promise<T>;
}

export const storeRuntimeApi={
  plans:()=>request<StorePlan[]>("/v1/plans"),
  storefrontSettings:()=>request<Record<string,unknown>>("/v1/storefront/settings"),
  paymentMethods:()=>request<{methods?:Array<Record<string,unknown>>}|Array<Record<string,unknown>>>("/v1/payments/methods"),
  createOrder:(planId:number,protocols:string[])=>{
    const token=getCustomerToken();
    if(!token)throw new Error("AUTH_REQUIRED");
    return request<StoreOrderResult>("/v1/store/orders",{
      method:"POST",
      body:JSON.stringify({plan_id:planId,protocols,idempotency_key:`web-buy-${planId}-${Date.now()}-${Math.random().toString(36).slice(2,9)}`})
    },token);
  }
};

export function planProtocols(plan:StorePlan){
  // Protocols are a plan-specific snapshot from the current backend. The
  // five enable_* fields remain only for older API installations.
  if(Array.isArray(plan.protocols)){
    const allowed=new Set(["cisco","openvpn","wireguard","l2tp","v2ray",
      "hysteria2","tuic","anytls","naive","shadowtls","snell",
      "mieru","trusttunnel","amneziawg","sudoku"]);
    return [...new Set(plan.protocols.filter(id=>typeof id==="string"&&allowed.has(id)))];
  }
  return [
    plan.enable_cisco&&"cisco",plan.enable_openvpn&&"openvpn",
    plan.enable_wireguard&&"wireguard",plan.enable_l2tp&&"l2tp",
    plan.enable_v2ray&&"v2ray"
  ].filter(Boolean) as string[];
}
