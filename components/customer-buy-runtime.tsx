"use client";

import {useEffect,useMemo,useState} from "react";
import {Badge,Card} from "./ui";
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

const protocolIcon=(value:string)=>({
  cisco:"◉",openvpn:"△",wireguard:"⚡",l2tp:"◎",v2ray:"◇"
} as Record<string,string>)[value]||"•";

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
    setError("");
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

  return <div className="page customer-runtime customer-buy-page">
    <section className="customer-buy-hero">
      <div>
        <span className="customer-buy-eyebrow">{pick("خرید مستقیم داخل پنل","IN-PANEL PURCHASE")}</span>
        <h1>{pick("پلن مناسب خودت را انتخاب کن","Choose your subscription")}</h1>
        <p>{pick("پلن، حجم، مدت و پروتکل‌ها را همین‌جا انتخاب کن؛ سفارش بدون خروج از پنل ساخته می‌شود.","Choose plan, quota, duration and protocols here. Your order is created without leaving the customer panel.")}</p>
      </div>
      <div className="customer-buy-hero-stats">
        <span><b>{plans.length.toLocaleString("fa-IR")}</b><small>{pick("پلن فعال","Active plans")}</small></span>
        <span><b>{plan?.traffic_gb?.toLocaleString("fa-IR")||"—"}</b><small>GB</small></span>
        <span><b>{selectedProtocols.length.toLocaleString("fa-IR")}</b><small>{pick("پروتکل","Protocols")}</small></span>
      </div>
    </section>

    {loading&&<div className="customer-buy-loading"><span className="customer-loader"/>{pick("در حال دریافت پلن‌ها...","Loading plans...")}</div>}
    {error&&<div className="customer-buy-alert error"><b>{pick("انجام عملیات ناموفق بود","Operation failed")}</b><span>{error}</span></div>}
    {message&&<div className="customer-buy-alert success">{message}</div>}
    {!loading&&plans.length===0&&<Card className="customer-empty"><span>◇</span><p>{pick("در حال حاضر پلن فعالی برای فروش وجود ندارد.","No active plans are available.")}</p></Card>}

    {!loading&&plans.length>0&&<>
      <div className="customer-buy-section-head">
        <div><small>{pick("مرحله ۱","STEP 1")}</small><h2>{pick("انتخاب پلن","Select a plan")}</h2></div>
        <span>{pick("برای تغییر پلن روی کارت کلیک کن","Click a card to switch plan")}</span>
      </div>

      <div className="customer-buy-grid">
        {plans.map((row,index)=>{
          const protocols=planProtocols(row);
          const selected=row.id===selectedPlan;
          return <button type="button" key={row.id} className={`customer-buy-plan ${selected?"selected":""}`} onClick={()=>choosePlan(row)}>
            <div className="customer-buy-plan-top">
              <div><small>#{row.id}</small><h3>{row.name}</h3></div>
              {selected?<Badge tone="violet">{pick("انتخاب شده","Selected")}</Badge>:index===Math.floor(plans.length/2)&&plans.length>1?<Badge tone="ok">{pick("پیشنهادی","Popular")}</Badge>:null}
            </div>
            {row.description&&<p>{row.description}</p>}
            <div className="customer-buy-price"><strong>{row.price_toman.toLocaleString("fa-IR")}</strong><span>{pick("تومان","Toman")}</span></div>
            <div className="customer-buy-facts">
              <span><i>◷</i><b>{row.duration_days.toLocaleString("fa-IR")}</b><small>{pick("روز","Days")}</small></span>
              <span><i>◉</i><b>{row.traffic_gb.toLocaleString("fa-IR")}</b><small>GB</small></span>
              <span><i>⌁</i><b>{row.device_limit.toLocaleString("fa-IR")}</b><small>{pick("دستگاه","Devices")}</small></span>
            </div>
            <div className="customer-buy-plan-protocols">{protocols.map(p=><span key={p}>{protocolIcon(p)} {protocolName(p)}</span>)}</div>
            <div className="customer-buy-select-indicator">{selected?pick("✓ این پلن انتخاب شده","✓ Selected plan"):pick("انتخاب این پلن","Select this plan")}</div>
          </button>;
        })}
      </div>

      {plan&&<section className="customer-buy-checkout">
        <div className="customer-buy-config">
          <div className="customer-buy-section-head compact">
            <div><small>{pick("مرحله ۲","STEP 2")}</small><h2>{pick("پروتکل‌های موردنیاز","Choose protocols")}</h2></div>
            <span>{pick("هر زمان خواستی می‌توانی انتخاب را تغییر بدهی","You can change this selection anytime")}</span>
          </div>
          <div className="customer-buy-protocol-grid">
            {available.map(p=>{
              const active=selectedProtocols.includes(p);
              return <button key={p} type="button" className={active?"active":""} onClick={()=>toggleProtocol(p)}>
                <span className="customer-buy-protocol-icon">{protocolIcon(p)}</span>
                <span><b>{protocolName(p)}</b><small>{active?pick("فعال در سفارش","Included"):pick("برای افزودن کلیک کن","Click to add")}</small></span>
                <i>{active?"✓":"+"}</i>
              </button>;
            })}
          </div>
        </div>

        <aside className="customer-buy-summary">
          <div className="customer-buy-summary-head"><small>{pick("خلاصه سفارش","ORDER SUMMARY")}</small><h3>{plan.name}</h3></div>
          <div className="customer-buy-summary-row"><span>{pick("مدت","Duration")}</span><b>{plan.duration_days.toLocaleString("fa-IR")} {pick("روز","days")}</b></div>
          <div className="customer-buy-summary-row"><span>{pick("حجم","Traffic")}</span><b>{plan.traffic_gb.toLocaleString("fa-IR")} GB</b></div>
          <div className="customer-buy-summary-row"><span>{pick("دستگاه","Devices")}</span><b>{plan.device_limit.toLocaleString("fa-IR")}</b></div>
          <div className="customer-buy-summary-row"><span>{pick("پروتکل‌ها","Protocols")}</span><b>{selectedProtocols.length.toLocaleString("fa-IR")}</b></div>
          <div className="customer-buy-summary-price"><span>{pick("مبلغ سفارش","Order total")}</span><div><strong>{plan.price_toman.toLocaleString("fa-IR")}</strong><small>{pick("تومان","Toman")}</small></div></div>
          <button className="customer-buy-submit" disabled={busy||selectedProtocols.length===0} onClick={()=>void createOrder()}>{busy?pick("در حال ساخت سفارش...","Creating order..."):pick("ساخت سفارش و ادامه پرداخت","Create order & continue")}</button>
          <a className="customer-buy-orders-link" href="/panel/orders">{pick("مشاهده سفارش‌های من","View my orders")}</a>
        </aside>
      </section>}
    </>}
  </div>;
}

export function CustomerBuyRuntime(){
  return <PortalShell type="customer" active="/panel/buy"><BuyBody/></PortalShell>;
}
