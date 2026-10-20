"use client";

import {useEffect,useState,type CSSProperties} from "react";
import {getCustomerToken} from "../lib/customer-api";
import {planProtocols,StorePlan,storeRuntimeApi} from "../lib/store-runtime-api";
import {useI18n} from "../lib/i18n";
import {
  DEFAULT_STOREFRONT_SETTINGS,
  StorefrontSettings,
  normalizeStorefrontSettings,
} from "../lib/storefront-config";
import {resolveStoreTemplateId} from "../lib/store-template-registry";
import {
  applyStoreTemplateOptions,
  storeTemplateCssVariables,
  type StoreTemplateOptionMap,
} from "../lib/store-template-options";
import {loadStoreTemplateSettings} from "../lib/store-template-settings-api";
import {StoreTemplateRuntime} from "./store-template-runtime-registry";

export function StoreRuntime2027(){
  const {pick}=useI18n();
  const [plans,setPlans]=useState<StorePlan[]>([]);
  const [settings,setSettings]=useState<StorefrontSettings>(DEFAULT_STOREFRONT_SETTINGS);
  const [templateSettings,setTemplateSettings]=useState<Record<string,Record<string,unknown>>>({});
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [buying,setBuying]=useState<number|null>(null);
  const [message,setMessage]=useState("");

  const load=async()=>{
    setLoading(true);setError("");
    const [plansResult,settingsResult,templateSettingsResult]=await Promise.allSettled([
      storeRuntimeApi.plans(),
      storeRuntimeApi.storefrontSettings(),
      loadStoreTemplateSettings(),
    ]);

    if(plansResult.status==="fulfilled")setPlans(plansResult.value.filter(plan=>plan.is_active));
    else setError(plansResult.reason instanceof Error?plansResult.reason.message:String(plansResult.reason));

    if(settingsResult.status==="fulfilled")setSettings(normalizeStorefrontSettings(settingsResult.value));
    else if(plansResult.status==="fulfilled")setError(settingsResult.reason instanceof Error?settingsResult.reason.message:String(settingsResult.reason));

    if(templateSettingsResult.status==="fulfilled")setTemplateSettings(templateSettingsResult.value.templates||{});
    else setTemplateSettings({});

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

  const templateId=resolveStoreTemplateId(settings.active_template);
  const rawTemplateOptions=templateSettings[templateId]||{};
  const hasTemplateOptions=Object.keys(rawTemplateOptions).length>0;
  const applied=hasTemplateOptions?applyStoreTemplateOptions(settings,templateId,rawTemplateOptions):{settings,options:{} as StoreTemplateOptionMap};
  const effectiveSettings={...applied.settings} as StorefrontSettings;
  const effectiveTarget=effectiveSettings as unknown as Record<string,unknown>;
  if(hasTemplateOptions){
    for(const [key,value] of Object.entries(rawTemplateOptions)){
      if(key in effectiveTarget&&(typeof value==="string"||typeof value==="boolean"||typeof value==="number"))effectiveTarget[key]=value;
    }
  }
  const effectiveOptions:StoreTemplateOptionMap=hasTemplateOptions
    ?({...applied.options,...rawTemplateOptions} as StoreTemplateOptionMap)
    :{};
  const themeStyle=storeTemplateCssVariables(effectiveOptions) as CSSProperties;

  const templateProps={
    settings:effectiveSettings,
    plans,
    loading,
    error,
    message,
    buying,
    onBuy:(plan:StorePlan)=>void buy(plan),
  };

  return <div data-store-theme-engine="v1" data-store-template-active={templateId} data-store-template-customized={hasTemplateOptions?"true":"false"} style={themeStyle}>
    <StoreTemplateRuntime templateId={templateId} {...templateProps}/>
  </div>;
}
