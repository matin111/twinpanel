"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {Badge,Card,Stat} from "./ui";
import {PortalShell} from "./portal-shells";
import {ResellerBotWalletTopupReview} from "./reseller-bot-wallet-topup-review";
import {resellerApi,ResellerRow} from "../lib/reseller-runtime-api";
import {useI18n} from "../lib/i18n";

const str=(row:ResellerRow,...keys:string[])=>{for(const key of keys){const value=row?.[key];if(value!==undefined&&value!==null)return String(value);}return "";};
const num=(row:ResellerRow,...keys:string[])=>{const value=Number(str(row,...keys).replace(/[,٬]/g,"")||0);return Number.isFinite(value)?value:0;};
const money=(value:number)=>`${Number(value||0).toLocaleString("fa-IR")} تومان`;
const dateText=(value:unknown)=>{if(!value)return "—";const d=new Date(String(value));return Number.isNaN(d.getTime())?String(value):d.toLocaleString("fa-IR");};
const idempotency=()=>`bot-wallet-${Date.now()}-${Math.random().toString(36).slice(2,12)}`;

function Notice({error,ok}:{error:string;ok:string}){return <>{error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}</>;}
function Empty({children}:{children:React.ReactNode}){return <div className="runtime-empty">{children}</div>;}

export function ResellerBotWalletRuntime(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<ResellerRow[]>([]);
  const [transactions,setTransactions]=useState<ResellerRow[]>([]);
  const [selected,setSelected]=useState<ResellerRow|null>(null);
  const [q,setQ]=useState("");
  const [mode,setMode]=useState<"credit"|"debit">("credit");
  const [amount,setAmount]=useState("");
  const [note,setNote]=useState("");
  const [adjustKey,setAdjustKey]=useState(()=>idempotency());
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const load=async()=>{
    setError("");
    try{setRows(await resellerApi.botWallets());}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
  };

  useEffect(()=>{void load();},[]);

  const filtered=useMemo(()=>{
    const needle=q.trim().toLowerCase();
    if(!needle)return rows;
    return rows.filter(row=>[
      row.user_id,row.full_name,row.phone,row.email,row.telegram_id,row.telegram_username,row.telegram_first_name
    ].some(value=>String(value??"").toLowerCase().includes(needle)));
  },[rows,q]);

  const totalBalance=rows.reduce((sum,row)=>sum+num(row,"balance_toman"),0);
  const funded=rows.filter(row=>num(row,"balance_toman")>0).length;

  const openWallet=async(row:ResellerRow)=>{
    const userId=Number(row.user_id||0);
    if(!userId)return;
    setSelected(row);setTransactions([]);setAmount("");setNote("");setMode("credit");setAdjustKey(idempotency());setError("");setOk("");
    setBusy(true);
    try{setTransactions(await resellerApi.botWalletTransactions(userId));}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const submit=async(event:FormEvent)=>{
    event.preventDefault();
    if(!selected||busy)return;
    const userId=Number(selected.user_id||0);
    const raw=Math.trunc(Number(amount)||0);
    if(!userId||raw<=0){setError(pick("مبلغ معتبر وارد کنید.","Enter a valid amount."));return;}
    if(note.trim().length<2){setError(pick("توضیح کوتاه برای ثبت حسابداری وارد کنید.","Enter a short accounting note."));return;}
    const signed=mode==="credit"?raw:-raw;
    setBusy(true);setError("");setOk("");
    try{
      const result=await resellerApi.botAdjustWallet(userId,{amount_toman:signed,note:note.trim(),idempotency_key:adjustKey});
      const duplicate=Boolean(result.duplicate);
      setOk(duplicate?pick("این عملیات قبلاً ثبت شده بود؛ موجودی دوباره تغییر نکرد.","This operation was already recorded; the balance was not changed again."):mode==="credit"?pick("موجودی کیف پول افزایش یافت.","Wallet credited."):pick("موجودی کیف پول کاهش یافت.","Wallet debited."));
      setAmount("");setNote("");setAdjustKey(idempotency());
      const [walletRows,txRows]=await Promise.all([resellerApi.botWallets(),resellerApi.botWalletTransactions(userId)]);
      setRows(walletRows);setTransactions(txRows);
      setSelected(walletRows.find(row=>Number(row.user_id||0)===userId)||selected);
    }catch(reason){
      // Keep adjustKey unchanged on failure. If the server committed but the
      // response was lost, retrying the same operation cannot double-credit.
      setError(reason instanceof Error?reason.message:String(reason));
    }
    finally{setBusy(false);}
  };

  return <PortalShell type="reseller" active="/reseller/bot-wallet">
    <div className="page reseller-parity-page">
      <div className="page-head">
        <div><h1>{pick("کیف پول ربات","Bot Wallet")}</h1><small>{pick("مدیریت موجودی کاربران متصل به ربات اختصاصی این نمایندگی","Manage balances for users linked to this reseller bot")}</small></div>
        <button className="ghost" type="button" onClick={()=>void load()} disabled={busy}>{pick("بروزرسانی","Refresh")}</button>
      </div>
      <Notice error={error} ok={ok}/>

      <div className="stats">
        <Stat label={pick("کاربران ربات","Bot users")} value={String(rows.length)}/>
        <Stat label={pick("دارای موجودی","Funded wallets")} value={String(funded)}/>
        <Stat label={pick("مجموع موجودی","Total balance")} value={money(totalBalance)}/>
      </div>

      <ResellerBotWalletTopupReview/>

      <Card>
        <div className="card-head"><div><b>{pick("کیف پول کاربران ربات","Bot customer wallets")}</b><small>{pick("فقط کاربرانی نمایش داده می‌شوند که با ربات همین نمایندگی /start زده‌اند.","Only users linked to this reseller bot are shown.")}</small></div><Badge tone="violet">{filtered.length}</Badge></div>
        <div className="runtime-toolbar reseller-order-toolbar"><label>⌕ <input value={q} onChange={e=>setQ(e.target.value)} placeholder={pick("جستجو با نام، یوزرنیم تلگرام یا شناسه...","Search name, Telegram username or ID...")}/></label></div>
        <div className="table"><table><thead><tr><th>{pick("کاربر","User")}</th><th>Telegram</th><th>{pick("موجودی","Balance")}</th><th>{pick("آخرین فعالیت","Last seen")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{filtered.map((row,index)=>{const userId=Number(row.user_id||0),username=str(row,"telegram_username");return <tr key={userId||index}><td><b>{str(row,"full_name","telegram_first_name")||`#${userId}`}</b><small dir="ltr">{str(row,"phone","email")||`User #${userId}`}</small></td><td><b dir="ltr">{username?`@${username.replace(/^@/,"")}`:"—"}</b><small dir="ltr">{str(row,"telegram_id")?`ID ${str(row,"telegram_id")}`:""}</small></td><td><b>{money(num(row,"balance_toman"))}</b></td><td>{dateText(row.last_seen_at)}</td><td><button className="mini-btn" type="button" onClick={()=>void openWallet(row)}>{pick("مدیریت کیف پول","Manage wallet")}</button></td></tr>})}</tbody></table></div>
        {!filtered.length&&<Empty>{pick("هنوز کاربری به ربات این نمایندگی متصل نشده است.","No user has linked to this reseller bot yet.")}</Empty>}
      </Card>

      {selected&&<div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" type="button" onClick={()=>!busy&&setSelected(null)}/><div className="runtime-modal-card reseller-sub-modal"><div className="card-head"><div><b>{pick("مدیریت کیف پول","Manage wallet")}</b><small>{str(selected,"full_name","telegram_first_name")||`#${str(selected,"user_id")}`} · {money(num(selected,"balance_toman"))}</small></div><button className="icon-button" type="button" onClick={()=>setSelected(null)}>×</button></div>
        <form onSubmit={submit}>
          <div className="setting-grid">
            <label className="field"><span>{pick("نوع عملیات","Operation")}</span><select value={mode} onChange={e=>setMode(e.target.value as "credit"|"debit")}><option value="credit">{pick("افزایش موجودی","Credit")}</option><option value="debit">{pick("کاهش موجودی","Debit")}</option></select></label>
            <label className="field"><span>{pick("مبلغ (تومان)","Amount (Toman)")}</span><input type="number" min={1} step={1} required value={amount} onChange={e=>setAmount(e.target.value)}/></label>
          </div>
          <label className="field"><span>{pick("توضیح حسابداری","Accounting note")}</span><input required minLength={2} maxLength={500} value={note} onChange={e=>setNote(e.target.value)} placeholder={pick("مثلاً شارژ دستی بابت واریز مشتری","e.g. Manual credit for customer payment")}/></label>
          {mode==="debit"&&<div className="runtime-error">{pick("کاهش موجودی فقط تا سقف موجودی فعلی مجاز است و در دفتر تراکنش ثبت می‌شود.","Debit cannot exceed the current balance and is recorded in the transaction ledger.")}</div>}
          <div className="runtime-modal-actions"><button className="ghost" type="button" onClick={()=>setSelected(null)}>{pick("بستن","Close")}</button><button className="primary" disabled={busy||Number(amount)<=0||note.trim().length<2}>{busy?"…":mode==="credit"?pick("افزایش موجودی","Credit wallet"):pick("کاهش موجودی","Debit wallet")}</button></div>
        </form>

        <div className="card-head"><div><b>{pick("آخرین تراکنش‌های همین ربات","This bot's recent transactions")}</b><small>{pick("خریدهای کیف پول این نمایندگی و تغییرات دستی همین نماینده نمایش داده می‌شوند.","Only this reseller bot's wallet purchases and manual adjustments are shown.")}</small></div><Badge tone="violet">{transactions.length}</Badge></div>
        <div className="table"><table><thead><tr><th>ID</th><th>{pick("مبلغ","Amount")}</th><th>{pick("نوع","Type")}</th><th>{pick("توضیح","Description")}</th><th>{pick("زمان","Time")}</th></tr></thead><tbody>{transactions.map((tx,index)=>{const value=num(tx,"amount_toman");return <tr key={Number(tx.id||0)||index}><td>#{str(tx,"id")}</td><td><b dir="ltr">{value>0?"+":""}{money(value)}</b></td><td>{str(tx,"kind")||"—"}</td><td>{str(tx,"description")||"—"}</td><td>{dateText(tx.created_at)}</td></tr>})}</tbody></table></div>
        {!transactions.length&&!busy&&<Empty>{pick("تراکنشی برای این ربات ثبت نشده است.","No transaction has been recorded for this bot wallet.")}</Empty>}
      </div></div>}
    </div>
  </PortalShell>;
}
