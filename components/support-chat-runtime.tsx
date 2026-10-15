"use client";

import {usePathname} from "next/navigation";
import {useEffect,useMemo,useState} from "react";
import {getCustomerToken} from "../lib/customer-api";
import {SupportAccountChatWidget} from "./support-account-chat-widget";
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

  if(!mode||token===undefined)return null;
  if(mode==="guest")return <SupportChatWidgetV2 key="store-guest-chat" customerToken={null}/>;
  if(!token)return null;
  return <SupportAccountChatWidget key="customer-account-chat" customerToken={token}/>;
}
