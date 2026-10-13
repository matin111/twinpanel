"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell} from "./ui";
import {API_BASE,api as routes} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

type Intent={
  id:number;order_id?:number|null;user_id?:number|null;method?:string;status?:string;
  base_amount_toman?:number;payable_amount_toman?:number;crypto_amount_usdt?:string|null;
  tracking_code?:string|null;has_receipt?:boolean;receipt_submitted_at?:string|null;
  txid?:string|null;sender_card_last4?:string|null;transfer_date?:string|null;transfer_time?:string|null;
  created_at?:string|null;submitted_at?:string|null;verified_at?:string|null;rejected_at?:string|null;
};

type PaymentSettings={
  card_enabled:boolean;card_number:string;card_holder:string;
  usdt_trc20_enabled:boolean;usdt_trc20_address:string;
  usdt_bep20_enabled:boolean;usdt_bep20_address:string;
  usdt_rate_toman:number;
  sms_reader_enabled:boolean;sms_auto_verify:boolean;sms_allowed_senders:string;
  unique_amount_max_extra:number;
  auto_rate_enabled:boolean;crypto_auto_verify:boolean;
  live_rate_toman?:number;live_rate_provider?:string|null;live_rate_updated_at?:string|null;live_rate_error?:string|null;
};

type LiveRate={
  ok:boolean;auto_rate_enabled:boolean;crypto_auto_verify:boolean;
  rate_toman:number;provider?:string|null;updated_at?:string|null;error?:string|null;
};

const defaultSettings:PaymentSettings={
  card_enabled:false,card_number:"",card_holder:"",
  usdt_trc20_enabled:false,usdt_trc20_address:"",
  usdt_bep20_enabled:false,usdt_bep20_address:"",
  usdt_rate_toman:0,sms_reader_enabled:false,sms_auto_verify:false,sms_allowed_senders:"",
  unique_amount_max_extra:999,auto_rate_enabled:true,crypto_auto_verify:true
};

const statusLabel:Record<string,string>={
  pending_payment:"در انتظار پرداخت",payment_submitted:"پرداخت ثبت شده",awaiting_review:"در انتظار بررسی",
  approved:"تأیید شده",auto_verified:"تأیید خودکار",rejected:"رد شده",paid:"پرداخت شده"
};
const methodLabel:Record<string,string>={card_to_card:"کارت به کارت",usdt_trc20:"USDT · TRC20",usdt_bep20:"USDT · BEP20"};
const money=(value:unknown)=>`${Number(value||0).toLocaleString("fa-IR")} تومان`;
const date=(value?:string|null)=>value?new Date(value).toLocaleString("fa-IR"):"—";

async function paymentRequest<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  if(response.status===204)return undefined as T;
  const raw=await response.text();
  let payload:unknown=null;
  if(raw){try{payload=JSON.parse(raw);}catch{payload=raw;}}
  if(!response.ok){
    const detail=payload&&typeof payload==="object"&&"detail" in payload?String((payload as {detail:unknown}).detail):`API error ${response.status}`;
    throw new Error(detail);
  }
  return payload as T;
}

function Toggle({label,sub,checked,onChange}:{label:string;sub?:string;checked:boolean;onChange:(value:boolean)=>void}){
  return <label className="payGatewayToggle"><span><b>{label}</b>{sub&&<small>{sub}</small>}</span><input type="checkbox" checked={checked} onChange={e=>onChange(e.target.checked)}/><i/></label>;
}

