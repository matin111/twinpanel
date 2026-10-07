"use client";

import {useEffect,useState} from "react";
import {clearCustomerToken,customerApi,getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

export function AdminAuthGuard({children}:{children:React.ReactNode}){
  const {pick}=useI18n();
  const [state,setState]=useState<"checking"|"ok"|"denied">("checking");

  useEffect(()=>{
    let alive=true;
    const run=async()=>{
      const token=getCustomerToken();
      if(!token){window.location.replace("/login");return;}
      try{
        const user=await customerApi.me(token);
        if(!alive)return;
        if(!user.is_active){clearCustomerToken();window.location.replace("/login");return;}
        if(user.role!=="admin"){
          setState("denied");
          window.location.replace(user.role==="reseller"?"/reseller":"/panel");
          return;
        }
        setState("ok");
      }catch{
        clearCustomerToken();
        if(alive)window.location.replace("/login");
      }
    };
    void run();
    return()=>{alive=false;};
  },[]);

  if(state==="checking")return <div className="auth-gate"><div className="auth-gate-card"><span className="spinner"/><b>{pick("در حال بررسی دسترسی مدیریت...","Checking admin access...")}</b></div></div>;
  if(state!=="ok")return null;
  return <>{children}</>;
}
