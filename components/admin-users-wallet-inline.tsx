"use client";

import {FormEvent,useCallback,useEffect,useMemo,useState} from "react";
import {createPortal} from "react-dom";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";


type WalletRow={
  user_id:number;
  balance_toman:number;
};

type WalletHistory={
  user_id:number;
  balance_toman:number;
  transactions:Array<{id:number;amount_toman:number;kind:string;description?:string|null;reference?:string|null;created_at:string;method?:string|null;tracking_code?:string|null}>;
  topups:Array<{id:number;amount_toman:number;method:string;status:string;tracking_code?:string|null;txid?:string|null;created_at:string;review_note?:string|null}>;
  purchases:Array<{id:number;source:string;kind:string;amount_toman:number;plan_name?:string|null;status:string;payment_method?:string|null;payment_status?:string|null;tracking_code?:string|null;subscription_id?:number|null;created_at:string;paid_at?:string|null}>;
  has_more_purchases:boolean;
  has_more_transactions:boolean;
  has_more_topups:boolean;
};

const walletDate=(value:string)=>{try{return new Date(value).toLocaleString("fa-IR");}catch{return value;}};
const walletKind=(kind:string)=>({
  topup:"شارژ کیف پول",admin_adjustment:"اصلاح دستی ادمین",
  store_purchase:"خرید اشتراک",purchase:"خرید اشتراک",
  wallet_payment:"پرداخت با کیف پول",refund:"بازگشت وجه"
} as Record<string,string>)[kind]||kind;
const walletStatus=(status:string)=>({
  approved:"تأیید و شارژ شده",awaiting_review:"در انتظار بررسی",
  pending_payment:"در انتظار پرداخت",rejected:"رد شده"
} as Record<string,string>)[status]||status;

type HostRow={
  userId:number;
  host:HTMLElement;
};

async function adminRequest<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");

  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");

  const response=await fetch(`${API_BASE}${path}`,{
    ...init,
    headers,
    cache:"no-store"
  });

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

const money=(value:number)=>`${Number(value||0).toLocaleString("fa-IR")} تومان`;

