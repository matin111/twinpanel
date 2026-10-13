"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import Link from "next/link";
import {Badge,Card,PageHead} from "./ui";
import {PortalShell} from "./portal-shells";
import {customerApi,Wallet,WalletPaymentMethod,WalletTransaction,WalletTopup} from "../lib/customer-api";
import {useCustomerSession} from "../lib/customer-session";
import {useI18n} from "../lib/i18n";


type WalletMethodV2=WalletPaymentMethod&{
  asset?:string;
  network?:string;
  auto_verify?:boolean;
};

type WalletTopupV2=WalletTopup&{
  crypto_asset?:string|null;
  crypto_amount?:string|null;
  crypto_rate_toman?:number|null;
};

const money=(value:unknown)=>`${Number(value||0).toLocaleString("fa-IR")} تومان`;
const statusFa=(status:string)=>({
  pending_payment:"در انتظار پرداخت",
  awaiting_review:"در حال تأیید خودکار",
  approved:"تأیید و شارژ شده",
  rejected:"رد شده"
} as Record<string,string>)[status]||status||"—";
const tone=(status:string):"ok"|"warn"|"bad"=>status==="approved"?"ok":status==="rejected"?"bad":"warn";

async function copyText(value:string){
  try{await navigator.clipboard.writeText(value);return true;}catch{return false;}
}

