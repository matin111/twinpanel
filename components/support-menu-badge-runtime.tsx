"use client";

import {useEffect,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";

type TicketRow={status?:string|null};

function ticketRows(value:unknown):TicketRow[]{
  if(Array.isArray(value))return value.filter(Boolean) as TicketRow[];
  if(value&&typeof value==="object"){
    const root=value as Record<string,unknown>;
    for(const key of ["tickets","items","results"]){
      if(Array.isArray(root[key]))return (root[key] as unknown[]).filter(Boolean) as TicketRow[];
    }
  }
  return [];
}

async function loadOpenSupportCount():Promise<number>{
  const token=getCustomerToken();
  if(!token)return 0;

  const response=await fetch(`${API_BASE}/v1/admin/support/tickets?status=open`,{
    headers:{Authorization:`Bearer ${token}`},
    cache:"no-store",
  });

  if(!response.ok)return 0;

  const payload=await response.json() as unknown;
  return ticketRows(payload).filter(row=>String(row.status||"").toLowerCase()==="open").length;
}

function supportLinks():HTMLAnchorElement[]{
  return Array.from(document.querySelectorAll<HTMLAnchorElement>('a[href="/admin/support"]'));
}

export function SupportMenuBadgeRuntime(){
  const [count,setCount]=useState(0);

  useEffect(()=>{
    if(!window.location.pathname.startsWith("/admin"))return;

    let cancelled=false;
    let timer=0;

    const refresh=async()=>{
      if(document.hidden)return;
      try{
        const next=await loadOpenSupportCount();
        if(!cancelled)setCount(next);
      }catch{
        if(!cancelled)setCount(0);
      }
    };

    const onVisibility=()=>{if(!document.hidden)void refresh();};

    void refresh();
    timer=window.setInterval(()=>void refresh(),30000);
    document.addEventListener("visibilitychange",onVisibility);

    return()=>{
      cancelled=true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange",onVisibility);
    };
  },[]);

  useEffect(()=>{
    const apply=()=>{
      for(const link of supportLinks()){
        if(count>0){
          link.classList.add("supportMenuNeedsReplyV1");
          link.dataset.supportCount=count>99?"99+":String(count);
        }else{
          link.classList.remove("supportMenuNeedsReplyV1");
          delete link.dataset.supportCount;
        }
      }
    };

    apply();
    const observer=new MutationObserver(apply);
    observer.observe(document.body,{subtree:true,childList:true});

    return()=>observer.disconnect();
  },[count]);

  return null;
}
