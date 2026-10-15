"use client";

import {useEffect,useState} from "react";
import {clearCustomerToken,customerApi,getCustomerToken} from "../lib/customer-api";
import {getResellerProfile} from "../lib/role-router";
import {useI18n} from "../lib/i18n";

const ADMIN_AUTH_TTL_MS=2*60*1000;
let verifiedAdminToken:string|null=null;
let verifiedAdminUntil=0;
let verifyPromise:Promise<"admin"|"reseller"|"user"|"inactive">|null=null;
let verifyPromiseToken:string|null=null;

async function verifyRole(token:string):Promise<"admin"|"reseller"|"user"|"inactive">{
  if(verifyPromise&&verifyPromiseToken===token)return verifyPromise;

  verifyPromiseToken=token;
  verifyPromise=(async()=>{
    const user=await customerApi.me(token);
    if(!user.is_active)return "inactive";
    if(user.role==="admin")return "admin";
    const reseller=await getResellerProfile(token);
    return reseller?"reseller":"user";
  })();

  try{
    return await verifyPromise;
  }finally{
    verifyPromise=null;
    verifyPromiseToken=null;
  }
}

export function AdminAuthGuard({children}:{children:React.ReactNode}){
  const {pick}=useI18n();
  const [state,setState]=useState<"checking"|"ok"|"denied">("checking");

  useEffect(()=>{
    let alive=true;
    const token=getCustomerToken();

    if(!token){
      window.location.replace("/login");
      return()=>{alive=false;};
    }

    if(token===verifiedAdminToken&&Date.now()<verifiedAdminUntil){
      setState("ok");
      return()=>{alive=false;};
    }

    const run=async()=>{
      try{
        const role=await verifyRole(token);
        if(!alive)return;

        if(role==="admin"){
          verifiedAdminToken=token;
          verifiedAdminUntil=Date.now()+ADMIN_AUTH_TTL_MS;
          setState("ok");
          return;
        }

        verifiedAdminToken=null;
        verifiedAdminUntil=0;

        if(role==="inactive"){
          clearCustomerToken();
          window.location.replace("/login");
          return;
        }

        setState("denied");
        window.location.replace(role==="reseller"?"/reseller":"/panel");
      }catch{
        verifiedAdminToken=null;
        verifiedAdminUntil=0;
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