function CustomerWalletV2Body(){
  const {pick}=useI18n();
  const {token}=useCustomerSession();
  const [wallet,setWallet]=useState<Wallet|null>(null);
  const [transactions,setTransactions]=useState<WalletTransaction[]>([]);
  const [topups,setTopups]=useState<WalletTopupV2[]>([]);
  const [methods,setMethods]=useState<WalletMethodV2[]>([]);
  const [amount,setAmount]=useState("");
  const [method,setMethod]=useState("");
  const [active,setActive]=useState<WalletTopupV2|null>(null);
  const [tracking,setTracking]=useState("");
  const [last4,setLast4]=useState("");
  const [transferDate,setTransferDate]=useState("");
  const [transferTime,setTransferTime]=useState("");
  const [txid,setTxid]=useState("");
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const [copied,setCopied]=useState("");

  const load=async()=>{
    if(!token)return;
    setLoading(true);setError("");
    try{
      const [w,t,u,m]=await Promise.all([
        customerApi.wallet(token),
        customerApi.walletTransactions(token),
        customerApi.walletTopups(token),
        customerApi.walletMethods(token)
      ]);
      const methodRows=(Array.isArray(m)?m:(m.methods||[])) as WalletMethodV2[];
      setWallet(w);setTransactions(t);setTopups(u as WalletTopupV2[]);setMethods(methodRows);
      if(!method&&methodRows.length)setMethod(methodRows[0].id);
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setLoading(false);}
  };

  useEffect(()=>{void load();},[token]);

  const selected=useMemo(()=>{
    const id=active?.method||method;
    return methods.find(row=>row.id===id)||active?.payment_method as WalletMethodV2|undefined||null;
  },[methods,active,method]);

  const isCrypto=Boolean(active&&active.method!=="card_to_card");
  const asset=String(active?.crypto_asset||selected?.asset||(active?.method==="usdt_bep20"?"USDT":active?.method==="trx_tron"?"TRX":active?.method==="bnb_bsc"?"BNB":"")).toUpperCase();
  const cryptoAmount=String(active?.crypto_amount||active?.crypto_amount_usdt||"");

  const create=async()=>{
    if(!token||!method)return;
    const numeric=Number(amount.replace(/\D/g,""));
    if(numeric<10000){setError(pick("حداقل مبلغ شارژ ۱۰٬۰۰۰ تومان است.","Minimum top-up is 10,000 toman."));return;}
    setBusy(true);setError("");setMessage("");
    try{
      const row=await customerApi.createWalletTopup(token,numeric,method) as WalletTopupV2;
      setActive(row);setTxid("");setTracking("");setLast4("");setTransferDate("");setTransferTime("");
      setMessage(pick("درخواست شارژ ساخته شد؛ مبلغ نمایش‌داده‌شده برای همین درخواست ثابت است.","Top-up created; the displayed quote is frozen for this request."));
      await load();
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  };

  const submit=async(event:FormEvent)=>{
    event.preventDefault();
    if(!token||!active)return;
    setBusy(true);setError("");setMessage("");
    try{
      const payload=isCrypto
        ?{txid:txid.trim()}
        :{tracking_code:tracking.trim(),sender_card_last4:last4.trim(),transfer_date:transferDate,transfer_time:transferTime};
      const row=await customerApi.submitWalletTopup(token,active.id,payload) as WalletTopupV2;
      setActive(row);
      setMessage(isCrypto
        ?pick("TXID ثبت شد؛ شبکه به‌صورت خودکار بررسی می‌شود و پس از تأیید، موجودی خودکار اضافه می‌شود.","TXID submitted; the chain will be checked automatically and the wallet credited after confirmation.")
        :pick("اطلاعات ثبت شد؛ SMS Reader مبلغ دقیق را به‌صورت خودکار تطبیق می‌دهد.","Submitted; SMS Reader will automatically match the exact amount."));
      await load();
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  };

  const copy=async(key:string,value:string)=>{if(await copyText(value)){setCopied(key);setTimeout(()=>setCopied(""),1200);}};

  if(loading)return <div className="page customer-runtime"><div className="customer-loading">{pick("در حال دریافت کیف پول...","Loading wallet...")}</div></div>;

  return <div className="page customer-runtime customer-wallet-2027">
    <div className="customer-page-title"><div><span>WALLET</span><PageHead title={pick("کیف پول","Wallet")}/></div><Link href="/panel/buy" className="ghost">{pick("خرید اشتراک","Buy subscription")}</Link></div>
    {error&&<div className="customer-inline-warning">{error}</div>}{message&&<div className="runtime-success">{message}</div>}

    <section className="customer-wallet-hero"><div><small>{pick("موجودی قابل استفاده","AVAILABLE BALANCE")}</small><strong>{money(wallet?.balance_toman)}</strong><span>{pick("شارژ پنل و ربات از همین موجودی مشترک استفاده می‌کنند.","Panel and Telegram bot share this balance.")}</span></div><div className="customer-wallet-orbit"><i/><i/><b>◉</b></div></section>

    <section className="customer-wallet-layout">
      <Card className="customer-wallet-topup-card">
        <div className="customer-section-head"><div><small>TOP UP</small><h2>{pick("افزایش موجودی","Add balance")}</h2></div>{active&&<button type="button" className="ghost" onClick={()=>{setActive(null);setMessage("");}}>{pick("درخواست جدید","New request")}</button>}</div>

        {!active?<>
          <label className="customer-money-input"><span>{pick("مبلغی که وارد کیف پول می‌شود","Wallet credit amount")}</span><div><input inputMode="numeric" dir="ltr" placeholder="500000" value={amount} onChange={e=>setAmount(e.target.value.replace(/\D/g,""))}/><em>{pick("تومان","toman")}</em></div></label>
          <div className="customer-method-grid">{methods.map(row=><button type="button" key={row.id} className={method===row.id?"active":""} onClick={()=>setMethod(row.id)}><i>{row.id==="card_to_card"?"◫":row.asset==="TRX"?"T":row.asset==="BNB"?"B":"₮"}</i><span><b>{row.title||row.id}</b><small>{row.id==="card_to_card"?pick("تأیید خودکار با SMS Reader","SMS auto verification"):`${row.asset||"Crypto"} · ${row.network||""}`}</small></span></button>)}</div>
          {!methods.length&&<p className="muted">{pick("روش شارژ فعالی وجود ندارد.","No top-up method is enabled.")}</p>}
          <button type="button" className="primary customer-wide-action" disabled={busy||!method} onClick={()=>void create()}>{busy?"…":pick("ساخت درخواست شارژ","Create top-up")}</button>
        </>:<form onSubmit={submit} className="customer-topup-payment">
          <div className="customer-topup-summary">
            <div><small>{pick("درخواست","Request")}</small><b>#{active.id}</b></div>
            <div><small>{pick("موجودی افزوده‌شونده","Wallet credit")}</small><b>{money(active.amount_toman)}</b></div>
            <div><small>{pick("مبلغ دقیق پرداخت","Exact payment")}</small><b>{isCrypto?`${cryptoAmount||"—"} ${asset}`:money(active.payable_amount_toman||active.amount_toman)}</b></div>
            <Badge tone={tone(active.status)}>{statusFa(active.status)}</Badge>
          </div>

          {isCrypto?<>
            <div className="customer-payment-destination"><span>{pick("مقدار دقیق","Exact amount")}</span><code>{cryptoAmount||"—"} {asset}</code>{cryptoAmount&&<button type="button" onClick={()=>void copy("amount",cryptoAmount)}>{copied==="amount"?"✓":pick("کپی","Copy")}</button>}</div>
            <div className="customer-payment-destination"><span>{pick("نرخ فریز‌شده","Frozen rate")}</span><code>{active.crypto_rate_toman?`${money(active.crypto_rate_toman)} / ${asset}`:"—"}</code></div>
            <div className="customer-payment-destination"><span>{pick("آدرس کیف پول","Wallet address")}</span><code>{selected?.address||"—"}</code>{selected?.address&&<button type="button" onClick={()=>void copy("address",String(selected.address))}>{copied==="address"?"✓":pick("کپی","Copy")}</button>}</div>
          </>:<>
            <div className="customer-payment-destination"><span>{pick("شماره کارت","Card number")}</span><code>{selected?.card_number||"—"}</code>{selected?.card_number&&<button type="button" onClick={()=>void copy("card",String(selected.card_number))}>{copied==="card"?"✓":pick("کپی","Copy")}</button>}</div>
            {selected?.card_holder&&<div className="customer-payment-holder">{pick("به نام","Card holder")}: <b>{selected.card_holder}</b></div>}
            <div className="customer-inline-warning">{pick("مبلغ دقیق نمایش‌داده‌شده را بدون گرد کردن و دقیقاً همان عدد واریز کنید تا SMS Reader خودکار تطبیق دهد.","Pay the exact displayed amount so SMS Reader can match it automatically.")}</div>
          </>}

          {["pending_payment","rejected"].includes(active.status)&&<div className="customer-topup-fields">
            {isCrypto?<label className="wide"><span>TXID</span><input dir="ltr" value={txid} onChange={e=>setTxid(e.target.value)} required/></label>:<>
              <label><span>{pick("۴ رقم آخر کارت","Last 4 digits")}</span><input dir="ltr" inputMode="numeric" maxLength={4} value={last4} onChange={e=>setLast4(e.target.value.replace(/\D/g,""))} required/></label>
              <label><span>{pick("کد پیگیری","Tracking code")}</span><input dir="ltr" value={tracking} onChange={e=>setTracking(e.target.value)} required/></label>
              <label><span>{pick("تاریخ انتقال","Transfer date")}</span><input dir="ltr" type="date" value={transferDate} onChange={e=>setTransferDate(e.target.value)} required/></label>
              <label><span>{pick("ساعت انتقال","Transfer time")}</span><input dir="ltr" type="time" value={transferTime} onChange={e=>setTransferTime(e.target.value)} required/></label>
            </>}
          </div>}

          {["pending_payment","rejected"].includes(active.status)&&<button className="primary customer-wide-action" disabled={busy}>{busy?"…":pick("ثبت پرداخت","Submit payment")}</button>}
          {active.status==="awaiting_review"&&<div className="paymentStateOk"><b>{pick("در حال تأیید خودکار","Automatic verification in progress")}</b><small>{isCrypto?pick("شبکه هر چند ثانیه دوباره بررسی می‌شود.","The blockchain is checked again automatically every few seconds."):pick("با دریافت پیامک بانکی، شارژ خودکار انجام می‌شود.","The wallet will be credited when the bank SMS arrives.")}</small></div>}
          {active.status==="approved"&&<div className="runtime-success">{pick("این شارژ تأیید شده و به موجودی کیف پول اضافه شده است.","This top-up has been approved and credited.")}</div>}
        </form>}
      </Card>

      <Card><div className="card-head"><div><b>{pick("درخواست‌های اخیر","Recent top-ups")}</b><small>{pick("پنل و ربات در همین لیست ثبت می‌شوند","Panel and Telegram requests share this history")}</small></div></div>{topups.slice(0,10).map(row=><div className="module-row" key={row.id}><div className="grow"><b>#{row.id} · {money(row.amount_toman)}</b><small>{row.method||"—"}</small></div><Badge tone={tone(row.status)}>{statusFa(row.status)}</Badge></div>)}</Card>
    </section>

    <Card><div className="card-head"><b>{pick("گردش حساب","Wallet ledger")}</b></div>{transactions.length?<div className="table"><table><thead><tr><th>{pick("زمان","Time")}</th><th>{pick("شرح","Description")}</th><th>{pick("مبلغ","Amount")}</th></tr></thead><tbody>{transactions.slice(0,30).map(row=><tr key={row.id}><td>{new Date(row.created_at).toLocaleString("fa-IR")}</td><td>{row.description||row.kind||"—"}</td><td dir="ltr">{Number(row.amount_toman||row.amount||0)>0?"+":""}{Number(row.amount_toman||row.amount||0).toLocaleString("fa-IR")} تومان</td></tr>)}</tbody></table></div>:<p className="muted">{pick("هنوز تراکنشی ثبت نشده است.","No wallet transactions yet.")}</p>}</Card>
  </div>;
}

export function CustomerWalletV2(){
  return <PortalShell role="customer"><CustomerWalletV2Body/></PortalShell>;
}
