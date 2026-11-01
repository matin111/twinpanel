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
    if(!window.location.pathname.startsWith("/admin")){setTarget(null);return;}
    const findTarget=()=>{
      const node=document.querySelector<HTMLElement>(".admin-shell .admin-commandbar .head-actions");
      if(!node)return false;
      setTarget(node);
      return true;
    };
    if(findTarget())return;
    const observer=new MutationObserver(()=>{if(findTarget())observer.disconnect();});
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
        minHeight:36,
        padding:"0 11px",
        display:"inline-flex",
        alignItems:"center",
        justifyContent:"center",
        gap:6,
        border:"1px solid color-mix(in srgb,var(--bad,#ef4444) 34%,var(--line))",
        borderRadius:10,
        background:"color-mix(in srgb,var(--bad,#ef4444) 9%,transparent)",
        color:"var(--bad,#ef4444)",
        fontSize:12,
        fontWeight:850,
        lineHeight:1,
        whiteSpace:"nowrap",
        cursor:"pointer"
      }}
    >
      <span aria-hidden="true">⎋</span>
      <span>{pick("خروج","Logout")}</span>
    </button>,
    target
  );
}
