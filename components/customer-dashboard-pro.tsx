"use client";

import Link from "next/link";
import {useEffect,useMemo,useState} from "react";
import {PortalShell} from "./portal-shells";
import {useCustomerSession} from "../lib/customer-session";
import {customerApi,MySubscription,PaymentIntent,StoreOrder,UserNotification,Wallet} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

function money(value:unknown){return `${Number(value||0).toLocaleString("fa-IR")} تومان`;}
function clamp(value:number){return Math.min(100,Math.max(0,value));}
function percent(used:number,limit:number){return limit>0?clamp(Math.round((used/limit)*100)):0;}
function dateText(value?:string|null){return value?new Date(value).toLocaleDateString("fa-IR",{year:"numeric",month:"short",day:"numeric"}):"—";}
function protocolName(value:string){return ({cisco:"Cisco / OpenConnect",openvpn:"OpenVPN",wireguard:"WireGuard",l2tp:"L2TP / IPsec",v2ray:"V2Ray / Xray",xray:"V2Ray / Xray"} as Record<string,string>)[value.toLowerCase()]||value;}
function statusText(value:string,pick:(fa:string,en:string)=>string){
  const map:Record<string,[string,string]>={active:["فعال","Active"],pending:["در انتظار","Pending"],suspended:["تعلیق","Suspended"],expired:["منقضی","Expired"],paid:["پرداخت شده","Paid"],fulfilled:["آماده","Ready"],pending_payment:["در انتظار پرداخت","Awaiting payment"],payment_submitted:["پرداخت ثبت شده","Payment submitted"],awaiting_review:["در انتظار تأیید","Awaiting review"],rejected:["رد شده","Rejected"]};
  const row=map[value];return row?pick(row[0],row[1]):value||"—";
}

