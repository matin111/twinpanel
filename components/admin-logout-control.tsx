"use client";

import {useEffect,useState} from "react";
import {createPortal} from "react-dom";
import {clearPortalAccess} from "../lib/access-cache";
import {clearCustomerToken,getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

export function AdminLogoutControl(){
  const {pick}=useI18n();
  const [target,setTarget]=useState<HTMLElement|null>(null);

  useEffect(()=>{
    const findTarget=()=>{
      const node=document.querySelector<HTMLElement>(".admin-shell .admin-commandbar .head-actions");
      setTarget(current=>current===node?current:node);
      return Boolean(node);
    };

    findTarget();
    const observer=new MutationObserver(()=>{findTarget();});
    observer.observe(document.body,{childList:true,subtree:true});
    return()=>observer.disconnect();
  },[]);

  if(!target)return null;

  const logout=()=>{
    const token=getCustomerToken();
    clearPortalAccess(token);
    clearCustomerToken();
    window.location.replace("/login");
  };

  return createPortal(
    <button
      type="button"
      onClick={logout}
      aria-label={pick("خروج از پنل","Log out of admin panel")}
      title={pick("خروج از پنل","Log out")}
      style={{
        width:38,
        height:38,
        padding:0,
        display:"inline-grid",
        placeItems:"center",
        flex:"0 0 38px",
        border:"1px solid var(--line)",
        borderRadius:12,
        background:"var(--surface)",
        color:"var(--muted)",
        cursor:"pointer",
        transition:"border-color .16s ease,background .16s ease,color .16s ease,transform .16s ease"
      }}
      onMouseEnter={event=>{
        event.currentTarget.style.borderColor="color-mix(in srgb,var(--bad,#ef4444) 38%,var(--line))";
        event.currentTarget.style.background="color-mix(in srgb,var(--bad,#ef4444) 7%,var(--surface))";
        event.currentTarget.style.color="var(--bad,#ef4444)";
      }}
      onMouseLeave={event=>{
        event.currentTarget.style.borderColor="var(--line)";
        event.currentTarget.style.background="var(--surface)";
        event.currentTarget.style.color="var(--muted)";
      }}
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M10 17l5-5-5-5"/>
        <path d="M15 12H3"/>
        <path d="M14 4h5a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-5"/>
      </svg>
    </button>,
    target
  );
}
