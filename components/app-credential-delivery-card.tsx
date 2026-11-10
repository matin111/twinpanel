"use client";

import {useEffect,useRef,useState} from "react";
import {useI18n} from "../lib/i18n";
import {getAppAccess,registerAppDirectory,type AppAccessDelivery} from "../lib/central-app-credential-api";

export function AppCredentialDeliveryCard({
  owner,subscriptionId
}:{
  owner:"admin"|"reseller";subscriptionId:number;
}){
  const {pick}=useI18n();
  const [data,setData]=useState<AppAccessDelivery|null>(null);
  const [busy,setBusy]=useState(false);
  const [registerBusy,setRegisterBusy]=useState(false);
  const [directoryAlias,setDirectoryAlias]=useState("");
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
      if(requestEpoch.current===epoch){
        const reason=e instanceof Error?e.message:String(e);
        setError(reason.includes("CENTRAL_APP_NOT_INCLUDED")
          ? pick("اپ TwinConnect در لایسنس این پنل فعال نیست.","TwinConnect is not enabled in this panel license.")
          : reason.includes("SUBSCRIPTION_NOT_FOUND")
            ? pick("اشتراک در دسترس نیست یا اجازه مشاهده آن را ندارید.","Subscription not found or access denied.")
            : reason);
      }
    }finally{
      if(requestEpoch.current===epoch)setBusy(false);
    }
  };

  const registerDirectory=async()=>{
    if(busy||registerBusy||owner!=="admin")return;
    const origin=window.prompt(
      pick("آدرس عمومی HTTPS پنل که اپ باید به آن متصل شود:",
           "Public HTTPS panel API origin for TwinConnect:"),
      window.location.origin,
    );
    if(!origin)return;
    setRegisterBusy(true);setError("");setDirectoryAlias("");
    try{
      const result=await registerAppDirectory(origin.trim());
      setDirectoryAlias(result.short_namespace);
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
    }finally{setRegisterBusy(false);}
  };

  const copy=(value:string)=>navigator.clipboard.writeText(value).catch(()=>{});
  return <section className="app-credential-delivery" data-testid="separate-app-login">
    <div className="card-head">
      <b>{pick("ورود مخصوص اپ","App login")}</b>
      <div className="action-row">
        {owner==="admin"&&<button type="button" className="ghost"
          data-testid="admin-app-directory-register"
          disabled={busy||registerBusy}
          onClick={()=>void registerDirectory()}>{registerBusy?"…":pick("ثبت آدرس پنل در لایسنس","Register panel for app")}</button>}
        <button type="button" className="ghost" disabled={busy||registerBusy||subscriptionId<=0}
          onClick={()=>void load(false)}>{busy?"…":pick("دریافت اطلاعات اپ","Show app credentials")}</button>
        <button type="button" className="ghost" disabled={busy||subscriptionId<=0}
          onClick={()=>void load(true)}>{pick("تغییر رمز اپ","Reset app password")}</button>
      </div>
    </div>
    {directoryAlias&&<p className="form-success" role="status">{pick("شناسه ثبت‌شده پنل: ","Registered app namespace: ")}<code dir="ltr">{directoryAlias}</code></p>}
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
