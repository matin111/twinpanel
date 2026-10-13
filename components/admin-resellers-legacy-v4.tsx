"use client";

import {FormEvent,useEffect,useMemo,useRef,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

type Row=Record<string,unknown>;
type UserHit={id:number;email:string;full_name?:string|null;phone?:string|null};
type CreateDraft={owner_user_id:number;name:string;initial_traffic_gb:string};
type EditDraft={id:number;name:string;brand_name:string;support_text:string};
type AdjustDraft={reseller_id:number;reseller_name:string;traffic_gb:string;description:string};
type CreditDraft={reseller_id:number;reseller_name:string;amount:string;description:string};
type PackageDraft={id:number;title:string;traffic_gb:string;price_toman:string;is_active:boolean;sort_order:string};

const emptyCreate:CreateDraft={owner_user_id:0,name:"",initial_traffic_gb:"0"};
const emptyEdit:EditDraft={id:0,name:"",brand_name:"",support_text:""};
const emptyAdjust:AdjustDraft={reseller_id:0,reseller_name:"",traffic_gb:"",description:""};
const emptyCredit:CreditDraft={reseller_id:0,reseller_name:"",amount:"",description:""};
const emptyPackage:PackageDraft={id:0,title:"",traffic_gb:"",price_toman:"",is_active:true,sort_order:"100"};

function text(row:Row,...keys:string[]){for(const key of keys){const value=row?.[key];if(value!==undefined&&value!==null)return String(value);}return "";}
function num(row:Row,...keys:string[]){const value=Number(text(row,...keys).replace(/[,٬]/g,"")||0);return Number.isFinite(value)?value:0;}
function bool(row:Row,key:string){return Boolean(row?.[key]);}
function gb(value:number){return `${Number(value||0).toLocaleString("fa-IR",{maximumFractionDigits:2})} GB`;}
function money(value:number){return `${Number(value||0).toLocaleString("fa-IR")} تومان`;}

async function api<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  let payload:unknown=null;
  const raw=await response.text();
  if(raw){try{payload=JSON.parse(raw);}catch{payload=raw;}}
  if(!response.ok){
    let message=`API error ${response.status}`;
    if(payload&&typeof payload==="object"){
      const row=payload as {detail?:unknown;message?:unknown};
      if(typeof row.detail==="string")message=row.detail;
      else if(typeof row.message==="string")message=row.message;
      else if(Array.isArray(row.detail))message=row.detail.map(item=>typeof item==="object"&&item&&"msg" in item?String((item as {msg:unknown}).msg):String(item)).join("، ");
    }
    throw new Error(message);
  }
  return payload as T;
}

function Notice({error,ok}:{error:string;ok:string}){return <>{error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}</>;}

