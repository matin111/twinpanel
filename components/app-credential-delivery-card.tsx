"use client";

import {useEffect,useRef,useState} from "react";
import {useI18n} from "../lib/i18n";
import {getAppAccess,type AppAccessDelivery} from "../lib/central-app-credential-api";

export function AppCredentialDeliveryCard({
  owner,subscriptionId
}:{
  owner:"admin"|"reseller";subscriptionId:number;
}){
  const {pick}=useI18n();
  const [data,setData]=useState<AppAccessDelivery|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const requestEpoch=useRef(0);
  useEffect(()=>{
    requestEpoch.current++;
    setData(null);
    setError("");
  },[subscriptionId,owner]);

  const load=async(reset:boolean)=>{
    if(busy)return;
    if(reset&&!window.confirm(pick("رمز مخصوص اپ تغییر کند؟","Reset the app password?")))return;
    const epoch=++requestEpoch.current;
    setBusy(true);setError("");setData(null);
    try{
      const result=await getAppAccess(owner,subscriptionId,reset);
      if(requestEpoch.current===epoch)setData(result);
    }catch(e){
      if(requestEpoch.current===epoch)setError(e instanceof Error?e.message:String(e));
    }finally{
      if(requestEpoch.current===epoch)setBusy(false);
    }
  };

  const copy=(value:string)=>navigator.clipboard.writeText(value).catch(()=>{});
  return <section className="app-credential-delivery" data-testid="separate-app-login">
    <div className="card-head">
      <b>{pick("ورود مخصوص اپ","App login")}</b>
      <div className="action-row">
        <button type="button" className="ghost" disabled={busy||subscriptionId<=0}
          onClick={()=>void load(false)}>{busy?"…":pick("دریافت اطلاعات اپ","Show app credentials")}</button>
        <button type="button" className="ghost" disabled={busy||subscriptionId<=0}
          onClick={()=>void load(true)}>{pick("تغییر رمز اپ","Reset app password")}</button>
      </div>
    </div>
    {error&&<p className="form-error" role="alert">{error}</p>}
    {data&&<div className="credential-grid">
      {[
        [pick("نام کاربری اپ","App username"),data.app_username],
        [pick("رمز مخصوص اپ","App password"),data.app_password],
        [pick("لینک اشتراک","Subscription link"),data.subscription_link],
      ].map(([label,value])=><div className="credential-card" key={label}>
        <span>{label}</span>
        <code dir="ltr" style={{overflowWrap:"anywhere"}}>{value}</code>
        <button type="button" className="mini-btn" onClick={()=>void copy(value)}>
          {pick("کپی","Copy")}
        </button>
      </div>)}
      <button type="button" className="ghost" onClick={()=>void copy(
        [
          `${pick("نام کاربری اپ","App username")}: ${data.app_username}`,
          `${pick("رمز اپ","App password")}: ${data.app_password}`,
          `${pick("لینک اشتراک","Subscription link")}: ${data.subscription_link}`,
        ].join("\n")
      )}>{pick("کپی همه","Copy all")}</button>
    </div>}
  </section>;
}
