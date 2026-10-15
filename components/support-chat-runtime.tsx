"use client";

import {usePathname} from "next/navigation";
import {useEffect,useMemo,useState} from "react";
import {getCustomerToken} from "../lib/customer-api";
import {SupportAccountChatWidget} from "./support-account-chat-widget";
import {SupportGuestChatWidgetV3} from "./support-guest-chat-widget-v3";

function migrateLegacyGuestChat(){
  try{
    const pairs=[
      ["twinpanel_guest_chat_v2","twinpanel_guest_chat_v3"],
      ["twinpanel_guest_chat_ticket_v2","twinpanel_guest_chat_ticket_v3"],
      ["twinpanel_guest_chat_open_v2","twinpanel_guest_chat_open_v3"],
    ] as const;
    for(const [oldKey,newKey] of pairs){
      if(localStorage.getItem(newKey)!==null)continue;
      const value=localStorage.getItem(oldKey);
      if(value!==null)localStorage.setItem(newKey,value);
    }
  }catch{}

  try{
    if(sessionStorage.getItem("twinpanel_guest_chat_session_v3")===null){
      const value=sessionStorage.getItem("twinpanel_guest_chat_session_v2");
      if(value!==null)sessionStorage.setItem("twinpanel_guest_chat_session_v3",value);
    }
  }catch{}

  try{
    const hasNew=document.cookie.split(";").some(row=>row.trim().startsWith("twinpanel_guest_chat_v3="));
    if(!hasNew){
      const old=document.cookie.split(";").map(row=>row.trim()).find(row=>row.startsWith("twinpanel_guest_chat="));
      if(old){
        const value=old.slice("twinpanel_guest_chat=".length);
        document.cookie=`twinpanel_guest_chat_v3=${value}; Max-Age=31536000; Path=/; SameSite=Lax`;
      }
    }
  }catch{}
}

export function SupportChatRuntime(){
  const pathname=usePathname();
  const [token,setToken]=useState<string|null|undefined>(undefined);

  useEffect(()=>{
    const path=(pathname||"/").replace(/\/$/,"")||"/";
    if(path==="/"||path==="/store")migrateLegacyGuestChat();

    setToken(getCustomerToken());
    const sync=()=>setToken(getCustomerToken());
    window.addEventListener("storage",sync);
    window.addEventListener("focus",sync);
    return()=>{
      window.removeEventListener("storage",sync);
      window.removeEventListener("focus",sync);
    };
  },[pathname]);

  const mode=useMemo<"guest"|"account"|null>(()=>{
    const path=(pathname||"/").replace(/\/$/,"")||"/";
    if(path==="/"||path==="/store")return "guest";
    if(path==="/panel"||path.startsWith("/panel/"))return "account";
    return null;
  },[pathname]);

  if(!mode||token===undefined)return null;
  if(mode==="guest")return <SupportGuestChatWidgetV3 key="store-guest-chat-v3"/>;
  if(!token)return null;
  return <SupportAccountChatWidget key="customer-account-chat" customerToken={token}/>;
}
