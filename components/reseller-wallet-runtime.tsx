"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {Badge,Card,Stat} from "./ui";
import {PortalShell} from "./portal-shells";
import {useI18n} from "../lib/i18n";
import {
  resellerWalletApi,
  ResellerWalletSummary,
  ResellerWalletTopup,
  ResellerWalletTransaction,
  WalletPaymentMethod,
} from "../lib/reseller-wallet-api";

const money=(value:unknown)=>`${Number(value||0).toLocaleString("fa-IR")} تومان`;
const dateText=(value:unknown)=>{if(!value)return "—";const d=new Date(String(value));return Number.isNaN(d.getTime())?String(value):d.toLocaleString("fa-IR");};
const statusTone=(status:string):"ok"|"warn"|"bad"|"violet"=>["approved","paid","completed","success","auto_verified"].includes(status.toLowerCase())?"ok":["rejected","failed","canceled"].includes(status.toLowerCase())?"bad":"warn";
const statusFa=(status:string)=>({pending_payment:"در انتظار پرداخت",awaiting_review:"در انتظار بررسی",approved:"تأیید و شارژ شده",rejected:"رد شده",paid:"پرداخت شده",failed:"ناموفق"} as Record<string,string>)[status]||status||"—";
const today=()=>new Date().toISOString().slice(0,10);
const nowTime=()=>new Date().toTimeString().slice(0,5);
const canSubmit=(status:string)=>["pending_payment","rejected"].includes(String(status||"").toLowerCase());

function Notice({error,ok}:{error:string;ok:string}){return <>{error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}</>;}
function Empty({children}:{children:React.ReactNode}){return <div className="runtime-empty">{children}</div>;}

