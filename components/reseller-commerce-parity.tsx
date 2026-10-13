"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {Badge,Card,Stat} from "./ui";
import {PortalShell} from "./portal-shells";
import {
  resellerApi,
  ResellerDiscountPayload,
  ResellerPaymentMethodPayload,
  ResellerRow
} from "../lib/reseller-runtime-api";
import {useI18n} from "../lib/i18n";

const str=(row:ResellerRow,...keys:string[])=>{for(const key of keys){const value=row?.[key];if(value!==undefined&&value!==null)return String(value);}return "";};
const num=(row:ResellerRow,...keys:string[])=>{const value=Number(str(row,...keys).replace(/[,٬]/g,"")||0);return Number.isFinite(value)?value:0;};
const money=(value:number)=>`${Number(value||0).toLocaleString("fa-IR")} تومان`;
const dateText=(value:unknown)=>{if(!value)return "—";const d=new Date(String(value));return Number.isNaN(d.getTime())?String(value):d.toLocaleString("fa-IR");};
const tone=(status:string):"ok"|"warn"|"bad"|"violet"=>["active","approved","paid","fulfilled","success","completed"].includes(status.toLowerCase())?"ok":["rejected","failed","canceled","disabled"].includes(status.toLowerCase())?"bad":"warn";
const clean=(value:string)=>value.trim()||null;

function Notice({error,ok}:{error:string;ok:string}){return <>{error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}</>;}
function Empty({children}:{children:React.ReactNode}){return <div className="runtime-empty">{children}</div>;}

const emptyMethod:ResellerPaymentMethodPayload={
  method_type:"card_to_card",
  title:"",
  card_number:"",
  iban:"",
  account_holder:"",
  instructions:"",
  is_active:true
};

