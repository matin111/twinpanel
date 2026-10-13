"use client";

import Link from "next/link";
import {useEffect,useState} from "react";
import {Badge,Card,Stat} from "./ui";
import {PortalShell} from "./portal-shells";
import {resellerApi,ResellerRow} from "../lib/reseller-runtime-api";
import {useI18n} from "../lib/i18n";

const GB=1024**3;
const str=(row:ResellerRow,...keys:string[])=>{for(const key of keys){const value=row?.[key];if(value!==undefined&&value!==null)return String(value);}return "";};
const num=(row:ResellerRow,...keys:string[])=>{const value=Number(str(row,...keys).replace(/[,٬]/g,"")||0);return Number.isFinite(value)?value:0;};
const money=(value:number)=>`${Number(value||0).toLocaleString("fa-IR")} تومان`;
const gbBytes=(value:number)=>`${(Number(value||0)/GB).toLocaleString("fa-IR",{maximumFractionDigits:2})} GB`;
const dateText=(value:unknown)=>{if(!value)return "—";const d=new Date(String(value));return Number.isNaN(d.getTime())?String(value):d.toLocaleString("fa-IR");};
const tone=(status:string):"ok"|"warn"|"bad"|"violet"=>status.toLowerCase()==="active"?"ok":["expired","canceled","suspended"].includes(status.toLowerCase())?"bad":"warn";

export function ResellerDashboardV3(){
  const {pick}=useI18n();
  const [me,setMe]=useState<ResellerRow>({});
  const [dash,setDash]=useState<ResellerRow>({});
  const [subs,setSubs]=useState<ResellerRow[]>([]);
  const [plans,setPlans]=useState<ResellerRow[]>([]);
  const [tx,setTx]=useState<ResellerRow[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");

  const load=async()=>{
    setLoading(true);setError("");
    const result=await Promise.allSettled([resellerApi.me(),resellerApi.dashboard(),resellerApi.subscriptions(),resellerApi.plans(),resellerApi.trafficTransactions()]);
    if(result[0].status==="fulfilled")setMe(result[0].value);
    if(result[1].status==="fulfilled")setDash(result[1].value);
    if(result[2].status==="fulfilled")setSubs(result[2].value);
    if(result[3].status==="fulfilled")setPlans(result[3].value);
    if(result[4].status==="fulfilled")setTx(result[4].value);
    const failed=result.find(item=>item.status==="rejected");
    if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));
    setLoading(false);
  };

  useEffect(()=>{void load();},[]);

  const remaining=num(dash,"traffic_balance_bytes")+num(dash,"traffic_credit_bytes");
  const active=num(dash,"active_subscriptions");
  const activePlans=plans.filter(row=>Boolean(row.is_active)).length;
  const purchaseCredit=num(me,"wallet_balance");

  return <PortalShell type="reseller" active="/reseller"><div className="page reseller-parity-page reseller-dashboard-v2">
    <div className="page-head"><div><h1>{pick("داشبورد نمایندگی","Reseller Dashboard")}</h1><small>{str(me,"brand_name","name")||str(me,"code")}</small></div><button className="ghost" onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div>
    {error&&<div className="runtime-error">{error}</div>}{loading&&<div className="runtime-loading">{pick("در حال دریافت اطلاعات...","Loading...")}</div>}

    {remaining<=0&&<div className="runtime-error">{pick("حجم نمایندگی تمام شده است؛ همه اشتراک‌های این نمایندگی تا شارژ مجدد حجم متوقف می‌شوند. ساخت اکانت محدود نمی‌شود.","The reseller traffic pool is exhausted; all reseller subscriptions remain suspended until traffic is recharged. Account creation stays unlimited.")}</div>}

    <div className="stats">
      <Stat label={pick("حجم قابل استفاده نمایندگی","Available reseller traffic")} value={gbBytes(remaining)}/>
      <Stat label={pick("اعتبار خرید حجم","Traffic purchase credit")} value={money(purchaseCredit)}/>
      <Stat label={pick("اشتراک فعال","Active subscriptions")} value={String(active)}/>
      <Stat label={pick("پلن فعال ربات","Active bot plans")} value={String(activePlans)}/>
    </div>

    <div className="module-grid two">
      <Card><div className="card-head"><div><b>{pick("اشتراک‌های اخیر","Recent subscriptions")}</b><small>{pick("تعداد ساخت نامحدود است؛ فقط مصرف واقعی از حجم مشترک نمایندگی کم می‌شود.","Account creation is unlimited; only real usage drains the shared reseller pool.")}</small></div><Link className="mini-btn" href="/reseller/subscriptions">{pick("ساخت اشتراک","Create")}</Link></div>{subs.slice(0,6).map((row,index)=><div className="module-row" key={str(row,"id")||index}><div className="grow"><b>{str(row,"account_username")||`#${str(row,"id")}`} · {str(row,"plan_name")||`#${str(row,"plan_id")}`}</b><small>{dateText(row.expires_at)}</small></div><Badge tone={tone(str(row,"status"))}>{str(row,"status")||"—"}</Badge></div>)}{!subs.length&&!loading&&<div className="runtime-empty">{pick("اشتراکی ثبت نشده است.","No subscriptions yet.")}</div>}</Card>
      <Card><div className="card-head"><div><b>{pick("آخرین تراکنش‌های حجم","Recent traffic activity")}</b><small>{pick("مصرف واقعی کاربران Pool را کم می‌کند؛ شارژ حجم سرویس‌های متوقف‌شده را دوباره فعال می‌کند.","Real usage drains the pool; recharging restores subscriptions suspended by pool exhaustion.")}</small></div><Link className="mini-btn" href="/reseller/traffic">{pick("خرید حجم","Recharge")}</Link></div>{tx.slice(0,6).map((row,index)=><div className="module-row" key={str(row,"id")||index}><div className="grow"><b className={num(row,"traffic_gb")>=0?"positive":"negative"}>{num(row,"traffic_gb")>=0?"+":""}{num(row,"traffic_gb").toLocaleString("fa-IR",{maximumFractionDigits:2})} GB</b><small>{str(row,"description","type")||"—"} · {dateText(row.created_at)}</small></div><span>{num(row,"balance_after_gb").toLocaleString("fa-IR",{maximumFractionDigits:2})} GB</span></div>)}{!tx.length&&!loading&&<div className="runtime-empty">{pick("تراکنش حجمی ثبت نشده است.","No traffic transactions yet.")}</div>}</Card>
    </div>

    <Card><div className="card-head"><b>{pick("دسترسی سریع","Quick access")}</b></div><div className="reseller-quick-grid"><Link href="/reseller/subscriptions">{pick("ساخت اشتراک","Create subscription")}</Link><Link href="/reseller/sales">{pick("پلن‌های ربات","Bot plans")}</Link><Link href="/reseller/traffic">{pick("خرید و شارژ حجم","Traffic recharge")}</Link><Link href="/reseller/bot">{pick("ربات نمایندگی","Reseller bot")}</Link><Link href="/reseller/orders">{pick("سفارش‌های ربات","Bot orders")}</Link></div></Card>
  </div></PortalShell>;
}
