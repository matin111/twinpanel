"use client";

import Link from "next/link";
import {FormEvent,useEffect,useMemo,useState} from "react";
import {Badge,Card,PageHead} from "./ui";
import {PortalShell} from "./portal-shells";
import {useI18n} from "../lib/i18n";
import {useCustomerSession} from "../lib/customer-session";
import {customerApi,StoreOrder,UserNotification,Wallet,WalletPaymentMethod,WalletTopup,WalletTransaction} from "../lib/customer-api";

type Section="orders"|"wallet"|"notifications"|"profile";

const money=(value:unknown)=>`${Number(value||0).toLocaleString("fa-IR")} تومان`;
const date=(value?:string|null)=>value?new Date(value).toLocaleString("fa-IR",{year:"numeric",month:"short",day:"numeric"}):"—";
const statusTone=(status:string):"ok"|"warn"|"bad"|"violet"=>["active","fulfilled","paid","approved","auto_verified"].includes(status)?"ok":["expired","canceled","rejected","payment_rejected","provision_failed"].includes(status)?"bad":"warn";
const statusFa=(status:string)=>({active:"فعال",pending:"در انتظار",suspended:"تعلیق",expired:"منقضی",canceled:"لغو شده",pending_payment:"در انتظار پرداخت",payment_submitted:"پرداخت ثبت شده",awaiting_review:"در انتظار تأیید",payment_rejected:"پرداخت رد شده",paid:"پرداخت شده",provisioning:"در حال ساخت",provision_failed:"خطای ساخت",fulfilled:"آماده",created:"ایجاد شده",submitted:"ثبت شده",approved:"تأیید شده",rejected:"رد شده",auto_verified:"تأیید خودکار"} as Record<string,string>)[status]||status||"—";
const protocolName=(value:string)=>({cisco:"Cisco",openvpn:"OpenVPN",wireguard:"WireGuard",l2tp:"L2TP",v2ray:"V2Ray",xray:"Xray"} as Record<string,string>)[value.toLowerCase()]||value;

function ErrorState({message,retry}:{message:string;retry?:()=>void}){
  const {pick}=useI18n();
  return <Card className="customer-empty customer-error"><b>{pick("دریافت اطلاعات ناموفق بود","Could not load data")}</b><p>{message}</p>{retry&&<button className="ghost" onClick={retry}>{pick("تلاش دوباره","Retry")}</button>}</Card>;
}
function Empty({text}:{text:string}){return <Card className="customer-empty"><span>◇</span><p>{text}</p></Card>;}
function Loading(){const {pick}=useI18n();return <div className="customer-loading"><span className="customer-loader"/>{pick("در حال دریافت اطلاعات...","Loading...")}</div>;}

async function copyText(value:string){
  if(!value)return false;
  try{if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(value);return true;}}catch{}
  try{const el=document.createElement("textarea");el.value=value;el.style.position="fixed";el.style.opacity="0";document.body.appendChild(el);el.select();const ok=document.execCommand("copy");el.remove();return ok;}catch{return false;}
}