export function AdminResellersLegacyV4(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<Row[]>([]);
  const [stats,setStats]=useState<Row>({});
  const [q,setQ]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [createOpen,setCreateOpen]=useState(false);
  const [editOpen,setEditOpen]=useState(false);
  const [adjustOpen,setAdjustOpen]=useState(false);
  const [creditOpen,setCreditOpen]=useState(false);
  const [plansOpen,setPlansOpen]=useState(false);
  const [packagesOpen,setPackagesOpen]=useState(false);
  const [create,setCreate]=useState<CreateDraft>(emptyCreate);
  const [edit,setEdit]=useState<EditDraft>(emptyEdit);
  const [adjust,setAdjust]=useState<AdjustDraft>(emptyAdjust);
  const [credit,setCredit]=useState<CreditDraft>(emptyCredit);
  const [selectedReseller,setSelectedReseller]=useState<Row|null>(null);
  const [plans,setPlans]=useState<Row[]>([]);
  const [packages,setPackages]=useState<Row[]>([]);
  const [packageDraft,setPackageDraft]=useState<PackageDraft>(emptyPackage);
  const [userQuery,setUserQuery]=useState("");
  const [userHits,setUserHits]=useState<UserHit[]>([]);
  const [selectedUser,setSelectedUser]=useState<UserHit|null>(null);
  const [searching,setSearching]=useState(false);
  const searchSeq=useRef(0);

  const load=async()=>{
    setError("");
    const [listResult,statsResult]=await Promise.allSettled([api<Row[]>("/v1/admin/resellers"),api<Row>("/v1/admin/resellers/stats")]);
    if(listResult.status==="fulfilled")setRows(listResult.value);
    if(statsResult.status==="fulfilled")setStats(statsResult.value);
    const failed=[listResult,statsResult].find(item=>item.status==="rejected");
    if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));
  };

  useEffect(()=>{void load();},[]);

  useEffect(()=>{
    if(!createOpen||selectedUser)return;
    const query=userQuery.trim();
    if(query.length<2){setUserHits([]);setSearching(false);return;}
    const seq=++searchSeq.current;setSearching(true);
    const timer=window.setTimeout(async()=>{
      try{const result=await api<UserHit[]>(`/v1/admin/resellers/user-search?q=${encodeURIComponent(query)}&limit=12`);if(seq===searchSeq.current)setUserHits(result);}
      catch(reason){if(seq===searchSeq.current)setError(reason instanceof Error?reason.message:String(reason));}
      finally{if(seq===searchSeq.current)setSearching(false);}
    },250);
    return()=>window.clearTimeout(timer);
  },[userQuery,createOpen,selectedUser]);

  const filtered=useMemo(()=>{
    const needle=q.trim().toLowerCase();
    if(!needle)return rows;
    return rows.filter(row=>{
      const owner=(row.owner&&typeof row.owner==="object"?row.owner:{}) as Row;
      return [row.id,row.name,row.code,row.email,row.phone,row.brand_name,owner.name,owner.email,owner.phone].some(value=>String(value??"").toLowerCase().includes(needle));
    });
  },[rows,q]);

  const totalTrafficGb=useMemo(()=>rows.reduce((sum,row)=>sum+num(row,"traffic_balance_gb"),0),[rows]);

  const act=async(label:string,fn:()=>Promise<unknown>)=>{if(busy)return;setBusy(true);setError("");setOk("");try{await fn();setOk(label);await load();}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy(false);}};
  const resetCreate=()=>{setCreateOpen(false);setCreate(emptyCreate);setUserQuery("");setUserHits([]);setSelectedUser(null);};
  const chooseUser=(user:UserHit)=>{setSelectedUser(user);setCreate(value=>({...value,owner_user_id:user.id,name:value.name||user.full_name||""}));setUserQuery(user.email);setUserHits([]);};

  const submitCreate=(event:FormEvent)=>{
    event.preventDefault();
    if(!selectedUser||!create.owner_user_id){setError(pick("ابتدا کاربر را جستجو و انتخاب کنید.","Search and select a user first."));return;}
    const initial=Number(create.initial_traffic_gb||0);
    if(!Number.isFinite(initial)||initial<0){setError(pick("حجم اولیه معتبر نیست.","Initial traffic is invalid."));return;}
    void act(pick("نمایندگی ساخته شد","Reseller created"),async()=>{await api("/v1/admin/resellers",{method:"POST",body:JSON.stringify({owner_user_id:create.owner_user_id,name:create.name.trim()||null,initial_traffic_gb:initial})});resetCreate();});
  };

  const openEdit=(row:Row)=>{setEdit({id:Number(row.id||0),name:text(row,"name"),brand_name:text(row,"brand_name"),support_text:text(row,"support_text")});setEditOpen(true);};
  const submitEdit=(event:FormEvent)=>{event.preventDefault();if(!edit.id||edit.name.trim().length<2)return;void act(pick("اطلاعات نماینده ذخیره شد","Reseller updated"),async()=>{await api(`/v1/admin/resellers/${edit.id}`,{method:"PATCH",body:JSON.stringify({name:edit.name.trim(),brand_name:edit.brand_name.trim()||null,support_text:edit.support_text.trim()||null})});setEditOpen(false);setEdit(emptyEdit);});};

  const openAdjust=(row:Row)=>{setAdjust({reseller_id:Number(row.id||0),reseller_name:text(row,"name")||`#${text(row,"id")}`,traffic_gb:"",description:""});setAdjustOpen(true);};
  const submitAdjust=(event:FormEvent)=>{event.preventDefault();const amount=Number(adjust.traffic_gb);if(!Number.isFinite(amount)||amount===0){setError(pick("مقدار حجم نباید صفر باشد.","Traffic amount must be non-zero."));return;}void act(pick("حجم نمایندگی تغییر کرد","Reseller traffic updated"),async()=>{await api(`/v1/admin/resellers/${adjust.reseller_id}/traffic/adjust`,{method:"POST",body:JSON.stringify({traffic_gb:amount,description:adjust.description.trim()||null,idempotency_key:`admin-reseller-traffic-${adjust.reseller_id}-${Date.now()}-${Math.random().toString(36).slice(2,8)}`})});setAdjustOpen(false);setAdjust(emptyAdjust);});};

  const openCredit=(row:Row)=>{setCredit({reseller_id:Number(row.id||0),reseller_name:text(row,"name")||`#${text(row,"id")}`,amount:"",description:""});setCreditOpen(true);};
  const submitCredit=(event:FormEvent)=>{event.preventDefault();const amount=Number(credit.amount);if(!Number.isFinite(amount)||amount===0){setError(pick("مبلغ اعتبار نباید صفر باشد.","Credit amount must be non-zero."));return;}void act(pick("اعتبار خرید حجم تغییر کرد","Traffic purchase credit updated"),async()=>{await api(`/v1/admin/resellers/${credit.reseller_id}/wallet/adjust`,{method:"POST",body:JSON.stringify({amount,description:credit.description.trim()||null,idempotency_key:`reseller-purchase-credit-${credit.reseller_id}-${Date.now()}-${Math.random().toString(36).slice(2,8)}`})});setCreditOpen(false);setCredit(emptyCredit);});};

  const loadPlans=async(resellerId:number)=>{setPlans(await api<Row[]>(`/v1/admin/resellers/${resellerId}/plans`));};
  const openPlans=async(row:Row)=>{setSelectedReseller(row);setPlansOpen(true);setError("");try{await loadPlans(Number(row.id||0));}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}};
  const togglePlan=async(plan:Row)=>{
    if(!selectedReseller)return;
    const rid=Number(selectedReseller.id||0),pid=Number(plan.plan_id||0),allowed=Boolean(plan.is_allowed);
    const defaultPrice=Math.max(1,num(plan,"sell_price_toman")||num(plan,"base_price_toman")||1);
    setBusy(true);setError("");setOk("");
    try{await api(`/v1/admin/resellers/${rid}/plans/${pid}`,{method:"PUT",body:JSON.stringify({buy_price_toman:0,sell_price_toman:defaultPrice,is_active:!allowed})});await loadPlans(rid);setOk(pick("دسترسی پلن اشتراک ذخیره شد","Subscription plan access saved"));}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const openPackages=async()=>{setPackagesOpen(true);setPackageDraft(emptyPackage);setError("");try{setPackages(await api<Row[]>("/v1/admin/resellers/traffic-packages/all"));}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}};
  const editPackage=(row:Row)=>setPackageDraft({id:Number(row.id||0),title:text(row,"title"),traffic_gb:String(num(row,"traffic_gb")),price_toman:String(num(row,"price_toman")),is_active:Boolean(row.is_active),sort_order:String(num(row,"sort_order")||100)});
  const submitPackage=async(event:FormEvent)=>{event.preventDefault();const payload={title:packageDraft.title.trim(),traffic_gb:Number(packageDraft.traffic_gb),price_toman:Number(packageDraft.price_toman),is_active:packageDraft.is_active,sort_order:Number(packageDraft.sort_order||100)};setBusy(true);setError("");setOk("");try{if(packageDraft.id)await api(`/v1/admin/resellers/traffic-packages/${packageDraft.id}`,{method:"PATCH",body:JSON.stringify(payload)});else await api("/v1/admin/resellers/traffic-packages",{method:"POST",body:JSON.stringify(payload)});setPackageDraft(emptyPackage);setPackages(await api<Row[]>("/v1/admin/resellers/traffic-packages/all"));setOk(pick("پلن شارژ حجم ذخیره شد","Traffic recharge package saved"));}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy(false);}};
  const disablePackage=async(id:number)=>{setBusy(true);setError("");try{await api(`/v1/admin/resellers/traffic-packages/${id}`,{method:"DELETE"});setPackages(await api<Row[]>("/v1/admin/resellers/traffic-packages/all"));}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy(false);}};

  return <Shell active="/admin/resellers"><div className="page reseller-admin-v2">
    <div className="page-head"><h1>{pick("نمایندگی‌ها","Resellers")}</h1><div className="action-row"><button className="ghost" onClick={()=>void openPackages()}>{pick("پلن‌های شارژ حجم","Traffic recharge packages")}</button><button className="primary" onClick={()=>{setCreateOpen(true);setError("");setOk("");}}>＋ {pick("نماینده جدید","New reseller")}</button></div></div>
    <Notice error={error} ok={ok}/>
    <div className="stats dashboard-stats reseller-admin-stats"><Stat label={pick("کل نمایندگان","All resellers")} value={String(num(stats,"total")||rows.length)}/><Stat label={pick("فعال","Active")} value={String(num(stats,"active")||rows.filter(row=>bool(row,"is_active")).length)}/><Stat label={pick("مشتریان","Customers")} value={String(num(stats,"customers"))}/><Stat label={pick("حجم باقی‌مانده کل","Total remaining traffic")} value={gb(totalTrafficGb)}/></div>

    <Card><div className="runtime-toolbar"><label>⌕ <input value={q} onChange={event=>setQ(event.target.value)} placeholder={pick("جستجو با نام، ایمیل، موبایل یا کد...","Search name, email, phone or code...")}/></label><Badge tone="violet">{filtered.length}</Badge></div><div className="table reseller-admin-table"><table><thead><tr><th>{pick("نماینده","Reseller")}</th><th>{pick("مالک","Owner")}</th><th>{pick("کد","Code")}</th><th>{pick("حجم باقی‌مانده","Remaining traffic")}</th><th>{pick("مشتری / اشتراک","Customers / Subs")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{filtered.map(row=>{const rid=Number(row.id||0),active=bool(row,"is_active"),owner=(row.owner&&typeof row.owner==="object"?row.owner:{}) as Row;return <tr key={rid}><td><b>{text(row,"name")||`#${rid}`}</b></td><td><b>{text(owner,"name")||`#${text(row,"owner_user_id")}`}</b><small dir="ltr">{text(owner,"email")||text(row,"email")||"—"}</small></td><td><code dir="ltr">{text(row,"code")||"—"}</code></td><td><b>{gb(num(row,"traffic_balance_gb"))}</b></td><td><b>{num(row,"customer_count").toLocaleString("fa-IR")} / {num(row,"subscription_count").toLocaleString("fa-IR")}</b></td><td><Badge tone={active?"ok":"warn"}>{active?pick("فعال","Active"):pick("تعلیق","Suspended")}</Badge></td><td><div className="row-actions"><button className="mini-btn" onClick={()=>openEdit(row)}>{pick("ویرایش","Edit")}</button><button className="mini-btn" onClick={()=>void openPlans(row)}>{pick("پلن اشتراک","Subscription plans")}</button><button className="mini-btn primary-lite" onClick={()=>openAdjust(row)}>＋ {pick("حجم مستقیم","Direct traffic")}</button><button className="mini-btn" onClick={()=>openCredit(row)}>＋ {pick("اعتبار خرید حجم","Purchase credit")}</button><button className="mini-btn" disabled={busy} onClick={()=>void act(active?pick("نمایندگی تعلیق شد","Reseller suspended"):pick("نمایندگی فعال شد","Reseller activated"),()=>api(`/v1/admin/resellers/${rid}/toggle-active`,{method:"POST"}))}>{active?pick("تعلیق","Suspend"):pick("فعال‌سازی","Activate")}</button><button className="mini-btn danger" disabled={busy} onClick={()=>{if(window.confirm(pick("نماینده حذف شود؟","Delete reseller?")))void act(pick("نماینده حذف شد","Reseller deleted"),()=>api(`/v1/admin/resellers/${rid}`,{method:"DELETE"}));}}>{pick("حذف","Delete")}</button></div></td></tr>})}</tbody></table></div>{!filtered.length&&<div className="runtime-empty">{pick("نماینده‌ای پیدا نشد.","No reseller found.")}</div>}</Card>

    {createOpen&&<div className="runtime-modal reseller-create-simple" role="dialog" aria-modal="true"><button className="runtime-modal-bg" type="button" onClick={()=>!busy&&resetCreate()}/><form className="runtime-modal-card reseller-simple-card" onSubmit={submitCreate}><div className="card-head"><b>{pick("ساخت نماینده","Create reseller")}</b><button className="icon-button" type="button" onClick={resetCreate}>×</button></div><div className="reseller-user-search-block"><label className="field"><span>{pick("ایمیل، نام یا موبایل کاربر","User email, name or phone")}</span><input autoFocus dir="ltr" value={userQuery} onChange={event=>{setUserQuery(event.target.value);setSelectedUser(null);setCreate(value=>({...value,owner_user_id:0}));}} placeholder="user@example.com" autoComplete="off"/></label>{!selectedUser&&userQuery.trim().length>=2&&<div className="reseller-user-results">{searching&&<div className="reseller-search-state">{pick("در حال جستجو...","Searching...")}</div>}{!searching&&userHits.map(user=><button type="button" key={user.id} onClick={()=>chooseUser(user)}><span className="reseller-user-avatar">{(user.full_name||user.email||"U").charAt(0).toUpperCase()}</span><div><b>{user.full_name||pick("بدون نام","No name")}</b><small dir="ltr">{user.email}</small>{user.phone&&<small dir="ltr">{user.phone}</small>}</div><em>#{user.id}</em></button>)}{!searching&&!userHits.length&&<div className="reseller-search-state">{pick("کاربری پیدا نشد.","No eligible user found.")}</div>}</div>}{selectedUser&&<div className="reseller-selected-user"><span className="reseller-user-avatar">{(selectedUser.full_name||selectedUser.email||"U").charAt(0).toUpperCase()}</span><div><b>{selectedUser.full_name||pick("کاربر","User")}</b><small dir="ltr">{selectedUser.email}</small></div><button type="button" className="mini-btn" onClick={()=>{setSelectedUser(null);setCreate(value=>({...value,owner_user_id:0}));setUserQuery("");}}>{pick("تغییر","Change")}</button></div>}</div><div className="setting-grid reseller-simple-fields"><label className="field"><span>{pick("نام نمایندگی (اختیاری)","Reseller name (optional)")}</span><input value={create.name} onChange={event=>setCreate(value=>({...value,name:event.target.value}))}/></label><label className="field"><span>{pick("حجم اولیه (GB)","Initial traffic (GB)")}</span><input type="number" min={0} step="0.01" value={create.initial_traffic_gb} onChange={event=>setCreate(value=>({...value,initial_traffic_gb:event.target.value}))}/></label></div><div className="runtime-modal-actions"><button className="ghost" type="button" onClick={resetCreate}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy||!selectedUser}>{busy?"…":pick("ساخت نماینده","Create reseller")}</button></div></form></div>}

    {editOpen&&<div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" type="button" onClick={()=>!busy&&setEditOpen(false)}/><form className="runtime-modal-card reseller-simple-card" onSubmit={submitEdit}><div className="card-head"><b>{pick("ویرایش نماینده","Edit reseller")}</b><button className="icon-button" type="button" onClick={()=>setEditOpen(false)}>×</button></div><label className="field"><span>{pick("نام نمایندگی","Reseller name")}</span><input required minLength={2} value={edit.name} onChange={event=>setEdit(value=>({...value,name:event.target.value}))}/></label><label className="field"><span>{pick("نام برند","Brand name")}</span><input value={edit.brand_name} onChange={event=>setEdit(value=>({...value,brand_name:event.target.value}))}/></label><label className="field"><span>{pick("متن پشتیبانی","Support text")}</span><textarea rows={4} value={edit.support_text} onChange={event=>setEdit(value=>({...value,support_text:event.target.value}))}/></label><div className="runtime-modal-actions"><button className="ghost" type="button" onClick={()=>setEditOpen(false)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy}>{pick("ذخیره","Save")}</button></div></form></div>}

    {adjustOpen&&<div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" type="button" onClick={()=>!busy&&setAdjustOpen(false)}/><form className="runtime-modal-card reseller-traffic-card" onSubmit={submitAdjust}><div className="card-head"><div><b>{pick("شارژ / کسر مستقیم حجم","Direct traffic adjustment")}</b><small>{adjust.reseller_name}</small></div><button className="icon-button" type="button" onClick={()=>setAdjustOpen(false)}>×</button></div><label className="field"><span>{pick("مقدار GB","Traffic GB")}</span><input autoFocus type="number" step="0.01" value={adjust.traffic_gb} onChange={event=>setAdjust(value=>({...value,traffic_gb:event.target.value}))}/></label><label className="field"><span>{pick("توضیح (اختیاری)","Note (optional)")}</span><textarea rows={3} value={adjust.description} onChange={event=>setAdjust(value=>({...value,description:event.target.value}))}/></label><div className="runtime-modal-actions"><button className="ghost" type="button" onClick={()=>setAdjustOpen(false)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy||!Number(adjust.traffic_gb)}>{pick("ثبت تغییر حجم","Apply")}</button></div></form></div>}

    {creditOpen&&<div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" type="button" onClick={()=>!busy&&setCreditOpen(false)}/><form className="runtime-modal-card reseller-traffic-card" onSubmit={submitCredit}><div className="card-head"><div><b>{pick("اعتبار خرید پلن شارژ حجم","Traffic-package purchase credit")}</b><small>{credit.reseller_name}</small></div><button className="icon-button" type="button" onClick={()=>setCreditOpen(false)}>×</button></div><label className="field"><span>{pick("مبلغ تومان","Amount (toman)")}</span><input autoFocus type="number" step="1" value={credit.amount} onChange={event=>setCredit(value=>({...value,amount:event.target.value}))}/></label><label className="field"><span>{pick("توضیح (اختیاری)","Note (optional)")}</span><textarea rows={3} value={credit.description} onChange={event=>setCredit(value=>({...value,description:event.target.value}))}/></label><small>{pick("این اعتبار فقط برای خرید پلن‌های شارژ حجم استفاده می‌شود و ربطی به ساخت اشتراک ندارد.","This credit is only used to buy traffic recharge packages and is not tied to subscription creation.")}</small><div className="runtime-modal-actions"><button className="ghost" type="button" onClick={()=>setCreditOpen(false)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy||!Number(credit.amount)}>{pick("ثبت اعتبار","Apply credit")}</button></div></form></div>}

    {plansOpen&&selectedReseller&&<div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" type="button" onClick={()=>setPlansOpen(false)}/><div className="runtime-modal-card reseller-admin-plans-card"><div className="card-head"><div><b>{pick("پلن‌های اشتراک مجاز","Authorized subscription plans")}</b><small>{pick("مدیر فقط دسترسی پلن را تعیین می‌کند؛ قیمت فروش را خود نماینده در پنل خودش تنظیم می‌کند.","Admin only assigns plan access; the reseller sets the selling price in their own panel.")}</small></div><button className="icon-button" onClick={()=>setPlansOpen(false)}>×</button></div><div className="reseller-plan-access-list">{plans.map((plan,index)=>{const pid=Number(plan.plan_id||0),allowed=Boolean(plan.is_allowed);return <div className="module-row" key={pid||index}><div className="grow"><b>{text(plan,"name")}</b><small>{num(plan,"traffic_gb")} GB · {num(plan,"duration_days")} {pick("روز","days")} · {pick("قیمت پایه سیستم","System base price")}: {money(num(plan,"base_price_toman"))}</small></div><Badge tone={allowed?"ok":"warn"}>{allowed?pick("مجاز","Allowed"):pick("غیرفعال","Disabled")}</Badge><button className="mini-btn" disabled={busy} onClick={()=>void togglePlan(plan)}>{allowed?pick("غیرفعال","Disable"):pick("فعال‌سازی","Enable")}</button></div>})}</div></div></div>}

    {packagesOpen&&<div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" type="button" onClick={()=>setPackagesOpen(false)}/><div className="runtime-modal-card reseller-packages-admin-card"><div className="card-head"><div><b>{pick("پلن‌های شارژ حجم نمایندگی","Reseller traffic recharge packages")}</b><small>{pick("این پلن‌ها جدا از پلن اشتراک هستند و نماینده با خریدشان موجودی حجم خود را شارژ می‌کند.","These packages are separate from subscription plans and recharge reseller traffic when purchased.")}</small></div><button className="icon-button" onClick={()=>setPackagesOpen(false)}>×</button></div><form className="runtime-editor" onSubmit={submitPackage}><div className="setting-grid"><label className="field"><span>{pick("عنوان","Title")}</span><input required minLength={2} value={packageDraft.title} onChange={event=>setPackageDraft(value=>({...value,title:event.target.value}))}/></label><label className="field"><span>{pick("حجم GB","Traffic GB")}</span><input required type="number" min={1} value={packageDraft.traffic_gb} onChange={event=>setPackageDraft(value=>({...value,traffic_gb:event.target.value}))}/></label><label className="field"><span>{pick("قیمت تومان","Price")}</span><input required type="number" min={1} value={packageDraft.price_toman} onChange={event=>setPackageDraft(value=>({...value,price_toman:event.target.value}))}/></label><label className="field"><span>{pick("ترتیب","Order")}</span><input type="number" min={0} value={packageDraft.sort_order} onChange={event=>setPackageDraft(value=>({...value,sort_order:event.target.value}))}/></label></div><label className="toggle module-toggle"><span>{pick("فعال","Active")}</span><input type="checkbox" checked={packageDraft.is_active} onChange={event=>setPackageDraft(value=>({...value,is_active:event.target.checked}))}/><i/></label><div className="action-row"><button className="primary" disabled={busy}>{packageDraft.id?pick("ذخیره ویرایش","Save changes"):pick("ساخت پلن شارژ حجم","Create recharge package")}</button>{packageDraft.id>0&&<button className="ghost" type="button" onClick={()=>setPackageDraft(emptyPackage)}>{pick("انصراف ویرایش","Cancel edit")}</button>}</div></form><div className="reseller-plan-access-list">{packages.map((row,index)=><div className="module-row" key={Number(row.id||0)||index}><div className="grow"><b>{text(row,"title")}</b><small>{num(row,"traffic_gb")} GB · {money(num(row,"price_toman"))}</small></div><Badge tone={Boolean(row.is_active)?"ok":"warn"}>{Boolean(row.is_active)?pick("فعال","Active"):pick("غیرفعال","Disabled")}</Badge><button className="mini-btn" onClick={()=>editPackage(row)}>{pick("ویرایش","Edit")}</button>{Boolean(row.is_active)&&<button className="mini-btn danger" disabled={busy} onClick={()=>void disablePackage(Number(row.id||0))}>{pick("غیرفعال","Disable")}</button>}</div>)}</div></div></div>}
  </div></Shell>;
}
