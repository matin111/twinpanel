"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type StoreTemplateSettingsEnvelope={
  templates:Record<string,Record<string,unknown>>;
  updated_at?:string|null;
};

export type StoreTemplateMediaUpload={
  template_id:string;
  slot:string;
  url:string;
};

async function parseResponse<T>(response:Response):Promise<T>{
  if(response.ok)return response.json() as Promise<T>;
  let detail=`API error ${response.status}`;
  try{
    const payload=await response.json() as {detail?:unknown;message?:unknown};
    if(typeof payload.detail==="string")detail=payload.detail;
    else if(typeof payload.message==="string")detail=payload.message;
  }catch{}
  throw new Error(detail);
}

export async function loadStoreTemplateSettings():Promise<StoreTemplateSettingsEnvelope>{
  const response=await fetch(`${API_BASE}/v1/storefront/settings/templates`,{cache:"no-store"});
  return parseResponse<StoreTemplateSettingsEnvelope>(response);
}

export async function saveStoreTemplateSettings(templateId:string,payload:Record<string,unknown>):Promise<Record<string,unknown>>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const response=await fetch(`${API_BASE}/v1/storefront/settings/templates/${encodeURIComponent(templateId)}`,{
    method:"PUT",
    headers:{
      "Authorization":`Bearer ${token}`,
      "Content-Type":"application/json",
    },
    body:JSON.stringify(payload),
    cache:"no-store",
  });
  return parseResponse<Record<string,unknown>>(response);
}

export async function resetStoreTemplateSettings(templateId:string):Promise<Record<string,unknown>>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const response=await fetch(`${API_BASE}/v1/storefront/settings/templates/${encodeURIComponent(templateId)}`,{
    method:"DELETE",
    headers:{"Authorization":`Bearer ${token}`},
    cache:"no-store",
  });
  return parseResponse<Record<string,unknown>>(response);
}

export async function uploadStoreTemplateMedia(templateId:string,slot:string,file:File):Promise<StoreTemplateMediaUpload>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const body=new FormData();
  body.append("file",file);
  const response=await fetch(`${API_BASE}/v1/storefront/settings/media/${encodeURIComponent(templateId)}/${encodeURIComponent(slot)}`,{
    method:"POST",
    headers:{"Authorization":`Bearer ${token}`},
    body,
    cache:"no-store",
  });
  return parseResponse<StoreTemplateMediaUpload>(response);
}

export async function deleteStoreTemplateMedia(templateId:string,slot:string):Promise<Record<string,unknown>>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const response=await fetch(`${API_BASE}/v1/storefront/settings/media/${encodeURIComponent(templateId)}/${encodeURIComponent(slot)}`,{
    method:"DELETE",
    headers:{"Authorization":`Bearer ${token}`},
    cache:"no-store",
  });
  return parseResponse<Record<string,unknown>>(response);
}
