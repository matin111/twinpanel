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

// Import large encrypted backups in bounded chunks. Never place a 600+ MB
// archive in one Cloudflare request or in a single browser ArrayBuffer.
export async function uploadBackup(file:File,onProgress?:(percent:number)=>void){
  const token=auth();
  const headers={Authorization:`Bearer ${token}`};
  const prefix=`${API_BASE}/v1/admin/backups/upload-session`;
  const init=await fetch(prefix,{
    method:"POST",headers:{...headers,"Content-Type":"application/json"},
    body:JSON.stringify({filename:file.name,size_bytes:file.size,sha256:""}),
    cache:"no-store",
  });
  if(!init.ok)throw new Error(await errorText(init));
  const setup=await init.json() as {id:string;chunk_bytes:number;uploaded_bytes:number};
  if(!/^[0-9a-f]{32}$/.test(setup.id))throw new Error("INVALID_UPLOAD_SESSION");
  const chunk=Math.min(Number(setup.chunk_bytes)||8*1024*1024,8*1024*1024);
  let offset=Number(setup.uploaded_bytes)||0;
  let attempts=0;
  while(offset<file.size){
    const next=Math.min(offset+chunk,file.size);
    const part=new FormData();
    part.append("file",file.slice(offset,next),"backup-part.bin");
    try{
      const response=await fetch(`${prefix}/${setup.id}/chunk?offset=${offset}`,{
        method:"POST",headers,body:part,cache:"no-store",
      });
      if(!response.ok)throw new Error(await errorText(response));
      const data=await response.json() as {uploaded_bytes:number};
      if(data.uploaded_bytes<=offset||data.uploaded_bytes>file.size)throw new Error("UPLOAD_PROGRESS_INVALID");
      offset=data.uploaded_bytes;attempts=0;
      onProgress?.(Math.min(95,Math.round(offset/file.size*95)));
    }catch(error){
      if(++attempts>3)throw error;
      const status=await fetch(`${prefix}/${setup.id}`,{headers,cache:"no-store"});
      if(!status.ok)throw error;
      const data=await status.json() as {session:{uploaded_bytes:number}};
      offset=Math.min(file.size,Math.max(0,Number(data.session.uploaded_bytes)||0));
      await new Promise<void>(resolve=>setTimeout(resolve,700*attempts));
    }
  }
  const finish=await fetch(`${prefix}/${setup.id}/finish`,{method:"POST",headers,cache:"no-store"});
  if(!finish.ok)throw new Error(await errorText(finish));
  onProgress?.(96);
  for(let i=0;i<360;i+=1){
    const response=await fetch(`${prefix}/${setup.id}`,{headers,cache:"no-store"});
    if(!response.ok)throw new Error(await errorText(response));
    const data=await response.json() as {session:{state:string;imported_filename?:string;error_code?:string}};
    if(data.session.state==="imported"){
      onProgress?.(100);
      return {ok:true,filename:data.session.imported_filename};
    }
    if(data.session.state==="failed")throw new Error(data.session.error_code||"BACKUP_IMPORT_FAILED");
    await new Promise<void>(resolve=>setTimeout(resolve,5000));
  }
  throw new Error("BACKUP_IMPORT_STILL_PROCESSING");
}

export type TelegramPartsSession={
  id:string;filename:string;total_parts:number;received_parts:number[];
  received_count:number;state:string;size_bytes:number;
  imported_filename?:string;error_code?:string;
};

const partsPrefix=`${API_BASE}/v1/admin/backups/telegram-parts`;
function telegramPartName(name:string){
  const match=name.match(/^([a-zA-Z0-9][a-zA-Z0-9._-]{0,163}\\.tpbak)\\.part(\\d{3})of(\\d{3})$/);
  if(!match)throw new Error("BACKUP_PART_FILENAME_INVALID");
  const number=Number(match[2]),total=Number(match[3]);
  if(number<1||total>75||number>total)throw new Error("BACKUP_PART_NUMBER_INVALID");
  return {filename:match[1],number,total};
}
export async function initTelegramParts(file:File,sha256=""):Promise<TelegramPartsSession>{
  telegramPartName(file.name);
  const response=await fetch(partsPrefix,{
    method:"POST",headers:{Authorization:`Bearer ${auth()}`,"Content-Type":"application/json"},
    body:JSON.stringify({part_filename:file.name,sha256:sha256.trim()}),
    cache:"no-store",
  });
  if(!response.ok)throw new Error(await errorText(response));
  return (await response.json() as {session:TelegramPartsSession}).session;
}
export async function getTelegramPartsStatus(id:string):Promise<TelegramPartsSession>{
  if(!/^[0-9a-f]{32}$/.test(id))throw new Error("BACKUP_PART_SESSION_ID_INVALID");
  const response=await fetch(`${partsPrefix}/${id}`,{
    headers:{Authorization:`Bearer ${auth()}`},cache:"no-store",
  });
  if(!response.ok)throw new Error(await errorText(response));
  return (await response.json() as {session:TelegramPartsSession}).session;
}
export async function uploadTelegramPart(id:string,file:File):Promise<TelegramPartsSession>{
  const info=telegramPartName(file.name);
  const current=await getTelegramPartsStatus(id);
  if(current.filename!==info.filename||current.total_parts!==info.total){
    throw new Error("BACKUP_PART_SET_MISMATCH");
  }
  if(file.size<=0||file.size>40*1024*1024)throw new Error("BACKUP_PART_TOO_LARGE");
  const form=new FormData();
  form.append("file",file,file.name);
  const response=await fetch(`${partsPrefix}/${id}/part`,{
    method:"POST",headers:{Authorization:`Bearer ${auth()}`},body:form,cache:"no-store",
  });
  if(!response.ok)throw new Error(await errorText(response));
  return (await response.json() as {session:TelegramPartsSession}).session;
}
export async function discardTelegramParts(id:string):Promise<void>{
  if(!/^[0-9a-f]{32}$/.test(id))throw new Error("BACKUP_PART_SESSION_ID_INVALID");
  const response=await fetch(`${partsPrefix}/${id}`,{
    method:"DELETE",headers:{Authorization:`Bearer ${auth()}`},cache:"no-store",
  });
  if(!response.ok)throw new Error(await errorText(response));
}
export async function finishTelegramParts(id:string):Promise<TelegramPartsSession>{
  const response=await fetch(`${partsPrefix}/${id}/finish`,{
    method:"POST",headers:{Authorization:`Bearer ${auth()}`},cache:"no-store",
  });
  if(!response.ok)throw new Error(await errorText(response));
  return (await response.json() as {session:TelegramPartsSession}).session;
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
