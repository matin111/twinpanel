"use client";

import Link from "next/link";
import {FormEvent,useEffect,useMemo,useState} from "react";
import {Badge,Card,Stat} from "./ui";
import {PortalShell} from "./portal-shells";
import {resellerApi,ResellerRow} from "../lib/reseller-runtime-api";
import {useI18n} from "../lib/i18n";

const GB=1024**3;
const str=(row:ResellerRow,...keys:string[])=>{for(const key of keys){const value=row?.[key];if(value!==undefined&&value!==null)return String(value);}return "";};
const num=(row:ResellerRow,...keys:string[])=>{const value=Number(str(row,...keys).replace(/[,٬]/g,"")||0);return Number.isFinite(value)?value:0;};
const money=(value:number)=>`${Number(value||0).toLocaleString("fa-IR")} تومان`;
const gbBytes=(value:number)=>`${(Number(value||0)/GB).toLocaleString("fa-IR",{maximumFractionDigits:2})} GB`;
const gbNumber=(value:number)=>`${Number(value||0).toLocaleString("fa-IR",{maximumFractionDigits:2})} GB`;
const dateText=(value:unknown)=>{if(!value)return "—";const d=new Date(String(value));return Number.isNaN(d.getTime())?String(value):d.toLocaleString("fa-IR");};
const statusTone=(status:string):"ok"|"warn"|"bad"|"violet"=>["active","online","approved","paid","completed","success","read"].includes(status.toLowerCase())?"ok":["expired","canceled","failed","rejected","offline","suspended"].includes(status.toLowerCase())?"bad":"warn";
const protocols=(row:ResellerRow)=>[["enable_cisco","Cisco"],["enable_openvpn","OpenVPN"],["enable_wireguard","WireGuard"],["enable_l2tp","L2TP"],["enable_v2ray","V2Ray"]].filter(([key])=>Boolean(row[key])).map(([,label])=>label);

function Notice({error,ok}:{error:string;ok:string}){return <>{error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}</>;}
function Empty({children}:{children:React.ReactNode}){return <div className="runtime-empty">{children}</div>;}

