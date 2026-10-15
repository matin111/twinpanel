"use client";

import {usePathname} from "next/navigation";
import {useEffect,useMemo,useState} from "react";
import {getCustomerToken} from "../lib/customer-api";
import {SupportChatWidgetV2} from "./support-chat-widget-v2";

export function SupportChatRuntime(){
  const pathname=usePathname();
  const [token,setToken]=useState<string|null|undefined>(undefined);

  useEffect(()=>{
    setToken(getCustomerToken());
    const sync=()=>setToken(getCustomerToken());
    window.addEventListener("storage",sync);
    window.addEventListener("focus",sync);
    return()=>{
      window.removeEventListener("storage",sync);
      window.removeEventListener("focus",sync);
    };
  },[]);

  const mode=useMemo<"guest"|"account"|null>(()=>{
    const path=(pathname||"/").replace(/\/$/,"")||"/";
    if(path==="/"||path==="/store")return "guest";
    if(path==="/panel"||path.startsWith("/panel/"))return "account";
    return null;
  },[pathname]);

  if(!mode)return null;
  if(token===undefined)return null;
  if(mode==="account"&&!token)return null;

  return <SupportChatWidgetV2 key={mode} mode={mode} customerToken={mode==="account"?token:null}/>;
}