export function ResellerWalletRuntime(){
  const {pick}=useI18n();
  const [summary,setSummary]=useState<ResellerWalletSummary|null>(null);
  const [transactions,setTransactions]=useState<ResellerWalletTransaction[]>([]);
  const [topups,setTopups]=useState<ResellerWalletTopup[]>([]);
  const [methods,setMethods]=useState<WalletPaymentMethod[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [amount,setAmount]=useState(100000);
  const [method,setMethod]=useState("");
  const [activeTopup,setActiveTopup]=useState<ResellerWalletTopup|null>(null);
  const [proof,setProof]=useState({tracking_code:"",sender_card_last4:"",transfer_date:today(),transfer_time:nowTime(),txid:""});

  const load=async(showLoading=false)=>{
    if(showLoading)setLoading(true);
    setError("");
    const result=await Promise.allSettled([
      resellerWalletApi.summary(),
      resellerWalletApi.transactions(),
      resellerWalletApi.topups(),
      resellerWalletApi.methods(),
    ]);
    if(result[0].status==="fulfilled")setSummary(result[0].value);
    if(result[1].status==="fulfilled")setTransactions(result[1].value);
    if(result[2].status==="fulfilled")setTopups(result[2].value);
    if(result[3].status==="fulfilled")setMethods(result[3].value);
    const failed=result.find(item=>item.status==="rejected");
    if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));
    setLoading(false);
  };

  useEffect(()=>{void load(true);},[]);
  useEffect(()=>{if(!method&&methods.length)setMethod(methods[0].id);},[methods,method]);

  const pendingCount=useMemo(()=>topups.filter(row=>["pending_payment","awaiting_review"].includes(String(row.status||"").toLowerCase())).length,[topups]);
  const selectedMethod=useMemo(()=>{
    if(activeTopup?.payment_method)return activeTopup.payment_method;
    const id=String(activeTopup?.method||method||"");
    return methods.find(row=>row.id===id)||null;
  },[activeTopup,methods,method]);

  const openTopup=(row:ResellerWalletTopup)=>{
    setActiveTopup(row);
    setMethod(row.method);
    setProof({
      tracking_code:String(row.tracking_code||""),
      sender_card_last4:String(row.sender_card_last4||""),
      transfer_date:String(row.transfer_date||today()),
      transfer_time:String(row.transfer_time||nowTime()),
      txid:String(row.txid||""),
    });
    setError("");setOk("");
  };

  const createTopup=async(e:FormEvent)=>{
    e.preventDefault();
    if(busy)return;
    if(!Number.isFinite(amount)||amount<10000||amount>100000000){setError(pick("مبلغ شارژ باید بین ۱۰٬۰۰۰ تا ۱۰۰٬۰۰۰٬۰۰۰ تومان باشد.","Top-up amount must be between 10,000 and 100,000,000 Toman."));return;}
    if(!method){setError(pick("یک روش پرداخت انتخاب کنید.","Select a payment method."));return;}
    setBusy(true);setError("");setOk("");
    try{
      const row=await resellerWalletApi.createTopup(Math.trunc(amount),method);
      openTopup(row);
      setOk(pick("درخواست شارژ ساخته شد. مبلغ و مقصد پرداخت را دقیقاً طبق اطلاعات زیر پرداخت کنید.","Top-up created. Pay the exact amount to the destination shown below."));
      await load(false);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const submitProof=async(e:FormEvent)=>{
    e.preventDefault();
    if(!activeTopup||busy||!canSubmit(activeTopup.status))return;
    const type=String(activeTopup.method||"").toLowerCase();
    if(type==="card_to_card"){
      if(!proof.tracking_code.trim()){setError(pick("کد پیگیری را وارد کنید.","Enter the tracking code."));return;}
      if(!/^\d{4}$/.test(proof.sender_card_last4.trim())){setError(pick("۴ رقم آخر کارت مبدا را صحیح وارد کنید.","Enter the last 4 digits of the sender card."));return;}
      if(!proof.transfer_date||!proof.transfer_time){setError(pick("تاریخ و ساعت انتقال الزامی است.","Transfer date and time are required."));return;}
    }else if(proof.txid.trim().length<10){setError(pick("TXID معتبر را وارد کنید.","Enter a valid TXID."));return;}

    setBusy(true);setError("");setOk("");
    try{
      const row=await resellerWalletApi.submitTopup(activeTopup.id,type==="card_to_card"?{
        tracking_code:proof.tracking_code.trim(),
        sender_card_last4:proof.sender_card_last4.trim(),
        transfer_date:proof.transfer_date,
        transfer_time:proof.transfer_time,
      }:{txid:proof.txid.trim()});
      setActiveTopup(row);
      setOk(row.status==="approved"?pick("پرداخت تأیید شد و کیف پول نمایندگی شارژ شد.","Payment approved and reseller wallet credited."):pick("اطلاعات پرداخت ثبت شد و در انتظار تأیید است.","Payment proof submitted and is awaiting approval."));
      await load(false);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const walletBalance=Number(summary?.wallet_balance||0);
  const creditLimit=Number(summary?.credit_limit||0);
  const availableCredit=Number(summary?.available_credit??walletBalance+creditLimit);
  const activeStatus=String(activeTopup?.status||"").toLowerCase();

  return <PortalShell type="reseller" active="/reseller/wallet"><div className="page">
    <div className="page-head"><div><h1>{pick("کیف پول نمایندگی","Reseller Wallet")}</h1><small>{pick("شارژهای این صفحه پس از تأیید مستقیماً وارد کیف پول نمایندگی می‌شوند و خرید بسته حجم از همین موجودی انجام می‌شود.","Approved top-ups are credited directly to the reseller wallet and traffic purchases use this balance.")}</small></div><button className="ghost" disabled={busy} onClick={()=>void load(true)}>{pick("بروزرسانی","Refresh")}</button></div>
    <Notice error={error} ok={ok}/>
    {loading?<div className="runtime-loading">{pick("در حال دریافت اطلاعات کیف پول...","Loading wallet...")}</div>:<>
      <div className="stats"><Stat label={pick("موجودی کیف پول","Wallet balance")} value={money(walletBalance)}/><Stat label={pick("سقف اعتبار","Credit limit")} value={money(creditLimit)}/><Stat label={pick("اعتبار قابل استفاده","Available credit")} value={money(availableCredit)}/><Stat label={pick("شارژهای در انتظار","Pending top-ups")} value={String(pendingCount)}/></div>

      <div className="module-grid two">
        <Card className="runtime-editor"><div className="card-head"><div><b>{pick("شارژ کیف پول","Top up wallet")}</b><small>{pick("حداقل شارژ ۱۰ هزار تومان است.","Minimum top-up is 10,000 Toman.")}</small></div></div>
          <form onSubmit={createTopup}>
            <div className="setting-grid"><label className="field"><span>{pick("مبلغ شارژ (تومان)","Top-up amount (Toman)")}</span><input type="number" min={10000} max={100000000} step={1000} value={amount} onChange={e=>setAmount(Number(e.target.value))}/></label><label className="field"><span>{pick("روش پرداخت","Payment method")}</span><select value={method} onChange={e=>setMethod(e.target.value)} disabled={!methods.length}>{!methods.length&&<option value="">{pick("روش فعالی وجود ندارد","No active method")}</option>}{methods.map(row=><option value={row.id} key={row.id}>{row.title||row.id}</option>)}</select></label></div>
            <button className="primary" type="submit" disabled={busy||!method}>{busy?pick("در حال ساخت...","Creating..."):pick("ایجاد درخواست شارژ","Create top-up")}</button>
          </form>
        </Card>

        <Card><div className="card-head"><div><b>{pick("جزئیات شارژ","Top-up details")}</b><small>{activeTopup?`#${activeTopup.id}`:pick("از فرم شارژ یا سوابق پایین یک درخواست را انتخاب کنید.","Create a top-up or select one from history below.")}</small></div>{activeTopup&&<Badge tone={statusTone(activeTopup.status)}>{pick(statusFa(activeTopup.status),activeTopup.status)}</Badge>}</div>
          {!activeTopup?<Empty>{pick("درخواست فعالی انتخاب نشده است.","No top-up selected.")}</Empty>:<>
            <div className="runtime-info-list"><div><span>{pick("مبلغ شارژ","Wallet credit")}</span><b>{money(activeTopup.amount_toman)}</b></div><div><span>{pick("مبلغ دقیق پرداخت","Exact payable amount")}</span><b>{money(activeTopup.payable_amount_toman??activeTopup.amount_toman)}</b></div><div><span>{pick("روش","Method")}</span><b>{selectedMethod?.title||activeTopup.method}</b></div></div>
            {canSubmit(activeTopup.status)&&<form onSubmit={submitProof}>
              {activeTopup.method==="card_to_card"?<>
                <div className="runtime-info-list"><div><span>{pick("شماره کارت مقصد","Destination card")}</span><b dir="ltr">{selectedMethod?.card_number||"—"}</b></div><div><span>{pick("به نام","Card holder")}</span><b>{selectedMethod?.card_holder||"—"}</b></div></div>
                <div className="setting-grid"><label className="field"><span>{pick("کد پیگیری","Tracking code")}</span><input dir="ltr" value={proof.tracking_code} onChange={e=>setProof(p=>({...p,tracking_code:e.target.value}))}/></label><label className="field"><span>{pick("۴ رقم آخر کارت مبدا","Sender card last 4")}</span><input dir="ltr" inputMode="numeric" maxLength={4} value={proof.sender_card_last4} onChange={e=>setProof(p=>({...p,sender_card_last4:e.target.value.replace(/\D/g,"").slice(0,4)}))}/></label><label className="field"><span>{pick("تاریخ انتقال","Transfer date")}</span><input type="date" dir="ltr" value={proof.transfer_date} onChange={e=>setProof(p=>({...p,transfer_date:e.target.value}))}/></label><label className="field"><span>{pick("ساعت انتقال","Transfer time")}</span><input type="time" dir="ltr" value={proof.transfer_time} onChange={e=>setProof(p=>({...p,transfer_time:e.target.value}))}/></label></div>
              </>:<>
                <div className="runtime-info-list"><div><span>{pick("دارایی","Asset")}</span><b dir="ltr">{activeTopup.crypto_asset||selectedMethod?.asset||"—"}</b></div><div><span>{pick("شبکه","Network")}</span><b>{selectedMethod?.network||"—"}</b></div><div><span>{pick("مقدار دقیق ارز","Exact crypto amount")}</span><b dir="ltr">{activeTopup.crypto_amount||"—"}</b></div><div><span>{pick("آدرس مقصد","Destination address")}</span><b dir="ltr">{selectedMethod?.address||"—"}</b></div></div>
                <label className="field"><span>TXID</span><input dir="ltr" value={proof.txid} onChange={e=>setProof(p=>({...p,txid:e.target.value}))}/></label>
              </>}
              <button className="primary" type="submit" disabled={busy}>{busy?pick("در حال ثبت...","Submitting..."):pick("ثبت اطلاعات پرداخت","Submit payment proof")}</button>
            </form>}
            {activeStatus==="awaiting_review"&&<div className="runtime-info">{pick("اطلاعات پرداخت ثبت شده و در انتظار تأیید است. پس از تأیید، موجودی نمایندگی خودکار افزایش می‌یابد.","Payment proof is awaiting approval. The reseller wallet will be credited automatically after approval.")}</div>}
            {activeStatus==="approved"&&<div className="runtime-success">{pick("این شارژ تأیید شده و مبلغ آن به کیف پول نمایندگی اضافه شده است.","This top-up is approved and has been credited to the reseller wallet.")}</div>}
            {activeStatus==="rejected"&&activeTopup.review_note&&<div className="runtime-error">{pick("علت رد:","Rejection reason:")} {String(activeTopup.review_note)}</div>}
          </>}
        </Card>
      </div>

      <div className="module-grid two">
        <Card><div className="card-head"><div><b>{pick("درخواست‌های شارژ","Top-up requests")}</b><small>{pick("سوابق پرداخت و وضعیت تأیید","Payment history and approval status")}</small></div><Badge tone="violet">{topups.length}</Badge></div>{!topups.length?<Empty>{pick("هنوز درخواست شارژی ثبت نشده است.","No top-up requests yet.")}</Empty>:topups.slice(0,20).map(row=><div className="module-row" key={row.id}><div className="grow"><b>#{row.id} · {money(row.amount_toman)}</b><small>{dateText(row.created_at)} · {row.method}</small></div><Badge tone={statusTone(row.status)}>{pick(statusFa(row.status),row.status)}</Badge>{["pending_payment","rejected","awaiting_review"].includes(String(row.status||"").toLowerCase())&&<button className="mini-btn" type="button" onClick={()=>openTopup(row)}>{pick("مشاهده","View")}</button>}</div>)}</Card>
        <Card><div className="card-head"><div><b>{pick("تراکنش‌های کیف پول","Wallet transactions")}</b><small>{pick("تمام افزایش و کاهش‌های موجودی نمایندگی","All reseller wallet credits and debits")}</small></div><Badge tone="violet">{transactions.length}</Badge></div>{!transactions.length?<Empty>{pick("تراکنشی ثبت نشده است.","No wallet transactions.")}</Empty>:transactions.slice(0,30).map(row=><div className="module-row" key={row.id}><div className="grow"><b>{row.description||row.type||`#${row.id}`}</b><small>{dateText(row.created_at)} · {pick("مانده","Balance")}: {money(row.balance_after)}</small></div><strong dir="ltr">{row.amount>0?"+":""}{Number(row.amount||0).toLocaleString("fa-IR")}</strong></div>)}</Card>
      </div>
    </>}
  </div></PortalShell>;
}
