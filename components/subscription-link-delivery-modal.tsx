"use client";

import {useEffect,useMemo,useState} from "react";
import {createPortal} from "react-dom";
import {QRCodeSVG} from "qrcode.react";
import {useI18n} from "../lib/i18n";

type SubscriptionLinkDeliveryModalProps={
  open:boolean;
  link?:string|null;
  reference?:string;
  loading?:boolean;
  error?:string;
  onClose:()=>void;
};

function absoluteLink(value:string){
  if(!value)return "";
  if(/^https?:\/\//i.test(value))return value;
  if(typeof window==="undefined")return value;
  try{return new URL(value,window.location.origin).toString();}catch{return value;}
}

export function SubscriptionLinkDeliveryModal({open,link,reference,loading=false,error="",onClose}:SubscriptionLinkDeliveryModalProps){
  const {pick}=useI18n();
  const [mounted,setMounted]=useState(false);
  const [copied,setCopied]=useState(false);
  const publicLink=useMemo(()=>absoluteLink(String(link||"")),[link]);

  useEffect(()=>{setMounted(true);},[]);
  useEffect(()=>{
    if(!open)return;
    setCopied(false);
    const previous=document.body.style.overflow;
    document.body.style.overflow="hidden";
    const onKey=(event:KeyboardEvent)=>{if(event.key==="Escape")onClose();};
    window.addEventListener("keydown",onKey);
    return()=>{document.body.style.overflow=previous;window.removeEventListener("keydown",onKey);};
  },[open,onClose]);

  const copy=async()=>{
    if(!publicLink)return;
    try{
      await navigator.clipboard.writeText(publicLink);
      setCopied(true);
      window.setTimeout(()=>setCopied(false),1600);
    }catch{
      setCopied(false);
    }
  };

  if(!mounted||!open)return null;

  return createPortal(
    <div className="runtime-modal subscription-link-unified-modal" data-subscription-link-surface="unified" role="dialog" aria-modal="true" aria-label={pick("سابلینک اشتراک","Subscription link")}>
      <button className="runtime-modal-bg" type="button" aria-label={pick("بستن","Close")} onClick={onClose}/>
      <section className="runtime-modal-card subscription-link-unified-card">
        <header className="subscription-link-unified-head">
          <div className="subscription-link-unified-icon" aria-hidden="true">⌁</div>
          <div className="subscription-link-unified-heading">
            <div className="subscription-link-unified-kicker">{pick("تحویل سریع و امن","Quick & secure delivery")}</div>
            <h2>{pick("سابلینک اشتراک","Subscription link")}</h2>
            <p>{pick("لینک عمومی اتصال را کپی کنید یا QR را اسکن کنید.","Copy the public connection link or scan the QR code.")}</p>
          </div>
          {reference&&<span className="subscription-link-unified-ref" dir="ltr">{reference}</span>}
          <button className="subscription-link-unified-close" type="button" aria-label={pick("بستن","Close")} onClick={onClose}>×</button>
        </header>

        {error&&<div className="subscription-link-unified-alert">{error}</div>}

        {loading?<div className="subscription-link-unified-loading"><span/><b>{pick("در حال آماده‌سازی سابلینک...","Preparing subscription link...")}</b></div>:publicLink?<div className="subscription-link-unified-grid">
          <div className="subscription-link-qr-card">
            <div className="subscription-link-card-title"><span aria-hidden="true">▦</span><div><b>{pick("کد QR","QR code")}</b><small>{pick("برای اتصال سریع اسکن کنید","Scan for quick access")}</small></div></div>
            <div className="subscription-link-qr-shell"><QRCodeSVG value={publicLink} size={196} level="M"/></div>
            <span className="subscription-link-ready"><i/>{pick("آماده استفاده","Ready to use")}</span>
          </div>

          <div className="subscription-link-url-card">
            <div className="subscription-link-card-title"><span aria-hidden="true">↗</span><div><b>{pick("لینک اشتراک","Subscription link")}</b><small>{pick("قابل استفاده در همه دستگاه‌ها","Works across all devices")}</small></div></div>
            <div className="subscription-link-url-field" dir="ltr"><code>{publicLink}</code></div>
            <div className="subscription-link-actions">
              <button className={`subscription-link-copy ${copied?"is-copied":""}`} type="button" onClick={()=>void copy()}><span aria-hidden="true">{copied?"✓":"⧉"}</span>{copied?pick("کپی شد","Copied"):pick("کپی لینک","Copy link")}</button>
              <a className="subscription-link-open" href={publicLink} target="_blank" rel="noreferrer"><span aria-hidden="true">↗</span>{pick("باز کردن","Open link")}</a>
            </div>
            <div className="subscription-link-hint"><span aria-hidden="true">✦</span>{pick("همین لینک برای کاربر، نماینده و ادمین یکسان است و همیشه آخرین تنظیمات اشتراک را نمایش می‌دهد.","The same link is used by customer, reseller and admin and always reflects the latest subscription settings.")}</div>
          </div>
        </div>:<div className="subscription-link-unified-empty"><span aria-hidden="true">⌁</span><b>{pick("سابلینک هنوز آماده نیست","Subscription link is not ready yet")}</b><small>{pick("پس از آماده‌شدن سرویس دوباره تلاش کنید.","Try again after the service is ready.")}</small></div>}
      </section>
    </div>,
    document.body,
  );
}
