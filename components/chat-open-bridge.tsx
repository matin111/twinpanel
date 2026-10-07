"use client";

import {useEffect} from "react";

export function ChatOpenBridge(){
  useEffect(()=>{
    const openChat=()=>{
      const launcher=document.querySelector<HTMLButtonElement>(".supportChatLauncher");
      if(launcher&&!launcher.classList.contains("active")) launcher.click();
    };
    window.addEventListener("twinpanel:open-chat",openChat);
    return()=>window.removeEventListener("twinpanel:open-chat",openChat);
  },[]);

  return null;
}
