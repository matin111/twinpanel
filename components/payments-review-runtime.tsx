"use client";

import {useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell} from "./ui";
import {matchesPaymentReviewFilter,needsPaymentReview,PaymentReviewFilter} from "../lib/payment-review-filters";
import {adminApi,AdminUser,RuntimeRow} from "../lib/admin-api";
import {AnyRow,parityApi} from "../lib/admin-parity-api";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {paymentDateTehran} from "../lib/payment-date-tehran";

type PaymentKind="purchase"|"wallet";

type ReviewRow={
  key:string;
  kind:PaymentKind;
  id:number;
  userId:number;
  amount:number;
  method:string;
  status:string;
  displayStatus:string;
  createdAt:unknown;
  submittedAt:unknown;
  hasReceipt:boolean;
  txid:string;
  trackingCode:string;
  orderId:number|null;
  sourceLabel:string;
};

const finalStatuses=new Set(["approved","auto_verified","paid","rejected","completed","fulfilled"]);
const reviewStatuses=new Set(["awaiting_review","payment_submitted","submitted","review","waiting"]);

function money(value:number){return `${Number(value||0).toLocaleString("fa-IR")} تومان`;}
function dateText(value:unknown){return paymentDateTehran(value);}
function n(value:unknown){const x=Number(value||0);return Number.isFinite(x)?x:0;}
function s(value:unknown){return String(value??"").trim();}

// Keep accounting statuses untouched. A wallet credit is persisted as
// "approved" for ledger idempotency even when its origin is an automatic
// SMS-reader or confirmed blockchain verification.
function adminPaymentDisplayStatus(kind:PaymentKind,status:string,reviewNote:unknown):string{
  const value=status.trim().toLowerCase();
  if(kind==="wallet"&&value==="approved"&&
      /^auto-credit:(?:sms-reader:|crypto:)/i.test(String(reviewNote??"").trim())){
    return "auto_verified";
  }
  return value;
}

function statusLabel(status:string,pick:(fa:string,en:string)=>string){
  switch(status.toLowerCase()){
    case "pending_payment":return pick("در انتظار پرداخت","Pending payment");
    case "payment_submitted":return pick("اطلاعات پرداخت ارسال شده","Payment submitted");
    case "awaiting_review":return pick("در انتظار بررسی","Awaiting review");
    case "approved":return pick("تأیید شده","Approved");
    case "auto_verified":return pick("تأیید خودکار","Auto verified");
    case "rejected":return pick("رد شده","Rejected");
    default:return status||"—";
  }
}

function methodLabel(method:string){
  switch(method){
    case "card_to_card":return "کارت به کارت";
    case "usdt_trc20":return "USDT · TRC20";
    case "usdt_bep20":return "USDT · BEP20";
    case "trx_tron":return "TRX · TRON";
    case "bnb_bsc":return "BNB · BSC";
    default:return method||"—";
  }
}

function statusTone(status:string):"ok"|"warn"|"bad"|"violet"{
  const value=status.toLowerCase();
  if(["approved","auto_verified","paid","completed","fulfilled"].includes(value))return "ok";
  if(["rejected","failed","canceled"].includes(value))return "bad";
  if(reviewStatuses.has(value))return "violet";
  return "warn";
}

function userName(user:AdminUser|undefined,userId:number){
  if(!user)return `#${userId}`;
  return user.full_name||user.email||`#${userId}`;
}

