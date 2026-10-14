"use client";

import {useEffect,useState} from "react";
import {Badge,Card} from "./ui";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

type Row=Record<string,unknown>;

const text=(row:Row,key:string)=>String(row?.[key]??"");
const number=(row:Row,key:string)=>Number(row?.[key]??0)||0;
const money=(value:number)=>`${Number(value||0).toLocaleString("fa-IR")} تومان`;
const dateText=(value:unknown)=>{if(!value)return "—";const d=new Date(String(value));return Number.isNaN(d.getTime())?String(value):d.toLocaleString("fa-IR");};

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body)headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  let payload:unknown=null;
  try{payload=await response.json();}catch{}
  if(!response.ok){
    if(payload&&typeof payload==="object"&&"detail" in payload)throw new Error(String((payload as {detail:unknown}).detail));
    throw new Error(`API error ${response.status}`);
  }
  return payload as T;
}

export function ResellerBotWalletTopupReview(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<Row[]>([]);
  const [busy,setBusy]=useState<number|null>(null);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const load=async()=>{
    setError("");
    try{setRows(await request<Row[]>("/v1/reseller/bot-commerce/wallet-topups"));}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
  };

  useEffect(()=>{void load();},[]);

  const openReceipt=async(id:number)=>{
    const token=getCustomerToken();
    if(!token){setError("AUTH_REQUIRED");return;}
    setError("");
    try{
      const response=await fetch(`${API_BASE}/v1/reseller/bot-commerce/wallet-topups/${id}/receipt`,{headers:{Authorization:`Bearer ${token}`},cache:"no-store"});
      if(!response.ok){
        let detail=`API error ${response.status}`;
        try{const payload=await response.json();if(payload&&typeof payload==="object"&&"detail" in payload)detail=String((payload as {detail:unknown}).detail);}catch{}
        throw new Error(detail);
      }
      const blob=await response.blob();
      const url=URL.createObjectURL(blob);
      const opened=window.open(url,"_blank","noopener,noreferrer");
      if(!opened){setError(pick("مرورگر اجازه باز کردن رسید را نداد.","Browser blocked the receipt window."));}
      window.setTimeout(()=>URL.revokeObjectURL(url),60_000);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
  };

  const approve=async(id:number)=>{
    if(!confirm(pick("این شارژ کیف پول تأیید شود؟","Approve this wallet top-up?")))return;
    setBusy(id);setError("");setOk("");
    try{
      const result=await request<Row>(`/v1/reseller/bot-commerce/wallet-topups/${id}/approve`,{method:"POST"});
      const notified=result.telegram_notified!==false;
      setOk(notified
        ?pick("شارژ تأیید شد، موجودی افزایش یافت و پیام برای کاربر ارسال شد.","Top-up approved, wallet credited, and the user was notified.")
        :pick("شارژ تأیید شد و موجودی افزایش یافت؛ اما پیام تلگرام ارسال نشد.","Top-up approved and wallet credited, but Telegram notification failed."));
      await load();
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(null);}
  };

  const reject=async(id:number)=>{
    const reason=prompt(pick("دلیل رد درخواست را وارد کنید:","Enter rejection reason:"),pick("اطلاعات پرداخت تأیید نشد","Payment could not be verified"));
    if(reason===null)return;
    setBusy(id);setError("");setOk("");
    try{
      const result=await request<Row>(`/v1/reseller/bot-commerce/wallet-topups/${id}/reject`,{method:"POST",body:JSON.stringify({reason:reason.trim()})});
      const notified=result.telegram_notified!==false;
      setOk(notified
        ?pick("درخواست رد شد و نتیجه برای کاربر در ربات ارسال شد.","Top-up rejected and the user was notified in Telegram.")
        :pick("درخواست رد شد؛ اما پیام تلگرام برای کاربر ارسال نشد.","Top-up rejected, but Telegram notification failed."));
      await load();
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(null);}
  };

  const pending=rows.filter(row=>text(row,"status")==="awaiting_review");

  return <Card>
    <div className="card-head">
      <div>
        <b>{pick("درخواست‌های شارژ کارت‌به‌کارت ربات","Bot card-to-card wallet top-ups")}</b>
        <small>{pick("رسید را بررسی کنید؛ نتیجه تأیید یا رد از همان ربات نماینده برای کاربر ارسال می‌شود. درخواست‌های ناقص قدیمی خودکار پاک می‌شوند.","Review the receipt; approval or rejection is sent to the user from the reseller bot. Stale incomplete requests are removed automatically.")}</small>
      </div>
      <div className="action-row"><Badge tone="violet">{pending.length}</Badge><button className="mini-btn" type="button" onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div>
    </div>

    {error&&<div className="runtime-error">{error}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}

    <div className="table"><table>
      <thead><tr><th>ID</th><th>{pick("کاربر","User")}</th><th>{pick("مبلغ شارژ","Credit")}</th><th>{pick("مبلغ واریز","Paid")}</th><th>{pick("رسید","Receipt")}</th><th>{pick("کد پیگیری","Tracking")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("زمان","Time")}</th><th>{pick("عملیات","Actions")}</th></tr></thead>
      <tbody>{rows.slice(0,100).map((row,index)=>{const id=number(row,"id"),username=text(row,"telegram_username"),status=text(row,"status"),receipt=Boolean(row.receipt_uploaded);return <tr key={id||index}>
        <td>#{id}</td>
        <td><b>{text(row,"customer_name")||`#${number(row,"user_id")}`}</b><small dir="ltr">{username?`@${username.replace(/^@/,"")}`:text(row,"telegram_id")||"—"}</small></td>
        <td><b>{money(number(row,"amount_toman"))}</b></td>
        <td>{money(number(row,"payable_amount_toman"))}</td>
        <td>{receipt?<button className="mini-btn" type="button" onClick={()=>void openReceipt(id)}>{pick("مشاهده رسید","View receipt")}</button>:<Badge tone="bad">{pick("بدون رسید","No receipt")}</Badge>}</td>
        <td><code dir="ltr">{text(row,"tracking_code")||"—"}</code></td>
        <td><Badge tone={status==="approved"?"ok":status==="rejected"?"bad":"violet"}>{status||"—"}</Badge></td>
        <td>{dateText(row.submitted_at??row.created_at)}</td>
        <td><div className="action-row">{status==="awaiting_review"&&<><button className="mini-btn" type="button" disabled={busy===id||!receipt} onClick={()=>void approve(id)}>{pick("تأیید","Approve")}</button><button className="mini-btn danger" type="button" disabled={busy===id} onClick={()=>void reject(id)}>{pick("رد","Reject")}</button></>}</div></td>
      </tr>})}</tbody>
    </table></div>
    {!rows.length&&<div className="runtime-empty">{pick("هنوز درخواست قابل بررسی یا سابقه‌ای ثبت نشده است.","No reviewable top-ups or history yet.")}</div>}
  </Card>;
}