function OrdersBody(){
  const {pick}=useI18n();const {token}=useCustomerSession();
  const [data,setData]=useState<StoreOrder[]>([]);const [loading,setLoading]=useState(true);const [error,setError]=useState("");
  const load=async()=>{if(!token)return;setLoading(true);setError("");try{setData(await customerApi.orders(token));}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setLoading(false);}};
  useEffect(()=>{void load();},[token]);
  const stats=useMemo(()=>({total:data.length,pending:data.filter(x=>["pending_payment","payment_submitted","awaiting_review","provisioning"].includes(x.status)).length,ready:data.filter(x=>["fulfilled","paid"].includes(x.status)).length}),[data]);
  if(loading)return <Loading/>;
  return <div className="page customer-runtime customer-orders-2027">
    <div className="customer-page-title"><div><span>ORDERS</span><PageHead title={pick("سفارش‌ها","Orders")}/></div><Link href="/panel/buy" className="primary">＋ {pick("خرید اشتراک","Buy subscription")}</Link></div>
    {error&&<ErrorState message={error} retry={load}/>} {!error&&<>
      <section className="customer-page-kpis"><Card><small>{pick("کل سفارش‌ها","Total orders")}</small><b>{stats.total.toLocaleString("fa-IR")}</b></Card><Card><small>{pick("در جریان","In progress")}</small><b>{stats.pending.toLocaleString("fa-IR")}</b></Card><Card><small>{pick("تکمیل شده","Completed")}</small><b>{stats.ready.toLocaleString("fa-IR")}</b></Card></section>
      {data.length===0?<Empty text={pick("هنوز سفارشی ثبت نشده است.","No orders yet.")}/>:<div className="customer-order-grid">{data.map(x=>{
        const needsPayment=["pending_payment","payment_submitted","awaiting_review"].includes(x.status);
        return <Card key={x.id} className="customer-order-card">
          <div className="customer-order-top"><div><small>ORDER</small><b>#{x.id}</b></div><Badge tone={statusTone(x.status)}>{statusFa(x.status)}</Badge></div>
          <div className="customer-order-amount"><small>{pick("مبلغ سفارش","Order amount")}</small><strong>{money(x.amount_toman)}</strong></div>
          <div className="customer-order-facts"><span><small>{pick("تاریخ","Date")}</small><b>{date(x.created_at)}</b></span><span><small>{pick("پروتکل‌ها","Protocols")}</small><b>{x.protocols?.map(protocolName).join(" · ")||"—"}</b></span>{x.payment_reference&&<span><small>{pick("پیگیری","Reference")}</small><b dir="ltr">{x.payment_reference}</b></span>}</div>
          {x.error&&<div className="customer-order-error">{x.error}</div>}
          <div className="customer-card-actions">{needsPayment&&<Link className="primary" href={`/panel/payments?order=${x.id}`}>{pick("ادامه پرداخت","Continue payment")}</Link>}{x.subscription_id&&<Link className="ghost" href="/panel/subscription">{pick("مشاهده اشتراک","View subscription")}</Link>}</div>
        </Card>;
      })}</div>}
    </>}</div>;
}

