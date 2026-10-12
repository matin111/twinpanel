"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import Link from "next/link";
import {PortalShell} from "./portal-shells";
import {Card,PageHead,Badge} from "./ui";
import {useCustomerSession} from "../lib/customer-session";
import {customerApi,PaymentIntent,StoreOrder} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

type Method={id:string;title?:string;card_number?:string;card_holder?:string;address?:string;rate_toman?:number};
type Intent=PaymentIntent&{base_amount_toman?:number;payable_amount_toman?:number;has_receipt?:boolean;receipt_submitted_at?:string|null};

const MAX_RECEIPT_BYTES=12*1024*1024;
const RECEIPT_TYPES=new Set(["image/jpeg","image/png","image/webp","image/gif","application/pdf"]);
const money=(value:unknown)=>`${Number(value||0).toLocaleString("fa-IR")} تومان`;
const statusFa=(status:string)=>({pending_payment:"در انتظار پرداخت",payment_submitted:"پرداخت ثبت شده",awaiting_review:"در انتظار تأیید",approved:"تأیید شده",auto_verified:"تأیید خودکار",rejected:"رد شده",paid:"پرداخت شده"} as Record<string,string>)[status]||status||"—";

async function api<T>(path:string,init:RequestInit={},token?:string|null):Promise<T>{
  const headers=new Headers(init.headers);
  if(init.body&&!headers.has("Content-Type")&&!(init.body instanceof FormData))headers.set("Content-Type","application/json");
  if(token)headers.set("Authorization",`Bearer ${token}`);
  const response=await fetch(path,{...init,headers,cache:"no-store"});
  if(!response.ok){let message=`API error ${response.status}`;try{const p=await response.json() as {detail?:string;message?:string};message=p.detail||p.message||message;}catch{}throw new Error(message);}
  return response.status===204?undefined as T:response.json() as Promise<T>;
}

