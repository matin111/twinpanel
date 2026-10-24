"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type PlanProtocolDefinition={
  key:string;
  title:string;
  family:"classic"|"modern";
};

export type PlanProtocolCatalogResponse={
  protocols:PlanProtocolDefinition[];
};

export type PlanProtocolsResponse={
  plan_id:number;
  protocols:string[];
};

function errorText(payload:unknown,status:number){
  if(payload&&typeof payload==="object"){
    const item=payload as {detail?:unknown;message?:unknown};
    if(typeof item.detail==="string")return item.detail;
    if(typeof item.message==="string")return item.message;
    if(Array.isArray(item.detail)){
      return item.detail
        .map(value=>typeof value==="object"&&value&&"msg" in value?String((value as {msg:unknown}).msg):String(value))
        .join("، ");
    }
  }
  if(typeof payload==="string"&&payload.trim())return payload.trim();
  return `API error ${status}`;
}

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");

  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");

  const response=await fetch(`${API_BASE}${path}`,{
    ...init,
    headers,
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

export const planProtocolApi={
  catalog:()=>request<PlanProtocolCatalogResponse>("/v1/plans/protocol-catalog"),
  get:(planId:number)=>request<PlanProtocolsResponse>(`/v1/plans/${planId}/protocols`),
  set:(planId:number,protocols:string[])=>request<PlanProtocolsResponse>(`/v1/plans/${planId}/protocols`,{
    method:"PUT",
    body:JSON.stringify({protocols}),
  }),
};
