"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";
import type {ResellerRow} from "./reseller-runtime-api";

export type ResellerManualSubscriptionPayload={
  traffic_gb:number;
  duration_days:number;
  node_ids:number[];
  protocols:string[];
  username:string|null;
  password:string|null;
  idempotency_key:string;
};

function apiError(payload:unknown,status:number){
  if(payload&&typeof payload==="object"){
    const row=payload as {detail?:unknown;message?:unknown};
    if(typeof row.detail==="string")return row.detail;
    if(typeof row.message==="string")return row.message;
    if(Array.isArray(row.detail))return row.detail.map(item=>typeof item==="object"&&item&&"msg" in item?String((item as {msg:unknown}).msg):String(item)).join("، ");
  }
  return `API error ${status}`;
}

export async function createResellerManualSubscription(
  payload:ResellerManualSubscriptionPayload
):Promise<ResellerRow>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");

  const response=await fetch(`${API_BASE}/v1/reseller/subscriptions/manual-create`,{
    method:"POST",
    headers:{
      Authorization:`Bearer ${token}`,
      "Content-Type":"application/json"
    },
    body:JSON.stringify(payload),
    cache:"no-store"
  });

  if(!response.ok){
    let body:unknown=null;
    try{body=await response.json();}catch{}
    throw new Error(apiError(body,response.status));
  }

  return response.json() as Promise<ResellerRow>;
}