function WalletBody(){
  const {pick}=useI18n();const {token}=useCustomerSession();
  const [wallet,setWallet]=useState<Wallet|null>(null);const [transactions,setTransactions]=useState<WalletTransaction[]>([]);const [topups,setTopups]=useState<WalletTopup[]>([]);const [methods,setMethods]=useState<WalletPaymentMethod[]>([]);
  const [loading,setLoading]=useState(true);const [error,setError]=useState("");const [message,setMessage]=useState("");const [busy,setBusy]=useState(false);
  const [amount,setAmount]=useState("");const [method,setMethod]=useState("");const [activeTopup,setActiveTopup]=useState<WalletTopup|null>(null);
  const [tracking,setTracking]=useState("");const [last4,setLast4]=useState("");const [transferDate,setTransferDate]=useState("");const [transferTime,setTransferTime]=useState("");const [txid,setTxid]=useState("");const [copied,setCopied]=useState("");

  const load=async()=>{if(!token)return;setLoading(true);setError("");try{
    const [w,t,u,m]=await Promise.all([customerApi.wallet(token),customerApi.walletTransactions(token),customerApi.walletTopups(token),customerApi.walletMethods(token)]);
    setWallet(w);setTransactions(t);setTopups(u);const list=Array.isArray(m)?m:(m.methods||[]);setMethods(list);if(!method&&list.length)setMethod(list[0].id);
  }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setLoading(false);}};
  useEffect(()=>{void load();},[token]);

  const selectedMethod=useMemo(()=>activeTopup?.payment_method||methods.find(x=>x.id===(activeTopup?.method||method))||null,[activeTopup,methods,method]);
  const createTopup=async()=>{if(!token)return;const numeric=Number(String(amount).replace(/[^0-9]/g,""));if(!numeric||numeric<10000){setError(pick("حداقل مبلغ شارژ ۱۰٬۰۰۰ تومان است.","Minimum top-up is 10,000 toman."));return;}if(!method){setError(pick("روش پرداخت را انتخاب کنید.","Choose a payment method."));return;}setBusy(true);setError("");setMessage("");try{const row=await customerApi.createWalletTopup(token,numeric,method);setActiveTopup(row);setMessage(pick("درخواست شارژ ساخته شد. پرداخت را انجام و اطلاعات را ثبت کنید.","Top-up created. Complete the payment and submit the details."));await load();}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}};
  const submitTopup=async(e:FormEvent)=>{e.preventDefault();if(!token||!activeTopup)return;setBusy(true);setError("");setMessage("");try{const isUsdt=String(activeTopup.method||"").startsWith("usdt_");const row=await customerApi.submitWalletTopup(token,activeTopup.id,isUsdt?{txid:txid.trim()}:{tracking_code:tracking.trim(),sender_card_last4:last4.trim(),transfer_date:transferDate,transfer_time:transferTime});setActiveTopup(row);setMessage(pick("اطلاعات پرداخت ثبت شد و در انتظار بررسی است.","Payment details submitted and awaiting review."));await load();}catch(x){setError(x instanceof Error?x.message:String(x));}finally{setBusy(false);}};
  const copy=async(label:string,value:string)=>{if(await copyText(value)){setCopied(label);window.setTimeout(()=>setCopied(""),1200);}};
  if(loading)return <Loading/>;
  const isUsdt=String(activeTopup?.method||"").startsWith("usdt_");
  return <div className="page customer-runtime customer-wallet-2027">
    <div className="customer-page-title"><div><span>WALLET</span><PageHead title={pick("کیف پول","Wallet")}/></div><Link href="/panel/buy" className="ghost">{pick("خرید اشتراک","Buy subscription")}</Link></div>
    {error&&<div className="customer-inline-warning">{error}</div>}{message&&<div className="runtime-success">{message}</div>}
    <section className="customer-wallet-hero"><div><small>{pick("موجودی قابل استفاده","AVAILABLE BALANCE")}</small><strong>{money(wallet?.balance_toman)}</strong><span>{pick("آخرین بروزرسانی","Updated")}: {wallet?.updated_at?date(String(wallet.updated_at)):"—"}</span></div><div className="customer-wallet-orbit"><i/><i/><b>◉</b></div></section>

    <section className="customer-wallet-layout">
      <Card className="customer-wallet-topup-card">
        <div className="customer-section-head"><div><small>TOP UP</small><h2>{pick("شارژ کیف پول","Top up wallet")}</h2></div>{activeTopup&&<button className="ghost" type="button" onClick={()=>{setActiveTopup(null);setMessage("");}}>{pick("درخواست جدید","New request")}</button>}</div>
        {!activeTopup?<>
          <label className="customer-money-input"><span>{pick("مبلغ شارژ","Top-up amount")}</span><div><input inputMode="numeric" dir="ltr" placeholder="500000" value={amount} onChange={e=>setAmount(e.target.value.replace(/\D/g,""))}/><em>{pick("تومان","toman")}</em></div></label>
          <div className="customer-method-grid">{methods.map(row=><button type="button" key={row.id} className={method===row.id?"active":""} onClick={()=>setMethod(row.id)}><i>{row.id.startsWith("usdt")?"₮":"◫"}</i><span><b>{row.title||row.id}</b><small>{row.id.startsWith("usdt")?"USDT":pick("انتقال بانکی","Bank transfer")}</small></span></button>)}</div>
          {methods.length===0&&<p className="muted">{pick("روش شارژ فعالی تنظیم نشده است.","No top-up method is enabled.")}</p>}
          <button className="primary customer-wide-action" disabled={busy||!method} type="button" onClick={()=>void createTopup()}>{busy?"…":pick("ساخت درخواست شارژ","Create top-up request")}</button>
        </>:<form onSubmit={submitTopup} className="customer-topup-payment">
          <div className="customer-topup-summary"><div><small>{pick("درخواست","Request")}</small><b>#{activeTopup.id}</b></div><div><small>{pick("مبلغ شارژ","Top-up")}</small><b>{money(activeTopup.amount_toman)}</b></div><div><small>{pick("مبلغ پرداخت","Payable")}</small><b>{isUsdt?`${activeTopup.crypto_amount_usdt||"—"} USDT`:money(activeTopup.payable_amount_toman||activeTopup.amount_toman)}</b></div><Badge tone={statusTone(activeTopup.status)}>{statusFa(activeTopup.status)}</Badge></div>
          {isUsdt?<div className="customer-payment-destination"><span>{pick("آدرس کیف پول","Wallet address")}</span><code>{selectedMethod?.address||"—"}</code>{selectedMethod?.address&&<button type="button" onClick={()=>void copy("address",String(selectedMethod.address))}>{copied==="address"?"✓":"کپی"}</button>}</div>:<><div className="customer-payment-destination"><span>{pick("شماره کارت","Card number")}</span><code>{selectedMethod?.card_number||"—"}</code>{selectedMethod?.card_number&&<button type="button" onClick={()=>void copy("card",String(selectedMethod.card_number))}>{copied==="card"?"✓":"کپی"}</button>}</div>{selectedMethod?.card_holder&&<div className="customer-payment-holder">{pick("به نام","Card holder")}: <b>{selectedMethod.card_holder}</b></div>}</>}
          {["pending_payment","rejected"].includes(activeTopup.status)&&<div className="customer-topup-fields">{isUsdt?<label className="wide"><span>TXID</span><input dir="ltr" value={txid} onChange={e=>setTxid(e.target.value)} required/></label>:<><label><span>{pick("۴ رقم آخر کارت","Last 4 digits")}</span><input dir="ltr" inputMode="numeric" maxLength={4} value={last4} onChange={e=>setLast4(e.target.value.replace(/\D/g,""))} required/></label><label><span>{pick("کد پیگیری","Tracking code")}</span><input dir="ltr" value={tracking} onChange={e=>setTracking(e.target.value)} required/></label><label><span>{pick("تاریخ انتقال","Transfer date")}</span><input dir="ltr" type="date" value={transferDate} onChange={e=>setTransferDate(e.target.value)} required/></label><label><span>{pick("ساعت انتقال","Transfer time")}</span><input dir="ltr" type="time" value={transferTime} onChange={e=>setTransferTime(e.target.value)} required/></label></>}</div>}
          {["pending_payment","rejected"].includes(activeTopup.status)&&<button className="primary customer-wide-action" disabled={busy}>{busy?"…":pick("ثبت اطلاعات پرداخت","Submit payment details")}</button>}
          {!["pending_payment","rejected"].includes(activeTopup.status)&&<div className="customer-topup-state"><b>{statusFa(activeTopup.status)}</b>{activeTopup.review_note&&<small>{activeTopup.review_note}</small>}</div>}
        </form>}
      </Card>

      <Card className="customer-wallet-requests"><div className="customer-section-head"><div><small>REQUESTS</small><h2>{pick("درخواست‌های اخیر","Recent top-ups")}</h2></div></div>{topups.length===0?<p className="muted">{pick("درخواستی ثبت نشده است.","No top-up requests.")}</p>:topups.slice(0,6).map(x=><button type="button" className="customer-wallet-request-row" key={x.id} onClick={()=>{setActiveTopup(x);setMethod(String(x.method||""));}}><span><b>#{x.id}</b><small>{date(x.created_at)}</small></span><strong>{money(x.amount_toman)}</strong><Badge tone={statusTone(x.status)}>{statusFa(x.status)}</Badge></button>)}</Card>
    </section>

    <Card className="customer-wallet-history"><div className="customer-section-head"><div><small>HISTORY</small><h2>{pick("تراکنش‌های کیف پول","Wallet transactions")}</h2></div></div>{transactions.length===0?<p className="muted">{pick("تراکنشی ثبت نشده است.","No transactions yet.")}</p>:<div className="customer-transaction-list">{transactions.map(x=>{const value=Number(x.amount_toman??x.amount??0);return <div key={x.id}><span className={value>=0?"credit":"debit"}>{value>=0?"＋":"−"}</span><div><b>{x.description||x.kind||x.type||`#${x.id}`}</b><small>{date(x.created_at)}{x.reference?` · ${x.reference}`:""}</small></div><strong className={value>=0?"credit":"debit"}>{money(value)}</strong></div>;})}</div>}</Card>
  </div>;
}

function NotificationsBody(){
  const {pick}=useI18n();const {token}=useCustomerSession();const [data,setData]=useState<UserNotification[]>([]);const [loading,setLoading]=useState(true);const [error,setError]=useState("");const [filter,setFilter]=useState<"all"|"unread">("all");const [busy,setBusy]=useState(false);
  const load=async()=>{if(!token)return;setLoading(true);try{setData(await customerApi.notifications(token,100));setError("");}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setLoading(false);}};useEffect(()=>{void load();},[token]);
  const read=async(id:number)=>{if(!token)return;await customerApi.readNotification(token,id);setData(rows=>rows.map(x=>x.id===id?{...x,is_read:true,read_at:new Date().toISOString()}:x));};
  const readAll=async()=>{if(!token)return;setBusy(true);try{await customerApi.readAllNotifications(token);setData(rows=>rows.map(x=>({...x,is_read:true,read_at:x.read_at||new Date().toISOString()})));}finally{setBusy(false);}};
  const unread=data.filter(x=>!x.is_read&&!x.read_at).length;const visible=filter==="unread"?data.filter(x=>!x.is_read&&!x.read_at):data;
  if(loading)return <Loading/>;
  return <div className="page customer-runtime customer-notifications-2027">
    <div className="customer-page-title"><div><span>NOTIFICATIONS</span><PageHead title={pick("اعلان‌ها","Notifications")}/></div><button className="ghost" disabled={busy||unread===0} onClick={()=>void readAll()}>{busy?"…":pick("خواندن همه","Mark all read")}</button></div>
    {error&&<ErrorState message={error} retry={load}/>} {!error&&<>
      <section className="customer-notice-summary"><div><i>◎</i><span><small>{pick("خوانده‌نشده","Unread")}</small><b>{unread.toLocaleString("fa-IR")}</b></span></div><div><i>✓</i><span><small>{pick("کل اعلان‌ها","Total")}</small><b>{data.length.toLocaleString("fa-IR")}</b></span></div><div className="customer-notice-filter"><button className={filter==="all"?"active":""} onClick={()=>setFilter("all")}>{pick("همه","All")}</button><button className={filter==="unread"?"active":""} onClick={()=>setFilter("unread")}>{pick("خوانده‌نشده","Unread")}</button></div></section>
      {visible.length===0?<Empty text={filter==="unread"?pick("اعلان خوانده‌نشده‌ای نداری.","No unread notifications."):pick("اعلانی ثبت نشده است.","No notifications yet.")}/>:<div className="customer-notice-cards">{visible.map(x=>{const isUnread=!x.is_read&&!x.read_at;return <Card key={x.id} className={`customer-notice-card ${isUnread?"unread":""}`}><span className="customer-notice-dot"/><div className="customer-notice-content"><div><b>{x.title||pick("اعلان","Notification")}</b>{x.kind&&<em>{x.kind}</em>}</div><p>{x.message||x.body||""}</p><small>{date(x.created_at)}</small></div>{isUnread&&<button className="mini-btn" onClick={()=>void read(x.id)}>{pick("خواندم","Mark read")}</button>}</Card>;})}</div>}
    </>}</div>;
}