export function ResellerDashboardParityV2(){
  const {pick}=useI18n();
  const [me,setMe]=useState<ResellerRow>({});
  const [dash,setDash]=useState<ResellerRow>({});
  const [subs,setSubs]=useState<ResellerRow[]>([]);
  const [tx,setTx]=useState<ResellerRow[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");

  const load=async()=>{
    setLoading(true);setError("");
    const result=await Promise.allSettled([resellerApi.me(),resellerApi.dashboard(),resellerApi.subscriptions(),resellerApi.trafficTransactions()]);
    if(result[0].status==="fulfilled")setMe(result[0].value);
    if(result[1].status==="fulfilled")setDash(result[1].value);
    if(result[2].status==="fulfilled")setSubs(result[2].value);
    if(result[3].status==="fulfilled")setTx(result[3].value);
    const failed=result.find(item=>item.status==="rejected");
    if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));
    setLoading(false);
  };
  useEffect(()=>{void load();},[]);

  const available=num(dash,"traffic_balance_bytes")+num(dash,"traffic_credit_bytes");
  const totalUsed=num(dash,"traffic_used_bytes");
  const active=num(dash,"active_subscriptions");
  const recent=subs.slice(0,6);

  return <PortalShell type="reseller" active="/reseller"><div className="page reseller-parity-page reseller-dashboard-v2">
    <div className="page-head"><div><h1>{pick("داشبورد","Dashboard")}</h1><small>{str(me,"brand_name","name")||str(me,"code")}</small></div><button className="ghost" onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div>
    {error&&<div className="runtime-error">{error}</div>}{loading&&<div className="runtime-loading">{pick("در حال دریافت اطلاعات...","Loading...")}</div>}
    <div className="stats">
      <Stat label={pick("حجم باقی‌مانده","Remaining traffic")} value={gbBytes(available)}/>
      <Stat label={pick("مصرف کاربران","Customer usage")} value={gbBytes(totalUsed)}/>
      <Stat label={pick("اشتراک فعال","Active subscriptions")} value={String(active)}/>
      <Stat label={pick("مشتریان","Customers")} value={String(num(dash,"customers"))}/>
    </div>
    <div className="module-grid two">
      <Card><div className="card-head"><b>{pick("اشتراک‌های اخیر","Recent subscriptions")}</b><Link className="mini-btn" href="/reseller/subscriptions">{pick("همه","All")}</Link></div>{recent.map((row,index)=><div className="module-row" key={str(row,"id")||index}><div className="grow"><b>{str(row,"customer_name")||`#${str(row,"customer_user_id")}`} · {str(row,"plan_name")||`#${str(row,"plan_id")}`}</b><small>{str(row,"account_username")||"—"} · {dateText(row.expires_at)}</small></div><Badge tone={statusTone(str(row,"status"))}>{str(row,"status")||"—"}</Badge></div>)}{!recent.length&&!loading&&<Empty>{pick("اشتراکی ثبت نشده است.","No subscriptions yet.")}</Empty>}</Card>
      <Card><div className="card-head"><b>{pick("آخرین تغییرات حجم","Recent traffic activity")}</b><Link className="mini-btn" href="/reseller/traffic">{pick("تاریخچه","History")}</Link></div>{tx.slice(0,6).map((row,index)=><div className="module-row" key={str(row,"id")||index}><div className="grow"><b className={num(row,"traffic_gb")>=0?"positive":"negative"}>{num(row,"traffic_gb")>=0?"+":""}{gbNumber(num(row,"traffic_gb"))}</b><small>{str(row,"description","type")||"—"} · {dateText(row.created_at)}</small></div><span>{gbNumber(num(row,"balance_after_gb"))}</span></div>)}{!tx.length&&!loading&&<Empty>{pick("تراکنش حجمی ثبت نشده است.","No traffic transactions yet.")}</Empty>}</Card>
    </div>
    <Card><div className="card-head"><b>{pick("دسترسی سریع","Quick access")}</b></div><div className="reseller-quick-grid"><Link href="/reseller/customers">{pick("مشتریان","Customers")}</Link><Link href="/reseller/subscriptions">{pick("اشتراک‌ها","Subscriptions")}</Link><Link href="/reseller/sales">{pick("فروش و قیمت‌ها","Sales & prices")}</Link><Link href="/reseller/traffic">{pick("حجم و تراکنش‌ها","Traffic")}</Link><Link href="/reseller/bot">{pick("ربات فروش","Sales bot")}</Link><Link href="/reseller/orders">{pick("سفارش‌های ربات","Bot orders")}</Link></div></Card>
  </div></PortalShell>;
}

