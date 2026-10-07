"use client";

import {API_BASE} from "./api";

export type ResellerProfile={
  id:number;
  code?:string|null;
  name?:string|null;
  is_active?:boolean;
  [key:string]:unknown;
};

async function errorText(response:Response){
  try{
    const payload=await response.json() as {detail?:unknown;message?:unknown};
    if(typeof payload.detail==="string")return payload.detail;
    if(typeof payload.message==="string")return payload.message;
  }catch{}
  return `API error ${response.status}`;
}

export async function getResellerProfile(token:string):Promise<ResellerProfile|null>{
  const response=await fetch(`${API_BASE}/v1/reseller/me`,{
    headers:{Authorization:`Bearer ${token}`},
    cache:"no-store"
  });
  if(response.ok)return response.json() as Promise<ResellerProfile>;
  if([400,401,403,404].includes(response.status))return null;
  throw new Error(await errorText(response));
}

export async function resolvePortal(token:string,role:string|null|undefined):Promise<"admin"|"reseller"|"customer">{
  if(String(role||"").toLowerCase()==="admin")return "admin";
  const reseller=await getResellerProfile(token);
  return reseller?"reseller":"customer";
}
