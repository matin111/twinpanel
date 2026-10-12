"use client";

import {useEffect,useMemo,useState} from "react";
import {Badge,Card,PageHead} from "./ui";
import {PortalShell} from "./portal-shells";
import {useI18n} from "../lib/i18n";
import {useCustomerSession} from "../lib/customer-session";

type StorePlan={
  id:number;
  name:string;
  description:string|null;
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

type StoreOrder={id:number;status:string;amount_toman:number;plan_id:number};

const protocolName=(value:string)=>({
  cisco:"Cisco / OpenConnect",
  openvpn:"OpenVPN",
  wireguard:"WireGuard",
  l2tp:"L2TP / IPsec",
  v2ray:"V2Ray / Xray"
} as Record<string,string>)[value]||value;

const planProtocols=(plan:StorePlan)=>[
  plan.enable_cisco&&"cisco",
  plan.enable_openvpn&&"openvpn",
  plan.enable_wireguard&&"wireguard",
  plan.enable_l2tp&&"l2tp",
  plan.enable_v2ray&&"v2ray"
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
  const [selectedPlan,setSelectedPlan]=useState<number|null>(null);
  const [selectedProtocols,setSelectedProtocols]=useState<string[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");

  useEffect(()=>{
    let alive=true;
    api<StorePlan[]>("/v1/plans")
      .then(rows=>{
        if(!alive)return;
        const active=(Array.isArray(rows)?rows:[]).filter(x=>x.is_active);
        setPlans(active);
        if(active.length){
          setSelectedPlan(active[0].id);
          setSelectedProtocols(planProtocols(active[0]));
        }
      })
      .catch(reason=>alive&&setError(reason instanceof Error?reason.message:String(reason)))
      .finally(()=>alive&&setLoading(false));
    return()=>{alive=false};
  },[]);

  const plan=useMemo(()=>plans.find(x=>x.id===selectedPlan)||null,[plans,selectedPlan]);
  const available=plan?planProtocols(plan):[];

  const choosePlan=(row:StorePlan)=>{
    setSelectedPlan(row.id);
    setSelectedProtocols(planProtocols(row));
    setMessage("");
  };

  const toggleProtocol=(value:string)=>{
    setSelectedProtocols(current=>current.includes(value)?current.filter(x=>x!==value):[...current,value]);
  };

  const createOrder=async()=>{
    if(!token||!plan)return;
    if(selectedProtocols.length===0){setError(pick("حداقل یک پروتکل انتخاب کنید.","Select at least one protocol."));return;}
    setBusy(true);setError("");setMessage("");
    try{
      const order=await api<StoreOrder>("/v1/store/orders",{
        method:"POST",
        body:JSON.stringify({
          plan_id:plan.id,
          protocols:selectedProtocols,
          idempotency_key:`panel-buy-${plan.id}-${Date.now()}-${Math.random().toString(36).slice(2,9)}`
        })
      },token);
      setMessage(`${pick("سفارش ساخته شد","Order created")} #${order.id}`);
      window.setTimeout(()=>window.location.href="/panel/orders",700);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  return <div className="page customer-runtime">
    <PageHead title={pick("خرید اشتراک","Buy Subscription")}/>
    <div className="customer-inline-warning">{pick("پلن، پروتکل و سفارش را بدون خروج از پنل کاربری مدیریت کنید.","Choose the plan and protocols without leaving your account.")}</div>
    {loading&&<div className="customer-loading"><span className="customer-loader"/>{pick("در حال دریافت پلن‌ها...","Loading plans...")}</div>}
    {error&&<Card className="customer-empty customer-error"><b>{pick("انجام عملیات ناموفق بود","Operation failed")}</b><p>{error}</p></Card>}
    {message&&<div className="customer-inline-warning">{message}</div>}
    {!loading&&plans.length===0&&<Card className="customer-empty"><span>◇</span><p>{pick("در حال حاضر پلن فعالی برای فروش وجود ندارد.","No active plans are available.")}</p></Card>}
    <div className="customer-subscriptions">
      {plans.map(row=>{
        const protocols=planProtocols(row);
        const selected=row.id===selectedPlan;
        return <Card key={row.id} className={selected?"customer-current-sub":""}>
          <div className="card-head"><div><b>{row.name}</b><small>{row.description||`#${row.id}`}</small></div>{selected&&<Badge tone="violet">{pick("انتخاب شده","Selected")}</Badge>}</div>
          <div className="customer-sub-meta">
            <span>{pick("مدت","Duration")}<b>{row.duration_days.toLocaleString("fa-IR")} {pick("روز","days")}</b></span>
            <span>{pick("حجم","Traffic")}<b>{row.traffic_gb.toLocaleString("fa-IR")} GB</b></span>
            <span>{pick("دستگاه","Devices")}<b>{row.device_limit.toLocaleString("fa-IR")}</b></span>
            <span>{pick("قیمت","Price")}<b>{row.price_toman.toLocaleString("fa-IR")} {pick("تومان","Toman")}</b></span>
          </div>
          <div className="customer-protocol-chips">{protocols.map(p=><span key={p}>{protocolName(p)}</span>)}</div>
          <div className="customer-actions"><button className={selected?"primary":"ghost"} onClick={()=>choosePlan(row)}>{selected?pick("انتخاب شده","Selected"):pick("انتخاب پلن","Select plan")}</button></div>
        </Card>;
      })}
    </div>
    {plan&&<Card>
      <div className="card-head"><div><b>{pick("پروتکل‌های سفارش","Order protocols")}</b><small>{plan.name}</small></div></div>
      <div className="customer-protocol-chips">{available.map(p=><button key={p} type="button" className={selectedProtocols.includes(p)?"active":""} onClick={()=>toggleProtocol(p)}>{selectedProtocols.includes(p)?"✓ ":""}{protocolName(p)}</button>)}</div>
      <div className="customer-actions"><button className="primary" disabled={busy||selectedProtocols.length===0} onClick={()=>void createOrder()}>{busy?pick("در حال ساخت سفارش...","Creating order..."):pick("ساخت سفارش و ادامه پرداخت","Create order & continue")}</button><a className="ghost" href="/panel/orders">{pick("سفارش‌های من","My orders")}</a></div>
    </Card>}
  </div>;
}

export function CustomerBuyRuntime(){
  return <PortalShell type="customer" active="/panel/buy"><BuyBody/></PortalShell>;
}
