"use client";

import {FormEvent,useCallback,useEffect,useMemo,useState} from "react";
import {createPortal} from "react-dom";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {Badge,Card} from "./ui";
import {useI18n} from "../lib/i18n";


type WalletTopup={
  id:number;
  user_id:number;
  amount_toman:number;
  payable_amount_toman?:number|null;
  method:string;
  status:string;
  crypto_asset?:string|null;
  crypto_amount?:string|null;
  crypto_rate_toman?:number|null;
  tracking_code?:string|null;
  txid?:string|null;
  sender_card_last4?:string|null;
  transfer_date?:string|null;
  transfer_time?:string|null;
  receipt_uploaded?:boolean;
  review_note?:string|null;
  created_at?:string|null;
  submitted_at?:string|null;
  approved_at?:string|null;
  rejected_at?:string|null;
  user?:{id?:number;email?:string|null;full_name?:string|null;phone?:string|null}|null;
};

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");

  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");

  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  const raw=await response.text();
  let payload:unknown=null;
  if(raw){try{payload=JSON.parse(raw);}catch{payload=raw;}}

  if(!response.ok){
    const detail=payload&&typeof payload==="object"&&"detail" in payload
      ?String((payload as {detail:unknown}).detail)
      :`API error ${response.status}`;
    throw new Error(detail);
  }

  return payload as T;
}

const money=(value:unknown)=>`${Number(value||0).toLocaleString("fa-IR")} تومان`;
const date=(value?:string|null)=>value?new Date(value).toLocaleString("fa-IR"):"—";
const isResellerBotTopup=(row:WalletTopup)=>String(row.method||"").toLowerCase().startsWith("reseller_card:");
const statusFa:Record<string,string>={
  pending_payment:"در انتظار پرداخت",
  awaiting_review:"در انتظار بررسی",
  approved:"تأیید و شارژ شده",
  rejected:"رد شده"
};
const methodFa:Record<string,string>={
  card_to_card:"کارت به کارت",
  usdt_bep20:"USDT · BEP20",
  trx_tron:"TRX · TRON",
  bnb_bsc:"BNB · BSC"
};