function CustomerDashboardInner(){
  const {pick}=useI18n();
  const {token,user}=useCustomerSession();
  const [subs,setSubs]=useState<MySubscription[]>([]);
  const [wallet,setWallet]=useState<Wallet|null>(null);
  const [orders,setOrders]=useState<StoreOrder[]>([]);
  const [payments,setPayments]=useState<PaymentIntent[]>([]);
  const [notes,setNotes]=useState<UserNotification[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");

  const load=async()=>{
    if(!token)return;
    setLoading(true);setError("");
    const result=await Promise.allSettled([
      customerApi.subscriptions(token),customerApi.wallet(token),customerApi.orders(token),customerApi.payments(token),customerApi.notifications(token,12)
    ]);
    if(result[0].status==="fulfilled")setSubs(result[0].value);
    if(result[1].status==="fulfilled")setWallet(result[1].value);
    if(result[2].status==="fulfilled")setOrders(result[2].value);
    if(result[3].status==="fulfilled")setPayments(result[3].value);
    if(result[4].status==="fulfilled")setNotes(result[4].value);
    const failed=result.find(item=>item.status==="rejected");
    if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));
    setLoading(false);
  };

  useEffect(()=>{void load();},[token]);

  const active=useMemo(()=>subs.find(item=>item.status==="active")||subs[0]||null,[subs]);
  const unread=notes.filter(item=>!item.is_read&&!item.read_at).length;
  const usedPct=active?percent(active.traffic_used_gb,active.traffic_limit_gb):0;
  const latestOrder=orders[0]||null;
  const latestPayment=payments[0]||null;
  const displayName=user?.full_name||user?.email?.split("@")[0]||pick("کاربر","Customer");

  return <div className="customer-pro-dashboard">
    <section className="customer-pro-welcome">
      <div><span className="customer-pro-kicker">{pick("حساب کاربری","CUSTOMER ACCOUNT")}</span><h1>{pick("سلام","Hello")} {displayName}</h1></div>
      <div className="customer-pro-welcome-actions"><Link href="/panel/buy" className="primary">＋ {pick("خرید سرویس","Buy service")}</Link><button type="button" className="ghost" onClick={()=>window.dispatchEvent(new Event("twinpanel:open-chat"))}>{pick("چت آنلاین","Live chat")}</button></div>
    </section>

    {error&&<div className="customer-pro-alert"><span>!</span><div><b>{pick("بخشی از اطلاعات دریافت نشد","Some data could not be loaded")}</b><small>{error}</small></div><button onClick={()=>void load()}>{pick("تلاش دوباره","Retry")}</button></div>}

    <section className="customer-pro-kpis">
      <div><span className="customer-pro-kpi-icon violet">▱</span><small>{pick("اشتراک فعال","Active subscription")}</small><strong>{loading?"…":subs.filter(x=>x.status==="active").length.toLocaleString("fa-IR")}</strong><em>{active?.plan_name||pick("بدون اشتراک فعال","No active plan")}</em></div>
      <div><span className="customer-pro-kpi-icon cyan">◔</span><small>{pick("حجم باقی‌مانده","Traffic remaining")}</small><strong>{loading?"…":active?`${active.traffic_remaining_gb.toLocaleString("fa-IR")} GB`:"—"}</strong><em>{active?`${usedPct}% ${pick("مصرف شده","used")}`:pick("اطلاعاتی نیست","No data")}</em></div>
      <div><span className="customer-pro-kpi-icon green">◉</span><small>{pick("موجودی کیف پول","Wallet balance")}</small><strong>{loading?"…":money(wallet?.balance_toman)}</strong><em><Link href="/panel/wallet">{pick("مدیریت کیف پول","Manage wallet")} ←</Link></em></div>
      <div><span className="customer-pro-kpi-icon amber">◎</span><small>{pick("اعلان خوانده‌نشده","Unread notifications")}</small><strong>{loading?"…":unread.toLocaleString("fa-IR")}</strong><em><Link href="/panel/notifications">{pick("مشاهده اعلان‌ها","View notifications")} ←</Link></em></div>
    </section>

    <section className="customer-pro-main-grid">
      <article className="customer-pro-service-card">
        <div className="customer-pro-card-head"><div><small>{pick("سرویس اصلی","PRIMARY SERVICE")}</small><h2>{active?.plan_name||pick("اشتراک فعالی ندارید","No active subscription")}</h2></div>{active&&<span className={`customer-pro-status ${active.status}`}>{statusText(active.status,pick)}</span>}</div>
        {active?<>
          <div className="customer-pro-service-stats"><div><small>{pick("روز باقی‌مانده","Days left")}</small><b>{active.days_remaining.toLocaleString("fa-IR")}</b></div><div><small>{pick("انقضا","Expires")}</small><b>{dateText(active.expires_at)}</b></div><div><small>{pick("دستگاه","Devices")}</small><b>{active.device_limit.toLocaleString("fa-IR")}</b></div></div>
          <div className="customer-pro-traffic"><div><span>{pick("مصرف ترافیک","Traffic usage")}</span><b>{active.traffic_used_gb.toLocaleString("fa-IR")} / {active.traffic_limit_gb.toLocaleString("fa-IR")} GB</b></div><div className="customer-pro-progress"><i style={{width:`${usedPct}%`}}/></div><small>{active.traffic_remaining_gb.toLocaleString("fa-IR")} GB {pick("باقی‌مانده","remaining")}</small></div>
          <div className="customer-pro-protocols">{active.protocols.length?active.protocols.map(p=><span key={p}>{protocolName(p)}</span>):<span>{pick("پروتکل هنوز تخصیص داده نشده","No protocol assigned yet")}</span>}</div>
          <div className="customer-pro-actions"><Link href="/panel/connection" className="primary">{pick("اطلاعات اتصال","Connection details")}</Link><Link href="/panel/subscription" className="ghost">{pick("مدیریت و تمدید","Manage & renew")}</Link></div>
        </>:<div className="customer-pro-empty"><span>◇</span><b>{pick("هنوز سرویسی نداری","You do not have a service yet")}</b><Link href="/panel/buy" className="primary">{pick("مشاهده پلن‌ها","View plans")}</Link></div>}
      </article>

      <aside className="customer-pro-quick-card">
        <div className="customer-pro-card-head"><div><small>{pick("دسترسی سریع","QUICK ACCESS")}</small><h2>{pick("کارهای پرکاربرد","Common actions")}</h2></div></div>
        <div className="customer-pro-quick-grid">
          <Link href="/panel/connection"><i>⌁</i><div><b>{pick("اتصال و کانفیگ","Connection")}</b></div><span>←</span></Link>
          <Link href="/panel/usage"><i>◔</i><div><b>{pick("مصرف","Usage")}</b></div><span>←</span></Link>
          <Link href="/panel/payments"><i>◫</i><div><b>{pick("پرداخت‌ها","Payments")}</b></div><span>←</span></Link>
          <Link href="/panel/profile"><i>♙</i><div><b>{pick("حساب و امنیت","Account & security")}</b></div><span>←</span></Link>
        </div>
      </aside>
    </section>

    <section className="customer-pro-bottom-grid">
      <article className="customer-pro-activity-card"><div className="customer-pro-card-head"><div><small>{pick("آخرین فعالیت","RECENT ACTIVITY")}</small><h2>{pick("سفارش و پرداخت","Orders & payments")}</h2></div><Link href="/panel/orders">{pick("همه سفارش‌ها","All orders")} ←</Link></div><div className="customer-pro-activity-list"><div><span className="dot violet"/><div><b>{pick("آخرین سفارش","Latest order")}</b><small>{latestOrder?`#${latestOrder.id} · ${dateText(latestOrder.created_at)}`:pick("سفارشی ثبت نشده","No order yet")}</small></div><em>{latestOrder?statusText(latestOrder.status,pick):"—"}</em></div><div><span className="dot green"/><div><b>{pick("آخرین پرداخت","Latest payment")}</b><small>{latestPayment?`#${latestPayment.id} · ${dateText(latestPayment.created_at)}`:pick("پرداختی ثبت نشده","No payment yet")}</small></div><em>{latestPayment?statusText(latestPayment.status,pick):"—"}</em></div></div></article>
      <article className="customer-pro-notice-card"><div className="customer-pro-card-head"><div><small>{pick("اعلان‌ها","NOTIFICATIONS")}</small><h2>{pick("آخرین پیام‌ها","Latest messages")}</h2></div><Link href="/panel/notifications">{pick("مشاهده همه","View all")} ←</Link></div><div className="customer-pro-notices">{notes.length?notes.slice(0,3).map(n=><div key={n.id}><span className={!n.is_read&&!n.read_at?"unread":""}/><div><b>{n.title||pick("اعلان","Notification")}</b><small>{n.message||n.body||"—"}</small></div></div>):<div className="customer-pro-no-note">{pick("اعلان جدیدی نداری.","You have no new notifications.")}</div>}</div></article>
    </section>
  </div>;
}

export function CustomerDashboardPro(){return <PortalShell type="customer" active="/panel"><CustomerDashboardInner/></PortalShell>;}
