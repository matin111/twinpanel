"use client";

import Link from "next/link";
import {CSSProperties,useEffect,useMemo,useState} from "react";
import {PortalShell} from "./portal-shells";
import {useCustomerSession} from "../lib/customer-session";
import {customerApi,MySubscription,PaymentIntent,StoreOrder,UserNotification,Wallet} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

function money(value:unknown){return `${Number(value||0).toLocaleString("fa-IR")} تومان`;}
function clamp(value:number){return Math.min(100,Math.max(0,value));}
function percent(used:number,limit:number){return limit>0?clamp(Math.round((used/limit)*100)):0;}
function dateText(value?:string|null){return value?new Date(value).toLocaleDateString("fa-IR",{year:"numeric",month:"short",day:"numeric"}):"—";}
function protocolName(value:string){return ({cisco:"Cisco",openvpn:"OpenVPN",wireguard:"WireGuard",l2tp:"L2TP",v2ray:"V2Ray",xray:"Xray"} as Record<string,string>)[value.toLowerCase()]||value;}
function statusText(value:string,pick:(fa:string,en:string)=>string){
  const map:Record<string,[string,string]>={active:["فعال","Active"],pending:["در انتظار","Pending"],suspended:["تعلیق","Suspended"],expired:["منقضی","Expired"],paid:["پرداخت شده","Paid"],fulfilled:["آماده","Ready"],pending_payment:["در انتظار پرداخت","Awaiting payment"],payment_submitted:["پرداخت ثبت شده","Payment submitted"],awaiting_review:["در انتظار تأیید","Awaiting review"],approved:["تأیید شده","Approved"],auto_verified:["تأیید خودکار","Auto verified"],rejected:["رد شده","Rejected"],provisioning:["در حال ساخت","Provisioning"]};
  const row=map[value];return row?pick(row[0],row[1]):value||"—";
}

