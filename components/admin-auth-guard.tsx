"use client";

import {useEffect,useState} from "react";
import {clearCustomerToken,customerApi,getCustomerToken} from "../lib/customer-api";
import {getResellerProfile} from "../lib/role-router";
import {readPortalAccess,writePortalAccess} from "../lib/access-cache";
import {useI18n} from "../lib/i18n";

type GateState="checking"|"ok"|"denied"|"retry";

function timeout(ms:number){return new Promise<never>((_,reject)=>window.setTimeout(()=>reject(new Error("AUTH_TIMEOUT")),ms));}

export function AdminAuthGuard({children}:{children:React.ReactNode}){
  const {pick}=useI18n();
  const [state,setState]=useState<GateState>(()=>{
    const token=getCustomerToken();
    return token&&readPortalAccess(token)?.portal==="admin"?"ok":"checking";
  });

  useEffect(()=>{
    let alive=true;
    const run=async()=>{
      const token=getCustomerToken();
      if(!token){window.location.replace("/login");return;}
      const cached=readPortalAccess(token);
      if(cached?.portal==="admin"&&alive)setState("ok");
      try{
        const user=await Promise.race([customerApi.me(token),timeout(cached?.portal==="admin"?6000:4500)]);
        if(!alive)return;
        if(!user.is_active){clearCustomerToken();window.location.replace("/login");return;}
        if(String(user.role||"").toLowerCase()==="admin"){
          writePortalAccess(token,"admin",user);setState("ok");return;
        }
        const reseller=await Promise.race([getResellerProfile(token),timeout(3500)]);
        if(!alive)return;
        writePortalAccess(token,reseller?"reseller":"customer",user);setState("denied");window.location.replace(reseller?"/reseller":"/panel");
      }catch{
        if(!alive)return;
        if(cached?.portal==="admin"){setState("ok");return;}
        setState("retry");
      }
    };
    void run();
    return()=>{alive=false;};
  },[]);

  if(state==="checking")return <div className="auth-gate"><div className="auth-gate-card"><span className="spinner"/><b>{pick("در حال آماده‌سازی مدیریت...","Preparing admin panel...")}</b></div></div>;
  if(state==="retry")return <div className="auth-gate"><div className="auth-gate-card"><b>{pick("ارتباط با پنل مدیریت کند است.","Admin verification is taking too long.")}</b><button type="button" className="primary" onClick={()=>window.location.reload()}>{pick("تلاش دوباره","Retry")}</button></div></div>;
  if(state!=="ok")return null;
  return <>{children}</>;
}