export function ResellerCustomersParityV2(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<ResellerRow[]>([]);
  const [q,setQ]=useState("");
  const [open,setOpen]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [form,setForm]=useState({full_name:"",email:"",phone:"",password:""});
  const load=async()=>{setError("");try{setRows(await resellerApi.customers());}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}};
  useEffect(()=>{void load();},[]);
  const filtered=useMemo(()=>{const needle=q.trim().toLowerCase();if(!needle)return rows;return rows.filter(row=>[row.id,row.full_name,row.email,row.phone].some(v=>String(v??"").toLowerCase().includes(needle)));},[rows,q]);
  const submit=async(event:FormEvent)=>{event.preventDefault();if(busy)return;setBusy(true);setError("");setOk("");try{await resellerApi.createCustomer({full_name:form.full_name.trim(),email:form.email.trim()||null,phone:form.phone.trim()||null,password:form.password});setOk(pick("مشتری ساخته شد","Customer created"));setForm({full_name:"",email:"",phone:"",password:""});setOpen(false);await load();}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy(false);}};
  return <PortalShell type="reseller" active="/reseller/customers"><div className="page reseller-parity-page"><div className="page-head"><h1>{pick("مشتریان","Customers")}</h1><button className="primary" onClick={()=>setOpen(true)}>＋ {pick("مشتری جدید","New customer")}</button></div><Notice error={error} ok={ok}/>
    {open&&<Card className="runtime-editor"><form onSubmit={submit}><div className="setting-grid"><label className="field"><span>{pick("نام","Name")}</span><input required minLength={2} value={form.full_name} onChange={e=>setForm(v=>({...v,full_name:e.target.value}))}/></label><label className="field"><span>Email</span><input type="email" dir="ltr" value={form.email} onChange={e=>setForm(v=>({...v,email:e.target.value}))}/></label><label className="field"><span>{pick("موبایل","Phone")}</span><input dir="ltr" value={form.phone} onChange={e=>setForm(v=>({...v,phone:e.target.value}))}/></label><label className="field"><span>{pick("رمز عبور","Password")}</span><input required minLength={8} type="password" dir="ltr" value={form.password} onChange={e=>setForm(v=>({...v,password:e.target.value}))}/></label></div><div className="action-row"><button className="ghost" type="button" onClick={()=>setOpen(false)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy}>{pick("ساخت مشتری","Create customer")}</button></div></form></Card>}
    <Card><div className="runtime-toolbar"><label>⌕ <input value={q} onChange={e=>setQ(e.target.value)} placeholder={pick("جستجوی نام، ایمیل یا موبایل...","Search name, email or phone...")}/></label><Badge tone="violet">{filtered.length}</Badge></div><div className="table"><table><thead><tr><th>ID</th><th>{pick("نام","Name")}</th><th>Email</th><th>{pick("موبایل","Phone")}</th><th>{pick("اشتراک‌ها","Subscriptions")}</th><th>{pick("وضعیت","Status")}</th></tr></thead><tbody>{filtered.map((row,index)=><tr key={str(row,"id")||index}><td>#{str(row,"id")}</td><td><b>{str(row,"full_name")||"—"}</b></td><td dir="ltr">{str(row,"email")||"—"}</td><td dir="ltr">{str(row,"phone")||"—"}</td><td>{num(row,"subscription_count")}</td><td><Badge tone={Boolean(row.is_active)?"ok":"bad"}>{Boolean(row.is_active)?pick("فعال","Active"):pick("غیرفعال","Inactive")}</Badge></td></tr>)}</tbody></table></div>{!filtered.length&&<Empty>{pick("مشتری پیدا نشد.","No customers found.")}</Empty>}</Card>
  </div></PortalShell>;
}

export function ResellerSalesParityV2(){
  const {pick}=useI18n();
  const [plans,setPlans]=useState<ResellerRow[]>([]);
  const [subs,setSubs]=useState<ResellerRow[]>([]);
  const [drafts,setDrafts]=useState<Record<number,string>>({});
  const [busy,setBusy]=useState<number|null>(null);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const load=async()=>{setError("");const result=await Promise.allSettled([resellerApi.plans(),resellerApi.subscriptions()]);if(result[0].status==="fulfilled"){setPlans(result[0].value);setDrafts(Object.fromEntries(result[0].value.map(row=>[Number(row.plan_id||row.id||0),String(num(row,"sell_price_toman"))])));}if(result[1].status==="fulfilled")setSubs(result[1].value);const failed=result.find(x=>x.status==="rejected");if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));};
  useEffect(()=>{void load();},[]);
  const revenue=subs.reduce((sum,row)=>sum+num(row,"sell_price_toman"),0);
  const profit=subs.reduce((sum,row)=>sum+num(row,"profit_toman"),0);
  const save=async(planId:number)=>{const value=Number(drafts[planId]||0);if(!Number.isFinite(value)||value<=0){setError(pick("قیمت فروش معتبر نیست.","Invalid selling price."));return;}setBusy(planId);setError("");setOk("");try{await resellerApi.setPlanPrice(planId,value);setOk(pick("قیمت فروش ذخیره شد","Selling price saved"));await load();}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy(null);}};
  return <PortalShell type="reseller" active="/reseller/sales"><div className="page reseller-parity-page"><div className="page-head"><h1>{pick("فروش و قیمت‌ها","Sales & Prices")}</h1><Link className="primary" href="/reseller/subscriptions">＋ {pick("فروش اشتراک","Sell subscription")}</Link></div><Notice error={error} ok={ok}/><div className="stats"><Stat label={pick("فروش ثبت‌شده","Recorded sales")} value={money(revenue)}/><Stat label={pick("سود ثبت‌شده","Recorded profit")} value={money(profit)}/><Stat label={pick("پلن‌های مجاز","Authorized plans")} value={String(plans.length)}/><Stat label={pick("تعداد فروش","Sales count")} value={String(subs.length)}/></div>
    <Card><div className="card-head"><b>{pick("قیمت فروش پلن‌ها","Plan selling prices")}</b></div><div className="table"><table><thead><tr><th>{pick("پلن","Plan")}</th><th>{pick("حجم / مدت","Traffic / Duration")}</th><th>{pick("پروتکل‌ها","Protocols")}</th><th>{pick("قیمت فروش","Selling price")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{plans.map((row,index)=>{const id=Number(row.plan_id||row.id||0);return <tr key={id||index}><td><b>{str(row,"name")||`#${id}`}</b></td><td>{num(row,"traffic_gb")} GB · {num(row,"duration_days")} {pick("روز","days")}</td><td>{protocols(row).join(" · ")||"—"}</td><td><input className="table-input" type="number" min={1} value={drafts[id]??""} onChange={e=>setDrafts(v=>({...v,[id]:e.target.value}))}/></td><td><button className="mini-btn" disabled={busy===id} onClick={()=>void save(id)}>{busy===id?"…":pick("ذخیره","Save")}</button></td></tr>})}</tbody></table></div>{!plans.length&&<Empty>{pick("مدیر هنوز پلنی برای این نمایندگی فعال نکرده است.","No plan has been assigned by the administrator.")}</Empty>}</Card>
    <Card><div className="card-head"><b>{pick("فروش‌های اخیر","Recent sales")}</b></div><div className="table"><table><thead><tr><th>ID</th><th>{pick("مشتری","Customer")}</th><th>{pick("پلن","Plan")}</th><th>{pick("مبلغ فروش","Sale price")}</th><th>{pick("سود","Profit")}</th><th>{pick("تاریخ","Date")}</th></tr></thead><tbody>{subs.slice(0,100).map((row,index)=><tr key={str(row,"id")||index}><td>#{str(row,"id")}</td><td>{str(row,"customer_name")||`#${str(row,"customer_user_id")}`}</td><td>{str(row,"plan_name")||`#${str(row,"plan_id")}`}</td><td>{money(num(row,"sell_price_toman"))}</td><td>{money(num(row,"profit_toman"))}</td><td>{dateText(row.created_at)}</td></tr>)}</tbody></table></div></Card>
  </div></PortalShell>;
}

export function ResellerTrafficParityV2(){
  const {pick}=useI18n();
  const [balance,setBalance]=useState<ResellerRow>({});
  const [packages,setPackages]=useState<ResellerRow[]>([]);
  const [tx,setTx]=useState<ResellerRow[]>([]);
  const [busy,setBusy]=useState<number|null>(null);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const load=async()=>{setError("");const result=await Promise.allSettled([resellerApi.traffic(),resellerApi.trafficPackages(),resellerApi.trafficTransactions()]);if(result[0].status==="fulfilled")setBalance(result[0].value);if(result[1].status==="fulfilled")setPackages(result[1].value);if(result[2].status==="fulfilled")setTx(result[2].value);const failed=result.find(x=>x.status==="rejected");if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));};
  useEffect(()=>{void load();},[]);
  const buy=async(id:number)=>{if(!window.confirm(pick("این بسته حجم خریداری شود؟","Buy this traffic package?")))return;setBusy(id);setError("");setOk("");try{await resellerApi.buyTraffic(id);setOk(pick("بسته حجم اضافه شد","Traffic package added"));await load();}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy(null);}};
  return <PortalShell type="reseller" active="/reseller/traffic"><div className="page reseller-parity-page"><div className="page-head"><h1>{pick("حجم","Traffic")}</h1><button className="ghost" onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div><Notice error={error} ok={ok}/><div className="stats"><Stat label={pick("حجم باقی‌مانده","Remaining traffic")} value={gbNumber(num(balance,"traffic_balance_gb"))}/><Stat label={pick("اعتبار حجمی","Traffic credit")} value={gbNumber(num(balance,"traffic_credit_gb"))}/><Stat label={pick("حجم قابل استفاده","Available traffic")} value={gbNumber(num(balance,"available_traffic_gb"))}/><Stat label={pick("تراکنش‌ها","Transactions")} value={String(tx.length)}/></div>
    {packages.length>0&&<Card><div className="card-head"><b>{pick("بسته‌های حجم","Traffic packages")}</b></div><div className="reseller-package-grid">{packages.map((row,index)=>{const id=Number(row.id||0);return <article key={id||index}><b>{str(row,"title")}</b><strong>{num(row,"traffic_gb")} GB</strong><span>{money(num(row,"price_toman"))}</span><button className="primary" disabled={busy===id} onClick={()=>void buy(id)}>{busy===id?"…":pick("خرید بسته","Buy package")}</button></article>})}</div></Card>}
    <Card><div className="card-head"><b>{pick("تاریخچه حجم","Traffic history")}</b></div><div className="table"><table><thead><tr><th>ID</th><th>{pick("تغییر","Change")}</th><th>{pick("مانده بعد","Balance after")}</th><th>{pick("نوع","Type")}</th><th>{pick("توضیح","Description")}</th><th>{pick("تاریخ","Date")}</th></tr></thead><tbody>{tx.map((row,index)=><tr key={str(row,"id")||index}><td>#{str(row,"id")}</td><td><b className={num(row,"traffic_gb")>=0?"positive":"negative"}>{num(row,"traffic_gb")>=0?"+":""}{gbNumber(num(row,"traffic_gb"))}</b></td><td>{gbNumber(num(row,"balance_after_gb"))}</td><td>{str(row,"type")||"—"}</td><td>{str(row,"description")||"—"}</td><td>{dateText(row.created_at)}</td></tr>)}</tbody></table></div>{!tx.length&&<Empty>{pick("تراکنش حجمی ثبت نشده است.","No traffic transactions yet.")}</Empty>}</Card>
  </div></PortalShell>;
}

export function ResellerNotificationsParityV2(){
  const {pick}=useI18n();
  const [items,setItems]=useState<ResellerRow[]>([]);
  const [unread,setUnread]=useState(0);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const load=async()=>{setError("");try{const payload=await resellerApi.notifications() as ResellerRow;setItems(Array.isArray(payload.items)?payload.items as ResellerRow[]:[]);setUnread(Number(payload.unread_count||0));}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}};
  useEffect(()=>{void load();},[]);
  const readOne=async(id:number)=>{setBusy(true);try{await resellerApi.notificationMarkRead(id);await load();}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy(false);}};
  const readAll=async()=>{setBusy(true);try{await resellerApi.notificationReadAll();await load();}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy(false);}};
  return <PortalShell type="reseller" active="/reseller/notifications"><div className="page reseller-parity-page"><div className="page-head"><div><h1>{pick("اعلان‌ها","Notifications")}</h1></div><button className="ghost" disabled={busy||!unread} onClick={()=>void readAll()}>{pick("خواندن همه","Mark all read")}</button></div>{error&&<div className="runtime-error">{error}</div>}<div className="stats"><Stat label={pick("خوانده‌نشده","Unread")} value={String(unread)}/><Stat label={pick("کل نمایش‌داده‌شده","Shown") } value={String(items.length)}/></div><Card>{items.map((row,index)=><div className={`module-row reseller-notification-row ${Boolean(row.is_read)?"is-read":""}`} key={str(row,"id")||index}><div className="grow"><div className="action-row"><b>{str(row,"title")||pick("اعلان","Notification")}</b><Badge tone={Boolean(row.is_read)?"ok":"violet"}>{str(row,"kind")||"info"}</Badge></div><p>{str(row,"message")}</p><small>{dateText(row.created_at)}</small></div>{!Boolean(row.is_read)&&<button className="mini-btn" disabled={busy} onClick={()=>void readOne(Number(row.id||0))}>{pick("خواندم","Mark read")}</button>}{str(row,"route")&&<Link className="mini-btn" href={str(row,"route")}>{pick("باز کردن","Open")}</Link>}</div>)}{!items.length&&<Empty>{pick("اعلانی وجود ندارد.","No notifications.")}</Empty>}</Card></div></PortalShell>;
}

