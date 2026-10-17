"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {Badge,Card,Shell,Stat} from "./ui";

type AnyRow=Record<string,unknown>;
type ManageTab="profile"|"finance"|"traffic"|"plans"|"access";

type CreateDraft={
  owner_email:string;
  name:string;
  code:string;
  initial_traffic_gb:number;
};

type ManagementDraft={
  name:string;
  code:string;
  brand_name:string;
  email:string;
  phone:string;
  support_text:string;
  credit_limit:number;
  traffic_credit_gb:number;
  owner_full_name:string;
  owner_password:string;
  reseller_active:boolean;
  owner_active:boolean;
};

const emptyCreate:CreateDraft={owner_email:"",name:"",code:"",initial_traffic_gb:0};
const emptyManagement:ManagementDraft={
  name:"",code:"",brand_name:"",email:"",phone:"",support_text:"",
  credit_limit:0,traffic_credit_gb:0,owner_full_name:"",owner_password:"",
  reseller_active:true,owner_active:true,
};

function text(row:AnyRow|undefined,...keys:string[]){
  if(!row)return "";
  for(const key of keys){
    const value=row[key];
    if(value!==undefined&&value!==null)return String(value);
  }
  return "";
}

function num(row:AnyRow|undefined,...keys:string[]){
  const value=text(row,...keys).replace(/[,٬]/g,"");
  const parsed=Number(value||0);
  return Number.isFinite(parsed)?parsed:0;
}

function bool(row:AnyRow|undefined,...keys:string[]){
  if(!row)return false;
  for(const key of keys){
    if(key in row)return Boolean(row[key]);
  }
  return false;
}

function money(value:number){return `${Number(value||0).toLocaleString("fa-IR")} تومان`;}
function gb(value:number){return `${Number(value||0).toLocaleString("fa-IR",{maximumFractionDigits:2})} GB`;}
function dateText(value:unknown){
  if(!value)return "—";
  const date=new Date(String(value));
  return Number.isNaN(date.getTime())?String(value):date.toLocaleString("fa-IR");
}

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  if(!response.ok){
    let detail=`API error ${response.status}`;
    try{
      const payload=await response.json() as {detail?:unknown;message?:unknown};
      if(typeof payload.detail==="string")detail=payload.detail;
      else if(typeof payload.message==="string")detail=payload.message;
      else if(Array.isArray(payload.detail))detail=payload.detail.map(item=>typeof item==="object"&&item&&"msg" in item?String((item as {msg:unknown}).msg):String(item)).join("، ");
    }catch{}
    throw new Error(detail);
  }
  if(response.status===204)return undefined as T;
  const type=response.headers.get("content-type")||"";
  if(!type.includes("application/json"))return await response.text() as T;
  return response.json() as Promise<T>;
}

function RuntimeMessage({error,ok}:{error:string;ok:string}){
  return <>{error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}</>;
}

