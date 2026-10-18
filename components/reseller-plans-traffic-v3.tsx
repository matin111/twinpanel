"use client";

import Link from "next/link";
import {useEffect,useMemo,useState} from "react";
import {Badge,Card,Stat} from "./ui";
import {PortalShell} from "./portal-shells";
import {resellerApi,ResellerRow} from "../lib/reseller-runtime-api";
import {useI18n} from "../lib/i18n";

const str=(row:ResellerRow,...keys:string[])=>{for(const key of keys){const value=row?.[key];if(value!==undefined&&value!==null)return String(value);}return "";};
const num=(row:ResellerRow,...keys:string[])=>{const value=Number(str(row,...keys).replace(/[,٬]/g,"")||0);return Number.isFinite(value)?value:0;};
const money=(value:number)=>`${Number(value||0).toLocaleString("fa-IR")} تومان`;
const gbNumber=(value:number)=>`${Number(value||0).toLocaleString("fa-IR",{maximumFractionDigits:2})} GB`;
const dateText=(value:unknown)=>{if(!value)return "—";const d=new Date(String(value));return Number.isNaN(d.getTime())?String(value):d.toLocaleString("fa-IR");};
const protocols=(row:ResellerRow)=>[["enable_cisco","Cisco"],["enable_openvpn","OpenVPN"],["enable_wireguard","WireGuard"],["enable_l2tp","L2TP"],["enable_v2ray","V2Ray"]].filter(([key])=>Boolean(row[key])).map(([,label])=>label);

function Notice({error,ok}:{error:string;ok:string}){return <>{error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}</>;}
function Empty({children}:{children:React.ReactNode}){return <div className="runtime-empty">{children}</div>;}

