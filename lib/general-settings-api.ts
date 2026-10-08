"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type SubscriptionUsernameSettings={
  prefix:string;
  template:string;
  preview:string;
  variables:string[];
};

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  if(!response.ok){
    let message=`API error ${response.status}`;
    try{const body=await response.json() as {detail?:unknown;message?:unknown};if(typeof body.detail==="string")message=body.detail;else if(typeof body.message==="string")message=body.message;}catch{}
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const generalSettingsApi={
  subscriptionUsername:()=>request<SubscriptionUsernameSettings>("/v1/settings/general/subscription-username"),
  saveSubscriptionUsername:(payload:{prefix:string;template:string})=>request<SubscriptionUsernameSettings>("/v1/settings/general/subscription-username",{method:"PUT",body:JSON.stringify(payload)})
};