export function ResellerBotParityRuntime(){
  const {pick}=useI18n();
  const [status,setStatus]=useState<ResellerRow>({});
  const [methods,setMethods]=useState<ResellerRow[]>([]);
  const [orders,setOrders]=useState<ResellerRow[]>([]);
  const [token,setToken]=useState("");
  const [welcome,setWelcome]=useState("");
  const [support,setSupport]=useState("");
  const [methodForm,setMethodForm]=useState<ResellerPaymentMethodPayload>(emptyMethod);
  const [editingMethod,setEditingMethod]=useState<number|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const load=async()=>{
    setError("");
    const result=await Promise.allSettled([
      resellerApi.botStatus(),
      resellerApi.botPaymentMethods(),
      resellerApi.botOrders()
    ]);
    if(result[0].status==="fulfilled"){
      setStatus(result[0].value);
      setWelcome(str(result[0].value,"welcome_message"));
      setSupport(str(result[0].value,"support_username"));
    }
    if(result[1].status==="fulfilled")setMethods(result[1].value);
    if(result[2].status==="fulfilled")setOrders(result[2].value);
    const failed=result.find(x=>x.status==="rejected");
    if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));
  };

  useEffect(()=>{void load();},[]);

  const act=async(label:string,fn:()=>Promise<unknown>)=>{
    if(busy)return;
    setBusy(true);setError("");setOk("");
    try{await fn();setOk(label);await load();}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const active=Boolean(status.is_active||status.active||status.runtime_ready);
  const pending=orders.filter(row=>["pending","pending_payment","awaiting_review","review","submitted"].includes(str(row,"status").toLowerCase())).length;

  const saveMethod=(event:FormEvent)=>{
    event.preventDefault();
    const payload:ResellerPaymentMethodPayload={
      method_type:methodForm.method_type.trim()||"card_to_card",
      title:clean(String(methodForm.title||"")),
      card_number:clean(String(methodForm.card_number||"")),
      iban:clean(String(methodForm.iban||"")),
      account_holder:clean(String(methodForm.account_holder||"")),
      instructions:clean(String(methodForm.instructions||"")),
      is_active:Boolean(methodForm.is_active)
    };
    void act(
      editingMethod?pick("روش پرداخت ویرایش شد","Payment method updated"):pick("روش پرداخت اضافه شد","Payment method added"),
      async()=>{
        if(editingMethod)await resellerApi.botUpdatePaymentMethod(editingMethod,payload);
        else await resellerApi.botCreatePaymentMethod(payload);
        setEditingMethod(null);
        setMethodForm(emptyMethod);
      }
    );
  };

  const editMethod=(row:ResellerRow)=>{
    setEditingMethod(Number(row.id||0));
    setMethodForm({
      method_type:str(row,"method_type")||"card_to_card",
      title:str(row,"title"),
      card_number:str(row,"card_number"),
      iban:str(row,"iban"),
      account_holder:str(row,"account_holder"),
      instructions:str(row,"instructions"),
      is_active:Boolean(row.is_active)
    });
  };

  return <PortalShell type="reseller" active="/reseller/bot">
    <div className="page reseller-parity-page">
      <div className="page-head">
        <div><h1>{pick("ربات نمایندگی","Reseller Bot")}</h1><small>{pick("فروش، پرداخت، سفارش و پشتیبانی مشتریان از داخل تلگرام","Telegram sales, payment, order and customer support")}</small></div>
        <button className="ghost" onClick={()=>void load()} disabled={busy}>{pick("بروزرسانی","Refresh")}</button>
      </div>
      <Notice error={error} ok={ok}/>

      <div className="stats">
        <Stat label={pick("وضعیت ربات","Bot status")} value={active?pick("فعال","Active"):pick("خاموش","Off")}/>
        <Stat label={pick("نام کاربری ربات","Bot username")} value={str(status,"bot_username","username")||"—"}/>
        <Stat label={pick("روش‌های پرداخت","Payment methods")} value={String(methods.filter(x=>Boolean(x.is_active)).length)}/>
        <Stat label={pick("در انتظار بررسی","Pending review")} value={String(pending)}/>
      </div>

      <div className="module-grid two">
        <Card>
          <div className="card-head"><div><b>{pick("اتصال BotFather","BotFather connection")}</b><small>{pick("توکن رمزنگاری‌شده ذخیره می‌شود و با تغییر توکن ربات تا فعال‌سازی مجدد متوقف می‌شود.","The token is stored encrypted and a token change pauses the bot until reactivation.")}</small></div><Badge tone={Boolean(status.token_configured)?"ok":"warn"}>{Boolean(status.token_configured)?pick("تنظیم شده","Configured"):pick("بدون توکن","No token")}</Badge></div>
          <label className="field"><span>Bot Token</span><input type="password" dir="ltr" value={token} onChange={e=>setToken(e.target.value)} placeholder={str(status,"token_masked")||"123456:ABC..."}/></label>
          <div className="action-row">
            <button className="primary" disabled={busy||token.trim().length<20} onClick={()=>void act(pick("توکن ربات ذخیره شد","Bot token saved"),async()=>{await resellerApi.botSaveToken(token.trim());setToken("");})}>{pick("ذخیره توکن","Save token")}</button>
            <button className="ghost" disabled={busy||!Boolean(status.token_configured)} onClick={()=>void act(pick("اتصال ربات تأیید شد","Bot connection verified"),resellerApi.botTest)}>{pick("تست اتصال","Test")}</button>
            <button className={active?"danger":"primary"} disabled={busy||!Boolean(status.token_configured)} onClick={()=>void act(active?pick("ربات غیرفعال شد","Bot deactivated"):pick("ربات فعال شد","Bot activated"),active?resellerApi.botDeactivate:resellerApi.botActivate)}>{active?pick("غیرفعال‌سازی","Deactivate"):pick("فعال‌سازی","Activate")}</button>
          </div>
        </Card>

        <Card>
          <div className="card-head"><div><b>{pick("متن‌ها و پشتیبانی","Messages & support")}</b><small>{pick("این اطلاعات مستقیماً در ربات اختصاصی نمایندگی استفاده می‌شوند.","These settings are used directly by the reseller bot.")}</small></div></div>
          <label className="field"><span>{pick("پیام خوش‌آمدگویی","Welcome message")}</span><textarea rows={5} maxLength={3000} value={welcome} onChange={e=>setWelcome(e.target.value)} placeholder={pick("پیام شروع ربات برای مشتری...","Welcome text shown to customers...")}/></label>
          <label className="field"><span>{pick("یوزرنیم پشتیبانی","Support username")}</span><input dir="ltr" maxLength={100} value={support} onChange={e=>setSupport(e.target.value)} placeholder="@support"/></label>
          <button className="primary" disabled={busy} onClick={()=>void act(pick("تنظیمات ربات ذخیره شد","Bot settings saved"),()=>resellerApi.botUpdateSettings({welcome_message:welcome.trim()||null,support_username:support.trim()||null}))}>{pick("ذخیره تنظیمات","Save settings")}</button>
        </Card>
      </div>

      <Card>
        <div className="card-head"><div><b>{pick("روش‌های پرداخت ربات","Bot payment methods")}</b><small>{pick("کارت، شبا، صاحب حساب و توضیحات پرداخت برای مشتری نمایش داده می‌شود.","Card, IBAN, account holder and instructions are shown to customers.")}</small></div><Badge tone="violet">{methods.length}</Badge></div>
        <form className="reseller-payment-editor" onSubmit={saveMethod}>
          <div className="setting-grid">
            <label className="field"><span>{pick("نوع روش","Method type")}</span><select value={methodForm.method_type} onChange={e=>setMethodForm(f=>({...f,method_type:e.target.value}))}><option value="card_to_card">{pick("کارت به کارت","Card to card")}</option><option value="bank_transfer">{pick("واریز بانکی","Bank transfer")}</option></select></label>
            <label className="field"><span>{pick("عنوان","Title")}</span><input value={String(methodForm.title||"")} onChange={e=>setMethodForm(f=>({...f,title:e.target.value}))} placeholder={pick("مثلاً کارت اصلی","e.g. Main card")}/></label>
            <label className="field"><span>{pick("شماره کارت","Card number")}</span><input dir="ltr" value={String(methodForm.card_number||"")} onChange={e=>setMethodForm(f=>({...f,card_number:e.target.value.replace(/[^0-9-]/g,"")}))}/></label>
            <label className="field"><span>{pick("شماره شبا","IBAN")}</span><input dir="ltr" value={String(methodForm.iban||"")} onChange={e=>setMethodForm(f=>({...f,iban:e.target.value}))} placeholder="IR..."/></label>
            <label className="field"><span>{pick("صاحب حساب","Account holder")}</span><input value={String(methodForm.account_holder||"")} onChange={e=>setMethodForm(f=>({...f,account_holder:e.target.value}))}/></label>
            <label className="toggle module-toggle"><span>{pick("فعال","Active")}</span><input type="checkbox" checked={methodForm.is_active} onChange={e=>setMethodForm(f=>({...f,is_active:e.target.checked}))}/><i/></label>
          </div>
          <label className="field"><span>{pick("توضیحات پرداخت","Payment instructions")}</span><textarea rows={3} value={String(methodForm.instructions||"")} onChange={e=>setMethodForm(f=>({...f,instructions:e.target.value}))}/></label>
          <div className="action-row"><button className="primary" disabled={busy}>{editingMethod?pick("ذخیره ویرایش","Save changes"):pick("افزودن روش پرداخت","Add payment method")}</button>{editingMethod&&<button type="button" className="ghost" onClick={()=>{setEditingMethod(null);setMethodForm(emptyMethod);}}>{pick("انصراف","Cancel")}</button>}</div>
        </form>

        <div className="table reseller-payment-table"><table><thead><tr><th>ID</th><th>{pick("عنوان","Title")}</th><th>{pick("کارت / شبا","Card / IBAN")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{methods.map((row,index)=>{const id=Number(row.id||0);return <tr key={id||index}><td>#{id}</td><td><b>{str(row,"title")||pick("روش پرداخت","Payment method")}</b><small>{str(row,"account_holder")}</small></td><td dir="ltr">{str(row,"card_number")||str(row,"iban")||"—"}</td><td><Badge tone={Boolean(row.is_active)?"ok":"bad"}>{Boolean(row.is_active)?pick("فعال","Active"):pick("غیرفعال","Disabled")}</Badge></td><td><div className="row-actions"><button className="mini-btn" type="button" onClick={()=>editMethod(row)}>{pick("ویرایش","Edit")}</button><button className="mini-btn danger" type="button" disabled={busy} onClick={()=>{if(window.confirm(pick("این روش پرداخت غیرفعال شود؟","Disable this payment method?")))void act(pick("روش پرداخت غیرفعال شد","Payment method disabled"),()=>resellerApi.botDeletePaymentMethod(id));}}>{pick("غیرفعال","Disable")}</button></div></td></tr>})}</tbody></table></div>
        {!methods.length&&<Empty>{pick("هنوز روش پرداختی برای ربات ثبت نشده است.","No bot payment method has been configured yet.")}</Empty>}
      </Card>
    </div>
  </PortalShell>;
}

export function ResellerOrdersParityRuntime(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<ResellerRow[]>([]);
  const [q,setQ]=useState("");
  const [statusFilter,setStatusFilter]=useState("all");
  const [selected,setSelected]=useState<ResellerRow|null>(null);
  const [receiptUrl,setReceiptUrl]=useState("");
  const [receiptType,setReceiptType]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const load=async()=>{setError("");try{setRows(await resellerApi.botOrders());}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}};
  useEffect(()=>{void load();return()=>{if(receiptUrl)URL.revokeObjectURL(receiptUrl);};},[]);

  const act=async(label:string,fn:()=>Promise<unknown>)=>{if(busy)return;setBusy(true);setError("");setOk("");try{await fn();setOk(label);setSelected(null);await load();}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy(false);}};

  const openReceipt=async(row:ResellerRow)=>{
    const id=Number(row.id||0);if(!id)return;
    setBusy(true);setError("");
    try{
      const blob=await resellerApi.botOrderReceipt(id);
      if(receiptUrl)URL.revokeObjectURL(receiptUrl);
      setReceiptType(blob.type||"");
      setReceiptUrl(URL.createObjectURL(blob));
      setSelected(row);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const closeDetail=()=>{
    setSelected(null);
    if(receiptUrl){URL.revokeObjectURL(receiptUrl);setReceiptUrl("");setReceiptType("");}
  };

  const statuses=useMemo(()=>Array.from(new Set(rows.map(row=>str(row,"status")).filter(Boolean))),[rows]);
  const filtered=useMemo(()=>rows.filter(row=>{
    const matchesStatus=statusFilter==="all"||str(row,"status")===statusFilter;
    if(!matchesStatus)return false;
    const needle=q.trim().toLowerCase();
    if(!needle)return true;
    return [row.id,row.plan_name,row.customer_user_id,(row.customer as ResellerRow|undefined)?.full_name,(row.customer as ResellerRow|undefined)?.phone,row.tracking_code,row.sender_card_last4].some(value=>String(value??"").toLowerCase().includes(needle));
  }),[rows,q,statusFilter]);

  return <PortalShell type="reseller" active="/reseller/orders">
    <div className="page reseller-parity-page">
      <div className="page-head"><div><h1>{pick("سفارش‌های ربات","Bot Orders")}</h1><small>{pick("بررسی رسید، تأیید یا رد و مشاهده جزئیات کامل سفارش","Receipt review, approval/rejection and full order details")}</small></div><button className="ghost" onClick={()=>void load()} disabled={busy}>{pick("بروزرسانی","Refresh")}</button></div>
      <Notice error={error} ok={ok}/>
      <Card>
        <div className="runtime-toolbar reseller-order-toolbar"><label>⌕ <input value={q} onChange={e=>setQ(e.target.value)} placeholder={pick("جستجو با نام، شماره، سفارش یا کد پیگیری...","Search customer, order or tracking code...")}/></label><select value={statusFilter} onChange={e=>setStatusFilter(e.target.value)}><option value="all">{pick("همه وضعیت‌ها","All statuses")}</option>{statuses.map(status=><option key={status} value={status}>{status}</option>)}</select><Badge tone="violet">{filtered.length}</Badge></div>
        <div className="table"><table><thead><tr><th>ID</th><th>{pick("مشتری","Customer")}</th><th>{pick("پلن","Plan")}</th><th>{pick("مبلغ","Amount")}</th><th>{pick("پرداخت","Payment")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{filtered.map((row,index)=>{const id=Number(row.id||0),status=str(row,"status"),customer=(row.customer&&typeof row.customer==="object"?row.customer:{} ) as ResellerRow,payment=(row.payment_method&&typeof row.payment_method==="object"?row.payment_method:{}) as ResellerRow;const actionable=["pending","pending_payment","awaiting_review","review","submitted"].includes(status.toLowerCase());return <tr key={id||index}><td>#{id}</td><td><b>{str(customer,"full_name")||`#${str(row,"customer_user_id","user_id")}`}</b><small dir="ltr">{str(customer,"phone")||str(customer,"email")}</small></td><td>{str(row,"plan_name")||`#${str(row,"plan_id")}`}</td><td>{money(num(row,"sell_price_toman","amount_toman"))}</td><td><span>{str(payment,"title")||str(payment,"method_type")||"—"}</span>{Boolean(row.has_receipt)&&<small>{pick("رسید ثبت شده","Receipt attached")}</small>}</td><td><Badge tone={tone(status)}>{status||"—"}</Badge></td><td><div className="row-actions"><button className="mini-btn" type="button" onClick={()=>{setSelected(row);if(receiptUrl){URL.revokeObjectURL(receiptUrl);setReceiptUrl("");setReceiptType("");}}}>{pick("جزئیات","Details")}</button>{Boolean(row.has_receipt)&&<button className="mini-btn" type="button" disabled={busy} onClick={()=>void openReceipt(row)}>{pick("رسید","Receipt")}</button>}{actionable&&<><button className="mini-btn" type="button" disabled={busy} onClick={()=>void act(pick("سفارش تأیید شد","Order approved"),()=>resellerApi.botApproveOrder(id))}>{pick("تأیید","Approve")}</button><button className="mini-btn danger" type="button" disabled={busy} onClick={()=>{const reason=window.prompt(pick("دلیل رد سفارش","Reject reason"),"")?.trim()||"";if(reason.length>=2)void act(pick("سفارش رد شد","Order rejected"),()=>resellerApi.botRejectOrder(id,reason));}}>{pick("رد","Reject")}</button></>}</div></td></tr>})}</tbody></table></div>
        {!filtered.length&&<Empty>{pick("سفارشی با این فیلتر پیدا نشد.","No order matches this filter.")}</Empty>}
      </Card>

      {selected&&<div className="runtime-modal reseller-order-modal" role="dialog" aria-modal="true"><button type="button" className="runtime-modal-bg" onClick={closeDetail}/><div className="runtime-modal-card reseller-order-detail"><div className="card-head"><div><b>{pick("جزئیات سفارش","Order details")} #{str(selected,"id")}</b><small>{dateText(selected.created_at)}</small></div><button className="icon-button" type="button" onClick={closeDetail}>×</button></div><div className="reseller-order-detail-grid"><div><span>{pick("مشتری","Customer")}</span><b>{str((selected.customer||{}) as ResellerRow,"full_name")||`#${str(selected,"customer_user_id")}`}</b></div><div><span>{pick("پلن","Plan")}</span><b>{str(selected,"plan_name")||`#${str(selected,"plan_id")}`}</b></div><div><span>{pick("مبلغ فروش","Sell amount")}</span><b>{money(num(selected,"sell_price_toman"))}</b></div><div><span>{pick("وضعیت","Status")}</span><Badge tone={tone(str(selected,"status"))}>{str(selected,"status")}</Badge></div><div><span>{pick("کد پیگیری","Tracking code")}</span><b dir="ltr">{str(selected,"tracking_code")||"—"}</b></div><div><span>{pick("۴ رقم کارت","Card last 4")}</span><b dir="ltr">{str(selected,"sender_card_last4")||"—"}</b></div><div><span>{pick("تاریخ انتقال","Transfer date")}</span><b>{str(selected,"transfer_date")||"—"}</b></div><div><span>{pick("ساعت انتقال","Transfer time")}</span><b>{str(selected,"transfer_time")||"—"}</b></div><div className="wide"><span>{pick("یادداشت پرداخت","Payment note")}</span><b>{str(selected,"payment_note")||"—"}</b></div><div className="wide"><span>{pick("یادداشت بررسی","Review note")}</span><b>{str(selected,"review_note")||"—"}</b></div></div>{receiptUrl&&<div className="reseller-receipt-preview">{receiptType.startsWith("image/")?<img src={receiptUrl} alt={pick("رسید پرداخت","Payment receipt")}/>:<iframe src={receiptUrl} title={pick("رسید پرداخت","Payment receipt")}/>}</div>}<div className="runtime-modal-actions"><button className="ghost" type="button" onClick={closeDetail}>{pick("بستن","Close")}</button></div></div></div>}
    </div>
  </PortalShell>;
}

const emptyDiscount:ResellerDiscountPayload={
  code:"",
  title:"",
  discount_type:"percent",
  discount_value:10,
  max_discount_toman:null,
  min_order_toman:0,
  applies_to:"both",
  plan_ids:[],
  usage_limit_total:null,
  usage_limit_per_user:null,
  starts_at:null,
  ends_at:null,
  is_active:true
};

const toLocalInput=(value:unknown)=>{if(!value)return "";const d=new Date(String(value));if(Number.isNaN(d.getTime()))return "";const pad=(n:number)=>String(n).padStart(2,"0");return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;};
const toIso=(value:string|null|undefined)=>value?new Date(value).toISOString():null;

export function ResellerDiscountsParityRuntime(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<ResellerRow[]>([]);
  const [plans,setPlans]=useState<ResellerRow[]>([]);
  const [form,setForm]=useState<ResellerDiscountPayload>(emptyDiscount);
  const [editing,setEditing]=useState<number|null>(null);
  const [open,setOpen]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const load=async()=>{
    setError("");
    const result=await Promise.allSettled([resellerApi.discounts(),resellerApi.plans()]);
    if(result[0].status==="fulfilled")setRows(result[0].value);
    if(result[1].status==="fulfilled")setPlans(result[1].value);
    const failed=result.find(x=>x.status==="rejected");if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));
  };
  useEffect(()=>{void load();},[]);

  const reset=()=>{setEditing(null);setForm(emptyDiscount);setOpen(false);};
  const edit=(row:ResellerRow)=>{
    setEditing(Number(row.id||0));setOpen(true);
    setForm({
      code:str(row,"code"),title:str(row,"title"),discount_type:(str(row,"discount_type")==="fixed"?"fixed":"percent"),discount_value:num(row,"discount_value"),max_discount_toman:row.max_discount_toman==null?null:num(row,"max_discount_toman"),min_order_toman:num(row,"min_order_toman"),applies_to:(['purchase','renewal','both'].includes(str(row,'applies_to'))?str(row,'applies_to'):'both') as "purchase"|"renewal"|"both",plan_ids:Array.isArray(row.plan_ids)?(row.plan_ids as unknown[]).map(Number).filter(Boolean):[],usage_limit_total:row.usage_limit_total==null?null:num(row,"usage_limit_total"),usage_limit_per_user:row.usage_limit_per_user==null?null:num(row,"usage_limit_per_user"),starts_at:toLocalInput(row.starts_at),ends_at:toLocalInput(row.ends_at),is_active:Boolean(row.is_active)
    });
  };

  const submit=async(event:FormEvent)=>{
    event.preventDefault();if(busy)return;setBusy(true);setError("");setOk("");
    const payload:ResellerDiscountPayload={...form,code:form.code.trim().toUpperCase(),title:clean(String(form.title||"")),starts_at:toIso(form.starts_at),ends_at:toIso(form.ends_at)};
    try{
      if(editing)await resellerApi.updateDiscount(editing,payload);else await resellerApi.createDiscount(payload);
      setOk(editing?pick("کد تخفیف ویرایش شد","Discount updated"):pick("کد تخفیف ساخته شد","Discount created"));reset();await load();
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const activeCount=rows.filter(x=>Boolean(x.is_active)).length;
  return <PortalShell type="reseller" active="/reseller/discounts"><div className="page reseller-parity-page"><div className="page-head"><div><h1>{pick("کدهای تخفیف","Discount Codes")}</h1><small>{pick("تخفیف اختصاصی نمایندگی برای خرید و تمدید در ربات","Reseller-specific discounts for bot purchases and renewals")}</small></div><button className="primary" onClick={()=>{if(open)reset();else setOpen(true);}}>＋ {pick("کد جدید","New code")}</button></div><Notice error={error} ok={ok}/><div className="stats"><Stat label={pick("کل کدها","Total codes")} value={String(rows.length)}/><Stat label={pick("فعال","Active") } value={String(activeCount)}/><Stat label={pick("غیرفعال","Disabled")} value={String(rows.length-activeCount)}/></div>
    {open&&<Card className="runtime-editor reseller-discount-editor"><form onSubmit={submit}><div className="setting-grid"><label className="field"><span>{pick("کد","Code")}</span><input required minLength={2} maxLength={64} dir="ltr" value={form.code} onChange={e=>setForm(f=>({...f,code:e.target.value.toUpperCase().replace(/\s/g,"")}))}/></label><label className="field"><span>{pick("عنوان","Title")}</span><input maxLength={160} value={String(form.title||"")} onChange={e=>setForm(f=>({...f,title:e.target.value}))}/></label><label className="field"><span>{pick("نوع تخفیف","Discount type")}</span><select value={form.discount_type} onChange={e=>setForm(f=>({...f,discount_type:e.target.value as "percent"|"fixed"}))}><option value="percent">{pick("درصدی","Percent")}</option><option value="fixed">{pick("مبلغ ثابت","Fixed amount")}</option></select></label><label className="field"><span>{form.discount_type==="percent"?pick("درصد","Percent"):pick("مبلغ تخفیف","Discount amount")}</span><input type="number" min={1} max={form.discount_type==="percent"?100:undefined} value={form.discount_value} onChange={e=>setForm(f=>({...f,discount_value:Number(e.target.value)}))}/></label><label className="field"><span>{pick("حداکثر تخفیف تومان","Max discount toman")}</span><input type="number" min={0} value={form.max_discount_toman??""} onChange={e=>setForm(f=>({...f,max_discount_toman:e.target.value===""?null:Number(e.target.value)}))}/></label><label className="field"><span>{pick("حداقل سفارش تومان","Minimum order toman")}</span><input type="number" min={0} value={form.min_order_toman} onChange={e=>setForm(f=>({...f,min_order_toman:Number(e.target.value)}))}/></label><label className="field"><span>{pick("کاربرد","Applies to")}</span><select value={form.applies_to} onChange={e=>setForm(f=>({...f,applies_to:e.target.value as "purchase"|"renewal"|"both"}))}><option value="both">{pick("خرید و تمدید","Purchase & renewal")}</option><option value="purchase">{pick("فقط خرید","Purchase only")}</option><option value="renewal">{pick("فقط تمدید","Renewal only")}</option></select></label><label className="field"><span>{pick("سقف مصرف کل","Total usage limit")}</span><input type="number" min={1} value={form.usage_limit_total??""} onChange={e=>setForm(f=>({...f,usage_limit_total:e.target.value===""?null:Number(e.target.value)}))}/></label><label className="field"><span>{pick("سقف هر کاربر","Per-user limit")}</span><input type="number" min={1} value={form.usage_limit_per_user??""} onChange={e=>setForm(f=>({...f,usage_limit_per_user:e.target.value===""?null:Number(e.target.value)}))}/></label><label className="field"><span>{pick("شروع","Starts at")}</span><input type="datetime-local" value={String(form.starts_at||"")} onChange={e=>setForm(f=>({...f,starts_at:e.target.value||null}))}/></label><label className="field"><span>{pick("پایان","Ends at")}</span><input type="datetime-local" value={String(form.ends_at||"")} onChange={e=>setForm(f=>({...f,ends_at:e.target.value||null}))}/></label><label className="toggle module-toggle"><span>{pick("فعال","Active")}</span><input type="checkbox" checked={form.is_active} onChange={e=>setForm(f=>({...f,is_active:e.target.checked}))}/><i/></label></div><div className="runtime-choice-section"><b>{pick("پلن‌های مجاز","Allowed plans")}</b><small>{pick("اگر هیچ پلنی انتخاب نشود، کد برای همه پلن‌هاست.","Leave empty to allow all plans.")}</small><div className="protocol-toggle-grid">{plans.map((plan,index)=>{const id=Number(plan.plan_id||plan.id||0),checked=form.plan_ids.includes(id);return <label className="toggle module-toggle" key={id||index}><span>{str(plan,"name")||`#${id}`}</span><input type="checkbox" checked={checked} onChange={e=>setForm(f=>({...f,plan_ids:e.target.checked?[...f.plan_ids,id]:f.plan_ids.filter(x=>x!==id)}))}/><i/></label>})}</div></div><div className="action-row"><button className="primary" disabled={busy}>{editing?pick("ذخیره تغییرات","Save changes"):pick("ساخت کد تخفیف","Create discount")}</button><button className="ghost" type="button" onClick={reset}>{pick("انصراف","Cancel")}</button></div></form></Card>}
    <Card><div className="table"><table><thead><tr><th>{pick("کد","Code")}</th><th>{pick("مقدار","Value")}</th><th>{pick("کاربرد","Applies")}</th><th>{pick("محدودیت","Limits")}</th><th>{pick("اعتبار زمانی","Schedule")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{rows.map((row,index)=>{const id=Number(row.id||0),isActive=Boolean(row.is_active),kind=str(row,"discount_type");return <tr key={id||index}><td><b dir="ltr">{str(row,"code")}</b><small>{str(row,"title")}</small></td><td>{kind==="percent"?`${num(row,"discount_value")}%`:money(num(row,"discount_value"))}{row.max_discount_toman!=null&&<small>{pick("حداکثر","Max")}: {money(num(row,"max_discount_toman"))}</small>}</td><td>{str(row,"applies_to")}</td><td><span>{row.usage_limit_total==null?pick("نامحدود","Unlimited"):String(row.usage_limit_total)}</span><small>{pick("هر کاربر","Per user")}: {row.usage_limit_per_user==null?pick("نامحدود","Unlimited"):String(row.usage_limit_per_user)}</small></td><td><span>{dateText(row.starts_at)}</span><small>{dateText(row.ends_at)}</small></td><td><Badge tone={isActive?"ok":"bad"}>{isActive?pick("فعال","Active"):pick("غیرفعال","Disabled")}</Badge></td><td><div className="row-actions"><button className="mini-btn" type="button" onClick={()=>edit(row)}>{pick("ویرایش","Edit")}</button>{isActive&&<button className="mini-btn danger" type="button" disabled={busy} onClick={()=>{if(window.confirm(pick("این کد تخفیف غیرفعال شود؟","Disable this discount code?")))void (async()=>{setBusy(true);setError("");try{await resellerApi.disableDiscount(id);setOk(pick("کد تخفیف غیرفعال شد","Discount disabled"));await load();}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy(false);}})();}}>{pick("غیرفعال","Disable")}</button>}</div></td></tr>})}</tbody></table></div>{!rows.length&&<Empty>{pick("هنوز کد تخفیفی ساخته نشده است.","No reseller discount code exists yet.")}</Empty>}</Card>
  </div></PortalShell>;
}
