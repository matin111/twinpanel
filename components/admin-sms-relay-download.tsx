"use client";

import {useEffect,useState} from "react";
import {createPortal} from "react-dom";
import {useI18n} from "../lib/i18n";

const SMS_RELAY_URL="https://github.com/automagen-ab/sms-relay/releases/latest";

export function AdminSmsRelayDownload(){
  const {pick}=useI18n();
  const [host,setHost]=useState<Element|null>(null);

  useEffect(()=>{
    const find=()=>setHost(document.querySelector(".page-head"));
    find();
    const observer=new MutationObserver(find);
    observer.observe(document.body,{childList:true,subtree:true});
    return()=>observer.disconnect();
  },[]);

  if(!host)return null;

  return createPortal(
    <a
      className="ghost button-link"
      href={SMS_RELAY_URL}
      target="_blank"
      rel="noopener noreferrer"
      title={pick("دانلود آخرین نسخه رسمی Automagen SMS Relay","Download the latest official Automagen SMS Relay")}
    >
      ↓ {pick("دانلود SMS Relay","Download SMS Relay")}
    </a>,
    host
  );
}