function ProfileBody(){
  const {pick}=useI18n();const {token,user,refresh,logout}=useCustomerSession();
  const [email,setEmail]=useState(user?.email||"");const [emailPassword,setEmailPassword]=useState("");const [currentPassword,setCurrentPassword]=useState("");const [newPassword,setNewPassword]=useState("");const [disablePassword,setDisablePassword]=useState("");
  const [twoFactor,setTwoFactor]=useState(false);const [secret,setSecret]=useState("");const [setupUri,setSetupUri]=useState("");const [code,setCode]=useState("");const [message,setMessage]=useState("");const [error,setError]=useState("");const [busy,setBusy]=useState(false);const [copied,setCopied]=useState(false);
  useEffect(()=>{setEmail(user?.email||"");},[user?.email]);
  useEffect(()=>{if(token)customerApi.twoFactorStatus(token).then(x=>setTwoFactor(x.enabled)).catch(()=>{});},[token]);
  const done=(text:string)=>{setMessage(text);setError("");};const fail=(x:unknown)=>{setError(x instanceof Error?x.message:String(x));setMessage("");};
  const changeEmail=async(e:FormEvent)=>{e.preventDefault();if(!token)return;setBusy(true);try{await customerApi.updateEmail(token,email.trim(),emailPassword);done(pick("ایمیل با موفقیت تغییر کرد.","Email updated."));setEmailPassword("");await refresh();}catch(x){fail(x);}finally{setBusy(false);}};
  const changePassword=async(e:FormEvent)=>{e.preventDefault();if(!token)return;setBusy(true);try{await customerApi.changePassword(token,currentPassword,newPassword);done(pick("رمز عبور تغییر کرد.","Password updated."));setCurrentPassword("");setNewPassword("");}catch(x){fail(x);}finally{setBusy(false);}};
  const setup2fa=async()=>{if(!token)return;setBusy(true);try{const x=await customerApi.twoFactorSetup(token);setSecret(x.secret);setSetupUri(x.otpauth_uri);setCode("");setError("");}catch(x){fail(x);}finally{setBusy(false);}};
  const enable2fa=async()=>{if(!token)return;setBusy(true);try{const x=await customerApi.twoFactorEnable(token,code);setTwoFactor(x.enabled);setSecret("");setSetupUri("");setCode("");done(pick("تأیید دو مرحله‌ای فعال شد.","Two-factor authentication enabled."));}catch(x){fail(x);}finally{setBusy(false);}};
  const disable2fa=async()=>{if(!token)return;setBusy(true);try{const x=await customerApi.twoFactorDisable(token,disablePassword,code);setTwoFactor(x.enabled);setCode("");setDisablePassword("");done(pick("تأیید دو مرحله‌ای غیرفعال شد.","Two-factor authentication disabled."));}catch(x){fail(x);}finally{setBusy(false);}};
  const copySecret=async()=>{if(await copyText(setupUri||secret)){setCopied(true);window.setTimeout(()=>setCopied(false),1200);}};
  return <div className="page customer-runtime customer-profile-2027">
    <div className="customer-page-title"><div><span>PROFILE & SECURITY</span><PageHead title={pick("پروفایل و امنیت","Profile & Security")}/></div></div>
    {message&&<div className="runtime-success">{message}</div>}{error&&<div className="runtime-error">{error}</div>}
    <section className="customer-profile-hero"><div className="customer-profile-avatar">{(user?.full_name||user?.email||"U").charAt(0).toUpperCase()}</div><div><h2>{user?.full_name||pick("کاربر","Customer")}</h2><span dir="ltr">{user?.email||"—"}</span><small>{pick("عضویت از","Member since")} {date(user?.created_at)}</small></div><Badge tone={user?.is_active?"ok":"bad"}>{user?.is_active?pick("حساب فعال","Active account"):pick("غیرفعال","Inactive")}</Badge></section>
    <section className="customer-profile-grid">
      <Card><div className="customer-section-head"><div><small>ACCOUNT</small><h2>{pick("ایمیل حساب","Account email")}</h2></div></div><form className="customer-modern-form" onSubmit={changeEmail}><label><span>{pick("ایمیل جدید","New email")}</span><input dir="ltr" type="email" value={email} onChange={e=>setEmail(e.target.value)} required/></label><label><span>{pick("رمز فعلی برای تأیید","Current password")}</span><input type="password" value={emailPassword} onChange={e=>setEmailPassword(e.target.value)} required/></label><button className="primary" disabled={busy}>{pick("ذخیره ایمیل","Save email")}</button></form></Card>
      <Card><div className="customer-section-head"><div><small>PASSWORD</small><h2>{pick("تغییر رمز عبور","Change password")}</h2></div></div><form className="customer-modern-form" onSubmit={changePassword}><label><span>{pick("رمز فعلی","Current password")}</span><input type="password" value={currentPassword} onChange={e=>setCurrentPassword(e.target.value)} required/></label><label><span>{pick("رمز جدید","New password")}</span><input type="password" value={newPassword} onChange={e=>setNewPassword(e.target.value)} minLength={8} required/></label><button className="primary" disabled={busy}>{pick("تغییر رمز","Change password")}</button></form></Card>
      <Card className="customer-2fa-card"><div className="customer-section-head"><div><small>2FA SECURITY</small><h2>{pick("تأیید دو مرحله‌ای","Two-factor authentication")}</h2></div><Badge tone={twoFactor?"ok":"warn"}>{twoFactor?pick("فعال","Enabled"):pick("خاموش","Off")}</Badge></div>{!twoFactor&&!secret&&<div className="customer-2fa-intro"><span>✦</span><p>{pick("برای ورود امن‌تر، کد یک‌بارمصرف را فعال کن.","Add one-time codes for stronger sign-in security.")}</p><button className="primary" disabled={busy} onClick={()=>void setup2fa()}>{pick("راه‌اندازی 2FA","Set up 2FA")}</button></div>}{secret&&<div className="customer-2fa-setup"><div className="customer-secret-box"><span>{pick("Secret / Setup URI","Secret / Setup URI")}</span><code dir="ltr">{setupUri||secret}</code><button type="button" onClick={()=>void copySecret()}>{copied?"✓":pick("کپی","Copy")}</button></div><label><span>{pick("کد برنامه Authenticator","Authenticator code")}</span><input dir="ltr" inputMode="numeric" placeholder="000000" value={code} onChange={e=>setCode(e.target.value.replace(/\D/g,"").slice(0,8))}/></label><button className="primary" disabled={busy||code.length<6} onClick={()=>void enable2fa()}>{pick("فعال‌سازی","Enable")}</button></div>}{twoFactor&&<div className="customer-2fa-setup"><label><span>{pick("رمز فعلی","Current password")}</span><input type="password" value={disablePassword} onChange={e=>setDisablePassword(e.target.value)}/></label><label><span>{pick("کد 2FA","2FA code")}</span><input dir="ltr" inputMode="numeric" placeholder="000000" value={code} onChange={e=>setCode(e.target.value.replace(/\D/g,"").slice(0,8))}/></label><button className="ghost" disabled={busy} onClick={()=>void disable2fa()}>{pick("غیرفعال‌سازی 2FA","Disable 2FA")}</button></div>}</Card>
      <Card className="customer-session-card"><div><small>SESSION</small><h2>{pick("نشست فعلی","Current session")}</h2><p>{pick("با خروج، توکن این مرورگر پاک می‌شود.","Signing out removes this browser token.")}</p></div><button className="ghost" onClick={logout}>{pick("خروج از حساب","Sign out")}</button></Card>
    </section>
  </div>;
}

function SectionBody({section}:{section:Section}){
  if(section==="orders")return <OrdersBody/>;
  if(section==="wallet")return <WalletBody/>;
  if(section==="notifications")return <NotificationsBody/>;
  return <ProfileBody/>;
}

export function CustomerSectionRuntime({section}:{section:string}){
  const safe=(['orders','wallet','notifications','profile'].includes(section)?section:'orders') as Section;
  return <PortalShell type="customer" active={`/panel/${safe}`}><SectionBody section={safe}/></PortalShell>;
}