export function AdminPaymentsWalletTopups(){
  const {pick}=useI18n();
  const [host,setHost]=useState<HTMLElement|null>(null);
  const [rows,setRows]=useState<WalletTopup[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [rejecting,setRejecting]=useState<WalletTopup|null>(null);
  const [reason,setReason]=useState("");

  const ensureHost=useCallback(()=>{
    const section=document.querySelector<HTMLElement>(".payTransactions");
    if(!section){setHost(null);return;}

    let target=section.querySelector<HTMLElement>(".admin-wallet-topups-payments-host");
    if(!target){
      target=document.createElement("div");
      target.className="admin-wallet-topups-payments-host";
      const toolbar=section.querySelector(".payToolbar");
      if(toolbar?.nextSibling)section.insertBefore(target,toolbar.nextSibling);
      else section.appendChild(target);
    }
    setHost(target);
  },[]);

  const load=useCallback(async()=>{
    setLoading(true);setError("");
    try{
      const result=await request<WalletTopup[]>("/v1/admin/wallet/topups");
      const clean=Array.isArray(result)?result.filter(row=>!isResellerBotTopup(row)):[];
      setRows(clean);
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setLoading(false);}
  },[]);

  useEffect(()=>{
    ensureHost();
    void load();
    const observer=new MutationObserver(ensureHost);
    observer.observe(document.body,{childList:true,subtree:true});
    const timer=window.setInterval(()=>void load(),15000);
    return()=>{observer.disconnect();window.clearInterval(timer);};
  },[ensureHost,load]);

  const visible=useMemo(()=>rows.slice(0,50),[rows]);
  const reviewCount=useMemo(()=>rows.filter(row=>row.status==="awaiting_review").length,[rows]);

  const run=async(message:string,fn:()=>Promise<unknown>)=>{
    if(busy)return;
    setBusy(true);setError("");setOk("");
    try{await fn();setOk(message);await load();}
    catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  };

  const openReceipt=async(row:WalletTopup)=>{
    if(busy)return;
    const token=getCustomerToken();
    if(!token){setError("AUTH_REQUIRED");return;}
    setBusy(true);setError("");
    try{
      const response=await fetch(`${API_BASE}/v1/admin/wallet/topups/${row.id}/receipt`,{
        headers:{Authorization:`Bearer ${token}`},
        cache:"no-store",
      });
      if(!response.ok){
        let detail=pick("رسید قابل دریافت نیست.","Receipt is unavailable.");
        try{const payload=await response.json();if(payload&&typeof payload.detail==="string")detail=payload.detail;}catch{}
        throw new Error(detail);
      }
      const blob=await response.blob();
      const url=URL.createObjectURL(blob);
      const opened=window.open(url,"_blank","noopener,noreferrer");
      if(!opened)throw new Error(pick("مرورگر اجازه باز کردن رسید را نداد.","The browser blocked the receipt window."));
      window.setTimeout(()=>URL.revokeObjectURL(url),60_000);
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  };

  const approve=(row:WalletTopup)=>void run(
    pick("شارژ کیف پول تأیید شد و موجودی افزایش یافت.","Wallet top-up approved and credited."),
    ()=>request(`/v1/admin/wallet/topups/${row.id}/approve`,{method:"POST"})
  );

  const reject=(event:FormEvent)=>{
    event.preventDefault();
    if(!rejecting)return;
    const row=rejecting;
    void run(
      pick("درخواست شارژ کیف پول رد شد.","Wallet top-up rejected."),
      async()=>{
        await request(`/v1/admin/wallet/topups/${row.id}/reject`,{
          method:"POST",
          body:JSON.stringify({reason:reason.trim()||"رد توسط مدیر"})
        });
        setRejecting(null);setReason("");
      }
    );
  };

  if(!host)return null;

  return <>
    {createPortal(
      <div className="walletPaymentsMerged">
        <div className="card-head">
          <div>
            <b>{pick("شارژ کیف پول","Wallet top-ups")}</b>
            <small>{pick("فقط شارژهای مستقیم پنل مرکزی در این بخش نمایش داده می‌شوند؛ رسیدهای ربات نماینده فقط در پنل همان نماینده بررسی می‌شوند.","Only direct central-panel wallet top-ups appear here; reseller-bot receipts stay in that reseller's panel.")}</small>
          </div>
          <div className="row-actions">
            {reviewCount>0&&<Badge tone="warn">{reviewCount.toLocaleString("fa-IR")} {pick("نیاز به بررسی","to review")}</Badge>}
            <button type="button" className="ghost" disabled={loading||busy} onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button>
          </div>
        </div>

        {error&&<div className="runtime-error">{error}</div>}
        {ok&&<div className="runtime-success">{ok}</div>}

        {loading&&!rows.length?<div className="runtime-loading">…</div>:visible.length===0?<Card><div className="runtime-empty">{pick("هنوز درخواست شارژ کیف پولی ثبت نشده است.","No wallet top-up requests yet.")}</div></Card>:<div className="payIntentList">{visible.map(row=>{
          const reviewing=row.status==="awaiting_review";
          const asset=String(row.crypto_asset||"").toUpperCase();
          const isCrypto=row.method!=="card_to_card";
          return <Card className="payIntentCard" key={`wallet-topup-${row.id}`}>
            <div className="payIntentMain">
              <div className="payIntentId">
                <span>W#{row.id}</span>
                <b>{methodFa[row.method]||row.method}</b>
                <small>{date(row.created_at)}</small>
              </div>
              <div className="payIntentAmount">
                <small>{pick("شارژ کیف پول","Wallet credit")}</small>
                <b>{money(row.amount_toman)}</b>
                {isCrypto&&row.crypto_amount&&<small>{row.crypto_amount} {asset}</small>}
                {!isCrypto&&row.payable_amount_toman&&row.payable_amount_toman!==row.amount_toman&&<small>{pick("مبلغ دقیق واریز","Exact transfer")}: {money(row.payable_amount_toman)}</small>}
              </div>
              <div style={{display:"grid",gap:6,justifyItems:"end"}}>
                <Badge tone="violet">{pick("شارژ کیف پول","Wallet top-up")}</Badge>
                <Badge tone={row.status==="approved"?"ok":row.status==="rejected"?"bad":"warn"}>{statusFa[row.status]||row.status}</Badge>
                {row.receipt_uploaded&&<Badge tone="ok">{pick("رسید دارد","Receipt attached")}</Badge>}
              </div>
            </div>

            <div className="payIntentMeta">
              <span>{pick("کاربر","User")}: <b>#{row.user_id}</b></span>
              {row.user?.full_name&&<span>{pick("نام","Name")}: <b>{row.user.full_name}</b></span>}
              {row.user?.email&&<span>{pick("ایمیل","Email")}: <b dir="ltr">{row.user.email}</b></span>}
              {row.sender_card_last4&&<span>{pick("کارت مبدا","Source card")}: <b dir="ltr">•••• {row.sender_card_last4}</b></span>}
              {row.tracking_code&&<span>{pick("کد پیگیری","Tracking")}: <b dir="ltr">{row.tracking_code}</b></span>}
              {(row.transfer_date||row.transfer_time)&&<span>{pick("زمان واریز","Transfer time")}: <b dir="ltr">{row.transfer_date||""} {row.transfer_time||""}</b></span>}
              {row.txid&&<span className="wide">TXID: <b dir="ltr">{row.txid}</b></span>}
              {row.review_note&&<span className="wide">{pick("یادداشت","Note")}: <b>{row.review_note}</b></span>}
            </div>

            {(reviewing||row.receipt_uploaded)&&<div className="payIntentActions">
              {row.receipt_uploaded&&<button type="button" className="ghost" disabled={busy} onClick={()=>void openReceipt(row)}>{pick("مشاهده رسید","View receipt")}</button>}
              {reviewing&&<button type="button" className="primary" disabled={busy} onClick={()=>approve(row)}>{pick("تأیید و شارژ کیف پول","Approve & credit wallet")}</button>}
              {reviewing&&<button type="button" className="danger" disabled={busy} onClick={()=>{setRejecting(row);setReason("");}}>{pick("رد","Reject")}</button>}
            </div>}
          </Card>;
        })}</div>}
      </div>,
      host
    )}

    {rejecting&&createPortal(
      <div className="runtime-modal" role="dialog" aria-modal="true">
        <button type="button" className="runtime-modal-bg" onClick={()=>!busy&&setRejecting(null)}/>
        <form className="runtime-modal-card" onSubmit={reject}>
          <div className="card-head">
            <div><b>{pick("رد شارژ کیف پول","Reject wallet top-up")} W#{rejecting.id}</b><small>{money(rejecting.amount_toman)}</small></div>
            <button type="button" className="icon-button" onClick={()=>!busy&&setRejecting(null)}>×</button>
          </div>
          <label className="payField"><span>{pick("دلیل رد","Reason")}</span><textarea rows={4} value={reason} onChange={e=>setReason(e.target.value)} placeholder={pick("دلیل رد درخواست را بنویسید","Enter rejection reason")}/></label>
          <div className="runtime-modal-actions"><button type="button" className="ghost" onClick={()=>setRejecting(null)}>{pick("انصراف","Cancel")}</button><button className="danger" disabled={busy}>{busy?"…":pick("رد درخواست","Reject request")}</button></div>
        </form>
      </div>,
      document.body
    )}
  </>;
}