export function ResellerSubscriptionPlansV3(){
  const {pick}=useI18n();
  const [plans,setPlans]=useState<ResellerRow[]>([]);
  const [subs,setSubs]=useState<ResellerRow[]>([]);
  const [drafts,setDrafts]=useState<Record<number,string>>({});
  const [busy,setBusy]=useState<number|null>(null);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const load=async()=>{
    setError("");
    const result=await Promise.allSettled([resellerApi.plans(),resellerApi.subscriptions()]);
    if(result[0].status==="fulfilled"){
      setPlans(result[0].value);
      setDrafts(Object.fromEntries(result[0].value.map(row=>[Number(row.id||row.reseller_plan_id||0),String(num(row,"sell_price_toman"))])));
    }
    if(result[1].status==="fulfilled")setSubs(result[1].value);
    const failed=result.find(item=>item.status==="rejected");
    if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));
  };

  useEffect(()=>{void load();},[]);

  const save=async(planId:number)=>{
    const value=Number(drafts[planId]||0);
    if(!Number.isFinite(value)||value<0){setError(pick("قیمت فروش نمی‌تواند منفی باشد.","Selling price cannot be negative."));return;}
    setBusy(planId);setError("");setOk("");
    try{
      await resellerApi.updatePlan(planId,{sell_price_toman:value});
      setOk(pick("قیمت فروش ذخیره شد.","Selling price saved."));
      await load();
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(null);}
  };

  const revenue=subs.reduce((sum,row)=>sum+num(row,"sell_price_toman"),0);
  const profit=subs.reduce((sum,row)=>sum+num(row,"profit_toman"),0);

  return <PortalShell type="reseller" active="/reseller/sales"><div className="page reseller-parity-page">
    <div className="page-head"><div><h1>{pick("پلن‌های اشتراک","Subscription Plans")}</h1><small>{pick("پلن‌هایی که مدیر برای نمایندگی فعال کرده است. قیمت فروش را خودتان برای فروش دستی و ربات تنظیم کنید.","Plans assigned by the administrator. Set your own selling price for manual sales and your bot.")}</small></div><div className="action-row"><button className="ghost" onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button><Link className="primary" href="/reseller/subscriptions">＋ {pick("فروش اشتراک","Sell subscription")}</Link></div></div>
    <Notice error={error} ok={ok}/>

    <div className="stats">
      <Stat label={pick("پلن اشتراک مجاز","Authorized subscription plans")} value={String(plans.length)}/>
      <Stat label={pick("تعداد فروش","Sales count")} value={String(subs.length)}/>
      <Stat label={pick("فروش ثبت‌شده","Recorded sales")} value={money(revenue)}/>
      <Stat label={pick("سود ثبت‌شده","Recorded profit")} value={money(profit)}/>
    </div>

    <Card>
      <div className="card-head"><div><b>{pick("قیمت فروش پلن‌های اشتراک","Subscription plan selling prices")}</b><small>{pick("تغییر قیمت اینجا، قیمت نمایش‌داده‌شده در ربات اختصاصی نمایندگی را هم تغییر می‌دهد.","Changing the price here also changes the price shown by your reseller bot.")}</small></div><Badge tone="violet">{plans.length}</Badge></div>
      <div className="table"><table><thead><tr><th>{pick("پلن اشتراک","Subscription plan")}</th><th>{pick("حجم / مدت","Traffic / Duration")}</th><th>{pick("پروتکل‌ها","Protocols")}</th><th>{pick("قیمت فروش شما","Your selling price")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{plans.map((row,index)=>{const id=Number(row.id||row.reseller_plan_id||0);return <tr key={id||index}><td><b>{str(row,"name","title")||`#${id}`}</b><small>{str(row,"description")}</small></td><td>{num(row,"traffic_gb")} GB · {num(row,"duration_days")} {pick("روز","days")}</td><td>{protocols(row).join(" · ")||"—"}</td><td><input className="table-input" type="number" step={1} value={drafts[id]??""} onChange={event=>setDrafts(value=>({...value,[id]:event.target.value}))}/><small>{pick("تومان","Toman")}</small></td><td><button className="mini-btn primary-lite" disabled={busy===id} onClick={()=>void save(id)}>{busy===id?"…":pick("ذخیره قیمت","Save price")}</button></td></tr>})}</tbody></table></div>
      {!plans.length&&<Empty>{pick("هنوز هیچ پلن اشتراکی برای این نمایندگی فعال نشده است.","No subscription plan is active for this reseller yet.")}</Empty>}
    </Card>

    <Card>
      <div className="card-head"><b>{pick("فروش‌های اخیر","Recent sales")}</b></div>
      <div className="table"><table><thead><tr><th>ID</th><th>{pick("مشتری","Customer")}</th><th>{pick("پلن اشتراک","Subscription plan")}</th><th>{pick("مبلغ فروش","Sale price")}</th><th>{pick("سود","Profit")}</th><th>{pick("تاریخ","Date")}</th></tr></thead><tbody>{subs.slice(0,100).map((row,index)=><tr key={str(row,"id")||index}><td>#{str(row,"id")}</td><td>{str(row,"customer_name")||`#${str(row,"customer_user_id")}`}</td><td>{str(row,"plan_name")||`#${str(row,"plan_id")}`}</td><td>{money(num(row,"sell_price_toman"))}</td><td>{money(num(row,"profit_toman"))}</td><td>{dateText(row.created_at)}</td></tr>)}</tbody></table></div>
      {!subs.length&&<Empty>{pick("هنوز فروشی ثبت نشده است.","No sales recorded yet.")}</Empty>}
    </Card>
  </div></PortalShell>;
}

export function ResellerTrafficRechargeV3(){
  const {pick}=useI18n();
  const [me,setMe]=useState<ResellerRow>({});
  const [balance,setBalance]=useState<ResellerRow>({});
  const [packages,setPackages]=useState<ResellerRow[]>([]);
  const [tx,setTx]=useState<ResellerRow[]>([]);
  const [busy,setBusy]=useState<number|null>(null);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const load=async()=>{
    setError("");
    const result=await Promise.allSettled([resellerApi.me(),resellerApi.traffic(),resellerApi.trafficPackages(),resellerApi.trafficTransactions()]);
    if(result[0].status==="fulfilled")setMe(result[0].value);
    if(result[1].status==="fulfilled")setBalance(result[1].value);
    if(result[2].status==="fulfilled")setPackages(result[2].value);
    if(result[3].status==="fulfilled")setTx(result[3].value);
    const failed=result.find(item=>item.status==="rejected");
    if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));
  };

  useEffect(()=>{void load();},[]);

  const buy=async(row:ResellerRow)=>{
    const id=Number(row.id||0);
    if(!id)return;
    const title=str(row,"title")||`#${id}`;
    const traffic=num(row,"traffic_gb");
    const price=num(row,"price_toman");
    if(!window.confirm(pick(`بسته «${title}» با ${traffic}GB به مبلغ ${price.toLocaleString("fa-IR")} تومان خریداری و به حجم نمایندگی اضافه شود؟`,`Buy ${title} (${traffic}GB) for ${price.toLocaleString()} toman and add it to reseller traffic?`)))return;
    setBusy(id);setError("");setOk("");
    try{
      await resellerApi.buyTraffic(id);
      setOk(pick(`بسته ${title} خریداری شد و ${traffic}GB به حجم نمایندگی اضافه شد.`,`Package ${title} was purchased and ${traffic}GB was added to reseller traffic.`));
      await load();
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(null);}
  };

  const purchaseCredit=num(me,"wallet_balance");
  const available=num(balance,"available_traffic_gb");

  return <PortalShell type="reseller" active="/reseller/traffic"><div className="page reseller-parity-page">
    <div className="page-head"><div><h1>{pick("خرید و شارژ حجم","Traffic Recharge")}</h1><small>{pick("پلن شارژ حجم از پلن اشتراک جدا است. با خرید هر بسته، حجم همان لحظه به موجودی حجمی نمایندگی اضافه می‌شود.","Traffic recharge packages are separate from subscription plans. Purchased traffic is added to the reseller pool immediately.")}</small></div><button className="ghost" onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div>
    <Notice error={error} ok={ok}/>

    <div className="stats">
      <Stat label={pick("حجم باقی‌مانده","Remaining traffic")} value={gbNumber(num(balance,"traffic_balance_gb"))}/>
      <Stat label={pick("حجم قابل استفاده","Available traffic")} value={gbNumber(available)}/>
      <Stat label={pick("اعتبار خرید حجم","Traffic purchase credit")} value={money(purchaseCredit)}/>
      <Stat label={pick("تراکنش‌های حجم","Traffic transactions")} value={String(tx.length)}/>
    </div>

    <Card>
      <div className="card-head"><div><b>{pick("پلن‌های شارژ حجم","Traffic Recharge Packages")}</b><small>{pick("این بسته‌ها فقط موجودی حجم نمایندگی را شارژ می‌کنند و هیچ ارتباطی با پلن اشتراک مشتری ندارند.","These packages only recharge reseller traffic and are separate from customer subscription plans.")}</small></div><Badge tone="violet">{packages.length}</Badge></div>
      <div className="reseller-package-grid">{packages.map((row,index)=>{const id=Number(row.id||0);return <article key={id||index}><b>{str(row,"title")||`#${id}`}</b><strong>{gbNumber(num(row,"traffic_gb"))}</strong><span>{money(num(row,"price_toman"))}</span><button className="primary" disabled={busy===id} onClick={()=>void buy(row)}>{busy===id?"…":pick("خرید و شارژ حجم","Buy & recharge")}</button></article>})}</div>
      {!packages.length&&<Empty>{pick("هنوز پلن شارژ حجمی فعالی تعریف نشده است.","No active traffic recharge package is available.")}</Empty>}
    </Card>

    <Card>
      <div className="card-head"><b>{pick("تاریخچه حجم نمایندگی","Reseller traffic history")}</b></div>
      <div className="table"><table><thead><tr><th>ID</th><th>{pick("تغییر حجم","Traffic change")}</th><th>{pick("مانده بعد","Balance after")}</th><th>{pick("نوع","Type")}</th><th>{pick("توضیح","Description")}</th><th>{pick("تاریخ","Date")}</th></tr></thead><tbody>{tx.map((row,index)=><tr key={str(row,"id")||index}><td>#{str(row,"id")}</td><td><b className={num(row,"traffic_gb")>=0?"positive":"negative"}>{num(row,"traffic_gb")>=0?"+":""}{gbNumber(num(row,"traffic_gb"))}</b></td><td>{gbNumber(num(row,"balance_after_gb"))}</td><td>{str(row,"type")||"—"}</td><td>{str(row,"description")||"—"}</td><td>{dateText(row.created_at)}</td></tr>)}</tbody></table></div>
      {!tx.length&&<Empty>{pick("تراکنش حجمی ثبت نشده است.","No traffic transactions yet.")}</Empty>}
    </Card>
  </div></PortalShell>;
}
