"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type FastSubscriptionCreatePayload={
  user_id:number;
  plan_id?:number|null;
  node_ids:number[];
  protocols:string[];
  traffic_gb?:number;
  duration_days?:number;
  device_limit?:number;
  username?:string;
  password?:string;
};

export type FastSubscriptionCreateResult={
  ok:boolean;
  queued:boolean;
  message?:string;
};

function errorText(payload:unknown,status:number){
  if(payload&&typeof payload==="object"){
    const value=payload as {detail?:unknown;message?:unknown};
    if(typeof value.detail==="string")return value.detail;
    if(value.detail&&typeof value.detail==="object")return JSON.stringify(value.detail);
    if(typeof value.message==="string")return value.message;
  }
  if(typeof payload==="string"&&payload.trim())return payload.trim();
  return `API error ${status}`;
}

export async function createSubscriptionFastV1(payload:FastSubscriptionCreatePayload):Promise<FastSubscriptionCreateResult>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");

  const response=await fetch(`${API_BASE}/v1/subscriptions/admin-create-fast-v1`,{
    method:"POST",
    cache:"no-store",
    headers:{
      Authorization:`Bearer ${token}`,
      "Content-Type":"application/json",
    },
    body:JSON.stringify(payload),
  });

  const raw=await response.text();
  let body:unknown=null;
  if(raw){
    try{body=JSON.parse(raw);}catch{body=raw;}
  }
  if(!response.ok)throw new Error(errorText(body,response.status));
  return body as FastSubscriptionCreateResult;
}
