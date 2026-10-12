"use client";

import {useEffect,useState} from "react";
import {PortalShell} from "./portal-shells";
import {Badge,Card} from "./ui";
import {useCustomerSession} from "../lib/customer-session";
import {useI18n} from "../lib/i18n";

type StorePlan={
  id:number;
  name:string;
  duration_days:number;
  traffic_gb:number;
  device_limit:number;
  price_toman:number;
  is_active:boolean;
  enable_cisco:boolean;
  enable_openvpn:boolean;
  enable_wireguard:boolean;
  enable_l2tp:boolean;
  enable_v2ray:boolean;
};

type StoreOrder={id:number};

const protocols=(plan:StorePlan)=>[
  plan.enable_cisco&&"Cisco / OpenConnect",
  plan.enable_openvpn&&"OpenVPN",
  plan.enable_wireguard&&"WireGuard",
  plan.enable_l2tp&&"L2TP / IPsec",
  plan.enable_v2ray&&"V2Ray / Xray"
].filter(Boolean) as string[];

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
    const requested=[
      plan.enable_cisco&&"cisco",
      plan.enable_openvpn&&"openvpn",
      plan.enable_wireguard&&"wireguard",
      plan.enable_l2tp&&"l2tp",
      plan.enable_v2ray&&"v2ray"
    ].filter(Boolean) as string[];
    if(!requested.length){setError(pick("برای این پلن پروتکلی فعال نیست.","No protocol is enabled for this plan."));return;}
    setBusy(plan.id);setError("");
    try{
      const order=await api<StoreOrder>("/v1/store/orders",{
        method:"POST",
        body:JSON.stringify({
          plan_id:plan.id,
          protocols:requested,
          idempotency_key:`panel-buy-${plan.id}-${Date.now()}-${Math.random().toString(36).slice(2,8)}`
        })
      },token);
      window.location.href=`/panel/payments?order=${order.id}`;
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));setBusy(null);}
  };

  return <div className="page customer-runtime customer-buy-rich">
    <div className="customer-buy-rich-head">
      <div><span>◇</span><h1>{pick("خرید اشتراک","Buy subscription")}</h1></div>
      <Badge tone="violet">{plans.length.toLocaleString("fa-IR")} {pick("پلن","plans")}</Badge>
    </div>

    {error&&<div className="customer-buy-alert error">{error}</div>}
    {loading&&<div className="customer-buy-loading"><span className="customer-loader"/></div>}
    {!loading&&plans.length===0&&<Card className="customer-empty"><p>{pick("پلن فعالی وجود ندارد.","No active plans.")}</p></Card>}

    {!loading&&plans.length>0&&<div className={`customer-buy-rich-grid ${plans.length===1?"single":""}`}>
      {plans.map((plan,index)=>{
        const enabled=protocols(plan);
        const free=Number(plan.price_toman||0)===0;
        return <article className="customer-buy-rich-card" key={plan.id}>
          <div className="customer-buy-rich-glow"/>
          <div className="customer-buy-rich-top">
            <div><small>#{plan.id}</small><h2>{plan.name}</h2></div>
            {index===0&&plans.length>1?<Badge tone="violet">{pick("پیشنهادی","Popular")}</Badge>:null}
          </div>

          <div className="customer-buy-rich-price">
            <strong>{free?pick("رایگان","Free"):Number(plan.price_toman).toLocaleString("fa-IR")}</strong>
            {!free&&<span>{pick("تومان","Toman")}</span>}
          </div>

          <div className="customer-buy-rich-facts">
            <div><i>◷</i><b>{plan.duration_days.toLocaleString("fa-IR")}</b><small>{pick("روز","Days")}</small></div>
            <div><i>◉</i><b>{plan.traffic_gb.toLocaleString("fa-IR")}</b><small>GB</small></div>
            <div><i>⌁</i><b>{plan.device_limit.toLocaleString("fa-IR")}</b><small>{pick("دستگاه","Devices")}</small></div>
          </div>

          <div className="customer-buy-rich-protocols">{enabled.map(item=><span key={item}>✓ {item}</span>)}</div>

          <button type="button" className="customer-buy-rich-action" disabled={busy===plan.id} onClick={()=>void buy(plan)}>
            {busy===plan.id?"…":pick("خرید و پرداخت","Buy & pay")}
          </button>
        </article>;
      })}
    </div>}
  </div>;
}

export function CustomerBuyRuntime(){return <PortalShell type="customer" active="/panel/buy"><BuyBody/></PortalShell>;}
