"use client";

import type {CustomerUser} from "./customer-api";

export type PortalAccess="admin"|"reseller"|"customer";

type AccessCacheRow={portal:PortalAccess;user?:CustomerUser|null;expires_at:number};

const ACCESS_TTL_MS=60*60*1000;

function tokenHash(token:string){
  let hash=2166136261;
  for(let index=0;index<token.length;index+=1){hash^=token.charCodeAt(index);hash=Math.imul(hash,16777619);}
  return (hash>>>0).toString(36);
}
function storageKey(token:string){return `twinpanel.access.${tokenHash(token)}`;}
function parse(raw:string|null):AccessCacheRow|null{
  if(!raw)return null;
  try{const row=JSON.parse(raw) as AccessCacheRow;if(!row?.portal||Number(row.expires_at||0)<=Date.now())return null;return row;}catch{return null;}
}

export function readPortalAccess(token:string):AccessCacheRow|null{
  if(typeof window==="undefined")return null;
  const key=storageKey(token);
  try{const session=parse(sessionStorage.getItem(key));if(session)return session;}catch{}
  try{
    const local=parse(localStorage.getItem(key));
    if(local){try{sessionStorage.setItem(key,JSON.stringify(local));}catch{}return local;}
    localStorage.removeItem(key);
  }catch{}
  return null;
}

export function writePortalAccess(token:string,portal:PortalAccess,user?:CustomerUser|null){
  if(typeof window==="undefined")return;
  const previous=readPortalAccess(token);
  const row:AccessCacheRow={portal,user:user===undefined?(previous?.user??null):user,expires_at:Date.now()+ACCESS_TTL_MS};
  const raw=JSON.stringify(row);const key=storageKey(token);
  try{sessionStorage.setItem(key,raw);}catch{}
  try{localStorage.setItem(key,raw);}catch{}
}

export function clearPortalAccess(token?:string|null){
  if(typeof window==="undefined")return;
  const remove=(storage:Storage)=>{
    try{
      if(token){storage.removeItem(storageKey(token));return;}
      const keys:string[]=[];for(let index=0;index<storage.length;index+=1){const key=storage.key(index);if(key?.startsWith("twinpanel.access."))keys.push(key);}keys.forEach(key=>storage.removeItem(key));
    }catch{}
  };
  remove(sessionStorage);remove(localStorage);
}
