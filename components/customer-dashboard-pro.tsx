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
  const ringStyle={"--usage":usedPct} as CSSProperties;

  return <div className="customer-home-2027">
    <section className="customer-home-head">
      <div className="customer-home-heading">
        <span>{pick("مرکز حساب","ACCOUNT CENTER")}</span>
        <h1>{pick("سلام","Hello")} {displayName}</h1>
        <p>{pick("اشتراک، پرداخت و حساب شما در یک نگاه","Your service, payments and account at a glance")}</p>
      </div>
      <div className="customer-home-head-actions">
        <Link href="/panel/buy" className="primary">＋ {pick("خرید اشتراک","Buy subscription")}</Link>
        <button type="button" className="ghost" onClick={()=>window.dispatchEvent(new Event("twinpanel:open-chat"))}>✦ {pick("چت آنلاین","Live chat")}</button>
      </div>
    </section>

    {error&&<div className="customer-home-alert"><span>!</span><div><b>{pick("بخشی از اطلاعات دریافت نشد","Some data could not be loaded")}</b><small>{error}</small></div><button type="button" onClick={()=>void load()}>{pick("تلاش دوباره","Retry")}</button></div>}

    <section className="customer-home-overview">
      <article className="customer-home-service">
        <div className="customer-home-service-top">
          <div><small>{pick("سرویس اصلی","PRIMARY SERVICE")}</small><h2>{loading?"…":active?.plan_name||pick("اشتراک فعالی ندارید","No active subscription")}</h2></div>
          {active&&<span className={`customer-home-status ${active.status}`}>{statusText(active.status,pick)}</span>}
        </div>
        {active?<div className="customer-home-service-body">
          <div className="customer-home-ring" style={ringStyle}><div><strong>{usedPct}%</strong><small>{pick("مصرف","used")}</small></div></div>
          <div className="customer-home-service-info">
            <div className="customer-home-service-metrics">
              <span><small>{pick("باقی‌مانده","Remaining")}</small><b>{active.traffic_remaining_gb.toLocaleString("fa-IR")} GB</b></span>
              <span><small>{pick("روز باقی‌مانده","Days left")}</small><b>{active.days_remaining.toLocaleString("fa-IR")}</b></span>
              <span><small>{pick("انقضا","Expires")}</small><b>{dateText(active.expires_at)}</b></span>
              <span><small>{pick("دستگاه","Devices")}</small><b>{active.device_limit.toLocaleString("fa-IR")}</b></span>
            </div>
            <div className="customer-home-protocols">{active.protocols.length?active.protocols.map(p=><span key={p}>{protocolName(p)}</span>):<span>{pick("در انتظار ساخت سرویس","Waiting for provisioning")}</span>}</div>
            <div className="customer-home-service-actions"><Link href="/panel/subscription" className="primary">{pick("مشاهده اطلاعات اتصال","Connection details")}</Link><Link href="/panel/subscription" className="ghost">{pick("مدیریت و تمدید","Manage & renew")}</Link></div>
          </div>
        </div>:<div className="customer-home-no-service"><span>◇</span><div><b>{pick("هنوز سرویس فعالی نداری","You do not have an active service yet")}</b><small>{pick("از پلن‌های موجود یک اشتراک انتخاب کن","Choose a subscription from available plans")}</small></div><Link href="/panel/buy" className="primary">{pick("مشاهده پلن‌ها","View plans")}</Link></div>}
      </article>

      <aside className="customer-home-stats">
        <Link href="/panel/wallet" className="customer-home-stat wallet"><i>◉</i><div><small>{pick("کیف پول","Wallet")}</small><strong>{loading?"…":money(wallet?.balance_toman)}</strong><em>{pick("مدیریت موجودی","Manage balance")} ←</em></div></Link>
        <Link href="/panel/orders" className="customer-home-stat orders"><i>▤</i><div><small>{pick("سفارش‌های در جریان","Open orders")}</small><strong>{loading?"…":pendingOrders.toLocaleString("fa-IR")}</strong><em>{orders.length.toLocaleString("fa-IR")} {pick("سفارش کل","total orders")}</em></div></Link>
        <Link href="/panel/notifications" className="customer-home-stat notice"><i>◎</i><div><small>{pick("اعلان جدید","New notifications")}</small><strong>{loading?"…":unread.toLocaleString("fa-IR")}</strong><em>{pick("مرکز اعلان‌ها","Notification center")} ←</em></div></Link>
        <Link href="/panel/subscription" className="customer-home-stat service"><i>▱</i><div><small>{pick("اشتراک فعال","Active services")}</small><strong>{loading?"…":activeCount.toLocaleString("fa-IR")}</strong><em>{pick("مدیریت سرویس","Manage service")} ←</em></div></Link>
      </aside>
    </section>

    <section className="customer-home-dock">
      <Link href="/panel/buy"><i>＋</i><span><b>{pick("خرید اشتراک","Buy")}</b><small>{pick("پلن جدید","New plan")}</small></span></Link>
      <Link href="/panel/subscription"><i>⌁</i><span><b>{pick("اشتراک من","Subscription")}</b><small>{pick("اتصال و تمدید","Connect & renew")}</small></span></Link>
      <Link href="/panel/orders"><i>▤</i><span><b>{pick("سفارش‌ها","Orders")}</b><small>{pick("پیگیری سفارش","Track orders")}</small></span></Link>
      <Link href="/panel/wallet"><i>◉</i><span><b>{pick("کیف پول","Wallet")}</b><small>{pick("شارژ و تراکنش","Top-up & history")}</small></span></Link>
      <Link href="/panel/payments"><i>◫</i><span><b>{pick("پرداخت‌ها","Payments")}</b><small>{pick("پرداخت و رسید","Pay & receipts")}</small></span></Link>
      <Link href="/panel/profile"><i>♙</i><span><b>{pick("امنیت حساب","Security")}</b><small>{pick("رمز و 2FA","Password & 2FA")}</small></span></Link>
    </section>

    <section className="customer-home-bottom">
      <article className="customer-home-activity">
        <div className="customer-home-card-head"><div><small>{pick("آخرین فعالیت","RECENT ACTIVITY")}</small><h2>{pick("سفارش و پرداخت","Orders & payments")}</h2></div><Link href="/panel/orders">{pick("همه سفارش‌ها","All orders")} ←</Link></div>
        <div className="customer-home-timeline">
          <div><span className="violet"/><div><b>{pick("آخرین سفارش","Latest order")}</b><small>{latestOrder?`#${latestOrder.id} · ${dateText(latestOrder.created_at)}`:pick("سفارشی ثبت نشده","No order yet")}</small></div><em>{latestOrder?statusText(latestOrder.status,pick):"—"}</em>{latestOrder&&["pending_payment","payment_submitted","awaiting_review"].includes(latestOrder.status)&&<Link href={`/panel/payments?order=${latestOrder.id}`}>{pick("ادامه پرداخت","Continue")} ←</Link>}</div>
          <div><span className="green"/><div><b>{pick("آخرین پرداخت","Latest payment")}</b><small>{latestPayment?`#${latestPayment.id} · ${dateText(latestPayment.created_at)}`:pick("پرداختی ثبت نشده","No payment yet")}</small></div><em>{latestPayment?statusText(latestPayment.status,pick):"—"}</em><Link href="/panel/payments">{pick("پرداخت‌ها","Payments")} ←</Link></div>
        </div>
      </article>

      <article className="customer-home-notifications">
        <div className="customer-home-card-head"><div><small>{pick("اعلان‌ها","NOTIFICATIONS")}</small><h2>{pick("آخرین پیام‌ها","Latest messages")}</h2></div><Link href="/panel/notifications">{pick("مشاهده همه","View all")} ←</Link></div>
        <div className="customer-home-note-list">{notes.length?notes.slice(0,4).map(n=><div key={n.id}><span className={!n.is_read&&!n.read_at?"unread":""}/><div><b>{n.title||pick("اعلان","Notification")}</b><small>{n.message||n.body||"—"}</small></div><time>{dateText(n.created_at)}</time></div>):<div className="customer-home-no-note">{pick("اعلان جدیدی نداری.","You have no notifications.")}</div>}</div>
      </article>
    </section>
  </div>;
}

export function CustomerDashboardPro(){return <PortalShell type="customer" active="/panel"><CustomerDashboardInner/></PortalShell>;}
