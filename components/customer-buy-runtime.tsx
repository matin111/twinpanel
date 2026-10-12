"use client";

import {useEffect,useState} from "react";
import {Badge,Card} from "./ui";
import {PortalShell} from "./portal-shells";
import {useI18n} from "../lib/i18n";
import {useCustomerSession} from "../lib/customer-session";

type StorePlan={id:number;name:string;description:string|null;duration_days:number;traffic_gb:number;device_limit:number;price_toman:number;is_active:boolean;enable_cisco:boolean;enable_openvpn:boolean;enable_wireguard:boolean;enable_l2tp:boolean;enable_v2ray:boolean};
type StoreOrder={id:number;status:string;amount_toman:number;plan_id:number};

const planProtocols=(plan:StorePlan)=>[
  plan.enable_cisco&&"cisco",plan.enable_openvpn&&"openvpn",plan.enable_wireguard&&"wireguard",plan.enable_l2tp&&"l2tp",plan.enable_v2ray&&"v2ray"
].filter(Boolean) as string[];

async function api<T>(path:string,init:RequestInit={},token?:string|null):Promise<T>{
  const headers=new Headers(init.headers);if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");if(token)headers.set("Authorization",`Bearer ${token}`);
  const response=await fetch(path,{...init,headers,cache:"no-store"});
  if(!response.ok){let message=`API error ${response.status}`;try{const p=await response.json() as {detail?:string;message?:string};message=p.detail||p.message||message;}catch{}throw new Error(message);}return response.json() as Promise<T>;
}

function BuyBody(){
  const {pick}=useI18n();const {token}=useCustomerSession();
  const [plans,setPlans]=useState<StorePlan[]>([]);const [loading,setLoading]=useState(true);const [busy,setBusy]=useState<number|null>(null);const [error,setError]=useState("");
  useEffect(()=>{let alive=true;api<StorePlan[]>("/v1/plans").then(rows=>alive&&setPlans((Array.isArray(rows)?rows:[]).filter(x=>x.is_active))).catch(e=>alive&&setError(e instanceof Error?e.message:String(e))).finally(()=>alive&&setLoading(false));return()=>{alive=false};},[]);

  const buy=async(plan:StorePlan)=>{
    if(!token||busy)return;setBusy(plan.id);setError("");
    try{
      const order=await api<StoreOrder>("/v1/store/orders",{method:"POST",body:JSON.stringify({plan_id:plan.id,protocols:planProtocols(plan),idempotency_key:`panel-buy-${plan.id}-${Date.now()}-${Math.random().toString(36).slice(2,9)}`})},token);
      window.location.href=`/panel/payments?order=${order.id}`;
    }catch(e){setError(e instanceof Error?e.message:String(e));setBusy(null);}
  };

  return <div className="page customer-runtime customer-buy-page customer-buy-simple">
    <div className="customer-buy-simple-head"><h1>{pick("خرید اشتراک","Buy Subscription")}</h1></div>
    {loading&&<div className="customer-buy-loading"><span className="customer-loader"/></div>}
    {error&&<div className="customer-buy-alert error"><span>{error}</span></div>}
    {!loading&&plans.length===0&&<Card className="customer-empty"><p>{pick("پلن فعالی وجود ندارد.","No active plans available.")}</p></Card>}
    <div className="customer-buy-simple-grid">{plans.map((plan,index)=><article key={plan.id} className="customer-buy-simple-card">
      <div className="customer-buy-simple-top"><div><small>#{plan.id}</small><h2>{plan.name}</h2></div>{index===Math.floor(plans.length/2)&&plans.length>1?<Badge tone="violet">{pick("پیشنهادی","Popular")}</Badge>:null}</div>
      <div className="customer-buy-simple-price"><strong>{plan.price_toman.toLocaleString("fa-IR")}</strong><span>{pick("تومان","Toman")}</span></div>
      <div className="customer-buy-simple-facts"><span><b>{plan.duration_days.toLocaleString("fa-IR")}</b><small>{pick("روز","Days")}</small></span><span><b>{plan.traffic_gb.toLocaleString("fa-IR")}</b><small>GB</small></span><span><b>{plan.device_limit.toLocaleString("fa-IR")}</b><small>{pick("دستگاه","Devices")}</small></span></div>
      <button type="button" className="primary" disabled={busy===plan.id} onClick={()=>void buy(plan)}>{busy===plan.id?"…":pick("خرید","Buy")}</button>
    </article>)}</div>
  </div>;
}

export function CustomerBuyRuntime(){return <PortalShell type="customer" active="/panel/buy"><BuyBody/></PortalShell>;}