function DashboardIcon({type}:{type:"service"|"wallet"|"order"|"bell"|"arrow"|"link"}){
  const common={width:20,height:20,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:1.8,strokeLinecap:"round" as const,strokeLinejoin:"round" as const,"aria-hidden":true};
  if(type==="service")return <svg {...common}><rect x="3.5" y="5" width="17" height="14" rx="3"/><path d="M7 9h10M7 13h6"/><circle cx="17" cy="14.5" r="1.5"/></svg>;
  if(type==="wallet")return <svg {...common}><path d="M4 7.5h14a2 2 0 0 1 2 2v8H6a2 2 0 0 1-2-2z"/><path d="M4 8V6a2 2 0 0 1 2-2h10v3.5"/><path d="M16 11.5h4v3h-4a1.5 1.5 0 0 1 0-3Z"/></svg>;
  if(type==="order")return <svg {...common}><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 9h8M8 13h8M8 17h5"/></svg>;
  if(type==="bell")return <svg {...common}><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 7h18s-3 0-3-7"/><path d="M10 20h4"/></svg>;
  if(type==="link")return <svg {...common}><path d="M10 13a4 4 0 0 0 5.7.1l2.2-2.2a4 4 0 0 0-5.7-5.7L11 6.4"/><path d="M14 11a4 4 0 0 0-5.7-.1L6.1 13a4 4 0 0 0 5.7 5.7l1.2-1.2"/></svg>;
  return <svg {...common}><path d="m9 18 6-6-6-6"/></svg>;
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
      customerApi.subscriptions(token),
      customerApi.wallet(token),
      customerApi.orders(token),
      customerApi.payments(token),
      customerApi.notifications(token,12)
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
  const activeCount=subs.filter(item=>item.status==="active").length;
  const unread=notes.filter(item=>!item.is_read&&!item.read_at).length;
  const pendingOrders=orders.filter(item=>["pending_payment","payment_submitted","awaiting_review","provisioning"].includes(item.status)).length;
  const usedPct=active?percent(active.traffic_used_gb,active.traffic_limit_gb):0;
  const latestOrder=orders[0]||null;
  const latestPayment=payments[0]||null;
  const displayName=user?.full_name||user?.email?.split("@")[0]||pick("کاربر","Customer");
  const usageStyle={"--usage":`${usedPct}%`} as CSSProperties;

  return <div className="customer-dash-v27">
    <section className="customer-dash-v27-head">
      <div className="customer-dash-v27-title">
        <span>{pick("مرکز کاربری ۲۰۲۷","CUSTOMER CENTER 2027")}</span>
        <h1>{pick("سلام","Hello")} {displayName}</h1>
        <p>{pick("وضعیت سرویس، حساب و پرداخت‌های شما در یک نمای ساده و سریع","Your service, account and payments in one clean view")}</p>
      </div>
      <div className="customer-dash-v27-head-actions">
        <Link href="/panel/buy" className="customer-dash-primary">＋ {pick("خرید اشتراک","Buy subscription")}</Link>
        <Link href="/panel/subscription" className="customer-dash-secondary"><DashboardIcon type="link"/>{pick("اطلاعات اتصال","Connection details")}</Link>
      </div>
    </section>

    {error&&<div className="customer-dash-v27-alert"><span>!</span><div><b>{pick("بخشی از اطلاعات دریافت نشد","Some data could not be loaded")}</b><small>{error}</small></div><button type="button" onClick={()=>void load()}>{pick("تلاش دوباره","Retry")}</button></div>}

    <section className="customer-dash-v27-kpis">
      <Link href="/panel/subscription" className="customer-dash-v27-kpi"><i className="violet"><DashboardIcon type="service"/></i><div><small>{pick("اشتراک فعال","Active subscriptions")}</small><strong>{loading?"…":activeCount.toLocaleString("fa-IR")}</strong><em>{pick("مدیریت سرویس‌ها","Manage services")}</em></div><span><DashboardIcon type="arrow"/></span></Link>
      <Link href="/panel/wallet" className="customer-dash-v27-kpi"><i className="green"><DashboardIcon type="wallet"/></i><div><small>{pick("موجودی کیف پول","Wallet balance")}</small><strong>{loading?"…":money(wallet?.balance_toman)}</strong><em>{pick("شارژ و تراکنش‌ها","Top-up and history")}</em></div><span><DashboardIcon type="arrow"/></span></Link>
      <Link href="/panel/orders" className="customer-dash-v27-kpi"><i className="blue"><DashboardIcon type="order"/></i><div><small>{pick("سفارش در جریان","Open orders")}</small><strong>{loading?"…":pendingOrders.toLocaleString("fa-IR")}</strong><em>{orders.length.toLocaleString("fa-IR")} {pick("سفارش کل","total orders")}</em></div><span><DashboardIcon type="arrow"/></span></Link>
      <Link href="/panel/notifications" className="customer-dash-v27-kpi"><i className="amber"><DashboardIcon type="bell"/></i><div><small>{pick("اعلان خوانده‌نشده","Unread notifications")}</small><strong>{loading?"…":unread.toLocaleString("fa-IR")}</strong><em>{pick("مرکز اعلان‌ها","Notification center")}</em></div><span><DashboardIcon type="arrow"/></span></Link>
    </section>

    <section className="customer-dash-v27-workspace">
      <article className="customer-dash-v27-service">
        <div className="customer-dash-v27-service-head">
          <div><span>{pick("سرویس اصلی","PRIMARY SERVICE")}</span><h2>{loading?"…":active?.plan_name||pick("اشتراک فعالی ندارید","No active subscription")}</h2></div>
          {active&&<b className={`customer-dash-v27-status ${active.status}`}>{statusText(active.status,pick)}</b>}
        </div>

        {active?<>
          <div className="customer-dash-v27-usage-row">
            <div className="customer-dash-v27-usage-copy"><small>{pick("مصرف این دوره","Usage this period")}</small><strong>{active.traffic_used_gb.toLocaleString("fa-IR")} <em>/ {active.traffic_limit_gb.toLocaleString("fa-IR")} GB</em></strong></div>
            <div className="customer-dash-v27-usage-percent"><strong>{usedPct}%</strong><small>{pick("مصرف شده","used")}</small></div>
          </div>
          <div className="customer-dash-v27-progress" style={usageStyle}><span/></div>

          <div className="customer-dash-v27-metrics">
            <div><small>{pick("حجم باقی‌مانده","Remaining traffic")}</small><b>{active.traffic_remaining_gb.toLocaleString("fa-IR")} GB</b></div>
            <div><small>{pick("روز باقی‌مانده","Days remaining")}</small><b>{active.days_remaining.toLocaleString("fa-IR")}</b></div>
            <div><small>{pick("تاریخ انقضا","Expiry date")}</small><b>{dateText(active.expires_at)}</b></div>
            <div><small>{pick("تعداد دستگاه","Device limit")}</small><b>{active.device_limit.toLocaleString("fa-IR")}</b></div>
          </div>

          <div className="customer-dash-v27-service-footer">
            <div className="customer-dash-v27-protocols"><small>{pick("پروتکل‌های فعال","ACTIVE PROTOCOLS")}</small><div>{active.protocols.length?active.protocols.map(p=><span key={p}>{protocolName(p)}</span>):<span>{pick("در انتظار ساخت سرویس","Waiting for provisioning")}</span>}</div></div>
            <div className="customer-dash-v27-service-actions"><Link href="/panel/subscription" className="customer-dash-primary">{pick("مشاهده اتصال","View connection")}</Link><Link href="/panel/subscription" className="customer-dash-secondary">{pick("تمدید و مدیریت","Renew & manage")}</Link></div>
          </div>
        </>:<div className="customer-dash-v27-empty"><i><DashboardIcon type="service"/></i><div><b>{pick("هنوز سرویس فعالی نداری","You do not have an active service yet")}</b><small>{pick("برای شروع یکی از پلن‌های موجود را انتخاب کن","Choose one of the available plans to get started")}</small></div><Link href="/panel/buy" className="customer-dash-primary">{pick("مشاهده پلن‌ها","View plans")}</Link></div>}
      </article>

      {/* CUSTOMER_SINGLE_NAV_V1:
          Quick Access removed because the primary PortalShell
          already provides the same customer navigation. */}

    </section>

    <section className="customer-dash-v27-bottom">
      <article className="customer-dash-v27-activity">
        <div className="customer-dash-v27-card-title row"><div><span>{pick("آخرین فعالیت","RECENT ACTIVITY")}</span><h3>{pick("سفارش و پرداخت","Orders & payments")}</h3></div><Link href="/panel/orders">{pick("همه سفارش‌ها","All orders")}</Link></div>
        <div className="customer-dash-v27-timeline">
          <div><i className="violet"/><div><b>{pick("آخرین سفارش","Latest order")}</b><small>{latestOrder?`#${latestOrder.id} · ${dateText(latestOrder.created_at)}`:pick("سفارشی ثبت نشده","No order yet")}</small></div><em>{latestOrder?statusText(latestOrder.status,pick):"—"}</em>{latestOrder&&["pending_payment","payment_submitted","awaiting_review"].includes(latestOrder.status)&&<Link href={`/panel/payments?order=${latestOrder.id}`}>{pick("ادامه پرداخت","Continue")}</Link>}</div>
          <div><i className="green"/><div><b>{pick("آخرین پرداخت","Latest payment")}</b><small>{latestPayment?`#${latestPayment.id} · ${dateText(latestPayment.created_at)}`:pick("پرداختی ثبت نشده","No payment yet")}</small></div><em>{latestPayment?statusText(latestPayment.status,pick):"—"}</em><Link href="/panel/payments">{pick("جزئیات","Details")}</Link></div>
        </div>
      </article>

      <article className="customer-dash-v27-notes">
        <div className="customer-dash-v27-card-title row"><div><span>{pick("اعلان‌ها","NOTIFICATIONS")}</span><h3>{pick("آخرین پیام‌ها","Latest messages")}</h3></div><Link href="/panel/notifications">{pick("مشاهده همه","View all")}</Link></div>
        <div className="customer-dash-v27-note-list">{notes.length?notes.slice(0,4).map(n=><div key={n.id}><i className={!n.is_read&&!n.read_at?"unread":""}/><div><b>{n.title||pick("اعلان","Notification")}</b><small>{n.message||n.body||"—"}</small></div><time>{dateText(n.created_at)}</time></div>):<div className="customer-dash-v27-no-note">{pick("اعلان جدیدی نداری.","You have no notifications.")}</div>}</div>
      </article>
    </section>
  </div>;
}

export function CustomerDashboardPro(){return <PortalShell type="customer" active="/panel"><CustomerDashboardInner/></PortalShell>;}
