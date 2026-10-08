"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type L2tpExitNode={id:number;name:string};
export type L2tpSettings={
  psk:string;
  length:number;
  exit_count:number;
  exit_nodes:L2tpExitNode[];
};

function errorText(payload:unknown,status:number){
  if(typeof payload==="string"&&payload.trim())return payload.trim();
  if(payload&&typeof payload==="object"){
    const row=payload as {detail?:unknown;message?:unknown};
    if(typeof row.detail==="string")return row.detail;
    if(typeof row.message==="string")return row.message;
    if(row.detail&&typeof row.detail==="object"){
      const detail=row.detail as {message?:unknown};
      if(typeof detail.message==="string")return detail.message;
    }
    if(Array.isArray(row.detail))return row.detail.map(item=>typeof item==="object"&&item&&"msg" in item?String((item as {msg:unknown}).msg):String(item)).join("، ");
  }
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

export const l2tpApi={
  settings:()=>request<L2tpSettings>("/v1/settings/vpn/l2tp"),
  generate:()=>request<{psk:string;length:number}>("/v1/settings/vpn/l2tp/generate",{method:"POST"}),
  update:(psk:string)=>request<{ok:boolean;changed:boolean;length?:number;synced_nodes?:L2tpExitNode[]}>("/v1/settings/vpn/l2tp",{
    method:"PUT",
    body:JSON.stringify({psk}),
  }),
};
