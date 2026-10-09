"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type ResellerRow=Record<string,unknown>;

function apiError(payload:unknown,status:number){
  if(payload&&typeof payload==="object"){
    const row=payload as {detail?:unknown;message?:unknown};
    if(typeof row.detail==="string")return row.detail;
    if(typeof row.message==="string")return row.message;
    if(Array.isArray(row.detail))return row.detail.map(x=>typeof x==="object"&&x&&"msg" in x?String((x as {msg:unknown}).msg):String(x)).join("، ");
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
  if(!response.ok){let payload:unknown=null;try{payload=await response.json();}catch{}throw new Error(apiError(payload,response.status));}
  if(response.status===204)return undefined as T;
  const type=response.headers.get("content-type")||"";
  if(!type.includes("application/json"))return await response.text() as T;
  return response.json() as Promise<T>;
}

export const resellerApi={
  me:()=>request<ResellerRow>("/v1/reseller/me"),
  dashboard:()=>request<ResellerRow>("/v1/reseller/dashboard"),
  customers:()=>request<ResellerRow[]>("/v1/reseller/customers"),
  createCustomer:(payload:{full_name:string;email?:string|null;phone?:string|null;password:string})=>request<ResellerRow>("/v1/reseller/customers",{method:"POST",body:JSON.stringify(payload)}),
  subscriptions:()=>request<ResellerRow[]>("/v1/reseller/subscriptions"),
  sellSubscription:(payload:{user_id?:number|null;traffic_gb:number;duration_days:number;node_ids:number[];protocols:string[];sell_price_toman:number;idempotency_key:string})=>request<ResellerRow>("/v1/reseller/subscriptions/sell",{method:"POST",body:JSON.stringify(payload)}),
  editSubscription:(id:number,payload:ResellerRow)=>request<ResellerRow>(`/v1/reseller/subscriptions/${id}/edit`,{method:"PATCH",body:JSON.stringify(payload)}),
  extendSubscription:(id:number,payload:{add_traffic_gb:number;add_days:number;charge_toman:number;idempotency_key:string})=>request<ResellerRow>(`/v1/reseller/subscriptions/${id}/extend`,{method:"POST",body:JSON.stringify(payload)}),
  toggleSubscription:(id:number)=>request<ResellerRow>(`/v1/reseller/subscriptions/${id}/toggle-active`,{method:"POST"}),
  deleteSubscription:(id:number)=>request<ResellerRow>(`/v1/reseller/subscriptions/${id}`,{method:"DELETE"}),
  connectionInfo:(id:number)=>request<ResellerRow>(`/v1/reseller/subscriptions/${id}/connection-info`),
  plans:()=>request<ResellerRow[]>("/v1/reseller/plans"),
  setPlanPrice:(planId:number,sellPrice:number)=>request<ResellerRow>(`/v1/reseller/plans/${planId}/price`,{method:"PUT",body:JSON.stringify({plan_id:planId,sell_price_toman:sellPrice})}),
  serverOptions:()=>request<ResellerRow>("/v1/reseller/server-options"),
  traffic:()=>request<ResellerRow>("/v1/reseller/traffic"),
  trafficPackages:()=>request<ResellerRow[]>("/v1/reseller/traffic/packages"),
  buyTraffic:(packageId:number)=>request<ResellerRow>("/v1/reseller/traffic/buy",{method:"POST",body:JSON.stringify({package_id:packageId,idempotency_key:`traffic-${Date.now()}-${Math.random().toString(36).slice(2,10)}`})}),
  trafficTransactions:()=>request<ResellerRow[]>("/v1/reseller/traffic/transactions"),
  walletTransactions:()=>request<ResellerRow[]>("/v1/reseller/wallet/transactions"),
  updateProfile:(payload:ResellerRow)=>request<ResellerRow>("/v1/reseller/profile",{method:"PATCH",body:JSON.stringify(payload)}),
  changePassword:(currentPassword:string,newPassword:string)=>request<ResellerRow>("/v1/auth/change-password",{method:"POST",body:JSON.stringify({current_password:currentPassword,new_password:newPassword})}),
  botStatus:()=>request<ResellerRow>("/v1/reseller/bot"),
  botSaveToken:(token:string)=>request<ResellerRow>("/v1/reseller/bot/token",{method:"PUT",body:JSON.stringify({token})}),
  botUpdateSettings:(payload:ResellerRow)=>request<ResellerRow>("/v1/reseller/bot/settings",{method:"PATCH",body:JSON.stringify(payload)}),
  botTest:()=>request<ResellerRow>("/v1/reseller/bot/test",{method:"POST"}),
  botActivate:()=>request<ResellerRow>("/v1/reseller/bot/activate",{method:"POST"}),
  botDeactivate:()=>request<ResellerRow>("/v1/reseller/bot/deactivate",{method:"POST"}),
  botOrders:()=>request<ResellerRow[]>("/v1/reseller/bot-commerce/orders"),
  botApproveOrder:(id:number)=>request<ResellerRow>(`/v1/reseller/bot-commerce/orders/${id}/approve`,{method:"POST"}),
  botRejectOrder:(id:number,reason:string)=>request<ResellerRow>(`/v1/reseller/bot-commerce/orders/${id}/reject`,{method:"POST",body:JSON.stringify({reason})}),
  notifications:()=>request<unknown>("/v1/reseller/notifications"),
  notificationMarkRead:(id:number)=>request<unknown>(`/v1/reseller/notifications/${id}/read`,{method:"POST"}),
  notificationReadAll:()=>request<unknown>("/v1/reseller/notifications/read-all",{method:"POST"})
};
