"use client";

import {API_BASE,api} from "./api";
import {getCustomerToken} from "./customer-api";

export type BrandingApiRecord={
  id?:number;
  brand_name:string;
  logo_url?:string|null;
  favicon_url?:string|null;
  primary_color:string;
  secondary_color:string;
  site_title?:string|null;
  site_description?:string|null;
  footer_text?:string|null;
  telegram_url?:string|null;
  updated_at?:string|null;
};

export type BrandingSavePayload={
  brand_name:string;
  primary_color:string;
  secondary_color:string;
};

export type BrandingAssetKind="logo"|"favicon";

function endpoint(path=""){
  return `${API_BASE}${api.settings.branding}${path}`;
}

function errorText(payload:unknown,status:number){
  if(payload&&typeof payload==="object"){
    const value=payload as {detail?:unknown;message?:unknown};
    if(typeof value.detail==="string")return value.detail;
    if(typeof value.message==="string")return value.message;
    if(Array.isArray(value.detail))return value.detail.map(item=>typeof item==="object"&&item&&"msg" in item?String((item as {msg:unknown}).msg):String(item)).join("، ");
  }
  return `API error ${status}`;
}

async function request<T>(path="",init:RequestInit={},authenticated=false):Promise<T>{
  const headers=new Headers(init.headers);
  if(authenticated){
    const token=getCustomerToken();
    if(!token)throw new Error("AUTH_REQUIRED");
    headers.set("Authorization",`Bearer ${token}`);
  }
  if(init.body&&!headers.has("Content-Type")&&!(init.body instanceof FormData))headers.set("Content-Type","application/json");

  const response=await fetch(endpoint(path),{...init,headers,cache:"no-store"});
  if(!response.ok){
    let payload:unknown=null;
    try{payload=await response.json();}catch{}
    throw new Error(errorText(payload,response.status));
  }
  return response.json() as Promise<T>;
}

export function resolveBrandingAssetUrl(value:string|null|undefined){
  const raw=String(value||"").trim();
  if(!raw)return "";
  if(/^https?:\/\//i.test(raw)||raw.startsWith("data:"))return raw;
  if(raw.startsWith("/v1/")&&API_BASE)return `${API_BASE}${raw}`;
  return raw;
}

export const brandingApi={
  get:()=>request<BrandingApiRecord>(),
  save:(payload:BrandingSavePayload)=>request<BrandingApiRecord>("",{method:"PUT",body:JSON.stringify(payload)},true),
  uploadAsset:(kind:BrandingAssetKind,file:File)=>{
    const form=new FormData();
    form.set("file",file);
    return request<BrandingApiRecord>(`/assets/${kind}`,{method:"POST",body:form},true);
  },
  deleteAsset:(kind:BrandingAssetKind)=>request<BrandingApiRecord>(`/assets/${kind}`,{method:"DELETE"},true),
};