export function AdminResellersManagementRuntime(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<AnyRow[]>([]);
  const [stats,setStats]=useState<AnyRow>({});
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [query,setQuery]=useState("");

  const [createOpen,setCreateOpen]=useState(false);
  const [createDraft,setCreateDraft]=useState<CreateDraft>(emptyCreate);

  const [selectedId,setSelectedId]=useState<number|null>(null);
  const [selected,setSelected]=useState<AnyRow|null>(null);
  const [tab,setTab]=useState<ManageTab>("profile");
  const [draft,setDraft]=useState<ManagementDraft>(emptyManagement);
  const [walletTransactions,setWalletTransactions]=useState<AnyRow[]>([]);
  const [trafficTransactions,setTrafficTransactions]=useState<AnyRow[]>([]);
  const [plans,setPlans]=useState<AnyRow[]>([]);
  const [mother,setMother]=useState<AnyRow>({});
  const [walletAmount,setWalletAmount]=useState(0);
  const [walletNote,setWalletNote]=useState("");
  const [trafficAmount,setTrafficAmount]=useState(0);
  const [trafficNote,setTrafficNote]=useState("");

  const load=async()=>{
    setLoading(true);setError("");
    try{
      const [listResult,statsResult]=await Promise.all([
        request<AnyRow[]>("/v1/admin/resellers"),
        request<AnyRow>("/v1/admin/resellers/stats"),
      ]);
      setRows(listResult);setStats(statsResult);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setLoading(false);}
  };

  useEffect(()=>{void load();},[]);

  const filtered=useMemo(()=>{
    const needle=query.trim().toLowerCase();
    if(!needle)return rows;
    return rows.filter(row=>[
      text(row,"name"),text(row,"brand_name"),text(row,"code"),text(row,"email"),text(row,"phone"),
    ].join(" ").toLowerCase().includes(needle));
  },[rows,query]);

  const act=async(label:string,fn:()=>Promise<unknown>,reload=true)=>{
    if(busy)return;
    setBusy(true);setError("");setOk("");
    try{await fn();setOk(label);if(reload)await load();}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const openManage=async(id:number)=>{
    if(!id)return;
    setSelectedId(id);setSelected(null);setError("");setOk("");setTab("profile");
    try{
      const [management,walletTx,trafficTx,planRows,motherSettings]=await Promise.all([
        request<AnyRow>(`/v1/admin/resellers/${id}/management`),
        request<AnyRow[]>(`/v1/admin/resellers/${id}/wallet/transactions`),
        request<AnyRow[]>(`/v1/admin/resellers/${id}/traffic/transactions`),
        request<AnyRow[]>(`/v1/admin/resellers/${id}/plans`),
        request<AnyRow>("/v1/mother-access/admin"),
      ]);
      setSelected(management);
      setWalletTransactions(walletTx);
      setTrafficTransactions(trafficTx);
      setPlans(planRows);
      setMother(motherSettings);
      const owner=(management.owner&&typeof management.owner==="object")?management.owner as AnyRow:{};
      setDraft({
        name:text(management,"name"),
        code:text(management,"code"),
        brand_name:text(management,"brand_name"),
        email:text(management,"email"),
        phone:text(management,"phone"),
        support_text:text(management,"support_text"),
        credit_limit:num(management,"credit_limit"),
        traffic_credit_gb:num(management,"traffic_credit_gb"),
        owner_full_name:text(owner,"name","full_name")||text(management,"name"),
        owner_password:"",
        reseller_active:bool(management,"is_active"),
        owner_active:"is_active" in owner?Boolean(owner.is_active):true,
      });
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
  };

  const refreshSelected=async()=>{
    if(selectedId)await openManage(selectedId);
  };

  const createReseller=(event:FormEvent)=>{
    event.preventDefault();
    void act(pick("نماینده ساخته شد","Reseller created"),async()=>{
      await request("/v1/admin/resellers",{
        method:"POST",
        body:JSON.stringify({
          owner_email:createDraft.owner_email.trim(),
          name:createDraft.name.trim()||undefined,
          code:createDraft.code.trim()||undefined,
          initial_traffic_gb:Number(createDraft.initial_traffic_gb||0),
        }),
      });
      setCreateOpen(false);setCreateDraft(emptyCreate);
    });
  };

  const saveManagement=(event:FormEvent)=>{
    event.preventDefault();
    if(!selectedId)return;
    void act(pick("اطلاعات نماینده ذخیره شد","Reseller updated"),async()=>{
      await request(`/v1/admin/resellers/${selectedId}/management`,{
        method:"PUT",
        body:JSON.stringify({
          name:draft.name.trim(),
          code:draft.code.trim(),
          brand_name:draft.brand_name.trim()||null,
          email:draft.email.trim(),
          phone:draft.phone.trim()||null,
          support_text:draft.support_text.trim()||null,
          credit_limit:Number(draft.credit_limit||0),
          traffic_credit_gb:Number(draft.traffic_credit_gb||0),
          owner_full_name:draft.owner_full_name.trim()||draft.name.trim(),
          owner_password:draft.owner_password.trim()||null,
          reseller_active:draft.reseller_active,
          owner_active:draft.owner_active,
        }),
      });
      await refreshSelected();
    });
  };

  const adjustWallet=()=>{
    if(!selectedId||!walletAmount)return;
    void act(pick("کیف پول نماینده بروزرسانی شد","Wallet adjusted"),async()=>{
      await request(`/v1/admin/resellers/${selectedId}/wallet/adjust`,{
        method:"POST",
        body:JSON.stringify({amount:Number(walletAmount),description:walletNote.trim()||null}),
      });
      setWalletAmount(0);setWalletNote("");await refreshSelected();
    });
  };

  const adjustTraffic=()=>{
    if(!selectedId||!trafficAmount)return;
    void act(pick("حجم نماینده بروزرسانی شد","Traffic adjusted"),async()=>{
      await request(`/v1/admin/resellers/${selectedId}/traffic/adjust`,{
        method:"POST",
        body:JSON.stringify({traffic_gb:Number(trafficAmount),description:trafficNote.trim()||null}),
      });
      setTrafficAmount(0);setTrafficNote("");await refreshSelected();
    });
  };

  const savePlan=async(row:AnyRow)=>{
    if(!selectedId)return;
    const planId=num(row,"plan_id");
    await act(pick("تنظیمات پلن ذخیره شد","Plan settings saved"),async()=>{
      await request(`/v1/admin/resellers/${selectedId}/plans/${planId}`,{
        method:"PUT",
        body:JSON.stringify({
          buy_price_toman:num(row,"buy_price_toman"),
          sell_price_toman:num(row,"sell_price_toman"),
          is_active:bool(row,"is_allowed"),
        }),
      });
      await refreshSelected();
    },false);
  };

  const setMotherAccess=async(enabled:boolean)=>{
    if(!selectedId)return;
    await act(pick("دسترسی سرور مادر ذخیره شد","Mother access updated"),async()=>{
      await request(`/v1/mother-access/admin/resellers/${selectedId}`,{
        method:"PUT",body:JSON.stringify({enabled}),
      });
      const latest=await request<AnyRow>("/v1/mother-access/admin");setMother(latest);
    },false);
  };

  const toggleReseller=(id:number)=>{
    void act(pick("وضعیت نماینده تغییر کرد","Reseller status changed"),async()=>{
      await request(`/v1/admin/resellers/${id}/toggle-active`,{method:"POST"});
      if(selectedId===id)await refreshSelected();
    });
  };

  const deleteReseller=(id:number)=>{
    if(!window.confirm(pick("نماینده حذف شود؟ اگر اشتراک ثبت‌شده داشته باشد حذف مسدود می‌شود.","Delete reseller? Deletion is blocked when subscriptions exist.")))return;
    void act(pick("نماینده حذف شد","Reseller deleted"),async()=>{
      await request(`/v1/admin/resellers/${id}`,{method:"DELETE"});
      if(selectedId===id){setSelectedId(null);setSelected(null);}
    });
  };

  const motherOverrides=(mother.reseller_overrides&&typeof mother.reseller_overrides==="object")?mother.reseller_overrides as Record<string,unknown>:{};
  const motherEnabled=selectedId?(
    String(selectedId) in motherOverrides?Boolean(motherOverrides[String(selectedId)]):Boolean(mother.reseller_enabled)
  ):false;

  return <Shell active="/admin/resellers"><div className="page">
    <div className="page-head"><div><h1>{pick("نمایندگی‌ها","Resellers")}</h1></div><div className="action-row"><button className="ghost" disabled={loading||busy} onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button><button className="primary" onClick={()=>setCreateOpen(value=>!value)}>＋ {pick("نماینده جدید","New reseller")}</button></div></div>
    <RuntimeMessage error={error} ok={ok}/>

    <div className="stats dashboard-stats">
      <Stat label={pick("کل نمایندگان","All resellers")} value={String(num(stats,"total")||rows.length)} icon="♜"/>
      <Stat label={pick("فعال","Active")} value={String(num(stats,"active")||rows.filter(row=>bool(row,"is_active")).length)} icon="◉"/>
      <Stat label={pick("مشتریان","Customers")} value={String(num(stats,"customers"))} icon="♙"/>
      <Stat label={pick("اشتراک‌ها","Subscriptions")} value={String(num(stats,"subscriptions"))} icon="▱"/>
    </div>

    {createOpen&&<Card className="runtime-editor"><form onSubmit={createReseller}>
      <div className="card-head"><div><b>{pick("ساخت نمایندگی","Create reseller")}</b><small>{pick("مالک باید از قبل یک کاربر فعال پنل باشد.","Owner must already be an active panel user.")}</small></div><button type="button" className="mini-btn" onClick={()=>setCreateOpen(false)}>×</button></div>
      <div className="setting-grid">
        <label className="field"><span>{pick("ایمیل کاربر مالک","Owner user email")}</span><input required type="email" dir="ltr" value={createDraft.owner_email} onChange={event=>setCreateDraft(d=>({...d,owner_email:event.target.value}))}/></label>
        <label className="field"><span>{pick("نام نمایندگی","Reseller name")}</span><input value={createDraft.name} onChange={event=>setCreateDraft(d=>({...d,name:event.target.value}))}/></label>
        <label className="field"><span>{pick("کد نمایندگی","Reseller code")}</span><input dir="ltr" placeholder={pick("خالی = ساخت خودکار","Blank = auto generated")} value={createDraft.code} onChange={event=>setCreateDraft(d=>({...d,code:event.target.value}))}/></label>
        <label className="field"><span>{pick("حجم اولیه (GB)","Initial traffic (GB)")}</span><input type="number" min={0} step="0.01" value={createDraft.initial_traffic_gb} onChange={event=>setCreateDraft(d=>({...d,initial_traffic_gb:Number(event.target.value)}))}/></label>
      </div>
      <button className="primary" disabled={busy}>{pick("ساخت نماینده","Create reseller")}</button>
    </form></Card>}

    <Card>
      <div className="card-head"><div><b>{pick("لیست نمایندگان","Reseller list")}</b></div><input className="table-search" value={query} onChange={event=>setQuery(event.target.value)} placeholder={pick("جستجو نام، کد، ایمیل یا تلفن…","Search name, code, email or phone…")}/></div>
      <div className="table"><table><thead><tr><th>{pick("نماینده","Reseller")}</th><th>{pick("کد","Code")}</th><th>{pick("مالک","Owner")}</th><th>{pick("مشتری / اشتراک","Customers / Subs")}</th><th>{pick("حجم","Traffic")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead>
      <tbody>{filtered.map(row=>{const rid=num(row,"id");const owner=(row.owner&&typeof row.owner==="object")?row.owner as AnyRow:{};const active=bool(row,"is_active");return <tr key={rid}>
        <td><b>{text(row,"name")||`#${rid}`}</b><small>{text(row,"brand_name")||text(row,"email")||"—"}</small></td>
        <td dir="ltr">{text(row,"code")||"—"}</td>
        <td><b>{text(owner,"name","email")||`#${text(row,"owner_user_id")}`}</b><small dir="ltr">{text(owner,"email")}</small></td>
        <td>{num(row,"customer_count")} / {num(row,"subscription_count")}</td>
        <td>{gb(num(row,"traffic_balance_gb"))}</td>
        <td><Badge tone={active?"ok":"warn"}>{active?pick("فعال","Active"):pick("تعلیق","Suspended")}</Badge></td>
        <td><div className="row-actions"><button className="mini-btn primary" onClick={()=>void openManage(rid)}>{pick("مدیریت","Manage")}</button><button className="mini-btn" onClick={()=>toggleReseller(rid)}>{active?pick("تعلیق","Suspend"):pick("فعال‌سازی","Activate")}</button><button className="mini-btn danger" onClick={()=>deleteReseller(rid)}>{pick("حذف","Delete")}</button></div></td>
      </tr>;})}</tbody></table></div>
    </Card>

    {selectedId&&<Card className="runtime-editor">
      <div className="card-head"><div><b>{pick("مدیریت کامل نماینده","Full reseller management")}{selected?` · ${text(selected,"name")}`:""}</b><small>{selected?`${text(selected,"code")} · #${selectedId}`:pick("در حال دریافت اطلاعات…","Loading…")}</small></div><div className="action-row"><button className="ghost" onClick={()=>void refreshSelected()}>{pick("بروزرسانی","Refresh")}</button><button className="mini-btn" onClick={()=>{setSelectedId(null);setSelected(null);}}>×</button></div></div>

      {selected&&<>
        <div className="stats dashboard-stats">
          <Stat label={pick("کیف پول","Wallet")} value={money(num(selected,"wallet_balance"))}/>
          <Stat label={pick("سقف اعتبار","Credit limit")} value={money(num(selected,"credit_limit"))}/>
          <Stat label={pick("موجودی حجم","Traffic balance")} value={gb(num(selected,"traffic_balance_gb"))}/>
          <Stat label={pick("اعتبار حجمی","Traffic credit")} value={gb(num(selected,"traffic_credit_gb"))}/>
        </div>

        <div className="action-row reseller-admin-tabs">
          {(["profile","finance","traffic","plans","access"] as ManageTab[]).map(item=>{
            const labels:Record<ManageTab,string>={profile:pick("مشخصات و ورود","Profile & Login"),finance:pick("مالی و کیف پول","Finance"),traffic:pick("حجم","Traffic"),plans:pick("پلن‌ها و قیمت‌ها","Plans & Pricing"),access:pick("دسترسی‌ها","Access")};
            return <button key={item} type="button" className={tab===item?"primary":"ghost"} onClick={()=>setTab(item)}>{labels[item]}</button>;
          })}
        </div>

        {tab==="profile"&&<form onSubmit={saveManagement}>
          <div className="setting-grid">
            <label className="field"><span>{pick("نام نمایندگی","Reseller name")}</span><input required value={draft.name} onChange={event=>setDraft(d=>({...d,name:event.target.value}))}/></label>
            <label className="field"><span>{pick("کد نمایندگی","Reseller code")}</span><input required dir="ltr" value={draft.code} onChange={event=>setDraft(d=>({...d,code:event.target.value}))}/></label>
            <label className="field"><span>{pick("نام برند","Brand name")}</span><input value={draft.brand_name} onChange={event=>setDraft(d=>({...d,brand_name:event.target.value}))}/></label>
            <label className="field"><span>{pick("نام صاحب حساب","Account owner name")}</span><input value={draft.owner_full_name} onChange={event=>setDraft(d=>({...d,owner_full_name:event.target.value}))}/></label>
            <label className="field"><span>Email</span><input required type="email" dir="ltr" value={draft.email} onChange={event=>setDraft(d=>({...d,email:event.target.value}))}/></label>
            <label className="field"><span>{pick("تلفن","Phone")}</span><input dir="ltr" value={draft.phone} onChange={event=>setDraft(d=>({...d,phone:event.target.value}))}/></label>
            <label className="field"><span>{pick("رمز جدید حساب نماینده","New reseller password")}</span><input type="password" minLength={8} value={draft.owner_password} onChange={event=>setDraft(d=>({...d,owner_password:event.target.value}))} placeholder={pick("خالی = بدون تغییر","Blank = unchanged")}/></label>
            <label className="field"><span>{pick("سقف اعتبار مالی","Financial credit limit")}</span><input type="number" min={0} value={draft.credit_limit} onChange={event=>setDraft(d=>({...d,credit_limit:Number(event.target.value)}))}/></label>
            <label className="field"><span>{pick("اعتبار حجمی (GB)","Traffic credit (GB)")}</span><input type="number" min={0} step="0.01" value={draft.traffic_credit_gb} onChange={event=>setDraft(d=>({...d,traffic_credit_gb:Number(event.target.value)}))}/></label>
          </div>
          <label className="field"><span>{pick("متن پشتیبانی نماینده","Reseller support text")}</span><textarea rows={3} value={draft.support_text} onChange={event=>setDraft(d=>({...d,support_text:event.target.value}))}/></label>
          <div className="module-grid two">
            <label className="toggle module-toggle"><span>{pick("نمایندگی فعال","Reseller active")}</span><input type="checkbox" checked={draft.reseller_active} onChange={event=>setDraft(d=>({...d,reseller_active:event.target.checked}))}/><i/></label>
            <label className="toggle module-toggle"><span>{pick("حساب ورود فعال","Login account active")}</span><input type="checkbox" checked={draft.owner_active} onChange={event=>setDraft(d=>({...d,owner_active:event.target.checked}))}/><i/></label>
          </div>
          <button className="primary" disabled={busy}>{pick("ذخیره همه تغییرات","Save all changes")}</button>
        </form>}

        {tab==="finance"&&<div className="module-grid two">
          <Card><div className="card-head"><div><b>{pick("اصلاح کیف پول","Wallet adjustment")}</b><small>{pick("مبلغ مثبت شارژ و مبلغ منفی کسر می‌کند.","Positive credits, negative debits.")}</small></div></div>
            <label className="field"><span>{pick("مبلغ (تومان)","Amount (Toman)")}</span><input type="number" value={walletAmount} onChange={event=>setWalletAmount(Number(event.target.value))}/></label>
            <label className="field"><span>{pick("یادداشت","Note")}</span><input value={walletNote} onChange={event=>setWalletNote(event.target.value)}/></label>
            <button className="primary" disabled={busy||!walletAmount} onClick={adjustWallet}>{pick("ثبت اصلاح کیف پول","Apply wallet adjustment")}</button>
          </Card>
          <Card><div className="card-head"><b>{pick("آخرین تراکنش‌های کیف پول","Latest wallet transactions")}</b></div><div className="table"><table><thead><tr><th>{pick("مبلغ","Amount")}</th><th>{pick("مانده","Balance")}</th><th>{pick("نوع","Type")}</th><th>{pick("زمان","Time")}</th></tr></thead><tbody>{walletTransactions.slice(0,20).map(row=><tr key={num(row,"id")}><td>{money(num(row,"amount"))}</td><td>{money(num(row,"balance_after"))}</td><td>{text(row,"type")}</td><td>{dateText(row.created_at)}</td></tr>)}</tbody></table></div></Card>
        </div>}

        {tab==="traffic"&&<div className="module-grid two">
          <Card><div className="card-head"><div><b>{pick("اصلاح موجودی حجم","Traffic adjustment")}</b><small>{pick("مثبت = افزودن حجم، منفی = کسر حجم","Positive adds traffic, negative removes traffic")}</small></div></div>
            <label className="field"><span>{pick("حجم (GB)","Traffic (GB)")}</span><input type="number" step="0.01" value={trafficAmount} onChange={event=>setTrafficAmount(Number(event.target.value))}/></label>
            <label className="field"><span>{pick("یادداشت","Note")}</span><input value={trafficNote} onChange={event=>setTrafficNote(event.target.value)}/></label>
            <button className="primary" disabled={busy||!trafficAmount} onClick={adjustTraffic}>{pick("ثبت تغییر حجم","Apply traffic adjustment")}</button>
          </Card>
          <Card><div className="card-head"><b>{pick("آخرین تراکنش‌های حجم","Latest traffic transactions")}</b></div><div className="table"><table><thead><tr><th>{pick("تغییر","Change")}</th><th>{pick("مانده","Balance")}</th><th>{pick("نوع","Type")}</th><th>{pick("زمان","Time")}</th></tr></thead><tbody>{trafficTransactions.slice(0,20).map(row=><tr key={num(row,"id")}><td>{gb(num(row,"traffic_gb"))}</td><td>{gb(num(row,"balance_after_gb"))}</td><td>{text(row,"type")}</td><td>{dateText(row.created_at)}</td></tr>)}</tbody></table></div></Card>
        </div>}

        {tab==="plans"&&<Card><div className="card-head"><div><b>{pick("پلن‌ها و قیمت نماینده","Reseller plans & pricing")}</b><small>{pick("دسترسی هر پلن و قیمت خرید/فروش را مستقل تنظیم کنید.","Control access and buy/sell pricing per plan.")}</small></div></div><div className="table"><table><thead><tr><th>{pick("پلن","Plan")}</th><th>{pick("قیمت پایه","Base price")}</th><th>{pick("قیمت خرید","Buy price")}</th><th>{pick("قیمت فروش","Sell price")}</th><th>{pick("اجازه فروش","Allowed")}</th><th></th></tr></thead><tbody>{plans.map((row,index)=><tr key={num(row,"plan_id")}><td><b>{text(row,"name")}</b><small>{num(row,"traffic_gb")} GB · {num(row,"duration_days")} {pick("روز","days")}</small></td><td>{money(num(row,"base_price_toman"))}</td><td><input type="number" min={0} value={num(row,"buy_price_toman")} onChange={event=>setPlans(current=>current.map((item,i)=>i===index?{...item,buy_price_toman:Number(event.target.value)}:item))}/></td><td><input type="number" min={0} value={num(row,"sell_price_toman")} onChange={event=>setPlans(current=>current.map((item,i)=>i===index?{...item,sell_price_toman:Number(event.target.value)}:item))}/></td><td><input type="checkbox" checked={bool(row,"is_allowed")} onChange={event=>setPlans(current=>current.map((item,i)=>i===index?{...item,is_allowed:event.target.checked}:item))}/></td><td><button className="mini-btn primary" disabled={busy} onClick={()=>void savePlan(row)}>{pick("ذخیره","Save")}</button></td></tr>)}</tbody></table></div></Card>}

        {tab==="access"&&<div className="module-grid two">
          <Card><div className="card-head"><div><b>{pick("دسترسی سرور مادر","Mother server access")}</b></div><Badge tone={motherEnabled?"ok":"warn"}>{motherEnabled?pick("فعال","Enabled"):pick("غیرفعال","Disabled")}</Badge></div><label className="toggle module-toggle"><span>{pick("اجازه استفاده این نماینده از سرور مادر","Allow this reseller to use mother server")}</span><input type="checkbox" checked={motherEnabled} onChange={event=>void setMotherAccess(event.target.checked)}/><i/></label></Card>
          <Card><div className="card-head"><div><b>{pick("کنترل‌های مدیریتی","Administrative controls")}</b></div></div><div className="action-row"><button className="ghost" onClick={()=>toggleReseller(selectedId)}>{bool(selected,"is_active")?pick("تعلیق نمایندگی","Suspend reseller"):pick("فعال‌سازی نمایندگی","Activate reseller")}</button><button className="danger" onClick={()=>deleteReseller(selectedId)}>{pick("حذف نمایندگی","Delete reseller")}</button></div><small>{pick("حذف در صورت وجود اشتراک ثبت‌شده توسط Backend مسدود می‌شود.","Backend blocks deletion when reseller subscriptions exist.")}</small></Card>
        </div>}
      </>}
    </Card>}
  </div></Shell>;
}
