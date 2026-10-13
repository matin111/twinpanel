"use client";

import {useEffect,useState} from "react";
import {clearCustomerToken,customerApi,getCustomerToken} from "../lib/customer-api";
import {getResellerProfile} from "../lib/role-router";
import {readPortalAccess,writePortalAccess} from "../lib/access-cache";
import {useI18n} from "../lib/i18n";

export function AdminAuthGuard({children}:{children:React.ReactNode}){
  const {pick}=useI18n();
  const [state,setState]=useState<"checking"|"ok"|"denied">(()=>{
    const token=getCustomerToken();
    return token&&readPortalAccess(token)?.portal==="admin"?"ok":"checking";
  });

  useEffect(()=>{
    let alive=true;
    const run=async()=>{
      const token=getCustomerToken();
      if(!token){window.location.replace("/login");return;}
      try{
        const user=await customerApi.me(token);
        if(!alive)return;
        if(!user.is_active){clearCustomerToken();window.location.replace("/login");return;}
        if(String(user.role||"").toLowerCase()==="admin"){
          writePortalAccess(token,"admin",user);
          setState("ok");
          return;
        }
        const reseller=await getResellerProfile(token);
        if(!alive)return;
        writePortalAccess(token,reseller?"reseller":"customer",user);
        setState("denied");
        window.location.replace(reseller?"/reseller":"/panel");
      }catch{
        clearCustomerToken();
        if(alive)window.location.replace("/login");
      }
    };
    void run();
    return()=>{alive=false;};
  },[]);

  if(state==="checking")return <div className="auth-gate"><div className="auth-gate-card"><span className="spinner"/><b>{pick("در حال آماده‌سازی مدیریت...","Preparing admin panel...")}</b></div></div>;
  if(state!=="ok")return null;
  return <>{children}</>;
}
