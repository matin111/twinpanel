"use client";

import {useEffect,useState} from "react";
import {clearCustomerToken,customerApi,getCustomerToken} from "../lib/customer-api";
import {getResellerProfile} from "../lib/role-router";
import {useI18n} from "../lib/i18n";

function loginUrlForCurrentPage(){
  const next=`${window.location.pathname}${window.location.search}`;
  return `/login?next=${encodeURIComponent(next)}`;
}

export function AdminAuthGuard({children}:{children:React.ReactNode}){
  const {pick}=useI18n();
  const [state,setState]=useState<"checking"|"ok"|"denied">("checking");

  useEffect(()=>{
    let alive=true;
    const run=async()=>{
      const token=getCustomerToken();
      if(!token){window.location.replace(loginUrlForCurrentPage());return;}
      try{
        const user=await customerApi.me(token);
        if(!alive)return;
        if(!user.is_active){
          clearCustomerToken();
          window.location.replace(loginUrlForCurrentPage());
          return;
        }
        if(user.role!=="admin"){
          const reseller=await getResellerProfile(token);
          if(!alive)return;
          setState("denied");
          window.location.replace(reseller?"/reseller":"/panel");
          return;
        }
        setState("ok");
      }catch{
        clearCustomerToken();
        if(alive)window.location.replace(loginUrlForCurrentPage());
      }
    };
    void run();
    return()=>{alive=false;};
  },[]);

  if(state==="checking")return <div className="auth-gate"><div className="auth-gate-card"><span className="spinner"/><b>{pick("در حال بررسی دسترسی مدیریت...","Checking admin access...")}</b></div></div>;
  if(state!=="ok")return null;
  return <>{children}</>;
}
