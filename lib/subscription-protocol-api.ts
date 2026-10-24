"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type SubscriptionProtocolDefinition={
  key:string;
  title:string;
  family:"classic"|"modern";
};

export type SubscriptionProtocolCatalogResponse={
  protocols:SubscriptionProtocolDefinition[];
};

function errorText(payload:unknown,status:number){
  if(payload&&typeof payload==="object"){
    const item=payload as {detail?:unknown;message?:unknown};
    if(typeof item.detail==="string")return item.detail;
    if(typeof item.message==="string")return item.message;
  }
  if(typeof payload==="string"&&payload.trim())return payload.trim();
  return `API error ${status}`;
}

async function request<T>(path:string):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");

  const response=await fetch(`${API_BASE}${path}`,{
    headers:{Authorization:`Bearer ${token}`},
    cache:"no-store",
  });

  const raw=await response.text();
  let payload:unknown=null;
  if(raw){
    try{payload=JSON.parse(raw);}catch{payload=raw;}
  }

  if(!response.ok)throw new Error(errorText(payload,response.status));
  return payload as T;
}

export const subscriptionProtocolApi={
  catalog:()=>request<SubscriptionProtocolCatalogResponse>("/v1/subscriptions/protocol-catalog"),
};
