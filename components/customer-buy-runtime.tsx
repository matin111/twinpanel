"use client";

import {useEffect,useState} from "react";
import {PortalShell} from "./portal-shells";
import {Badge,Card} from "./ui";
import {useCustomerSession} from "../lib/customer-session";
import {useI18n} from "../lib/i18n";

type StorePlan={
  id:number;name:string;description?:string|null;duration_days:number;traffic_gb:number;device_limit:number;price_toman:number;is_active:boolean;
  enable_cisco:boolean;enable_openvpn:boolean;enable_wireguard:boolean;enable_l2tp:boolean;enable_v2ray:boolean;
  trial_enabled?:boolean;trial_duration_days?:number;trial_traffic_mb?:number;
};
type StoreOrder={id:number};
type TrialResult={ok:boolean;subscription_id:number;duration_days:number;traffic_mb:number};

const planDeviceLabels=["Android","iPhone","Windows","Mac","Linux"] as const;

async function api<T>(path:string,init:RequestInit={},token?:string|null):Promise<T>{
  const headers=new Headers(init.headers);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  if(token)headers.set("Authorization",`Bearer ${token}`);
  const response=await fetch(path,{...init,headers,cache:"no-store"});
  if(!response.ok){
    let message=`API error ${response.status}`;
    try{
      const payload=await response.json() as {detail?:unknown;message?:unknown};
      if(typeof payload.detail==="string")message=payload.detail;
      else if(payload.detail&&typeof payload.detail==="object"&&"message" in payload.detail)message=String((payload.detail as {message?:unknown}).message||message);
      else if(typeof payload.message==="string")message=payload.message;
    }catch{}
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

function BuyBody(){
  const {pick}=useI18n();
  const {token}=useCustomerSession();
  const [plans,setPlans]=useState<StorePlan[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState<number|null>(null);
  const [trialBusy,setTrialBusy]=useState<number|null>(null);
  const [error,setError]=useState("");

  useEffect(()=>{
    let alive=true;
    api<StorePlan[]>("/v1/plans")
      .then(rows=>alive&&setPlans((Array.isArray(rows)?rows:[]).filter(x=>x.is_active)))
      .catch(reason=>alive&&setError(reason instanceof Error?reason.message:String(reason)))
      .finally(()=>alive&&setLoading(false));
    return()=>{alive=false};
  },[]);

  const buy=async(plan:StorePlan)=>{
    if(!token)return;
    const requested=[plan.enable_cisco&&"cisco",plan.enable_openvpn&&"openvpn",plan.enable_wireguard&&"wireguard",plan.enable_l2tp&&"l2tp",plan.enable_v2ray&&"v2ray"].filter(Boolean) as string[];
    if(!requested.length){setError(pick("برای این پلن پروتکلی فعال نیست.","No protocol is enabled for this plan."));return;}
    setBusy(plan.id);setError("");
    try{
      const order=await api<StoreOrder>("/v1/store/orders",{method:"POST",body:JSON.stringify({plan_id:plan.id,protocols:requested,idempotency_key:`panel-buy-${plan.id}-${Date.now()}-${Math.random().toString(36).slice(2,8)}`})},token);
      window.location.href=`/panel/payments?order=${order.id}`;
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));setBusy(null);}
  };

  const claimTrial=async(plan:StorePlan)=>{
    if(!token)return;
    setTrialBusy(plan.id);setError("");
    try{
      const result=await api<TrialResult>("/v1/trial/claim",{method:"POST",body:JSON.stringify({plan_id:plan.id})},token);
      if(result.ok)window.location.href=`/panel/subscriptions?trial=${result.subscription_id}`;
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));setTrialBusy(null);}
  };

  const featuredPlanIndex=plans.length>2?Math.floor(plans.length/2):0;

  return <div className="page customer-runtime customer-buy-rich">
    <div className="customer-buy-rich-head"><div><span>◇</span><h1>{pick("خرید اشتراک","Buy subscription")}</h1></div><Badge tone="violet">{plans.length.toLocaleString("fa-IR")} {pick("پلن","plans")}</Badge></div>
    {error&&<div className="customer-buy-alert error">{error}</div>}
    {loading&&<div className="customer-buy-loading"><span className="customer-loader"/></div>}
    {!loading&&plans.length===0&&<Card className="customer-empty"><p>{pick("پلن فعالی وجود ندارد.","No active plans.")}</p></Card>}

    {!loading&&plans.length>0&&<div className={`customer-buy-rich-grid ${plans.length===1?"single":""}`}>
      {plans.map((plan,index)=>{
        const featured=index===featuredPlanIndex;const free=Number(plan.price_toman||0)===0;const hasTrial=Boolean(plan.trial_enabled);
        return <article className={`customer-buy-rich-card ${featured?"featured":""}`} key={plan.id}>
          {featured&&<span className="customer-buy-rich-ribbon">{pick("محبوب‌ترین انتخاب","Popular choice")}</span>}
          <div className="customer-buy-rich-top"><div><small>{pick("اشتراک VPN","VPN subscription")}</small><h2>{plan.name}</h2></div><span className="customer-buy-rich-status">{pick("فعال","Active")}</span></div>
          {plan.description&&<p className="customer-buy-rich-desc">{plan.description}</p>}
          <div className="customer-buy-rich-price"><strong>{free?pick("رایگان","Free"):Number(plan.price_toman).toLocaleString("fa-IR")}</strong>{!free&&<span>{pick("تومان","Toman")}</span>}</div>
          <div className="customer-buy-rich-facts"><div><b>{plan.traffic_gb.toLocaleString("fa-IR")} GB</b><small>{pick("حجم","Traffic")}</small></div><div><b>{plan.duration_days.toLocaleString("fa-IR")}</b><small>{pick("روز","days")}</small></div><div><b>{plan.device_limit.toLocaleString("fa-IR")}</b><small>{pick("دستگاه","devices")}</small></div></div>
          <ul className="customer-buy-rich-list">
            {hasTrial&&<li><i>🎁</i><b>{pick(`تست ${Number(plan.trial_duration_days||1).toLocaleString("fa-IR")} روزه با ${Number(plan.trial_traffic_mb||500).toLocaleString("fa-IR")} MB`,`Trial: ${Number(plan.trial_duration_days||1)} day(s), ${Number(plan.trial_traffic_mb||500)} MB`)}</b></li>}
            <li><i>✓</i>{pick("تحویل سریع پس از پرداخت","Fast delivery after payment")}</li><li><i>✓</i>{pick("قابل استفاده روی دستگاه‌های مختلف","Works across multiple devices")}</li><li><i>✓</i>{pick("مدیریت اشتراک از پنل کاربری","Manage the subscription from your panel")}</li>
          </ul>
          <div className="customer-buy-rich-devices">{planDeviceLabels.map(device=><span key={device}>{device}</span>)}</div>
          {hasTrial&&<button type="button" className="customer-buy-rich-action" disabled={trialBusy===plan.id||busy===plan.id} onClick={()=>void claimTrial(plan)}>{trialBusy===plan.id?pick("در حال ساخت اکانت تست...","Creating trial..."):pick("🎁 دریافت اکانت تست","🎁 Get trial account")}<span>←</span></button>}
          <button type="button" className="customer-buy-rich-action" disabled={busy===plan.id||trialBusy===plan.id} onClick={()=>void buy(plan)}>{busy===plan.id?pick("در حال ثبت سفارش...","Creating order..."):pick("خرید اشتراک","Buy subscription")}<span>←</span></button>
        </article>;
      })}
    </div>}
  </div>;
}

export function CustomerBuyRuntime(){return <PortalShell type="customer" active="/panel/buy"><BuyBody/></PortalShell>;}
