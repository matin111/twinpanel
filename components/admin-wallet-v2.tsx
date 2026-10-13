"use client";

import {useEffect,useMemo,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {Badge,Card,Shell,Stat} from "./ui";

type WalletRow={
  user_id:number;
  balance_toman:number;
  updated_at?:string|null;
  email?:string|null;
  full_name?:string|null;
  phone?:string|null;
  user?:{id?:number;email?:string|null;full_name?:string|null;phone?:string|null}|null;
};

type TopupRow={
  id:number;
  user_id:number;
  amount_toman:number;
  payable_amount_toman?:number;
  method?:string|null;
  status:string;
  crypto_asset?:string|null;
  crypto_amount?:string|null;
  crypto_rate_toman?:number|null;
  crypto_amount_usdt?:string|null;
  tracking_code?:string|null;
  txid?:string|null;
  sender_card_last4?:string|null;
  transfer_date?:string|null;
  transfer_time?:string|null;
  review_note?:string|null;
  created_at?:string|null;
  submitted_at?:string|null;
  approved_at?:string|null;
  rejected_at?:string|null;
  user?:{email?:string|null;full_name?:string|null;phone?:string|null}|null;
};

const money=(value:unknown)=>`${Number(value||0).toLocaleString("fa-IR")} تومان`;
const dateText=(value?:string|null)=>value?new Date(value).toLocaleString("fa-IR"):"—";
const methodFa:Record<string,string>={
  card_to_card:"کارت به کارت",
  usdt_bep20:"USDT · BEP20",
  trx_tron:"TRX · TRON",
  bnb_bsc:"BNB · BSC",
};
const statusFa:Record<string,string>={
  pending_payment:"در انتظار پرداخت",
  awaiting_review:"در حال بررسی",
  approved:"تأیید و شارژ شده",
  rejected:"رد شده",
};

async function api<T>(path:string,init:RequestInit={}):Promise<T>{
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

export function AdminWalletV2(){
  const {pick}=useI18n();
  const [wallets,setWallets]=useState<WalletRow[]>([]);
  const [topups,setTopups]=useState<TopupRow[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [query,setQuery]=useState("");
  const [filter,setFilter]=useState("all");
  const [userId,setUserId]=useState("");
  const [adjustAmount,setAdjustAmount]=useState("");
  const [note,setNote]=useState("");

  const load=async()=>{
    setLoading(true);setError("");
    try{
      const [walletRows,topupRows]=await Promise.all([
        api<WalletRow[]>("/v1/admin/wallet/wallets"),
        api<TopupRow[]>("/v1/admin/wallet/topups"),
      ]);
      setWallets(Array.isArray(walletRows)?walletRows:[]);
      setTopups(Array.isArray(topupRows)?topupRows:[]);
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setLoading(false);}
  };

  useEffect(()=>{void load();},[]);

  const run=async(message:string,fn:()=>Promise<unknown>)=>{
    if(busy)return;
    setBusy(true);setError("");setOk("");
    try{await fn();setOk(message);await load();}
    catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  };

  const approve=(row:TopupRow)=>void run(
    pick("شارژ کیف پول تأیید شد.","Wallet top-up approved."),
    ()=>api(`/v1/admin/wallet/topups/${row.id}/approve`,{method:"POST"}),
  );

  const reject=(row:TopupRow)=>{
    const reason=window.prompt(pick("دلیل رد درخواست شارژ","Top-up rejection reason"),"")?.trim();
    if(!reason)return;
    void run(
      pick("درخواست شارژ رد شد.","Top-up rejected."),
      ()=>api(`/v1/admin/wallet/topups/${row.id}/reject`,{
        method:"POST",
        body:JSON.stringify({reason}),
      }),
    );
  };

  const adjust=()=>{
    const uid=Number(userId);
    const amount=Number(adjustAmount);
    if(!Number.isInteger(uid)||uid<=0){setError(pick("شناسه کاربر معتبر نیست.","Invalid user ID."));return;}
    if(!Number.isInteger(amount)||amount===0){setError(pick("مبلغ باید عدد صحیح مثبت یا منفی و غیرصفر باشد.","Amount must be a non-zero integer."));return;}
    void run(
      pick("موجودی کیف پول اصلاح شد و اعلان برای کاربر ثبت شد.","Wallet balance adjusted and user notified."),
      async()=>{
        await api(`/v1/admin/wallet/wallets/${uid}/adjust`,{
          method:"POST",
          body:JSON.stringify({amount_toman:amount,note:note.trim()}),
        });
        setAdjustAmount("");setNote("");
      },
    );
  };

  const summary=useMemo(()=>({
    wallets:wallets.length,
    balance:wallets.reduce((sum,row)=>sum+Number(row.balance_toman||0),0),
    pending:topups.filter(row=>["pending_payment","awaiting_review"].includes(String(row.status))).length,
    approved:topups.filter(row=>row.status==="approved").length,
  }),[wallets,topups]);

  const filtered=useMemo(()=>topups.filter(row=>{
    if(filter!=="all"&&row.status!==filter)return false;
    const q=query.trim().toLowerCase();
    if(!q)return true;
    return [
      row.id,row.user_id,row.method,row.status,row.txid,row.tracking_code,
      row.user?.email,row.user?.full_name,row.user?.phone,
    ].some(value=>String(value??"").toLowerCase().includes(q));
  }),[topups,query,filter]);

  return <Shell active="/admin/wallet"><div className="page adminWalletV2">
    <div className="page-head"><div><h1>{pick("کیف پول","Wallet")}</h1><p className="muted">{pick("مدیریت موجودی، شارژ خودکار کارت و ارز دیجیتال","Balances, automatic card and crypto top-ups")}</p></div><button className="ghost" onClick={()=>void load()} disabled={loading||busy}>{pick("بروزرسانی","Refresh")}</button></div>

    {error&&<div className="runtime-error">{error}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}

    <div className="stats dashboard-stats">
      <Stat label={pick("کیف پول‌ها","Wallets")} value={String(summary.wallets)} icon="◉"/>
      <Stat label={pick("موجودی کل","Total balance")} value={money(summary.balance)} icon="₮"/>
      <Stat label={pick("درخواست باز","Open top-ups")} value={String(summary.pending)} icon="◷"/>
      <Stat label={pick("شارژ تأییدشده","Approved top-ups")} value={String(summary.approved)} icon="✓"/>
    </div>

    <div className="module-grid two">
      <Card>
        <div className="card-head"><div><b>{pick("اصلاح دستی موجودی","Manual balance adjustment")}</b><small>{pick("مبلغ مثبت افزایش و مبلغ منفی کاهش می‌دهد؛ برای کاربر اعلان پنل و تلگرام ثبت می‌شود.","Positive adds balance; negative subtracts it. The user is notified in panel and Telegram.")}</small></div></div>
        <label className="field"><span>User ID</span><input type="number" min={1} dir="ltr" value={userId} onChange={e=>setUserId(e.target.value)}/></label>
        <label className="field"><span>{pick("مبلغ تغییر (تومان)","Adjustment (Toman)")}</span><input type="number" dir="ltr" placeholder="50000 یا -50000" value={adjustAmount} onChange={e=>setAdjustAmount(e.target.value)}/></label>
        <label className="field"><span>{pick("توضیح","Note")}</span><input value={note} onChange={e=>setNote(e.target.value)}/></label>
        <button className="primary" disabled={busy||!userId||!adjustAmount} onClick={adjust}>{pick("ثبت اصلاح موجودی","Apply adjustment")}</button>
      </Card>

      <Card>
        <div className="card-head"><div><b>{pick("وضعیت اتوماسیون شارژ","Top-up automation")}</b><small>{pick("کارت‌به‌کارت با مبلغ یکتا و SMS Reader؛ کریپتو با TXID و بررسی شبکه","Card payments use unique amounts + SMS Reader; crypto uses TXID + on-chain verification")}</small></div></div>
        <div className="module-row"><div className="grow"><b>{pick("کارت‌به‌کارت","Card to card")}</b><small>{pick("تطبیق مبلغ دقیق پیامک بانکی","Exact bank-SMS amount matching")}</small></div><Badge tone="ok">AUTO</Badge></div>
        <div className="module-row"><div className="grow"><b>USDT · BEP20</b><small>BNB Smart Chain</small></div><Badge tone="ok">TXID</Badge></div>
        <div className="module-row"><div className="grow"><b>TRX · TRON</b><small>TRON Network</small></div><Badge tone="ok">TXID</Badge></div>
        <div className="module-row"><div className="grow"><b>BNB · BSC</b><small>BNB Smart Chain</small></div><Badge tone="ok">TXID</Badge></div>
      </Card>
    </div>

    <Card>
      <div className="card-head"><div><b>{pick("درخواست‌های شارژ","Top-up requests")}</b><small>{pick("همه ورودی‌ها از پنل کاربر و ربات در یک صف","Panel and Telegram requests in one queue")}</small></div></div>
      <div className="payToolbar"><label>⌕<input value={query} onChange={e=>setQuery(e.target.value)} placeholder={pick("جستجو با کاربر، TXID، پیگیری...","Search user, TXID, tracking...")}/></label><select value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">{pick("همه وضعیت‌ها","All statuses")}</option><option value="pending_payment">{pick("در انتظار پرداخت","Pending payment")}</option><option value="awaiting_review">{pick("در حال بررسی","Awaiting review")}</option><option value="approved">{pick("تأیید شده","Approved")}</option><option value="rejected">{pick("رد شده","Rejected")}</option></select></div>

      {loading?<div className="runtime-loading">{pick("در حال دریافت اطلاعات...","Loading...")}</div>:filtered.length===0?<div className="runtime-empty">{pick("درخواست شارژی پیدا نشد.","No top-up requests found.")}</div>:<div className="customer-list">{filtered.map(row=>{
        const method=String(row.method||"");
        const crypto=method!=="card_to_card";
        const asset=String(row.crypto_asset||(method==="usdt_bep20"?"USDT":method==="trx_tron"?"TRX":method==="bnb_bsc"?"BNB":""));
        const cryptoAmount=row.crypto_amount||row.crypto_amount_usdt;
        const review=row.status==="awaiting_review";
        const rejectable=["pending_payment","awaiting_review"].includes(row.status);
        const userLabel=row.user?.full_name||row.user?.email||`User #${row.user_id}`;
        return <div className="module-row" key={row.id}>
          <div className="grow">
            <b>#{row.id} · {methodFa[method]||method||"—"}</b>
            <small>{userLabel} · #{row.user_id} · {dateText(row.created_at)}</small>
            <small>{pick("اعتبار کیف پول","Wallet credit")}: {money(row.amount_toman)} · {crypto&&cryptoAmount?`${pick("پرداخت","Payment")}: ${cryptoAmount} ${asset}`:`${pick("پرداخت","Payment")}: ${money(row.payable_amount_toman||row.amount_toman)}`}</small>
            {crypto&&row.crypto_rate_toman&&<small>{pick("نرخ فریز‌شده","Frozen rate")}: {money(row.crypto_rate_toman)} / {asset}</small>}
            {row.txid&&<small dir="ltr">TXID: {row.txid}</small>}
            {row.tracking_code&&<small>{pick("پیگیری","Tracking")}: <span dir="ltr">{row.tracking_code}</span>{row.sender_card_last4?` · •••• ${row.sender_card_last4}`:""}</small>}
            {row.review_note&&<small>{row.review_note}</small>}
          </div>
          <Badge tone={row.status==="approved"?"ok":row.status==="rejected"?"bad":"warn"}>{statusFa[row.status]||row.status}</Badge>
          {(review||rejectable)&&<div className="row-actions">{review&&<button className="mini-btn" disabled={busy} onClick={()=>approve(row)}>{pick("تأیید","Approve")}</button>}{rejectable&&<button className="mini-btn danger" disabled={busy} onClick={()=>reject(row)}>{pick("رد","Reject")}</button>}</div>}
        </div>;
      })}</div>}
    </Card>

    <Card>
      <div className="card-head"><div><b>{pick("موجودی کاربران","Customer balances")}</b><small>{pick("آخرین موجودی ثبت‌شده هر کاربر","Latest recorded balance per customer")}</small></div></div>
      <div className="table"><table><thead><tr><th>User</th><th>{pick("نام / ایمیل","Name / Email")}</th><th>{pick("موجودی","Balance")}</th><th>{pick("آخرین بروزرسانی","Updated")}</th></tr></thead><tbody>{wallets.map(row=><tr key={row.user_id}><td>#{row.user_id}</td><td>{row.full_name||row.user?.full_name||row.email||row.user?.email||"—"}</td><td>{money(row.balance_toman)}</td><td>{dateText(row.updated_at)}</td></tr>)}</tbody></table></div>
    </Card>
  </div></Shell>;
}
