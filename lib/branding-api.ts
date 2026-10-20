"use client";

import {getCustomerToken} from "./customer-api";

export type BrandingRecord={
  id?:number;
  brand_name?:string|null;
  logo_url?:string|null;
  favicon_url?:string|null;
  primary_color?:string|null;
  secondary_color?:string|null;
  site_title?:string|null;
  site_description?:string|null;
  footer_text?:string|null;
  telegram_url?:string|null;
  updated_at?:string|null;
};

export type BrandingSavePayload={
  brand_name?:string;
  primary_color?:string;
  secondary_color?:string;
  site_title?:string;
};

export type BrandingAssetKind="logo"|"favicon";

function errorText(payload:unknown,status:number){
  if(payload&&typeof payload==="object"){
    const detail=(payload as {detail?:unknown}).detail;
    if(typeof detail==="string")return detail;
    if(detail&&typeof detail==="object")return JSON.stringify(detail);
  }
  return `API error ${status}`;
}

async function request<T>(path:string,options:RequestInit={},admin=false):Promise<T>{
  const headers=new Headers(options.headers);
  const token=admin?getCustomerToken():null;
  if(admin&&!token)throw new Error("admin_auth_required");
  if(token)headers.set("Authorization",`Bearer ${token}`);
  if(options.body&&!(options.body instanceof FormData)&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");

  const response=await fetch(path,{...options,headers,cache:"no-store"});
  if(!response.ok){
    let payload:unknown=null;
    try{payload=await response.json();}catch{}
    throw new Error(errorText(payload,response.status));
  }
  return response.json() as Promise<T>;
}

export const brandingApi={
  get:()=>request<BrandingRecord>("/v1/settings/branding"),
  save:(payload:BrandingSavePayload)=>request<BrandingRecord>("/v1/settings/branding",{
    method:"PUT",
    body:JSON.stringify(payload),
  },true),
  uploadAsset:(kind:BrandingAssetKind,file:File)=>{
    const body=new FormData();
    body.append("file",file);
    return request<BrandingRecord>(`/v1/settings/branding/assets/${kind}`,{method:"POST",body},true);
  },
  deleteAsset:(kind:BrandingAssetKind)=>request<BrandingRecord>(`/v1/settings/branding/assets/${kind}`,{method:"DELETE"},true),
};
