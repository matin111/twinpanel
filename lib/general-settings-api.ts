"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type SubscriptionUsernameSettings={
  prefix:string;
  template:string;
  preview:string;
  variables:string[];
};

export type SettingsUser={
  id:number;
  email:string|null;
  phone?:string|null;
  full_name:string|null;
  role:string;
  is_active:boolean;
  created_at:string;
};

export type TwoFactorStatus={enabled:boolean};
export type TwoFactorSetup={secret:string;otpauth_uri:string};

export type L2tpSettings={
  psk:string;
  length:number;
  exit_count:number;
  exit_nodes:Array<{id:number;name:string}>;
};

export type L2tpUpdateResult={
  ok:boolean;
  changed:boolean;
  length?:number;
  synced_nodes?:Array<{id:number;name:string}>;
};

export type MotherAccessSettings={
  admin_enabled:boolean;
  reseller_enabled:boolean;
  reseller_overrides:Record<string,boolean>;
};

export type SettingsReseller={
  id:number;
  code?:string|null;
  name:string;
  email?:string|null;
  brand_name?:string|null;
  is_active?:boolean;
};

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type")&&!(init.body instanceof FormData))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  if(!response.ok){
    let message=`API error ${response.status}`;
    try{
      const body=await response.json() as {detail?:unknown;message?:unknown};
      if(typeof body.detail==="string")message=body.detail;
      else if(typeof body.message==="string")message=body.message;
      else if(body.detail&&typeof body.detail==="object"&&"message" in body.detail)message=String((body.detail as {message:unknown}).message);
      else if(Array.isArray(body.detail))message=body.detail.map(item=>typeof item==="object"&&item&&"msg" in item?String((item as {msg:unknown}).msg):String(item)).join("، ");
    }catch{}
    throw new Error(message);
  }
  if(response.status===204)return undefined as T;
  return response.json() as Promise<T>;
}

export const generalSettingsApi={
  me:()=>request<SettingsUser>("/v1/auth/me"),
  updateEmail:(payload:{email:string;current_password:string})=>request<SettingsUser>("/v1/auth/me/email",{method:"PATCH",body:JSON.stringify(payload)}),
  changePassword:(payload:{current_password:string;new_password:string})=>request<{ok?:boolean;message?:string}>("/v1/auth/change-password",{method:"POST",body:JSON.stringify(payload)}),

  twoFactorStatus:()=>request<TwoFactorStatus>("/v1/auth/2fa/status"),
  twoFactorSetup:()=>request<TwoFactorSetup>("/v1/auth/2fa/setup",{method:"POST"}),
  twoFactorEnable:(code:string)=>request<{ok:boolean;enabled:boolean}>("/v1/auth/2fa/enable",{method:"POST",body:JSON.stringify({code})}),
  twoFactorDisable:(payload:{current_password:string;code:string})=>request<{ok:boolean;enabled:boolean}>("/v1/auth/2fa/disable",{method:"POST",body:JSON.stringify(payload)}),

  subscriptionUsername:()=>request<SubscriptionUsernameSettings>("/v1/settings/general/subscription-username"),
  saveSubscriptionUsername:(payload:{prefix:string;template:string})=>request<SubscriptionUsernameSettings>("/v1/settings/general/subscription-username",{method:"PUT",body:JSON.stringify(payload)}),

  l2tp:()=>request<L2tpSettings>("/v1/settings/vpn/l2tp"),
  generateL2tpPsk:()=>request<{psk:string;length:number}>("/v1/settings/vpn/l2tp/generate",{method:"POST"}),
  saveL2tpPsk:(psk:string)=>request<L2tpUpdateResult>("/v1/settings/vpn/l2tp",{method:"PUT",body:JSON.stringify({psk})}),

  motherAccess:()=>request<MotherAccessSettings>("/v1/mother-access/admin"),
  saveMotherAccess:(payload:{admin_enabled:boolean;reseller_enabled:boolean})=>request<{ok:boolean;admin_enabled:boolean;reseller_enabled:boolean}>("/v1/mother-access/admin",{method:"PUT",body:JSON.stringify(payload)}),
  resellers:()=>request<SettingsReseller[]>("/v1/admin/resellers"),
  setResellerMotherAccess:(resellerId:number,enabled:boolean)=>request<{ok:boolean;reseller_id:number;enabled:boolean;effective:boolean}>(`/v1/mother-access/admin/resellers/${resellerId}`,{method:"PUT",body:JSON.stringify({enabled})})
};