export function AdminPaymentsRuntime(){
  const {pick}=useI18n();
  const [tab,setTab]=useState<"transactions"|"gateways">("transactions");
  const [rows,setRows]=useState<Intent[]>([]);
  const [settings,setSettings]=useState<PaymentSettings>(defaultSettings);
  const [liveRate,setLiveRate]=useState<LiveRate|null>(null);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [query,setQuery]=useState("");
  const [filter,setFilter]=useState("all");
  const [rejecting,setRejecting]=useState<Intent|null>(null);
  const [rejectReason,setRejectReason]=useState("");

  const refreshLiveRate=async()=>{
    try{
      const rate=await paymentRequest<LiveRate>("/v1/payments/admin/live-rate");
      setLiveRate(rate);
    }catch{/* keep last known live rate */}
  };

  const load=async()=>{
    setLoading(true);setError("");
    try{
      const [paymentRows,paymentSettings,rate]=await Promise.all([
        paymentRequest<Intent[]>(routes.payments.adminIntents),
        paymentRequest<Partial<PaymentSettings>>(routes.payments.adminSettings),
        paymentRequest<LiveRate>("/v1/payments/admin/live-rate")
      ]);
      setRows(Array.isArray(paymentRows)?paymentRows:[]);
      setSettings({...defaultSettings,...paymentSettings});
      setLiveRate(rate);
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setLoading(false);}
  };
  useEffect(()=>{void load();},[]);
  useEffect(()=>{
    const timer=window.setInterval(()=>{void refreshLiveRate();},10000);
    return()=>window.clearInterval(timer);
  },[]);

  const summary=useMemo(()=>({
    total:rows.length,
    review:rows.filter(x=>["payment_submitted","awaiting_review"].includes(String(x.status))).length,
    approved:rows.filter(x=>["approved","auto_verified","paid"].includes(String(x.status))).length,
    rejected:rows.filter(x=>x.status==="rejected").length
  }),[rows]);

  const filtered=useMemo(()=>rows.filter(row=>{
    const status=String(row.status||"");
    if(filter!=="all"&&status!==filter)return false;
    const q=query.trim().toLowerCase();
    if(!q)return true;
    return [row.id,row.order_id,row.user_id,row.method,row.status,row.tracking_code,row.txid].some(x=>String(x??"").toLowerCase().includes(q));
  }),[rows,query,filter]);

  const run=async(message:string,fn:()=>Promise<unknown>)=>{
    if(busy)return;setBusy(true);setError("");setOk("");
    try{await fn();setOk(message);await load();}
    catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  };

  const approve=(row:Intent)=>void run(pick("پرداخت تأیید شد.","Payment approved."),()=>paymentRequest(`/v1/payments/admin/intents/${row.id}/approve`,{method:"POST"}));
  const reject=(event:FormEvent)=>{event.preventDefault();if(!rejecting)return;void run(pick("پرداخت رد شد.","Payment rejected."),async()=>{
    await paymentRequest(`/v1/payments/admin/intents/${rejecting.id}/reject`,{method:"POST",body:JSON.stringify({reason:rejectReason.trim()||"Rejected by admin"})});
    setRejecting(null);setRejectReason("");
  });};

  const saveSettings=(event:FormEvent)=>{event.preventDefault();void run(pick("تنظیمات درگاه‌ها ذخیره شد.","Gateway settings saved."),()=>paymentRequest(routes.payments.adminSettings,{method:"PUT",body:JSON.stringify(settings)}));};

  const forceRateRefresh=()=>void run(pick("نرخ USDT بروزرسانی شد.","USDT rate refreshed."),()=>paymentRequest("/v1/payments/admin/live-rate/refresh",{method:"POST"}));

  const openReceipt=async(row:Intent)=>{
    try{
      const token=getCustomerToken();if(!token)throw new Error("AUTH_REQUIRED");
      const response=await fetch(`${API_BASE}/v1/payments/admin/intents/${row.id}/receipt`,{headers:{Authorization:`Bearer ${token}`},cache:"no-store"});
      if(!response.ok)throw new Error(`API error ${response.status}`);
      const blob=await response.blob();const url=URL.createObjectURL(blob);window.open(url,"_blank","noopener,noreferrer");
      window.setTimeout(()=>URL.revokeObjectURL(url),60000);
    }catch(e){setError(e instanceof Error?e.message:String(e));}
  };

  const activeGateways=[settings.card_enabled,settings.usdt_trc20_enabled,settings.usdt_bep20_enabled].filter(Boolean).length;
  const displayedRate=Number(liveRate?.rate_toman||settings.live_rate_toman||settings.usdt_rate_toman||0);

  return <Shell active="/admin/payments"><div className="page adminPayments2027">
    <div className="payPageHead"><div><span>{pick("مالی و فروش","Sales & Finance")}</span><h1>{pick("پرداخت‌ها و درگاه‌ها","Payments & Gateways")}</h1></div><button className="ghost" onClick={()=>void load()} disabled={loading||busy}>{pick("بروزرسانی","Refresh")}</button></div>

    {error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}

    <div className="paySummaryGrid">
      <Card><small>{pick("کل تراکنش‌ها","All transactions")}</small><b>{summary.total.toLocaleString("fa-IR")}</b><i>▣</i></Card>
      <Card><small>{pick("نیاز به بررسی","Needs review")}</small><b>{summary.review.toLocaleString("fa-IR")}</b><i>◷</i></Card>
      <Card><small>{pick("تأیید شده","Approved")}</small><b>{summary.approved.toLocaleString("fa-IR")}</b><i>✓</i></Card>
      <Card><small>{pick("درگاه فعال","Active gateways")}</small><b>{activeGateways.toLocaleString("fa-IR")}</b><i>◈</i></Card>
    </div>

    <div className="payTabs"><button className={tab==="transactions"?"active":""} onClick={()=>setTab("transactions")}>{pick("تراکنش‌ها","Transactions")}</button><button className={tab==="gateways"?"active":""} onClick={()=>setTab("gateways")}>{pick("درگاه‌ها","Gateways")}</button></div>

    {tab==="transactions"?<section className="payTransactions">
      <div className="payToolbar"><label>⌕<input value={query} onChange={e=>setQuery(e.target.value)} placeholder={pick("جستجو با شناسه، کاربر، TXID...","Search ID, user, TXID...")}/></label><select value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">{pick("همه وضعیت‌ها","All statuses")}</option><option value="awaiting_review">{pick("در انتظار بررسی","Awaiting review")}</option><option value="payment_submitted">{pick("پرداخت ثبت شده","Submitted")}</option><option value="approved">{pick("تأیید شده","Approved")}</option><option value="auto_verified">{pick("تأیید خودکار","Auto verified")}</option><option value="rejected">{pick("رد شده","Rejected")}</option></select></div>
      {loading?<div className="runtime-loading">{pick("در حال دریافت پرداخت‌ها...","Loading payments...")}</div>:filtered.length===0?<Card><div className="runtime-empty">{pick("تراکنشی پیدا نشد.","No transactions found.")}</div></Card>:<div className="payIntentList">{filtered.map(row=>{
        const status=String(row.status||"");const review=["payment_submitted","awaiting_review"].includes(status);
        return <Card className="payIntentCard" key={row.id}>
          <div className="payIntentMain"><div className="payIntentId"><span>#{row.id}</span><b>{methodLabel[String(row.method)]||row.method||"—"}</b><small>{date(row.created_at)}</small></div><div className="payIntentAmount"><small>{pick("مبلغ پرداخت","Payment amount")}</small><b>{row.crypto_amount_usdt?`${row.crypto_amount_usdt} USDT`:money(row.payable_amount_toman??row.base_amount_toman)}</b></div><Badge tone={["approved","auto_verified","paid"].includes(status)?"ok":status==="rejected"?"bad":"warn"}>{statusLabel[status]||status||"—"}</Badge></div>
          <div className="payIntentMeta"><span>{pick("سفارش","Order")}: <b>#{row.order_id??"—"}</b></span><span>{pick("کاربر","User")}: <b>#{row.user_id??"—"}</b></span>{row.sender_card_last4&&<span>{pick("کارت","Card")}: <b dir="ltr">•••• {row.sender_card_last4}</b></span>}{row.tracking_code&&<span>{pick("پیگیری","Tracking")}: <b dir="ltr">{row.tracking_code}</b></span>}{row.txid&&<span className="wide">TXID: <b dir="ltr">{row.txid}</b></span>}</div>
          <div className="payIntentActions">{row.has_receipt&&<button className="ghost" onClick={()=>void openReceipt(row)}>{pick("مشاهده رسید","View receipt")}</button>}{review&&<><button className="primary" disabled={busy} onClick={()=>approve(row)}>{pick("تأیید","Approve")}</button><button className="danger" disabled={busy} onClick={()=>{setRejecting(row);setRejectReason("");}}>{pick("رد پرداخت","Reject")}</button></>}</div>
        </Card>;
      })}</div>}
    </section>:<form className="payGateways" onSubmit={saveSettings}>
      <div className="gatewayGrid">
        <Card className={`gatewayCard ${settings.card_enabled?"enabled":""}`}><div className="gatewayHead"><div className="gatewayIcon">◫</div><div><b>{pick("کارت به کارت","Card to card")}</b><small>{pick("پرداخت ریالی با مبلغ یکتا","Toman payment with unique amount")}</small></div><Badge tone={settings.card_enabled?"ok":"bad"}>{settings.card_enabled?pick("فعال","Active"):pick("غیرفعال","Inactive")}</Badge></div><Toggle label={pick("فعال بودن کارت به کارت","Enable card to card")} checked={settings.card_enabled} onChange={v=>setSettings(s=>({...s,card_enabled:v}))}/><label className="payField"><span>{pick("شماره کارت","Card number")}</span><input dir="ltr" value={settings.card_number||""} onChange={e=>setSettings(s=>({...s,card_number:e.target.value}))}/></label><label className="payField"><span>{pick("نام صاحب کارت","Card holder")}</span><input value={settings.card_holder||""} onChange={e=>setSettings(s=>({...s,card_holder:e.target.value}))}/></label><label className="payField"><span>{pick("حداکثر مبلغ اضافه برای یکتاسازی","Maximum unique amount extra")}</span><div className="inputSuffix"><input type="number" min={10} max={999} value={settings.unique_amount_max_extra||999} onChange={e=>setSettings(s=>({...s,unique_amount_max_extra:Number(e.target.value)}))}/><em>{pick("تومان","Toman")}</em></div></label></Card>

        <Card className={`gatewayCard ${settings.usdt_trc20_enabled?"enabled":""}`}><div className="gatewayHead"><div className="gatewayIcon">₮</div><div><b>USDT · TRC20</b><small>TRON Network</small></div><Badge tone={settings.usdt_trc20_enabled?"ok":"bad"}>{settings.usdt_trc20_enabled?pick("فعال","Active"):pick("غیرفعال","Inactive")}</Badge></div><Toggle label={pick("فعال بودن TRC20","Enable TRC20")} checked={settings.usdt_trc20_enabled} onChange={v=>setSettings(s=>({...s,usdt_trc20_enabled:v}))}/><label className="payField"><span>{pick("آدرس کیف پول","Wallet address")}</span><textarea dir="ltr" rows={3} value={settings.usdt_trc20_address||""} onChange={e=>setSettings(s=>({...s,usdt_trc20_address:e.target.value}))}/></label></Card>

        <Card className={`gatewayCard ${settings.usdt_bep20_enabled?"enabled":""}`}><div className="gatewayHead"><div className="gatewayIcon">₮</div><div><b>USDT · BEP20</b><small>BNB Smart Chain</small></div><Badge tone={settings.usdt_bep20_enabled?"ok":"bad"}>{settings.usdt_bep20_enabled?pick("فعال","Active"):pick("غیرفعال","Inactive")}</Badge></div><Toggle label={pick("فعال بودن BEP20","Enable BEP20")} checked={settings.usdt_bep20_enabled} onChange={v=>setSettings(s=>({...s,usdt_bep20_enabled:v}))}/><label className="payField"><span>{pick("آدرس کیف پول","Wallet address")}</span><textarea dir="ltr" rows={3} value={settings.usdt_bep20_address||""} onChange={e=>setSettings(s=>({...s,usdt_bep20_address:e.target.value}))}/></label></Card>

        <Card className="gatewayCard gatewayAutomation"><div className="gatewayHead"><div className="gatewayIcon">⌁</div><div><b>{pick("نرخ و تأیید خودکار","Rate & Auto verification")}</b><small>{pick("SMS Reader، بلاکچین و نرخ زنده USDT","SMS Reader, blockchain and live USDT rate")}</small></div><Badge tone={settings.auto_rate_enabled?"ok":"warn"}>{settings.auto_rate_enabled?pick("خودکار","Auto"):pick("دستی","Manual")}</Badge></div>
          <label className="payField"><span>{pick("نرخ لحظه‌ای هر USDT","Live USDT rate")}</span><div className="inputSuffix"><input type="text" readOnly value={displayedRate?displayedRate.toLocaleString("fa-IR"):"—"}/><em>{pick("تومان","Toman")}</em></div><small>{liveRate?.provider?`${liveRate.provider} · ${date(liveRate.updated_at)}`:pick("در انتظار دریافت نرخ...","Waiting for live rate...")}</small>{liveRate?.error&&<small>{liveRate.error}</small>}</label>
          <Toggle label={pick("دریافت خودکار نرخ USDT","Automatic USDT rate")} sub={pick("بروزرسانی خودکار هر چند ثانیه","Refresh automatically every few seconds")} checked={settings.auto_rate_enabled} onChange={v=>setSettings(s=>({...s,auto_rate_enabled:v}))}/>
          {!settings.auto_rate_enabled&&<label className="payField"><span>{pick("نرخ دستی هر USDT","Manual USDT rate")}</span><div className="inputSuffix"><input type="number" min={0} value={settings.usdt_rate_toman||0} onChange={e=>setSettings(s=>({...s,usdt_rate_toman:Number(e.target.value)}))}/><em>{pick("تومان","Toman")}</em></div></label>}
          <button type="button" className="ghost" disabled={busy} onClick={forceRateRefresh}>{pick("دریافت نرخ همین حالا","Refresh rate now")}</button>
          <Toggle label="SMS Reader" sub={pick("خواندن پیامک‌های بانکی","Read bank SMS messages")} checked={settings.sms_reader_enabled} onChange={v=>setSettings(s=>({...s,sms_reader_enabled:v}))}/>
          <Toggle label={pick("تأیید خودکار کارت‌به‌کارت","Automatic card payment verification")} sub={pick("تطبیق مبلغ یکتا با پیامک بانکی","Match unique amount with bank SMS")} checked={settings.sms_auto_verify} onChange={v=>setSettings(s=>({...s,sms_auto_verify:v}))}/>
          <Toggle label={pick("تأیید خودکار ارز دیجیتال","Automatic crypto verification")} sub={pick("بررسی TXID روی TRON و BNB Smart Chain","Verify TXID on TRON and BNB Smart Chain")} checked={settings.crypto_auto_verify} onChange={v=>setSettings(s=>({...s,crypto_auto_verify:v}))}/>
          <label className="payField"><span>{pick("فرستنده‌های مجاز پیامک","Allowed SMS senders")}</span><textarea rows={3} value={settings.sms_allowed_senders||""} onChange={e=>setSettings(s=>({...s,sms_allowed_senders:e.target.value}))} placeholder={pick("هر فرستنده در یک خط یا با کاما","One sender per line or comma-separated")}/></label>
        </Card>
      </div>
      <div className="gatewaySaveBar"><div><b>{pick("تنظیمات درگاه‌ها","Gateway settings")}</b><small>{pick("تغییرات پس از ذخیره برای کاربران فعال می‌شود.","Changes become available after saving.")}</small></div><button className="primary" disabled={busy}>{busy?"…":pick("ذخیره تنظیمات","Save settings")}</button></div>
    </form>}

    {rejecting&&<div className="runtime-modal"><button className="runtime-modal-bg" onClick={()=>setRejecting(null)} aria-label="close"/><form className="runtime-modal-card" onSubmit={reject}><div className="card-head"><div><b>{pick("رد پرداخت","Reject payment")} #{rejecting.id}</b><small>{money(rejecting.payable_amount_toman??rejecting.base_amount_toman)}</small></div><button type="button" className="icon-button" onClick={()=>setRejecting(null)}>×</button></div><label><span>{pick("دلیل رد","Rejection reason")}</span><textarea autoFocus rows={4} value={rejectReason} onChange={e=>setRejectReason(e.target.value)} required/></label><div className="runtime-modal-actions"><button type="button" className="ghost" onClick={()=>setRejecting(null)}>{pick("انصراف","Cancel")}</button><button className="danger" disabled={busy}>{pick("رد پرداخت","Reject payment")}</button></div></form></div>}
  </div></Shell>;
}
