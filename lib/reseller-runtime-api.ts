"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type ResellerRow=Record<string,unknown>;

export type ResellerPaymentMethodPayload={
  method_type:string;
  title?:string|null;
  card_number?:string|null;
  iban?:string|null;
  account_holder?:string|null;
  instructions?:string|null;
  is_active:boolean;
};

export type ResellerDiscountPayload={
  code:string;
  title?:string|null;
  discount_type:"percent"|"fixed";
  discount_value:number;
  max_discount_toman?:number|null;
  min_order_toman:number;
  applies_to:"purchase"|"renewal"|"both";
  plan_ids:number[];
  usage_limit_total?:number|null;
  usage_limit_per_user?:number|null;
  starts_at?:string|null;
  ends_at?:string|null;
  is_active:boolean;
};

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

async function requestBlob(path:string):Promise<Blob>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const response=await fetch(`${API_BASE}${path}`,{
    headers:{Authorization:`Bearer ${token}`},
    cache:"no-store"
  });
  if(!response.ok){
    let payload:unknown=null;
    try{payload=await response.json();}catch{}
    throw new Error(apiError(payload,response.status));
  }
  return response.blob();
}

export const resellerApi={
  me:()=>request<ResellerRow>("/v1/reseller/me"),
  dashboard:()=>request<ResellerRow>("/v1/reseller/dashboard"),
  customers:()=>request<ResellerRow[]>("/v1/reseller/customers"),
  createCustomer:(payload:{full_name:string;email?:string|null;phone?:string|null;password:string})=>request<ResellerRow>("/v1/reseller/customers",{method:"POST",body:JSON.stringify(payload)}),
  attachCustomer:(userId:number)=>request<ResellerRow>("/v1/reseller/customers/attach",{method:"POST",body:JSON.stringify({user_id:userId})}),
  subscriptions:()=>request<ResellerRow[]>("/v1/reseller/subscriptions"),
  sellSubscription:(payload:{user_id?:number|null;plan_id?:number|null;traffic_gb:number;duration_days:number;node_ids:number[];protocols:string[];sell_price_toman:number;idempotency_key:string;username?:string|null;password?:string|null})=>request<ResellerRow>("/v1/reseller/subscriptions/sell",{method:"POST",body:JSON.stringify(payload)}),
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

  botPaymentMethods:()=>request<ResellerRow[]>("/v1/reseller/bot-commerce/payment-methods"),
  botCreatePaymentMethod:(payload:ResellerPaymentMethodPayload)=>request<ResellerRow>("/v1/reseller/bot-commerce/payment-methods",{method:"POST",body:JSON.stringify(payload)}),
  botUpdatePaymentMethod:(id:number,payload:ResellerPaymentMethodPayload)=>request<ResellerRow>(`/v1/reseller/bot-commerce/payment-methods/${id}`,{method:"PUT",body:JSON.stringify(payload)}),
  botDeletePaymentMethod:(id:number)=>request<ResellerRow>(`/v1/reseller/bot-commerce/payment-methods/${id}`,{method:"DELETE"}),
  botOrders:()=>request<ResellerRow[]>("/v1/reseller/bot-commerce/orders"),
  botOrderReceipt:(id:number)=>requestBlob(`/v1/reseller/bot-commerce/orders/${id}/receipt`),
  botApproveOrder:(id:number)=>request<ResellerRow>(`/v1/reseller/bot-commerce/orders/${id}/approve`,{method:"POST"}),
  botRejectOrder:(id:number,reason:string)=>request<ResellerRow>(`/v1/reseller/bot-commerce/orders/${id}/reject`,{method:"POST",body:JSON.stringify({reason})}),

  discounts:()=>request<ResellerRow[]>("/v1/discounts/reseller"),
  createDiscount:(payload:ResellerDiscountPayload)=>request<ResellerRow>("/v1/discounts/reseller",{method:"POST",body:JSON.stringify(payload)}),
  updateDiscount:(id:number,payload:ResellerDiscountPayload)=>request<ResellerRow>(`/v1/discounts/reseller/${id}`,{method:"PUT",body:JSON.stringify(payload)}),
  disableDiscount:(id:number)=>request<ResellerRow>(`/v1/discounts/reseller/${id}`,{method:"DELETE"}),

  notifications:()=>request<unknown>("/v1/reseller/notifications"),
  notificationMarkRead:(id:number)=>request<unknown>(`/v1/reseller/notifications/${id}/read`,{method:"POST"}),
  notificationReadAll:()=>request<unknown>("/v1/reseller/notifications/read-all",{method:"POST"})
};
