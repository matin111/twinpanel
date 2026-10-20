"use client";

import {useEffect,useMemo,useState} from "react";
import {usePathname} from "next/navigation";
import {createPortal} from "react-dom";
import {QRCodeSVG} from "qrcode.react";
import {useI18n} from "../lib/i18n";

function absoluteLink(value:string){
  if(!value)return "";
  if(/^https?:\/\//i.test(value))return value;
  if(typeof window!=="undefined"){
    try{return new URL(value,window.location.origin).toString();}catch{return value;}
  }
  return value;
}

type SubscriptionLinkPanelProps={
  link:string;
  reference?:string;
  className?:string;
};

export function SubscriptionLinkPanel({link,reference="",className=""}:SubscriptionLinkPanelProps){
  const {pick}=useI18n();
  const publicLink=useMemo(()=>absoluteLink(link),[link]);
  const [copied,setCopied]=useState(false);
  const [copyError,setCopyError]=useState(false);

  const copyLink=async()=>{
    if(!publicLink)return;
    setCopyError(false);
    try{
      await navigator.clipboard.writeText(publicLink);
      setCopied(true);
      window.setTimeout(()=>setCopied(false),1600);
    }catch{
      setCopyError(true);
      window.setTimeout(()=>setCopyError(false),2200);
    }
  };

  if(!publicLink){
    return <div className={`unified-subscription-link empty ${className}`}>
      <div className="usl-empty-icon">↗</div>
      <b>{pick("سابلینک هنوز آماده نیست","Subscription link is not ready yet")}</b>
      <small>{pick("پس از آماده شدن سرویس، لینک عمومی در همین بخش نمایش داده می‌شود.","The public link will appear here when the service is ready.")}</small>
    </div>;
  }

  return <div className={`unified-subscription-link ${className}`}>
    <section className="usl-qr-card">
      <div className="usl-card-kicker"><span className="usl-kicker-icon">⌗</span>{pick("اسکن سریع","Quick scan")}</div>
      <div className="usl-qr-shell"><QRCodeSVG value={publicLink} size={210} level="M"/></div>
      <div className="usl-qr-caption">
        <b>{pick("QR سابلینک","Subscription QR")}</b>
        <small>{pick("با دوربین یا اپ VPN اسکن کنید","Scan with a camera or VPN app")}</small>
      </div>
    </section>

    <section className="usl-link-card">
      <div className="usl-meta-row">
        <span className="usl-ready"><i/>{pick("آماده ارسال","Ready to share")}</span>
        {reference&&<span className="usl-reference" dir="ltr">{reference}</span>}
      </div>

      <div className="usl-title-block">
        <span className="usl-title-icon">↗</span>
        <div><b>{pick("سابلینک اشتراک","Subscription link")}</b><small>{pick("یک لینک واحد برای دریافت تنظیمات این اشتراک","One link for this subscription configuration")}</small></div>
      </div>

      <div className="usl-link-field" dir="ltr">
        <code>{publicLink}</code>
      </div>

      <div className="usl-actions">
        <button type="button" className={`usl-copy ${copied?"success":""}`} onClick={()=>void copyLink()}>{copied?`✓ ${pick("کپی شد","Copied")}`:pick("کپی لینک","Copy link")}</button>
        <a className="usl-open" href={publicLink} target="_blank" rel="noreferrer">{pick("باز کردن لینک","Open link")} <span>↗</span></a>
      </div>

      {copyError&&<div className="usl-copy-error">{pick("کپی خودکار انجام نشد؛ لینک را دستی انتخاب کنید.","Automatic copy failed; select the link manually.")}</div>}

      <div className="usl-tip"><span>✓</span><p>{pick("برای تحویل سرویس به مشتری فقط همین لینک یا QR کافی است؛ نیازی به ارسال جداگانه کانفیگ‌ها نیست.","This link or QR is enough to deliver the service; individual configs do not need to be sent separately.")}</p></div>
    </section>
  </div>;
}

type SubscriptionLinkModalProps={
  link:string;
  reference?:string;
  onClose:()=>void;
};

export function SubscriptionLinkModal({link,reference="",onClose}:SubscriptionLinkModalProps){
  const {pick}=useI18n();
  const [ready,setReady]=useState(false);

  useEffect(()=>setReady(true),[]);
  useEffect(()=>{
    if(!ready)return;
    const onKey=(event:KeyboardEvent)=>{if(event.key==="Escape")onClose();};
    document.addEventListener("keydown",onKey);
    return()=>document.removeEventListener("keydown",onKey);
  },[ready,onClose]);

  if(!ready)return null;
  return createPortal(<div className="runtime-modal unified-sublink-modal" role="dialog" aria-modal="true" aria-label={pick("سابلینک اشتراک","Subscription link")}>
    <button className="runtime-modal-bg" type="button" aria-label={pick("بستن","Close")} onClick={onClose}/>
    <div className="runtime-modal-card unified-sublink-modal-card">
      <header className="usl-modal-head">
        <div className="usl-modal-brand"><span className="usl-modal-mark">↗</span><div><b>{pick("سابلینک اشتراک","Subscription link")}</b><small>{pick("تحویل سریع، امن و یکپارچه سرویس","Fast, clean and unified service delivery")}</small></div></div>
        <button className="icon-button usl-close" type="button" onClick={onClose} aria-label={pick("بستن","Close")}>×</button>
      </header>
      <SubscriptionLinkPanel link={link} reference={reference}/>
    </div>
  </div>,document.body);
}

type BridgeState={link:string;reference:string;source:HTMLElement};

export function UnifiedSubscriptionLinkBridge(){
  const pathname=usePathname();
  const [bridge,setBridge]=useState<BridgeState|null>(null);
  const active=pathname==="/admin/subscriptions"||pathname==="/reseller/subscriptions";

  useEffect(()=>{
    if(!active){setBridge(null);return;}

    const detect=()=>{
      if(bridge)return;
      const roots=Array.from(document.querySelectorAll<HTMLElement>(".runtime-modal"));
      for(const root of roots){
        if(root.dataset.unifiedSublinkSource==="1"||root.classList.contains("unified-sublink-modal"))continue;
        const surface=root.querySelector<HTMLElement>(".subscription-link-stack, .reseller-connection-content");
        if(!surface)continue;
        const code=surface.querySelector<HTMLElement>("code");
        const raw=code?.textContent?.trim()||"";
        if(!raw)continue;
        const link=absoluteLink(raw);
        if(!/^https?:\/\//i.test(link))continue;
        const reference=root.querySelector<HTMLElement>(".card-head small")?.textContent?.trim()||"";
        root.dataset.unifiedSublinkSource="1";
        root.style.display="none";
        setBridge({link,reference,source:root});
        return;
      }
    };

    detect();
    const observer=new MutationObserver(detect);
    observer.observe(document.body,{childList:true,subtree:true,characterData:true});
    return()=>observer.disconnect();
  },[active,bridge]);

  useEffect(()=>()=>{
    if(bridge?.source?.isConnected){
      bridge.source.style.display="";
      delete bridge.source.dataset.unifiedSublinkSource;
    }
  },[bridge]);

  const close=()=>{
    if(!bridge)return;
    const source=bridge.source;
    const closeButton=source.querySelector<HTMLButtonElement>(".icon-button")||source.querySelector<HTMLButtonElement>(".runtime-modal-bg");
    setBridge(null);
    if(closeButton){
      closeButton.click();
      window.setTimeout(()=>{
        if(source.isConnected){
          source.style.display="";
          delete source.dataset.unifiedSublinkSource;
        }
      },120);
    }else{
      source.style.display="";
      delete source.dataset.unifiedSublinkSource;
    }
  };

  if(!bridge)return null;
  return <SubscriptionLinkModal link={bridge.link} reference={bridge.reference} onClose={close}/>;
}