export function PaymentsReviewRuntime(){
  const {pick}=useI18n();
  const [purchases,setPurchases]=useState<RuntimeRow[]>([]);
  const [wallets,setWallets]=useState<AnyRow[]>([]);
  const [users,setUsers]=useState<AdminUser[]>([]);
  const [filter,setFilter]=useState<PaymentReviewFilter>("all");
  const [query,setQuery]=useState("");
  const [busyKey,setBusyKey]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const load=async(quiet=false)=>{
    if(!quiet)setError("");

    // User names are secondary metadata. Do not block the payment table on a
    // potentially large /admin/users response.
    void adminApi.users().then(setUsers).catch(()=>{});

    const result=await Promise.allSettled([
      adminApi.payments(),
      parityApi.walletTopups(),
    ]);

    if(result[0].status==="fulfilled")setPurchases(result[0].value);
    if(result[1].status==="fulfilled")setWallets(result[1].value);

    const failed=result.find(item=>item.status==="rejected");
    if(!quiet&&failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));
  };

  useEffect(()=>{void load();},[]);

  const rows=useMemo<ReviewRow[]>(()=>{
    const purchaseRows=purchases.map(row=>({
      key:`purchase:${n(row.id)}`,
      kind:"purchase" as const,
      id:n(row.id),
      userId:n(row.user_id),
      amount:n(row.payable_amount_toman||row.base_amount_toman||row.amount_toman),
      method:s(row.method),
      status:s(row.status),
      displayStatus:s(row.status),
      createdAt:row.created_at,
      submittedAt:row.receipt_submitted_at||row.submitted_at,
      hasReceipt:Boolean(row.has_receipt),
      txid:s(row.txid),
      trackingCode:s(row.tracking_code),
      orderId:n(row.order_id)||null,
      sourceLabel:pick("خرید اشتراک","Subscription purchase"),
    }));
    const walletRows=wallets.map(row=>{
      const method=s(row.method);
      const status=s(row.status);
      const trackingCode=s(row.tracking_code);
      // The backend returns receipt_uploaded explicitly. A tracking code is
      // NOT an uploaded image; never advertise a missing attachment as a
      // viewable receipt or inflate the "New receipts" count.
      const hasReceipt=Boolean(row.receipt_uploaded);
      return {
        key:`wallet:${n(row.id)}`,
        kind:"wallet" as const,
        id:n(row.id),
        userId:n(row.user_id),
        amount:n(row.payable_amount_toman||row.amount_toman),
        method,
        status,
        displayStatus:adminPaymentDisplayStatus("wallet",status,row.review_note),
        createdAt:row.created_at,
        submittedAt:row.submitted_at,
        hasReceipt,
        txid:s(row.txid),
        trackingCode,
        orderId:null,
        sourceLabel:pick("شارژ کیف پول","Wallet top-up"),
      };
    });
    return [...purchaseRows,...walletRows].sort((a,b)=>{
      const at=new Date(String(a.createdAt||0)).getTime()||0;
      const bt=new Date(String(b.createdAt||0)).getTime()||0;
      return bt-at;
    });
  },[purchases,wallets,pick]);

  const userMap=useMemo(()=>new Map(users.map(user=>[user.id,user])),[users]);

  // The KPI counters and their click filters share the same predicate:
  // clicking a card must reveal exactly the payment rows counted by it.
  const pendingRows=rows.filter(row=>matchesPaymentReviewFilter(row,"needs_review"));
  const receiptRows=rows.filter(row=>matchesPaymentReviewFilter(row,"new_receipts"));
  const walletPending=rows.filter(row=>matchesPaymentReviewFilter(row,"wallet_review"));
  const purchasePending=rows.filter(row=>matchesPaymentReviewFilter(row,"purchase_review"));

  const selectFilter=(next:PaymentReviewFilter)=>{
    setFilter(next);
    setQuery(""); // Old search terms must not hide rows counted in the card.
  };

  const selectedFilterLabel:Record<PaymentReviewFilter,string>={
    all:pick("همه پرداخت‌ها","All payments"),
    purchase:pick("همه خریدهای اشتراک","All subscription purchases"),
    wallet:pick("همه شارژهای کیف پول","All wallet top-ups"),
    needs_review:pick("نیاز به بررسی","Needs review"),
    new_receipts:pick("رسید تصویری جدید","New receipts"),
    purchase_review:pick("خرید اشتراک نیازمند بررسی","Subscription purchases to review"),
    wallet_review:pick("شارژ کیف پول نیازمند بررسی","Wallet top-ups to review"),
  };

  const filtered=useMemo(()=>{
    const q=query.trim().toLowerCase();
    return rows.filter(row=>{
      if(!matchesPaymentReviewFilter(row,filter))return false;
      if(!q)return true;
      const user=userMap.get(row.userId);
      return [row.id,row.userId,row.amount,row.method,row.status,row.txid,row.trackingCode,row.orderId,user?.email,user?.full_name,row.sourceLabel]
        .some(value=>String(value??"").toLowerCase().includes(q));
    });
  },[rows,filter,query,userMap]);

  const markRow=(row:ReviewRow,status:string)=>{
    const stamp=new Date().toISOString();
    if(row.kind==="purchase"){
      setPurchases(prev=>prev.map(item=>n(item.id)===row.id?{...item,status,verified_at:status==="approved"?stamp:item.verified_at,rejected_at:status==="rejected"?stamp:item.rejected_at}:item));
    }else{
      setWallets(prev=>prev.map(item=>n(item.id)===row.id?{...item,status,approved_at:status==="approved"?stamp:item.approved_at,rejected_at:status==="rejected"?stamp:item.rejected_at}:item));
    }
  };

  const act=async(key:string,label:string,fn:()=>Promise<unknown>,optimistic?:()=>void)=>{
    if(busyKey)return;
    setBusyKey(key);setError("");setOk("");

    // TWINPANEL_PAYMENT_REVIEW_OPTIMISTIC_V2
    // Remove the row from the review queue immediately. Approval endpoints
    // commit payment state before slow provisioning continues in background,
    // so the admin UI must not look stuck while account delivery is running.
    optimistic?.();

    try{
      await fn();
      setOk(label);

      // Reconcile after a short delay instead of replacing the optimistic row
      // immediately with a concurrent/stale list response. The delayed refresh
      // keeps the UI truthful without requiring a manual page reload.
      window.setTimeout(()=>{void load(true);},1500);
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
      // Roll back the optimistic state from the authoritative API if approval
      // actually failed.
      void load(true);
    }finally{
      setBusyKey("");
    }
  };

  const openReceipt=async(row:ReviewRow)=>{
    setError("");
    const popup=window.open("about:blank","_blank");

    if(!popup){
      setError(pick("مرورگر اجازه باز کردن رسید را نداد. Pop-up را برای این سایت فعال کنید.","The browser blocked the receipt window. Allow pop-ups for this site."));
      return;
    }

    try{
      popup.opener=null;
      popup.document.open();
      popup.document.write(`<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><title>رسید پرداخت #${row.id}</title><style>html,body{height:100%;margin:0}body{display:grid;place-items:center;background:#0b0f18;color:#e5e7eb;font-family:system-ui,-apple-system,sans-serif}.box{padding:24px;text-align:center}.spinner{width:34px;height:34px;margin:0 auto 14px;border:3px solid #30384a;border-top-color:#8b5cf6;border-radius:50%;animation:s .8s linear infinite}@keyframes s{to{transform:rotate(360deg)}}</style></head><body><div class="box"><div class="spinner"></div><div>در حال دریافت رسید پرداخت...</div></div></body></html>`);
      popup.document.close();
    }catch{}

    try{
      const token=getCustomerToken();
      if(!token)throw new Error("AUTH_REQUIRED");

      const receiptPath=row.kind==="wallet"
        ?`/v1/admin/wallet/topups/${row.id}/receipt`
        :`/v1/payments/admin/intents/${row.id}/receipt`;
      const response=await fetch(`${API_BASE}${receiptPath}`,{
        headers:{Authorization:`Bearer ${token}`},
        cache:"no-store",
      });

      if(!response.ok){
        let detail=`API error ${response.status}`;
        try{
          const payload=await response.json() as {detail?:unknown};
          if(typeof payload.detail==="string")detail=payload.detail;
        }catch{}
        throw new Error(detail);
      }

      const blob=await response.blob();
      if(!blob.size)throw new Error(pick("فایل رسید خالی است.","The receipt file is empty."));

      const url=URL.createObjectURL(blob);
      if(popup.closed){URL.revokeObjectURL(url);return;}
      popup.location.replace(url);
      window.setTimeout(()=>URL.revokeObjectURL(url),300_000);
    }catch(e){
      const message=e instanceof Error?e.message:String(e);
      setError(message);

      try{
        if(!popup.closed){
          popup.document.open();
          popup.document.write(`<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><title>خطای نمایش رسید</title><style>html,body{height:100%;margin:0}body{display:grid;place-items:center;background:#0b0f18;color:#f3f4f6;font-family:system-ui,-apple-system,sans-serif}.box{max-width:620px;padding:28px;text-align:center}.error{color:#fca5a5;font-weight:700;margin-bottom:10px}.hint{color:#9ca3af;font-size:14px}</style></head><body><div class="box"><div class="error">نمایش رسید ناموفق بود</div><div class="hint">به پنل برگردید و دوباره تلاش کنید.</div></div></body></html>`);
          popup.document.close();
        }
      }catch{
        popup.close();
      }
    }
  };

  const approve=(row:ReviewRow)=>{
    if(row.kind==="purchase")return act(row.key,pick("پرداخت خرید تأیید شد","Purchase payment approved"),()=>adminApi.approvePayment(row.id),()=>markRow(row,"approved"));
    return act(row.key,pick("شارژ کیف پول تأیید شد","Wallet top-up approved"),()=>parityApi.walletApprove(row.id),()=>markRow(row,"approved"));
  };

  const reject=(row:ReviewRow)=>{
    const reason=window.prompt(pick("دلیل رد پرداخت","Reject reason"),"")||"";
    if(!reason.trim())return;
    if(row.kind==="purchase")void act(row.key,pick("پرداخت خرید رد شد","Purchase payment rejected"),()=>adminApi.rejectPayment(row.id,reason.trim()),()=>markRow(row,"rejected"));
    else void act(row.key,pick("شارژ کیف پول رد شد","Wallet top-up rejected"),()=>parityApi.walletReject(row.id,reason.trim()),()=>markRow(row,"rejected"));
  };

  return <Shell active="/admin/payments"><div className="page payment-review-center">
    <div className="page-head"><div><h1>{pick("پرداخت‌ها","Payments")}</h1></div><div className="action-row"><button className="ghost" onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div></div>
    {error&&<div className="runtime-error">{error}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}

    <div className="stats dashboard-stats payment-review-quick-filters" role="group" aria-label={pick("فیلتر سریع رسید و پرداخت‌ها","Quick receipt and payment filters")}>
      {([
        {id:"needs_review",label:pick("نیاز به بررسی","Needs review"),value:pendingRows.length,icon:"◫"},
        {id:"new_receipts",label:pick("رسید تصویری جدید","New receipts"),value:receiptRows.length,icon:"▧"},
        {id:"purchase_review",label:pick("خرید اشتراک","Subscription purchases"),value:purchasePending.length,icon:"◇"},
        {id:"wallet_review",label:pick("شارژ کیف پول","Wallet top-ups"),value:walletPending.length,icon:"◉"},
      ] as const).map(item=>
        <button
          key={item.id} type="button"
          className={`card stat payment-review-filter-card${filter===item.id?" active":""}`}
          aria-pressed={filter===item.id}
          aria-label={`${item.label}: ${item.value} · ${pick("نمایش رسیدهای این دسته","Show payments in this category")}`}
          onClick={()=>selectFilter(item.id)}
        >
          <span className="stat-icon" aria-hidden="true">{item.icon}</span>
          <span className="payment-review-stat-text"><small>{item.label}</small><b>{item.value.toLocaleString("fa-IR")}</b></span>
        </button>
      )}
    </div>

    <Card>
      <div className="runtime-toolbar" style={{gap:10,flexWrap:"wrap"}}>
        <div className="action-row">
          <button type="button" className={filter==="all"?"primary":"ghost"} onClick={()=>selectFilter("all")}>{pick("همه","All")}</button>
          <button type="button" className={filter==="purchase"?"primary":"ghost"} onClick={()=>selectFilter("purchase")}>{pick("خرید اشتراک","Purchases")}</button>
          <button type="button" className={filter==="wallet"?"primary":"ghost"} onClick={()=>selectFilter("wallet")}>{pick("شارژ کیف پول","Wallet")}</button>
          <button type="button" className={filter==="new_receipts"?"primary":"ghost"} onClick={()=>selectFilter("new_receipts")}>{pick("رسیدهای جدید","New receipts")}</button>
        </div>
        <label>⌕ <input value={query} onChange={e=>setQuery(e.target.value)} placeholder={pick("جستجو در پرداخت‌ها...","Search payments...")}/></label>
        <span className="payment-review-active-filter" aria-live="polite">{selectedFilterLabel[filter]} · {filtered.length.toLocaleString("fa-IR")}</span>
      </div>

      <div className="table"><table>
        <thead><tr>
          <th>{pick("نوع","Type")}</th>
          <th>{pick("شناسه","ID")}</th>
          <th>{pick("کاربر","User")}</th>
          <th>{pick("مبلغ","Amount")}</th>
          <th>{pick("روش","Method")}</th>
          <th>{pick("رسید / مدرک","Receipt / Proof")}</th>
          <th>{pick("وضعیت","Status")}</th>
          <th>{pick("زمان ارسال","Submitted")}</th>
          <th>{pick("عملیات","Actions")}</th>
        </tr></thead>
        <tbody>{filtered.map(row=>{
          const status=row.status.toLowerCase();
          const user=userMap.get(row.userId);
          const reviewable=needsPaymentReview(row);
          const proofCode=row.txid?`TXID: ${row.txid}`:row.trackingCode?`${pick("کد رهگیری","Tracking code")}: ${row.trackingCode}`:"";
          return <tr key={row.key}>
            <td><Badge tone={row.kind==="purchase"?"violet":"warn"}>{row.sourceLabel}</Badge></td>
            <td>{row.hasReceipt?<button type="button" className="payment-review-receipt-link" onClick={()=>void openReceipt(row)} aria-label={pick(`مشاهده رسید شماره ${row.id}`,`Open receipt #${row.id}`)}>#{row.id}</button>:<>#{row.id}</>}{row.orderId?<small style={{display:"block"}}>Order #{row.orderId}</small>:null}</td>
            <td><b>{userName(user,row.userId)}</b><small style={{display:"block"}}>{user?.email||`User #${row.userId}`}</small></td>
            <td>{money(row.amount)}</td>
            <td>{methodLabel(row.method)}</td>
            <td><div style={{display:"grid",gap:6,maxWidth:320}}>
              {row.hasReceipt&&<button type="button" className="payment-review-receipt-link" onClick={()=>void openReceipt(row)}>{pick("✓ مشاهده رسید تصویری","✓ View receipt image")}</button>}
              {proofCode?<span dir="ltr" style={{display:"block",wordBreak:"break-all",fontSize:11}}>{proofCode}</span>:!row.hasReceipt?<span>{pick("ارسال نشده","Not submitted")}</span>:null}
            </div></td>
            <td><Badge tone={statusTone(status)}>{statusLabel(row.displayStatus,pick)}</Badge></td>
            <td>{dateText(row.submittedAt||row.createdAt)}</td>
            <td><div className="row-actions">
              {row.hasReceipt&&<button className="mini-btn" onClick={()=>void openReceipt(row)}>{pick("مشاهده رسید","View receipt")}</button>}
              {reviewable&&<button className="mini-btn" disabled={busyKey===row.key} onClick={()=>void approve(row)}>{pick("تأیید","Approve")}</button>}
              {reviewable&&<button className="mini-btn danger" disabled={busyKey===row.key} onClick={()=>reject(row)}>{pick("رد","Reject")}</button>}
            </div></td>
          </tr>;
        })}</tbody>
      </table></div>
      {filtered.length===0&&<div className="runtime-empty" role="status">
        {pick("پرداخت یا رسیدی برای این فیلتر پیدا نشد.","No payments or receipts match this filter.")}
      </div>}
    </Card>
  </div></Shell>;
}