function CustomerPaymentsBody(){
  const {pick}=useI18n();
  const {token}=useCustomerSession();
  const [orders,setOrders]=useState<StoreOrder[]>([]);
  const [intents,setIntents]=useState<Intent[]>([]);
  const [methods,setMethods]=useState<Method[]>([]);
  const [orderId,setOrderId]=useState<number|null>(null);
  const [method,setMethod]=useState("");
  const [intent,setIntent]=useState<Intent|null>(null);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const [txid,setTxid]=useState("");
  const [last4,setLast4]=useState("");
  const [tracking,setTracking]=useState("");
  const [transferDate,setTransferDate]=useState("");
  const [transferTime,setTransferTime]=useState("");
  const [copied,setCopied]=useState("");
  const [receiptFile,setReceiptFile]=useState<File|null>(null);
  const [receiptKey,setReceiptKey]=useState(0);

  const load=async()=>{
    if(!token)return;
    setLoading(true);setError("");
    try{
      const [o,p,m]=await Promise.all([customerApi.orders(token),customerApi.payments(token),customerApi.paymentMethods()]);
      setOrders(Array.isArray(o)?o:[]);setIntents(Array.isArray(p)?p:[]);setMethods(Array.isArray(m?.methods)?m.methods as Method[]:[]);
      const query=typeof window!=="undefined"?Number(new URLSearchParams(window.location.search).get("order")||0):0;
      const pending=(Array.isArray(o)?o:[]).find(x=>x.id===query)|| (Array.isArray(o)?o:[]).find(x=>["pending_payment","payment_submitted","awaiting_review"].includes(x.status)) || null;
      if(pending)setOrderId(pending.id);
      const existing=(Array.isArray(p)?p:[]).find(x=>x.order_id===pending?.id&&["pending_payment","payment_submitted","awaiting_review"].includes(x.status)) as Intent|undefined;
      if(existing){setIntent(existing);setMethod(existing.method||existing.payment_method||"");}
      else if(Array.isArray(m?.methods)&&m.methods.length)setMethod(String((m.methods[0] as Method).id||""));
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setLoading(false);}
  };
  useEffect(()=>{void load();},[token]);

  const order=useMemo(()=>orders.find(x=>x.id===orderId)||null,[orders,orderId]);
  const currentMethod=useMemo(()=>methods.find(x=>x.id===(intent?.method||method))||null,[methods,intent,method]);

  const createIntent=async()=>{
    if(!token||!orderId||!method)return;
    setBusy(true);setError("");setMessage("");
    try{const row=await api<Intent>("/v1/payments/intents",{method:"POST",body:JSON.stringify({order_id:orderId,method})},token);setIntent(row);setMethod(row.method||method);setReceiptFile(null);setReceiptKey(v=>v+1);}
    catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  };

  const selectReceipt=(file:File|null)=>{
    setError("");
    if(!file){setReceiptFile(null);return;}
    if(file.size>MAX_RECEIPT_BYTES){setReceiptFile(null);setReceiptKey(v=>v+1);setError(pick("حجم رسید نباید بیشتر از ۱۲ مگابایت باشد.","Receipt must be 12 MB or smaller."));return;}
    if(!RECEIPT_TYPES.has(file.type)){setReceiptFile(null);setReceiptKey(v=>v+1);setError(pick("فرمت رسید باید JPG، PNG، WEBP، GIF یا PDF باشد.","Receipt must be JPG, PNG, WEBP, GIF or PDF."));return;}
    setReceiptFile(file);
  };

  const uploadReceipt=async(current:Intent)=>{
    if(!token||!receiptFile)return current;
    const form=new FormData();
    form.append("receipt",receiptFile,receiptFile.name);
    const uploaded=await api<Intent>(`/v1/payments/intents/${current.id}/receipt-upload`,{method:"POST",body:form},token);
    setIntent(uploaded);
    setReceiptFile(null);
    setReceiptKey(v=>v+1);
    return uploaded;
  };

  const submit=async(event:FormEvent)=>{
    event.preventDefault();if(!token||!intent)return;
    setBusy(true);setError("");setMessage("");
    try{
      const isUsdt=String(intent.method||"").startsWith("usdt_");
      let workingIntent=intent;
      if(!isUsdt){
        if(!workingIntent.has_receipt&&!receiptFile)throw new Error(pick("برای کارت‌به‌کارت تصویر رسید را انتخاب کنید.","Please select a receipt image for card payment."));
        if(receiptFile)workingIntent=await uploadReceipt(workingIntent);
      }
      const payload=isUsdt?{txid:txid.trim()}:{tracking_code:tracking.trim()||null,sender_card_last4:last4.trim(),transfer_date:transferDate.trim(),transfer_time:transferTime.trim()};
      const row=await api<Intent>(`/v1/payments/intents/${workingIntent.id}/submit`,{method:"POST",body:JSON.stringify(payload)},token);
      setIntent(row);setMessage(pick("اطلاعات و رسید پرداخت ثبت شد.","Payment details and receipt submitted."));
      void load();
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  };

  const copy=async(label:string,value:string)=>{try{await navigator.clipboard.writeText(value);setCopied(label);window.setTimeout(()=>setCopied(""),1200);}catch{}};

  if(loading)return <div className="page customer-runtime"><div className="customer-loading"><span className="customer-loader"/>{pick("در حال دریافت پرداخت‌ها...","Loading payments...")}</div></div>;

  return <div className="page customer-runtime customerPaymentsParity">
    <PageHead title={pick("پرداخت‌ها","Payments")}/>
    {error&&<div className="runtime-error">{error}</div>}{message&&<div className="runtime-success">{message}</div>}

    {order&&!["fulfilled","paid"].includes(order.status)&&<Card className="paymentCheckoutCard">
      <div className="card-head"><div><b>{pick("پرداخت سفارش","Order payment")} #{order.id}</b><small>{money(order.amount_toman)}</small></div><Badge tone="warn">{statusFa(order.status)}</Badge></div>
      {!intent?<>
        <div className="paymentMethodGrid">{methods.map(row=><button type="button" key={row.id} className={method===row.id?"active":""} onClick={()=>setMethod(row.id)}><b>{row.title||row.id}</b></button>)}</div>
        <button className="primary paymentMainAction" disabled={!method||busy} onClick={()=>void createIntent()}>{busy?"…":pick("ادامه پرداخت","Continue payment")}</button>
      </>:<form onSubmit={submit} className="paymentIntentBody">
        <div className="paymentDestination">
          <div><span>{pick("روش","Method")}</span><b>{currentMethod?.title||intent.method}</b></div>
          {intent.method==="card_to_card"?<>
            <div><span>{pick("مبلغ دقیق","Exact amount")}</span><b>{money(intent.payable_amount_toman||intent.amount_toman||order.amount_toman)}</b></div>
            <div><span>{pick("شماره کارت","Card number")}</span><b dir="ltr">{currentMethod?.card_number||"—"}</b>{currentMethod?.card_number&&<button type="button" onClick={()=>void copy("card",currentMethod.card_number!)}>{copied==="card"?"✓":"⧉"}</button>}</div>
            <div><span>{pick("به نام","Card holder")}</span><b>{currentMethod?.card_holder||"—"}</b></div>
          </>:<>
            <div><span>{pick("مقدار USDT","USDT amount")}</span><b dir="ltr">{intent.crypto_amount_usdt||"—"} USDT</b></div>
            <div><span>{pick("آدرس کیف پول","Wallet address")}</span><b dir="ltr" className="breakAll">{currentMethod?.address||"—"}</b>{currentMethod?.address&&<button type="button" onClick={()=>void copy("addr",currentMethod.address!)}>{copied==="addr"?"✓":"⧉"}</button>}</div>
          </>}
        </div>
        {["pending_payment","payment_submitted"].includes(intent.status)&&<div className="paymentSubmitFields">{intent.method==="card_to_card"?<>
          <label><span>{pick("۴ رقم آخر کارت","Last 4 card digits")}</span><input dir="ltr" maxLength={4} value={last4} onChange={e=>setLast4(e.target.value.replace(/\D/g,""))} required/></label>
          <label><span>{pick("تاریخ انتقال","Transfer date")}</span><input dir="ltr" type="date" value={transferDate} onChange={e=>setTransferDate(e.target.value)} required/></label>
          <label><span>{pick("ساعت انتقال","Transfer time")}</span><input dir="ltr" type="time" value={transferTime} onChange={e=>setTransferTime(e.target.value)} required/></label>
          <label><span>{pick("کد پیگیری","Tracking code")}</span><input dir="ltr" value={tracking} onChange={e=>setTracking(e.target.value)}/></label>
          <label className="wide paymentReceiptField"><span>{pick("رسید پرداخت","Payment receipt")}</span><div className={`paymentReceiptPicker ${receiptFile||intent.has_receipt?"ready":""}`}><input key={receiptKey} type="file" accept="image/jpeg,image/png,image/webp,image/gif,application/pdf" onChange={e=>selectReceipt(e.target.files?.[0]||null)} required={!intent.has_receipt}/><div><b>{receiptFile?receiptFile.name:intent.has_receipt?pick("رسید قبلاً ثبت شده است","Receipt already uploaded"):pick("تصویر رسید را انتخاب کنید","Choose receipt image")}</b><small>{pick("JPG، PNG، WEBP، GIF یا PDF تا ۱۲ مگابایت","JPG, PNG, WEBP, GIF or PDF up to 12 MB")}</small></div><i>{receiptFile||intent.has_receipt?"✓":"↑"}</i></div></label>
        </>:<label className="wide"><span>TXID</span><input dir="ltr" value={txid} onChange={e=>setTxid(e.target.value)} required/></label>}</div>}
        {["pending_payment","payment_submitted"].includes(intent.status)&&<button className="primary paymentMainAction" disabled={busy}>{busy?pick("در حال ثبت...","Submitting..."):pick("ثبت اطلاعات پرداخت","Submit payment")}</button>}
        {["awaiting_review","approved","auto_verified"].includes(intent.status)&&<div className="paymentStateOk"><b>{statusFa(intent.status)}</b>{intent.has_receipt&&<small>{pick("رسید پرداخت ثبت شده است.","Payment receipt uploaded.")}</small>}</div>}
      </form>}
    </Card>}

    <section className="paymentHistorySection"><div className="sectionMiniHead"><b>{pick("تاریخچه پرداخت","Payment history")}</b></div>{intents.length===0?<Card><p className="muted">{pick("پرداختی ثبت نشده است.","No payments yet.")}</p></Card>:<div className="customer-list">{intents.map(x=><Card key={x.id} className="customer-list-row"><div><b>#{x.id}</b><small>{x.created_at?new Date(x.created_at).toLocaleString("fa-IR"):"—"}</small></div><div><span>{pick("سفارش","Order")}</span><b>#{x.order_id||"—"}</b></div><div><span>{pick("روش","Method")}</span><b>{x.method||x.payment_method||"—"}</b></div>{x.has_receipt&&<div><span>{pick("رسید","Receipt")}</span><b className="receiptHistoryOk">✓ {pick("ثبت شده","Uploaded")}</b></div>}<Badge tone={["approved","auto_verified"].includes(x.status)?"ok":["rejected"].includes(x.status)?"bad":"warn"}>{statusFa(x.status)}</Badge></Card>)}</div>}</section>
    <div className="customer-actions"><Link href="/panel/orders" className="ghost">{pick("سفارش‌ها","Orders")}</Link><Link href="/panel/buy" className="primary">{pick("خرید اشتراک","Buy subscription")}</Link></div>
  </div>;
}

export function CustomerPaymentsRuntime(){return <PortalShell type="customer" active="/panel/payments"><CustomerPaymentsBody/></PortalShell>;}
