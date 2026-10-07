"use client";

import Link from "next/link";
import {usePathname} from "next/navigation";
import {useEffect,useState} from "react";
import {createPortal} from "react-dom";
import {useI18n} from "../lib/i18n";

export function StorePublicNavigation(){
  const pathname=usePathname();
  const {pick}=useI18n();
  const [selectedPlan,setSelectedPlan]=useState("");
  const isStore=pathname==="/"||pathname==="/store";

  useEffect(()=>{
    if(!isStore)return;
    const onClick=(event:MouseEvent)=>{
      const target=event.target as HTMLElement|null;
      const link=target?.closest<HTMLAnchorElement>(".sales-plan a[href='/login']");
      if(!link)return;
      event.preventDefault();
      const card=link.closest<HTMLElement>(".sales-plan");
      const name=card?.querySelector("h3")?.textContent?.trim()||pick("پلن انتخابی","Selected plan");
      document.querySelectorAll(".sales-plan.store-plan-selected").forEach(el=>el.classList.remove("store-plan-selected"));
      card?.classList.add("store-plan-selected");
      setSelectedPlan(name);
      window.setTimeout(()=>document.getElementById("store-checkout-ready")?.scrollIntoView({behavior:"smooth",block:"nearest"}),30);
    };
    document.addEventListener("click",onClick,true);
    return()=>document.removeEventListener("click",onClick,true);
  },[isStore,pick]);

  useEffect(()=>{
    if(!isStore)return;
    const updatePrivateGuideLink=()=>{
      const link=document.querySelector<HTMLAnchorElement>(".legacy-guide-head a[href='/panel/connection']");
      if(!link)return;
      link.href="/login?next=%2Fpanel%2Fconnection";
      link.textContent=pick("ورود برای دریافت اطلاعات اکانت","Sign in to get account details");
      link.setAttribute("data-private-action","1");
    };
    updatePrivateGuideLink();
    const observer=new MutationObserver(updatePrivateGuideLink);
    observer.observe(document.body,{subtree:true,childList:true});
    return()=>observer.disconnect();
  },[isStore,pick]);

  if(!isStore||!selectedPlan||typeof document==="undefined")return null;
  const next=`/panel/orders?plan=${encodeURIComponent(selectedPlan)}`;

  return createPortal(
    <div className="store-checkout-ready" id="store-checkout-ready" role="status">
      <div><small>{pick("پلن انتخاب شد","PLAN SELECTED")}</small><b>{selectedPlan}</b><span>{pick("می‌توانی قبل از ورود همچنان فروشگاه و آموزش‌ها را بررسی کنی.","You can keep browsing the store and guides before signing in.")}</span></div>
      <div className="store-checkout-ready-actions">
        <button type="button" className="ghost" onClick={()=>{setSelectedPlan("");document.querySelectorAll(".sales-plan.store-plan-selected").forEach(el=>el.classList.remove("store-plan-selected"));}}>{pick("تغییر پلن","Change plan")}</button>
        <Link className="primary" href={`/login?next=${encodeURIComponent(next)}`}>{pick("ادامه خرید","Continue purchase")}</Link>
      </div>
    </div>,
    document.body
  );
}
