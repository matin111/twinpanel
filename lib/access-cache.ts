"use client";

import type {CustomerUser} from "./customer-api";

export type PortalAccess="admin"|"reseller"|"customer";

type AccessCacheRow={
  portal:PortalAccess;
  user?:CustomerUser|null;
  expires_at:number;
};

const ACCESS_TTL_MS=10*60*1000;

function tokenHash(token:string){
  let hash=2166136261;
  for(let index=0;index<token.length;index+=1){
    hash^=token.charCodeAt(index);
    hash=Math.imul(hash,16777619);
  }
  return (hash>>>0).toString(36);
}

function storageKey(token:string){
  return `twinpanel.access.${tokenHash(token)}`;
}

export function readPortalAccess(token:string):AccessCacheRow|null{
  if(typeof window==="undefined")return null;
  try{
    const raw=sessionStorage.getItem(storageKey(token));
    if(!raw)return null;
    const parsed=JSON.parse(raw) as AccessCacheRow;
    if(!parsed?.portal||Number(parsed.expires_at||0)<=Date.now()){
      sessionStorage.removeItem(storageKey(token));
      return null;
    }
    return parsed;
  }catch{
    return null;
  }
}

export function writePortalAccess(token:string,portal:PortalAccess,user?:CustomerUser|null){
  if(typeof window==="undefined")return;
  try{
    const previous=readPortalAccess(token);
    const row:AccessCacheRow={
      portal,
      user:user===undefined?(previous?.user??null):user,
      expires_at:Date.now()+ACCESS_TTL_MS
    };
    sessionStorage.setItem(storageKey(token),JSON.stringify(row));
  }catch{}
}

export function clearPortalAccess(token?:string|null){
  if(typeof window==="undefined")return;
  try{
    if(token){sessionStorage.removeItem(storageKey(token));return;}
    const keys:string[]=[];
    for(let index=0;index<sessionStorage.length;index+=1){
      const key=sessionStorage.key(index);
      if(key?.startsWith("twinpanel.access."))keys.push(key);
    }
    keys.forEach(key=>sessionStorage.removeItem(key));
  }catch{}
}
