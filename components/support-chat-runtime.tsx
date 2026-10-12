"use client";

import {useEffect,useState} from "react";
import {getCustomerToken} from "../lib/customer-api";
import {SupportChatWidget} from "./support-chat-widget";

export function SupportChatRuntime(){
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

  if(token===undefined)return null;
  return <SupportChatWidget customerToken={token}/>;
}
