"use client";

import {usePathname} from "next/navigation";
import {useEffect,useState} from "react";
import {createPortal} from "react-dom";
import {QRCodeSVG} from "qrcode.react";
import {customerApi,CustomerConnectionInfo,getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

export function CustomerDeliveryEnhancement(){
  const pathname=usePathname();const {pick}=useI18n();
  const [host,setHost]=useState<Element|null>(null);const [info,setInfo]=useState<CustomerConnectionInfo|null>(null);const [loading,setLoading]=useState(false);const [error,setError]=useState("");const [copied,setCopied]=useState("");
  const active=pathname==="/panel/connection";

  useEffect(()=>{
    if(!active){setHost(null);return;}
    const timer=window.setTimeout(()=>setHost(document.querySelector(".customer-runtime")),80);
    return()=>window.clearTimeout(timer);
  },[active]);

  useEffect(()=>{
    if(!active)return;
    const token=getCustomerToken();if(!token)return;
    let alive=true;setLoading(true);setError("");
    customerApi.subscriptions(token).then(rows=>{
      const sub=rows.find(x=>x.status==="active")||rows[0];
      if(!sub)throw new Error(pick("اشتراکی برای تحویل اتصال پیدا نشد","No subscription available for delivery"));
      return customerApi.connectionInfo(token,sub.id);
    }).then(data=>{if(alive)setInfo(data)}).catch(e=>{if(alive)setError(e instanceof Error?e.message:String(e))}).finally(()=>{if(alive)setLoading(false)});
    return()=>{alive=false};
  },[active]);

  const copy=async(label:string,value:string)=>{try{await navigator.clipboard.writeText(value);setCopied(label);window.setTimeout(()=>setCopied(""),1300)}catch{}};
  if(!active||!host)return null;

  return createPortal(<section className="delivery-enhancement">
    <div className="delivery-enhancement-head"><div><small>{pick("تحویل کامل اکانت","ACCOUNT DELIVERY")}</small><h2>{pick("لینک، QR، مشخصات و دانلودها","Link, QR, credentials & downloads")}</h2></div></div>
    {loading&&<div className="delivery-loading">{pick("در حال آماده‌سازی اطلاعات اتصال...","Preparing connection details...")}</div>}
    {error&&<div className="runtime-error">{error}</div>}
    {info&&!loading&&<div className="delivery-enhancement-grid">
      <article className="delivery-qr-card"><div className="delivery-qr">{info.subscription_link?<QRCodeSVG value={info.subscription_link} size={180} includeMargin/>:<span>QR</span>}</div><div><small>{pick("لینک سابسکریپشن","Subscription link")}</small><code dir="ltr">{info.subscription_link||"—"}</code>{info.subscription_link&&<button className="primary" onClick={()=>void copy("sub",info.subscription_link)}>{copied==="sub"?"✓":pick("کپی لینک","Copy link")}</button>}</div></article>
      <article className="delivery-account-card"><div><small>{pick("نام کاربری","Username")}</small><code dir="ltr">{info.account?.username||"—"}</code>{info.account?.username&&<button onClick={()=>void copy("user",info.account.username!)}>{copied==="user"?"✓":"⧉"}</button>}</div><div><small>{pick("رمز عبور","Password")}</small><code dir="ltr">{info.account?.password||"—"}</code>{info.account?.password&&<button onClick={()=>void copy("pass",info.account.password!)}>{copied==="pass"?"✓":"⧉"}</button>}</div><p>{pick("برای Cisco/L2TP و پروتکل‌هایی که Username/Password نیاز دارند از همین مشخصات استفاده کن.","Use these credentials for Cisco/L2TP and protocols that require username/password.")}</p></article>
      <article className="delivery-download-card"><div className="card-head"><b>{pick("فایل‌ها و دانلودهای این اشتراک","Subscription files & downloads")}</b></div><div className="delivery-download-list">{Object.entries(info.downloads||{}).map(([key,value])=>{const v=typeof value==="string"?value:"";return v&&(v.startsWith("/")||v.startsWith("http"))?<a key={key} href={v} target="_blank" rel="noreferrer"><span>↓</span><b>{key}</b><small dir="ltr">{v}</small></a>:<button key={key} onClick={()=>void copy(key,JSON.stringify(value))}><span>⧉</span><b>{key}</b><small>{pick("کپی اطلاعات","Copy data")}</small></button>})}</div></article>
    </div>}
  </section>,host);
}