export function ResellerSettingsParityV2(){
  const {pick}=useI18n();
  const [me,setMe]=useState<ResellerRow>({});
  const [form,setForm]=useState({name:"",brand_name:"",email:"",phone:"",support_text:""});
  const [password,setPassword]=useState({current:"",next:"",confirm:""});
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const load=async()=>{setError("");try{const row=await resellerApi.me();setMe(row);setForm({name:str(row,"name"),brand_name:str(row,"brand_name"),email:str(row,"email"),phone:str(row,"phone"),support_text:str(row,"support_text")});}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}};
  useEffect(()=>{void load();},[]);
  const saveProfile=async(event:FormEvent)=>{event.preventDefault();if(busy)return;setBusy(true);setError("");setOk("");try{await resellerApi.updateProfile({name:form.name.trim(),brand_name:form.brand_name.trim()||null,email:form.email.trim(),phone:form.phone.trim()||null,support_text:form.support_text.trim()||null});setOk(pick("تنظیمات ذخیره شد","Settings saved"));await load();}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy(false);}};
  const savePassword=async(event:FormEvent)=>{event.preventDefault();if(password.next!==password.confirm){setError(pick("تکرار رمز جدید یکسان نیست.","New password confirmation does not match."));return;}if(password.next.length<8){setError(pick("رمز جدید حداقل ۸ کاراکتر باشد.","New password must be at least 8 characters."));return;}setBusy(true);setError("");setOk("");try{await resellerApi.changePassword(password.current,password.next);setPassword({current:"",next:"",confirm:""});setOk(pick("رمز عبور تغییر کرد","Password changed"));}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy(false);}};
  return <PortalShell type="reseller" active="/reseller/settings"><div className="page reseller-parity-page"><div className="page-head"><div><h1>{pick("تنظیمات","Settings")}</h1><small dir="ltr">{str(me,"code")}</small></div></div><Notice error={error} ok={ok}/><div className="module-grid two">
    <Card><div className="card-head"><b>{pick("پروفایل نمایندگی","Reseller profile")}</b></div><form className="runtime-editor" onSubmit={saveProfile}><label className="field"><span>{pick("نام نمایندگی","Reseller name")}</span><input required minLength={2} value={form.name} onChange={e=>setForm(v=>({...v,name:e.target.value}))}/></label><label className="field"><span>{pick("نام برند","Brand name")}</span><input value={form.brand_name} onChange={e=>setForm(v=>({...v,brand_name:e.target.value}))}/></label><label className="field"><span>Email</span><input required type="email" dir="ltr" value={form.email} onChange={e=>setForm(v=>({...v,email:e.target.value}))}/></label><label className="field"><span>{pick("موبایل","Phone")}</span><input dir="ltr" value={form.phone} onChange={e=>setForm(v=>({...v,phone:e.target.value}))}/></label><label className="field"><span>{pick("متن پشتیبانی","Support text")}</span><textarea rows={4} value={form.support_text} onChange={e=>setForm(v=>({...v,support_text:e.target.value}))}/></label><button className="primary" disabled={busy}>{pick("ذخیره","Save")}</button></form></Card>
    <Card><div className="card-head"><b>{pick("تغییر رمز عبور","Change password")}</b></div><form className="runtime-editor" onSubmit={savePassword}><label className="field"><span>{pick("رمز فعلی","Current password")}</span><input required type="password" dir="ltr" value={password.current} onChange={e=>setPassword(v=>({...v,current:e.target.value}))}/></label><label className="field"><span>{pick("رمز جدید","New password")}</span><input required minLength={8} type="password" dir="ltr" value={password.next} onChange={e=>setPassword(v=>({...v,next:e.target.value}))}/></label><label className="field"><span>{pick("تکرار رمز جدید","Confirm new password")}</span><input required minLength={8} type="password" dir="ltr" value={password.confirm} onChange={e=>setPassword(v=>({...v,confirm:e.target.value}))}/></label><button className="primary" disabled={busy}>{pick("تغییر رمز","Change password")}</button></form></Card>
  </div></div></PortalShell>;
}
