"use client";

import {useEffect,useState} from "react";
import {getCustomerToken} from "../lib/customer-api";
import {planProtocols,StorePlan,storeRuntimeApi} from "../lib/store-runtime-api";
import {useI18n} from "../lib/i18n";
import {
  DEFAULT_STOREFRONT_SETTINGS,
  StorefrontSettings,
  normalizeStorefrontSettings,
} from "../lib/storefront-config";
import {resolveStoreTemplateId} from "../lib/store-template-registry";
import {StoreTemplateRenderer} from "./store-template-renderer";
import {EditorialGrid2027Template} from "./store-template-editorial-grid";

export function StoreRuntime2027(){
  const {pick}=useI18n();
  const [plans,setPlans]=useState<StorePlan[]>([]);
  const [settings,setSettings]=useState<StorefrontSettings>(DEFAULT_STOREFRONT_SETTINGS);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [buying,setBuying]=useState<number|null>(null);
  const [message,setMessage]=useState("");

  const load=async()=>{
    setLoading(true);setError("");
    const [plansResult,settingsResult]=await Promise.allSettled([
      storeRuntimeApi.plans(),
      storeRuntimeApi.storefrontSettings(),
    ]);

    if(plansResult.status==="fulfilled")setPlans(plansResult.value.filter(plan=>plan.is_active));
    else setError(plansResult.reason instanceof Error?plansResult.reason.message:String(plansResult.reason));

    if(settingsResult.status==="fulfilled")setSettings(normalizeStorefrontSettings(settingsResult.value));
    else if(plansResult.status==="fulfilled")setError(settingsResult.reason instanceof Error?settingsResult.reason.message:String(settingsResult.reason));

    setLoading(false);
  };

  useEffect(()=>{void load();},[]);

  const buy=async(plan:StorePlan)=>{
    const token=getCustomerToken();
    if(!token){
      window.location.href=`/login?next=${encodeURIComponent(`/store?plan=${plan.id}`)}`;
      return;
    }
    if(buying)return;
    setBuying(plan.id);setError("");setMessage("");
    try{
      const order=await storeRuntimeApi.createOrder(plan.id,planProtocols(plan));
      setMessage(`${pick("سفارش ساخته شد","Order created")} #${order.id}`);
      window.setTimeout(()=>{window.location.href="/panel/orders";},700);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBuying(null);}
  };

  const templateProps={
    settings,
    plans,
    loading,
    error,
    message,
    buying,
    onBuy:(plan:StorePlan)=>void buy(plan),
  };

  if(resolveStoreTemplateId(settings.active_template)==="editorial-grid-2027"){
    return <EditorialGrid2027Template {...templateProps}/>;
  }

  return <StoreTemplateRenderer {...templateProps}/>;
}
