"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

function auth(){
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  return token;
}

async function errorText(response:Response){
  try{
    const body=await response.json() as {detail?:unknown;message?:unknown};
    if(typeof body.detail==="string")return body.detail;
    if(typeof body.message==="string")return body.message;
  }catch{}
  return `API error ${response.status}`;
}

export async function uploadBackup(file:File){
  const data=new FormData();data.append("file",file,file.name);
  const response=await fetch(`${API_BASE}/v1/admin/backups/upload`,{method:"POST",headers:{Authorization:`Bearer ${auth()}`},body:data,cache:"no-store"});
  if(!response.ok)throw new Error(await errorText(response));
  return response.json() as Promise<Record<string,unknown>>;
}

export async function downloadBackupFile(filename:string){
  return downloadAuthenticated(`/v1/admin/backups/${encodeURIComponent(filename)}/download`,filename);
}

export async function downloadRecoveryKey(){
  return downloadAuthenticated("/v1/admin/backups/recovery-key","twinpanel-backup-recovery.key");
}

async function downloadAuthenticated(path:string,fallbackName:string){
  const response=await fetch(`${API_BASE}${path}`,{headers:{Authorization:`Bearer ${auth()}`},cache:"no-store"});
  if(!response.ok)throw new Error(await errorText(response));
  const blob=await response.blob();
  const disposition=response.headers.get("content-disposition")||"";
  const match=disposition.match(/filename\*?=(?:UTF-8''|\")?([^\";]+)/i);
  const name=match?decodeURIComponent(match[1].replace(/^"|"$/g,"")):fallbackName;
  const url=URL.createObjectURL(blob);
  const anchor=document.createElement("a");anchor.href=url;anchor.download=name;document.body.appendChild(anchor);anchor.click();anchor.remove();
  window.setTimeout(()=>URL.revokeObjectURL(url),1000);
}
