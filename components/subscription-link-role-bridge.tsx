"use client";

import {useEffect,useRef,useState} from "react";
import {usePathname} from "next/navigation";
import {SubscriptionLinkDeliveryModal} from "./subscription-link-delivery-modal";
import {adminApi} from "../lib/admin-api";
import {resellerApi} from "../lib/reseller-runtime-api";

type BridgeRole="admin"|"reseller"|null;
type RuntimeRow=Record<string,unknown>;

function roleForPath(pathname:string):BridgeRole{
  if(pathname==="/admin/subscriptions")return "admin";
  if(pathname==="/reseller/subscriptions")return "reseller";
  return null;
}

function isSubLinkButton(button:HTMLButtonElement){
  const label=(button.textContent||"").replace(/\s+/g," ").trim().toLowerCase();
  return label==="سابلینک"||label==="sub-link"||label==="sublink"||label==="subscription link";
}

function subscriptionIdFromRow(row:HTMLTableRowElement,role:Exclude<BridgeRole,null>){
  const rowText=row.textContent||"";

  if(role==="admin"){
    const match=rowText.match(/\bMV\s*-\s*(\d+)\b/i);
    if(match)return Number(match[1]);
  }

  const firstCell=row.querySelector("td");
  const firstCellMatch=(firstCell?.textContent||"").match(/#\s*(\d+)/);
  if(firstCellMatch)return Number(firstCellMatch[1]);

  const fallback=rowText.match(/#\s*(\d+)/);
  return fallback?Number(fallback[1]):0;
}

function publicLinkFrom(value:RuntimeRow){
  const link=value.subscription_link;
  return typeof link==="string"?link:"";
}

export function SubscriptionLinkRoleBridge(){
  const pathname=usePathname();
  const role=roleForPath(pathname);
  const requestSerial=useRef(0);
  const [open,setOpen]=useState(false);
  const [loading,setLoading]=useState(false);
  const [link,setLink]=useState("");
  const [reference,setReference]=useState("");
  const [error,setError]=useState("");

  useEffect(()=>{
    requestSerial.current+=1;
    setOpen(false);
    setLoading(false);
    setLink("");
    setReference("");
    setError("");
  },[pathname]);

  useEffect(()=>{
    if(!role)return;

    const onClick=(event:MouseEvent)=>{
      const target=event.target;
      if(!(target instanceof Element))return;

      const button=target.closest("button");
      if(!(button instanceof HTMLButtonElement)||!isSubLinkButton(button))return;

      const row=button.closest("tr");
      if(!(row instanceof HTMLTableRowElement))return;

      const subscriptionId=subscriptionIdFromRow(row,role);
      if(!subscriptionId)return;

      // Capture before the legacy React onClick runs. Admin, reseller and
      // customer must all render the exact same SubscriptionLinkDeliveryModal.
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();

      const serial=++requestSerial.current;
      setOpen(true);
      setLoading(true);
      setLink("");
      setReference(`MV-${subscriptionId}`);
      setError("");

      void (async()=>{
        try{
          const data=role==="admin"
            ?await adminApi.subscriptionConnectionInfo(subscriptionId)
            :await resellerApi.connectionInfo(subscriptionId);

          if(requestSerial.current!==serial)return;
          setLink(publicLinkFrom(data as RuntimeRow));
        }catch(reason){
          if(requestSerial.current!==serial)return;
          setError(reason instanceof Error?reason.message:String(reason));
        }finally{
          if(requestSerial.current===serial)setLoading(false);
        }
      })();
    };

    document.addEventListener("click",onClick,true);
    return()=>document.removeEventListener("click",onClick,true);
  },[role]);

  const close=()=>{
    requestSerial.current+=1;
    setOpen(false);
    setLoading(false);
    setLink("");
    setError("");
  };

  return <SubscriptionLinkDeliveryModal
    open={open}
    link={link}
    reference={reference}
    loading={loading}
    error={error}
    onClose={close}
  />;
}