export function AdminUsersWalletInline(){
  const {pick}=useI18n();
  const [hosts,setHosts]=useState<HostRow[]>([]);
  const [balances,setBalances]=useState<Record<number,number>>({});
  const [userId,setUserId]=useState<number|null>(null);
  const [mode,setMode]=useState<"credit"|"debit"|"history">("credit");
  const [history,setHistory]=useState<WalletHistory|null>(null);
  const [historyLoading,setHistoryLoading]=useState(false);
  const [historySearch,setHistorySearch]=useState("");
  const [amount,setAmount]=useState("");
  const [note,setNote]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const loadBalances=useCallback(async()=>{
    try{
      const rows=await adminRequest<WalletRow[]>("/v1/admin/wallet/wallets");
      const map:Record<number,number>={};
      for(const row of Array.isArray(rows)?rows:[])map[Number(row.user_id)]=Number(row.balance_toman||0);
      setBalances(map);
    }catch{/* users page must remain usable even if wallet endpoint is unavailable */}
  },[]);

  const scan=useCallback(()=>{
    const found:HostRow[]=[];
    // User management now renders responsive cards instead of table rows.
    // Look up each card's own ID so wallet actions never attach to another user.
    const rows=document.querySelectorAll<HTMLElement>(".admin-users-runtime .admin-user-card");

    rows.forEach(row=>{
      const first=row.querySelector<HTMLElement>(".admin-user-names small");
      const actions=row.querySelector<HTMLElement>(".admin-user-card-actions");
      if(!first||!actions)return;

      const match=(first.textContent||"").match(/^#\s*(\d+)$/);
      if(!match)return;

      const id=Number(match[1]);
      if(!Number.isFinite(id)||id<=0)return;

      let host=actions.querySelector<HTMLElement>(`.admin-user-wallet-slot[data-user-id="${id}"]`);
      if(!host){
        host=document.createElement("span");
        host.className="admin-user-wallet-slot";
        host.style.cssText="grid-column:1/-1;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;align-items:center";
        host.dataset.userId=String(id);
        actions.prepend(host);
      }

      found.push({userId:id,host});
    });

    setHosts(previous=>{
      if(previous.length===found.length&&previous.every((item,index)=>item.userId===found[index]?.userId&&item.host===found[index]?.host))return previous;
      return found;
    });
  },[]);

  useEffect(()=>{
    // Render the user table first; wallet balances are secondary data.
    const walletTimer=window.setTimeout(()=>void loadBalances(),150);
    scan();
    // Watch only the user table subtree. Observing document.body caused
    // redundant full-table rescans on unrelated dashboard/header updates.
    const table=document.querySelector<HTMLElement>(".admin-users-runtime");
    const observer=new MutationObserver(scan);
    if(table)observer.observe(table,{childList:true,subtree:true});
    return()=>{window.clearTimeout(walletTimer);observer.disconnect();};
  },[loadBalances,scan]);

  const currentBalance=useMemo(()=>userId?Number(balances[userId]||0):0,[balances,userId]);

  const open=(id:number,nextMode:"credit"|"debit"|"history")=>{
    setHistory(null);
    setHistorySearch("");
    if(nextMode==="history"){
      setHistoryLoading(true);
      void adminRequest<WalletHistory>(`/v1/admin/wallet/wallets/${id}/history?limit=200`)
        .then(data=>{setHistory(data);setBalances(current=>({...current,[id]:data.balance_toman}));})
        .catch(e=>setError(e instanceof Error?e.message:String(e)))
        .finally(()=>setHistoryLoading(false));
    }
    setMode(nextMode);
    setUserId(id);
    setAmount("");
    setNote("");
    setError("");
    setOk("");
  };

  const close=()=>{
    if(busy)return;
    setUserId(null);
    setHistory(null);
    setAmount("");
    setNote("");
    setError("");
    setOk("");
  };

  const submit=async(event:FormEvent)=>{
    event.preventDefault();
    if(!userId||busy||mode==="history")return;

    const value=Number(amount.replace(/[^0-9]/g,""));
    if(!Number.isSafeInteger(value)||value<=0||value>100000000){
      setError(pick("مبلغ باید بین ۱ تا ۱۰۰ میلیون تومان باشد.","Amount must be between 1 and 100,000,000 toman."));
      return;
    }

    if(mode==="debit"&&value>currentBalance){
      setError(pick("مبلغ کاهش از موجودی فعلی بیشتر است.","Debit exceeds current wallet balance."));
      return;
    }
    if(mode==="debit"&&!window.confirm(pick(`آیا ${money(value)} از کیف پول کاربر #${userId} کسر شود؟`,`Deduct ${money(value)} from user #${userId}?`)))return;

    setBusy(true);setError("");setOk("");
    try{
      const result=await adminRequest<{balance_toman:number}>(`/v1/admin/wallet/wallets/${userId}/adjust`,{
        method:"POST",
        body:JSON.stringify({
          amount_toman:mode==="debit"?-value:value,
          note:note.trim()||(mode==="debit"?"کاهش موجودی توسط ادمین":"شارژ کیف پول توسط ادمین")
        })
      });
      setBalances(current=>({...current,[userId]:Number(result.balance_toman||0)}));
      setOk(mode==="debit"?pick("موجودی با موفقیت کسر شد و در پنل و ربات بروزرسانی می‌شود.","Balance deducted and reflected in panel and bot."):pick("کیف پول شارژ شد؛ موجودی در پنل کاربری و ربات مشترک است.","Wallet credited; balance is shared by user panel and bot."));
      setAmount("");setNote("");
      // The balance from the committed response is authoritative. A secondary
      // list refresh must not keep the money-action button busy after success.
      void loadBalances();
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  };

  return <>
    {hosts.map(({userId:id,host})=>createPortal(
      <>
        <button type="button" className="ghost" onClick={()=>open(id,"credit")} title={pick("افزایش موجودی کیف پول","Credit user wallet")}>
          {pick("➕ شارژ","➕ Credit")}
        </button>
        <button type="button" className="ghost" onClick={()=>open(id,"debit")} title={pick("کاهش موجودی کیف پول","Deduct from wallet")}>
          {pick("➖ کاهش","➖ Deduct")}
        </button>
        <button type="button" className="ghost" style={{gridColumn:"1/-1"}} onClick={()=>open(id,"history")}>
          {pick("◷ تاریخچه کیف پول","◷ Wallet history")}
        </button>
        <small style={{gridColumn:"1/-1",textAlign:"center",whiteSpace:"nowrap"}}>{pick("موجودی کیف پول","Wallet balance")}: {money(Number(balances[id]||0))}</small>
      </>,
      host,
      `wallet-${id}`
    ))}

    {userId&&createPortal(
      <div className="runtime-modal" role="dialog" aria-modal="true">
        <button type="button" className="runtime-modal-bg" onClick={close}/>
        <form className="runtime-modal-card" onSubmit={submit} style={mode==="history"?{width:"min(720px,96vw)",maxHeight:"88vh",overflowY:"auto"}:undefined}>
          <div className="card-head">
            <div>
              <b>{mode==="history"?pick("تاریخچه مالی و خرید","Financial and purchase history"):mode==="debit"?pick("کاهش موجودی کیف پول","Deduct from wallet"):pick("افزایش موجودی کیف پول","Credit user wallet")} #{userId}</b>
              <small>{pick("موجودی فعلی","Current balance")}: {money(currentBalance)}</small>
              <small>{pick("توجه: این تغییر فقط برای شناسه همین کاربر است. ربات باید به همین حساب متصل باشد.","This change affects only this user ID. The bot must be linked to the same account.")}</small>
            </div>
            <button type="button" className="icon-button" onClick={close}>×</button>
          </div>

          {error&&<div className="runtime-error">{error}</div>}
          {ok&&<div className="runtime-success">{ok}</div>}

          {mode==="history" ? <div style={{display:"grid",gap:12}}>
            {historyLoading&&<p>{pick("در حال دریافت تاریخچه…","Loading history…")}</p>}
            {history&&<>
              <div style={{display:"grid",gridTemplateColumns:"repeat(3,minmax(0,1fr))",gap:8}}>
                {[
                  [pick("کل ورودی ثبت‌شده","Recorded credits"),history.transactions.filter(t=>t.amount_toman>0).reduce((v,t)=>v+t.amount_toman,0)],
                  [pick("کل خروجی ثبت‌شده","Recorded debits"),history.transactions.filter(t=>t.amount_toman<0).reduce((v,t)=>v-t.amount_toman,0)],
                  [pick("موجودی فعلی","Current balance"),history.balance_toman]
                ].map(([label,value])=><div key={String(label)} style={{padding:10,border:"1px solid var(--line, #dbe2ed)",borderRadius:12,textAlign:"center"}}>
                  <small>{label}</small><div style={{fontWeight:700}}>{money(Number(value))}</div>
                </div>)}
              </div>
              <small>{pick("جمع ورودی و خروجی فقط براساس سوابق دریافت‌شده است و لزوماً کل تاریخچه نیست.","Totals reflect only loaded records, not necessarily the entire history.")}</small>
              <input value={historySearch} onChange={e=>setHistorySearch(e.target.value)} placeholder={pick("جستجو در تراکنش‌ها، روش، رسید و توضیحات","Search transactions, method, receipt or notes")} />
              <b>{pick("گردش مالی","Transactions")}</b>
              {history.transactions.filter(t=>[t.kind,t.description,t.reference,t.method,t.tracking_code,String(t.amount_toman)].join(" ").toLowerCase().includes(historySearch.toLowerCase())).map(t=><div key={t.id} style={{border:"1px solid var(--line, #dbe2ed)",borderRadius:12,padding:12,display:"grid",gap:5}}>
                <div style={{display:"flex",justifyContent:"space-between",gap:8,flexWrap:"wrap"}}>
                  <strong>{walletKind(t.kind)}</strong><strong style={{color:t.amount_toman>=0?"#15803d":"#dc2626",direction:"ltr"}}>{t.amount_toman>0?"+":""}{money(t.amount_toman)}</strong>
                </div>
                <small>{walletDate(t.created_at)} · #{t.id}</small>
                {t.description&&<small>{t.description}</small>}
                {t.method&&<small>{pick("روش","Method")}: {t.method}</small>}
                {t.reference&&<small style={{overflowWrap:"anywhere"}}>{pick("مرجع","Reference")}: {t.reference}</small>}
                {t.tracking_code&&<small>{pick("کد پیگیری","Tracking code")}: {t.tracking_code}</small>}
              </div>)}
              {!history.transactions.length&&<small>{pick("تراکنش ثبت‌شده‌ای یافت نشد.","No recorded transactions found.")}</small>}
              {history.has_more_transactions&&<small>{pick("فقط ۲۰۰ تراکنش آخر نمایش داده شده است.","Showing the latest 200 transactions.")}</small>}
              <b>{pick("خریدها و سفارش‌های کاربر","Customer purchases and orders")}</b>
              {(history.purchases||[]).filter(o=>[o.plan_name,o.status,o.payment_method,o.tracking_code,String(o.id),String(o.subscription_id||""),String(o.amount_toman)].join(" ").toLowerCase().includes(historySearch.toLowerCase())).map(o=><div key={o.source+"-"+o.id} style={{border:"1px solid var(--line,#dbe2ed)",borderRadius:12,padding:12,display:"grid",gap:5}}>
                <div style={{display:"flex",justifyContent:"space-between",gap:8,flexWrap:"wrap"}}>
                  <strong>{pick("خرید اشتراک","Subscription purchase")} #{o.id} · {o.plan_name||pick("پلن ثبت نشده","Unknown plan")}</strong>
                  <strong>{money(o.amount_toman)}</strong>
                </div>
                <small>{walletDate(o.created_at)} · {pick("وضعیت سفارش","Order status")}: {o.status}</small>
                {o.payment_method&&<small>{pick("روش پرداخت","Payment method")}: {o.payment_method}</small>}
                {o.payment_status&&<small>{pick("وضعیت پرداخت","Payment status")}: {o.payment_status}</small>}
                {o.subscription_id&&<small>{pick("اشتراک","Subscription")}: MV-{o.subscription_id}</small>}
                {o.tracking_code&&<small>{pick("کد پیگیری","Tracking code")}: {o.tracking_code}</small>}
              </div>)}
              {!history.purchases?.length&&<small>{pick("سفارش خریدی ثبت نشده است.","No purchases recorded.")}</small>}
              {history.has_more_purchases&&<small>{pick("فقط آخرین سفارش‌ها نمایش داده شده‌اند.","Only recent orders are shown.")}</small>}
                            <b>{pick("درخواست‌های شارژ","Top-up requests")}</b>
              {history.topups.filter(t=>[t.method,t.status,t.tracking_code,t.txid,t.review_note,String(t.amount_toman)].join(" ").toLowerCase().includes(historySearch.toLowerCase())).map(t=><div key={t.id} style={{border:"1px solid var(--line, #dbe2ed)",borderRadius:12,padding:10,display:"grid",gap:4}}>
                <div style={{display:"flex",justifyContent:"space-between",gap:8}}><strong>#{t.id} · {walletStatus(t.status)}</strong><strong>{money(t.amount_toman)}</strong></div>
                <small>{walletDate(t.created_at)} · {t.method}</small>
                {t.tracking_code&&<small>{pick("کد پیگیری","Tracking code")}: {t.tracking_code}</small>}
                {t.txid&&<small style={{overflowWrap:"anywhere"}}>TXID: {t.txid}</small>}
                {t.review_note&&<small>{t.review_note}</small>}
              </div>)}
              {!history.topups.length&&<small>{pick("درخواست شارژی ثبت نشده است.","No top-up requests found.")}</small>}
              {history.has_more_topups&&<small>{pick("فقط ۲۰۰ درخواست آخر نمایش داده شده است.","Showing the latest 200 requests.")}</small>}
            </>}
          </div> : <>
          <label className="payField">
            <span>{mode==="debit"?pick("مبلغ کاهش","Debit amount"):pick("مبلغ شارژ","Credit amount")}</span>
            <div className="inputSuffix">
              <input
                dir="ltr"
                inputMode="numeric"
                value={amount}
                onChange={e=>setAmount(e.target.value.replace(/[^0-9]/g,""))}
                placeholder="100000"
                required
              />
              <em>{pick("تومان","toman")}</em>
            </div>
          </label>

          <label className="payField">
            <span>{pick("توضیح (اختیاری)","Note (optional)")}</span>
            <textarea
              rows={3}
              value={note}
              onChange={e=>setNote(e.target.value)}
              placeholder={mode==="debit"?pick("مثلاً اصلاح موجودی؛ اختیاری","e.g. balance adjustment; optional"):pick("مثلاً شارژ هدیه؛ اختیاری","e.g. bonus credit; optional")}
            />
          </label>

          </>}
          <div className="runtime-modal-actions">
            <button type="button" className="ghost" onClick={close}>{pick("بستن","Close")}</button>
            {mode!=="history"&&<button className="primary" disabled={busy}>{busy?"…":mode==="debit"?pick("تأیید کاهش موجودی","Confirm deduction"):pick("تأیید و شارژ کیف پول","Confirm wallet credit")}</button>}
          </div>
        </form>
      </div>,
      document.body
    )}
  </>;
}
