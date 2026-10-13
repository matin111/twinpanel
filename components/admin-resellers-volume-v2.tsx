"use client";

import {FormEvent,useEffect,useMemo,useRef,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

type Row=Record<string,unknown>;

type UserHit={
  id:number;
  email:string;
  full_name?:string|null;
  phone?:string|null;
};

type CreateDraft={
  owner_user_id:number;
  name:string;
  initial_traffic_gb:string;
};

type AdjustDraft={
  reseller_id:number;
  reseller_name:string;
  traffic_gb:string;
  description:string;
};

const emptyCreate:CreateDraft={owner_user_id:0,name:"",initial_traffic_gb:"0"};
const emptyAdjust:AdjustDraft={reseller_id:0,reseller_name:"",traffic_gb:"",description:""};

function text(row:Row,...keys:string[]){
  for(const key of keys){
    const value=row?.[key];
    if(value!==undefined&&value!==null)return String(value);
  }
  return "";
}

function num(row:Row,...keys:string[]){
  const value=Number(text(row,...keys).replace(/[,٬]/g,"")||0);
  return Number.isFinite(value)?value:0;
}

function bool(row:Row,key:string){return Boolean(row?.[key]);}
function gb(value:number){return `${Number(value||0).toLocaleString("fa-IR",{maximumFractionDigits:2})} GB`;}

async function api<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");

  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");

  const response=await fetch(`${API_BASE}${path}`,{
    ...init,
    headers,
    cache:"no-store",
  });

  let payload:unknown=null;
  const raw=await response.text();
  if(raw){
    try{payload=JSON.parse(raw);}catch{payload=raw;}
  }

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

function Notice({error,ok}:{error:string;ok:string}){
  return <>{error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}</>;
}

export function AdminResellersVolumeV2(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<Row[]>([]);
  const [stats,setStats]=useState<Row>({});
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [createOpen,setCreateOpen]=useState(false);
  const [adjustOpen,setAdjustOpen]=useState(false);
  const [create,setCreate]=useState<CreateDraft>(emptyCreate);
  const [adjust,setAdjust]=useState<AdjustDraft>(emptyAdjust);

  const [userQuery,setUserQuery]=useState("");
  const [userHits,setUserHits]=useState<UserHit[]>([]);
  const [selectedUser,setSelectedUser]=useState<UserHit|null>(null);
  const [searching,setSearching]=useState(false);
  const searchSeq=useRef(0);

  const load=async()=>{
    setError("");
    const [listResult,statsResult]=await Promise.allSettled([
      api<Row[]>("/v1/admin/resellers"),
      api<Row>("/v1/admin/resellers/stats"),
    ]);
    if(listResult.status==="fulfilled")setRows(listResult.value);
    if(statsResult.status==="fulfilled")setStats(statsResult.value);
    const failed=[listResult,statsResult].find(item=>item.status==="rejected");
    if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));
  };

  useEffect(()=>{void load();},[]);

  useEffect(()=>{
    if(!createOpen||selectedUser)return;
    const q=userQuery.trim();
    if(q.length<2){setUserHits([]);setSearching(false);return;}

    const seq=++searchSeq.current;
    setSearching(true);
    const timer=window.setTimeout(async()=>{
      try{
        const result=await api<UserHit[]>(`/v1/admin/resellers/user-search?q=${encodeURIComponent(q)}&limit=12`);
        if(seq===searchSeq.current)setUserHits(result);
      }catch(reason){
        if(seq===searchSeq.current)setError(reason instanceof Error?reason.message:String(reason));
      }finally{
        if(seq===searchSeq.current)setSearching(false);
      }
    },250);
    return()=>window.clearTimeout(timer);
  },[userQuery,createOpen,selectedUser]);

  const act=async(label:string,fn:()=>Promise<unknown>)=>{
    if(busy)return;
    setBusy(true);setError("");setOk("");
    try{await fn();setOk(label);await load();}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const resetCreate=()=>{
    setCreateOpen(false);
    setCreate(emptyCreate);
    setUserQuery("");
    setUserHits([]);
    setSelectedUser(null);
  };

  const chooseUser=(user:UserHit)=>{
    setSelectedUser(user);
    setCreate(d=>({...d,owner_user_id:user.id,name:d.name||user.full_name||""}));
    setUserQuery(user.email);
    setUserHits([]);
  };

  const submitCreate=(event:FormEvent)=>{
    event.preventDefault();
    if(!selectedUser||!create.owner_user_id){setError(pick("ابتدا کاربر را با ایمیل جستجو و انتخاب کنید.","Search and select a user first."));return;}
    const initial=Number(create.initial_traffic_gb||0);
    if(!Number.isFinite(initial)||initial<0){setError(pick("حجم اولیه معتبر نیست.","Initial traffic is invalid."));return;}

    void act(pick("نمایندگی ساخته شد","Reseller created"),async()=>{
      await api("/v1/admin/resellers",{
        method:"POST",
        body:JSON.stringify({
          owner_user_id:create.owner_user_id,
          name:create.name.trim()||null,
          initial_traffic_gb:initial,
        }),
      });
      resetCreate();
    });
  };

  const openAdjust=(row:Row)=>{
    setAdjust({
      reseller_id:Number(row.id||0),
      reseller_name:text(row,"name")||`#${text(row,"id")}`,
      traffic_gb:"",
      description:"",
    });
    setAdjustOpen(true);
  };

  const submitAdjust=(event:FormEvent)=>{
    event.preventDefault();
    const amount=Number(adjust.traffic_gb);
    if(!Number.isFinite(amount)||amount===0){setError(pick("مقدار حجم باید بیشتر یا کمتر از صفر باشد.","Traffic amount must be non-zero."));return;}

    void act(pick("حجم نمایندگی تغییر کرد","Reseller traffic updated"),async()=>{
      await api(`/v1/admin/resellers/${adjust.reseller_id}/traffic/adjust`,{
        method:"POST",
        body:JSON.stringify({
          traffic_gb:amount,
          description:adjust.description.trim()||null,
          idempotency_key:`admin-reseller-traffic-${adjust.reseller_id}-${Date.now()}-${Math.random().toString(36).slice(2,8)}`,
        }),
      });
      setAdjustOpen(false);
      setAdjust(emptyAdjust);
    });
  };

  const totalTrafficGb=useMemo(()=>{
    if("traffic_balance_bytes" in stats)return Number(stats.traffic_balance_bytes||0)/1024/1024/1024;
    return rows.reduce((sum,row)=>sum+num(row,"traffic_balance_gb"),0);
  },[rows,stats]);

  return <Shell active="/admin/resellers"><div className="page reseller-admin-v2">
    <div className="page-head">
      <div>
        <h1>{pick("نمایندگی‌ها","Resellers")}</h1>
        <small>{pick("مدل حجمی: ساخت اشتراک نامحدود و کسر حجم فقط بر اساس مصرف واقعی کاربران","Volume model: unlimited subscription creation; reseller traffic is deducted only from real customer usage")}</small>
      </div>
      <button className="primary" onClick={()=>{setCreateOpen(true);setError("");setOk("");}}>＋ {pick("نماینده جدید","New reseller")}</button>
    </div>

    <Notice error={error} ok={ok}/>

    <div className="stats dashboard-stats reseller-admin-stats">
      <Stat label={pick("کل نمایندگان","All resellers")} value={String(num(stats,"total")||rows.length)}/>
      <Stat label={pick("فعال","Active")} value={String(num(stats,"active")||rows.filter(row=>bool(row,"is_active")).length)}/>
      <Stat label={pick("مشتریان","Customers")} value={String(num(stats,"customers"))}/>
      <Stat label={pick("حجم باقی‌مانده کل","Total remaining traffic")} value={gb(totalTrafficGb)}/>
    </div>

    <Card className="reseller-volume-info">
      <div className="reseller-volume-info-grid">
        <div><span>∞</span><div><b>{pick("ساخت اشتراک نامحدود","Unlimited subscription creation")}</b><small>{pick("تعداد اشتراک‌ها محدود نمی‌شود.","Subscription count is not limited.")}</small></div></div>
        <div><span>GB</span><div><b>{pick("حسابداری بر اساس مصرف واقعی","Usage-based traffic accounting")}</b><small>{pick("ساخت یا تمدید اشتراک از حجم نماینده کم نمی‌کند؛ مصرف واقعی کاربران کم می‌کند.","Creating or renewing subscriptions does not reserve reseller traffic; real usage consumes the pool.")}</small></div></div>
        <div><span>↻</span><div><b>{pick("فعال‌سازی خودکار بعد از شارژ","Automatic restore after recharge")}</b><small>{pick("اگر حجم تمام شود سرویس‌های نماینده متوقف و بعد از شارژ حجم دوباره فعال می‌شوند.","When the pool is exhausted, reseller services are suspended and restored after recharge.")}</small></div></div>
      </div>
    </Card>

    <Card>
      <div className="card-head"><div><b>{pick("لیست نمایندگان","Reseller list")}</b><small>{pick("مدیریت نماینده فقط با حجم انجام می‌شود؛ کیف پول و سقف ساخت اشتراک در این مدل استفاده نمی‌شود.","Resellers are managed by traffic only; wallet and subscription-count limits are not used in this model.")}</small></div><Badge tone="violet">{rows.length}</Badge></div>
      <div className="table reseller-admin-table"><table><thead><tr><th>{pick("نماینده","Reseller")}</th><th>{pick("مالک","Owner")}</th><th>{pick("کد","Code")}</th><th>{pick("حجم باقی‌مانده","Remaining traffic")}</th><th>{pick("مشتری / اشتراک","Customers / Subs")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{rows.map(row=>{const rid=Number(row.id||0);const active=bool(row,"is_active");const owner=(row.owner&&typeof row.owner==="object"?row.owner:{}) as Row;return <tr key={rid}><td><b>{text(row,"name")||`#${rid}`}</b><small>{text(row,"brand_name")||pick("نمایندگی حجمی","Volume reseller")}</small></td><td><b>{text(owner,"name")||`#${text(row,"owner_user_id")}`}</b><small dir="ltr">{text(owner,"email")||text(row,"email")||"—"}</small></td><td><code dir="ltr">{text(row,"code")||"—"}</code></td><td><b>{gb(num(row,"traffic_balance_gb"))}</b><small>{pick("اعتبار حجمی","Traffic credit")}: {gb(num(row,"traffic_credit_gb"))}</small></td><td><b>{num(row,"customer_count").toLocaleString("fa-IR")} / {num(row,"subscription_count").toLocaleString("fa-IR")}</b><small>{pick("ساخت اشتراک: نامحدود","Subscription creation: unlimited")}</small></td><td><Badge tone={active?"ok":"warn"}>{active?pick("فعال","Active"):pick("تعلیق","Suspended")}</Badge></td><td><div className="row-actions"><button className="mini-btn primary-lite" onClick={()=>openAdjust(row)}>＋ {pick("شارژ حجم","Traffic")}</button><button className="mini-btn" disabled={busy} onClick={()=>void act(active?pick("نمایندگی تعلیق شد","Reseller suspended"):pick("نمایندگی فعال شد","Reseller activated"),()=>api(`/v1/admin/resellers/${rid}/toggle-active`,{method:"POST"}))}>{active?pick("تعلیق","Suspend"):pick("فعال‌سازی","Activate")}</button><button className="mini-btn danger" disabled={busy} onClick={()=>{if(window.confirm(pick("نماینده حذف شود؟ اگر اشتراک ثبت‌شده داشته باشد حذف مجاز نیست.","Delete reseller? Deletion is blocked while reseller subscriptions exist.")))void act(pick("نماینده حذف شد","Reseller deleted"),()=>api(`/v1/admin/resellers/${rid}`,{method:"DELETE"}));}}>{pick("حذف","Delete")}</button></div></td></tr>})}</tbody></table></div>
      {!rows.length&&<div className="runtime-empty">{pick("هنوز نماینده‌ای ساخته نشده است.","No reseller exists yet.")}</div>}
    </Card>

    {createOpen&&<div className="runtime-modal reseller-create-simple" role="dialog" aria-modal="true">
      <button className="runtime-modal-bg" type="button" onClick={()=>!busy&&resetCreate()}/>
      <form className="runtime-modal-card reseller-simple-card" onSubmit={submitCreate}>
        <div className="card-head"><div><b>{pick("ساخت نماینده","Create reseller")}</b><small>{pick("فقط کاربر و حجم اولیه را مشخص کنید؛ بقیه اطلاعات خودکار است.","Choose the user and initial traffic; everything else is automatic.")}</small></div><button className="icon-button" type="button" onClick={resetCreate}>×</button></div>

        <div className="reseller-user-search-block">
          <label className="field">
            <span>{pick("جستجوی کاربر با ایمیل، نام یا موبایل","Search user by email, name or phone")}</span>
            <input autoFocus dir="ltr" value={userQuery} onChange={e=>{setUserQuery(e.target.value);setSelectedUser(null);setCreate(d=>({...d,owner_user_id:0}));}} placeholder="user@example.com" autoComplete="off"/>
          </label>

          {!selectedUser&&userQuery.trim().length>=2&&<div className="reseller-user-results">
            {searching&&<div className="reseller-search-state">{pick("در حال جستجو...","Searching...")}</div>}
            {!searching&&userHits.map(user=><button type="button" key={user.id} onClick={()=>chooseUser(user)}><span className="reseller-user-avatar">{(user.full_name||user.email||"U").charAt(0).toUpperCase()}</span><div><b>{user.full_name||pick("بدون نام","No name")}</b><small dir="ltr">{user.email}</small>{user.phone&&<small dir="ltr">{user.phone}</small>}</div><em>#{user.id}</em></button>)}
            {!searching&&!userHits.length&&<div className="reseller-search-state">{pick("کاربر آزادی با این مشخصات پیدا نشد.","No eligible user matches this search.")}</div>}
          </div>}

          {selectedUser&&<div className="reseller-selected-user"><span className="reseller-user-avatar">{(selectedUser.full_name||selectedUser.email||"U").charAt(0).toUpperCase()}</span><div><b>{selectedUser.full_name||pick("کاربر","User")}</b><small dir="ltr">{selectedUser.email}</small>{selectedUser.phone&&<small dir="ltr">{selectedUser.phone}</small>}</div><button type="button" className="mini-btn" onClick={()=>{setSelectedUser(null);setCreate(d=>({...d,owner_user_id:0}));setUserQuery("");}}>{pick("تغییر","Change")}</button></div>}
        </div>

        <div className="setting-grid reseller-simple-fields">
          <label className="field"><span>{pick("نام نمایندگی (اختیاری)","Reseller name (optional)")}</span><input value={create.name} onChange={e=>setCreate(d=>({...d,name:e.target.value}))} placeholder={selectedUser?.full_name||pick("از نام کاربر استفاده می‌شود","Uses customer name")}/></label>
          <label className="field"><span>{pick("حجم اولیه (GB)","Initial traffic (GB)")}</span><input type="number" min={0} step="0.01" value={create.initial_traffic_gb} onChange={e=>setCreate(d=>({...d,initial_traffic_gb:e.target.value}))}/><small>{pick("بعداً هر زمان خواستی از همین صفحه شارژ یا کسر می‌کنی.","You can add or deduct traffic from this page later.")}</small></label>
        </div>

        <div className="reseller-auto-note"><span>✓</span><div><b>{pick("خودکار انجام می‌شود","Automatic")}</b><small>{pick("کد نمایندگی ساخته می‌شود؛ ایمیل و تلفن از حساب کاربر خوانده می‌شود؛ ساخت اشتراک محدودیت تعدادی ندارد.","The reseller code is generated automatically; email and phone come from the user account; subscription creation has no count limit.")}</small></div></div>

        <div className="runtime-modal-actions"><button className="ghost" type="button" onClick={resetCreate}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy||!selectedUser}>{busy?"…":pick("ساخت نماینده","Create reseller")}</button></div>
      </form>
    </div>}

    {adjustOpen&&<div className="runtime-modal" role="dialog" aria-modal="true">
      <button className="runtime-modal-bg" type="button" onClick={()=>!busy&&setAdjustOpen(false)}/>
      <form className="runtime-modal-card reseller-traffic-card" onSubmit={submitAdjust}>
        <div className="card-head"><div><b>{pick("شارژ / کسر حجم","Add / deduct traffic")}</b><small>{adjust.reseller_name}</small></div><button className="icon-button" type="button" onClick={()=>setAdjustOpen(false)}>×</button></div>
        <label className="field"><span>{pick("مقدار GB","Traffic GB")}</span><input autoFocus type="number" step="0.01" value={adjust.traffic_gb} onChange={e=>setAdjust(d=>({...d,traffic_gb:e.target.value}))} placeholder="100"/><small>{pick("برای شارژ عدد مثبت و برای کسر عدد منفی وارد کنید.","Use a positive number to add traffic and a negative number to deduct it.")}</small></label>
        <label className="field"><span>{pick("توضیح (اختیاری)","Note (optional)")}</span><textarea rows={3} value={adjust.description} onChange={e=>setAdjust(d=>({...d,description:e.target.value}))}/></label>
        <div className="runtime-modal-actions"><button className="ghost" type="button" onClick={()=>setAdjustOpen(false)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy||!Number(adjust.traffic_gb)}>{pick("ثبت تغییر حجم","Apply traffic change")}</button></div>
      </form>
    </div>}
  </div></Shell>;
}
