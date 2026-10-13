"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {Badge,Card,Shell,Stat} from "./ui";

type Row=Record<string,unknown>;
type UserHit={id:number;email:string;full_name?:string|null;phone?:string|null};

const text=(row:Row,...keys:string[])=>{for(const key of keys){const value=row[key];if(value!==undefined&&value!==null)return String(value);}return "";};
const num=(row:Row,...keys:string[])=>{const raw=text(row,...keys).replace(/[,٬]/g,"");const value=Number(raw||0);return Number.isFinite(value)?value:0;};
const gbFromBytes=(bytes:number)=>Number(bytes||0)/1024/1024/1024;
const gbText=(bytes:number)=>`${gbFromBytes(bytes).toLocaleString("fa-IR",{maximumFractionDigits:2})} GB`;

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  if(!response.ok){
    let message=`API error ${response.status}`;
    try{
      const payload=await response.json() as {detail?:unknown;message?:unknown};
      if(typeof payload.detail==="string")message=payload.detail;
      else if(typeof payload.message==="string")message=payload.message;
      else if(Array.isArray(payload.detail))message=payload.detail.map(item=>typeof item==="object"&&item&&"msg" in item?String((item as {msg:unknown}).msg):String(item)).join("، ");
    }catch{}
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

const api={
  list:()=>request<Row[]>("/v1/admin/resellers"),
  stats:()=>request<Row>("/v1/admin/resellers/stats"),
  searchUsers:(q:string)=>request<UserHit[]>(`/v1/admin/resellers/user-search?q=${encodeURIComponent(q)}`),
  create:(payload:Row)=>request<Row>("/v1/admin/resellers",{method:"POST",body:JSON.stringify(payload)}),
  toggle:(id:number)=>request<Row>(`/v1/admin/resellers/${id}/toggle-active`,{method:"POST"}),
  remove:(id:number)=>request<Row>(`/v1/admin/resellers/${id}`,{method:"DELETE"}),
  trafficAdjust:(id:number,traffic_gb:number,description:string)=>request<Row>(`/v1/admin/resellers/${id}/traffic/adjust`,{method:"POST",body:JSON.stringify({traffic_gb,description:description.trim()||null,idempotency_key:`admin-traffic-${id}-${Date.now()}-${Math.random().toString(36).slice(2,8)}`})})
};

function Message({error,ok}:{error:string;ok:string}){return <>{error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}</>;}

export function AdminResellersV2(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<Row[]>([]);
  const [stats,setStats]=useState<Row>({});
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [open,setOpen]=useState(false);
  const [emailQuery,setEmailQuery]=useState("");
  const [hits,setHits]=useState<UserHit[]>([]);
  const [searching,setSearching]=useState(false);
  const [selected,setSelected]=useState<UserHit|null>(null);
  const [name,setName]=useState("");
  const [initialGb,setInitialGb]=useState("0");
  const [filter,setFilter]=useState("");
  const [trafficRow,setTrafficRow]=useState<Row|null>(null);
  const [trafficGb,setTrafficGb]=useState("");
  const [trafficNote,setTrafficNote]=useState("");

  const load=async()=>{
    setError("");
    const result=await Promise.allSettled([api.list(),api.stats()]);
    if(result[0].status==="fulfilled")setRows(result[0].value);
    if(result[1].status==="fulfilled")setStats(result[1].value);
    const failed=result.find(item=>item.status==="rejected");
    if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));
  };

  useEffect(()=>{void load();},[]);

  useEffect(()=>{
    const query=emailQuery.trim();
    if(selected&&query.toLowerCase()===selected.email.toLowerCase()){setHits([]);return;}
    if(query.length<2){setHits([]);return;}
    const timer=window.setTimeout(async()=>{
      setSearching(true);
      try{setHits(await api.searchUsers(query));}
      catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
      finally{setSearching(false);}
    },260);
    return()=>window.clearTimeout(timer);
  },[emailQuery,selected]);

  const filtered=useMemo(()=>{
    const needle=filter.trim().toLowerCase();
    if(!needle)return rows;
    return rows.filter(row=>[
      row.name,row.code,row.email,row.phone,(row.owner as Row|undefined)?.email,(row.owner as Row|undefined)?.name,row.id
    ].some(value=>String(value??"").toLowerCase().includes(needle)));
  },[rows,filter]);

  const resetCreate=()=>{
    setSelected(null);setEmailQuery("");setHits([]);setName("");setInitialGb("0");
  };

  const act=async(label:string,fn:()=>Promise<unknown>)=>{
    if(busy)return;
    setBusy(true);setError("");setOk("");
    try{await fn();setOk(label);await load();}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const submitCreate=(event:FormEvent)=>{
    event.preventDefault();
    if(!selected){setError(pick("ابتدا کاربر را با ایمیل پیدا و انتخاب کنید.","Find and select a user by email first."));return;}
    const volume=Number(initialGb||0);
    if(!Number.isFinite(volume)||volume<0){setError(pick("حجم اولیه معتبر نیست.","Initial traffic is invalid."));return;}
    void act(pick("نمایندگی ساخته شد","Reseller created"),async()=>{
      await api.create({owner_user_id:selected.id,owner_email:selected.email,name:name.trim()||undefined,initial_traffic_gb:volume});
      setOpen(false);resetCreate();
    });
  };

  const submitTraffic=(event:FormEvent)=>{
    event.preventDefault();
    if(!trafficRow)return;
    const amount=Number(trafficGb);
    if(!Number.isFinite(amount)||amount===0){setError(pick("مقدار حجم باید بیشتر یا کمتر از صفر باشد.","Traffic adjustment cannot be zero."));return;}
    const id=Number(trafficRow.id||0);
    void act(amount>0?pick("حجم نمایندگی شارژ شد","Reseller traffic credited"):pick("حجم نمایندگی اصلاح شد","Reseller traffic adjusted"),async()=>{
      await api.trafficAdjust(id,amount,trafficNote);
      setTrafficRow(null);setTrafficGb("");setTrafficNote("");
    });
  };

  return <Shell active="/admin/resellers"><div className="page reseller-admin-v2">
    <div className="page-head"><div><h1>{pick("نمایندگی‌ها","Resellers")}</h1><small>{pick("مدل حجمی: ساخت اشتراک محدودیت تعدادی ندارد و مصرف واقعی از حجم نماینده کم می‌شود.","Volume model: subscription count is unlimited and real usage consumes reseller traffic.")}</small></div><div className="action-row"><button className="ghost" onClick={()=>void load()} disabled={busy}>{pick("بروزرسانی","Refresh")}</button><button className="primary" onClick={()=>{setOpen(v=>!v);setError("");setOk("");}}>＋ {pick("نماینده جدید","New reseller")}</button></div></div>
    <Message error={error} ok={ok}/>

    <div className="stats dashboard-stats">
      <Stat label={pick("کل نمایندگان","All resellers")} value={String(num(stats,"total")||rows.length)}/>
      <Stat label={pick("فعال","Active")} value={String(num(stats,"active")||rows.filter(row=>Boolean(row.is_active)).length)}/>
      <Stat label={pick("مشتریان","Customers")} value={String(num(stats,"customers"))}/>
      <Stat label={pick("حجم باقی‌مانده کل","Total remaining traffic")} value={gbText(num(stats,"traffic_balance_bytes"))}/>
    </div>

    {open&&<Card className="runtime-editor reseller-create-simple"><form onSubmit={submitCreate}>
      <div className="card-head"><div><b>{pick("ساخت نمایندگی","Create reseller")}</b><small>{pick("فقط کاربر را با ایمیل انتخاب کنید؛ کد و اطلاعات تماس خودکار ثبت می‌شوند.","Select the user by email; code and contact details are filled automatically.")}</small></div><button type="button" className="mini-btn" onClick={()=>{setOpen(false);resetCreate();}}>×</button></div>
      <div className="reseller-simple-grid">
        <div className="field reseller-user-picker"><span>{pick("ایمیل کاربر","User email")}</span><input type="search" dir="ltr" value={emailQuery} onChange={event=>{setEmailQuery(event.target.value);if(selected&&event.target.value!==selected.email)setSelected(null);}} placeholder="user@example.com" autoComplete="off"/>{searching&&<small>{pick("در حال جستجو...","Searching...")}</small>}
          {!selected&&hits.length>0&&<div className="reseller-user-results">{hits.map(user=><button type="button" key={user.id} onClick={()=>{setSelected(user);setEmailQuery(user.email);setName(user.full_name||"");setHits([]);}}><b dir="ltr">{user.email}</b><span>{user.full_name||pick("بدون نام","No name")}{user.phone?` · ${user.phone}`:""}</span></button>)}</div>}
          {!selected&&!searching&&emailQuery.trim().length>=2&&hits.length===0&&<small>{pick("کاربر پیدا نشد؛ ایمیل کاربری که قبلاً در پنل ثبت شده را وارد کنید.","No user found. Enter an email already registered in the panel.")}</small>}
        </div>
        {selected&&<div className="reseller-selected-user"><span>✓</span><div><b>{selected.full_name||pick("کاربر انتخاب شد","User selected")}</b><small dir="ltr">{selected.email}{selected.phone?` · ${selected.phone}`:""}</small></div><button type="button" className="mini-btn" onClick={()=>{setSelected(null);setEmailQuery("");setName("");}}>{pick("تغییر","Change")}</button></div>}
        <label className="field"><span>{pick("نام نمایندگی (اختیاری)","Reseller name (optional)")}</span><input value={name} onChange={event=>setName(event.target.value)} placeholder={selected?.full_name||pick("از نام کاربر استفاده می‌شود","Uses user name")}/></label>
        <label className="field"><span>{pick("حجم اولیه","Initial traffic")}</span><div className="input-with-unit"><input type="number" min={0} step="0.1" value={initialGb} onChange={event=>setInitialGb(event.target.value)}/><span>GB</span></div><small>{pick("بعداً هم از همین صفحه قابل شارژ است.","You can add more traffic later from this page.")}</small></label>
      </div>
      <div className="action-row"><button className="primary" disabled={busy||!selected}>{pick("ساخت نمایندگی","Create reseller")}</button><button type="button" className="ghost" onClick={()=>{setOpen(false);resetCreate();}}>{pick("انصراف","Cancel")}</button></div>
    </form></Card>}

    <Card>
      <div className="runtime-toolbar reseller-list-toolbar"><label>⌕ <input value={filter} onChange={event=>setFilter(event.target.value)} placeholder={pick("جستجو با نام، ایمیل یا کد...","Search name, email or code...")}/></label><Badge tone="violet">{filtered.length}</Badge></div>
      <div className="table"><table><thead><tr><th>{pick("نماینده","Reseller")}</th><th>{pick("کاربر / ایمیل","User / Email")}</th><th>{pick("کد","Code")}</th><th>{pick("حجم باقی‌مانده","Remaining traffic")}</th><th>{pick("مشتری / اشتراک","Customers / Subs")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{filtered.map(row=>{const id=Number(row.id||0);const owner=(row.owner&&typeof row.owner==="object"?row.owner:{}) as Row;const active=Boolean(row.is_active);return <tr key={id}><td><b>{text(row,"name")||`#${id}`}</b><small>{text(row,"brand_name")}</small></td><td><b>{text(owner,"name")||"—"}</b><small dir="ltr">{text(owner,"email")||text(row,"email")||"—"}</small></td><td><code dir="ltr">{text(row,"code")||"—"}</code></td><td><b>{gbText(num(row,"traffic_balance_bytes"))}</b>{num(row,"traffic_credit_bytes")>0&&<small>{pick("اعتبار","Credit")}: {gbText(num(row,"traffic_credit_bytes"))}</small>}</td><td>{num(row,"customer_count")} / {num(row,"subscription_count")}</td><td><Badge tone={active?"ok":"warn"}>{active?pick("فعال","Active"):pick("تعلیق","Suspended")}</Badge></td><td><div className="row-actions"><button className="mini-btn primary" onClick={()=>{setTrafficRow(row);setTrafficGb("");setTrafficNote("");}}>{pick("شارژ حجم","Add traffic")}</button><button className="mini-btn" disabled={busy} onClick={()=>void act(active?pick("نمایندگی تعلیق شد","Reseller suspended"):pick("نمایندگی فعال شد","Reseller activated"),()=>api.toggle(id))}>{active?pick("تعلیق","Suspend"):pick("فعال‌سازی","Activate")}</button><button className="mini-btn danger" disabled={busy} onClick={()=>{if(window.confirm(pick("نمایندگی حذف شود؟","Delete reseller?")))void act(pick("نمایندگی حذف شد","Reseller deleted"),()=>api.remove(id));}}>{pick("حذف","Delete")}</button></div></td></tr>})}</tbody></table></div>
      {!filtered.length&&<div className="runtime-empty">{pick("نمایندگی‌ای پیدا نشد.","No reseller found.")}</div>}
    </Card>

    {trafficRow&&<div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" type="button" onClick={()=>!busy&&setTrafficRow(null)}/><Card className="runtime-modal-card reseller-traffic-modal"><form onSubmit={submitTraffic}><div className="card-head"><div><b>{pick("شارژ / اصلاح حجم نمایندگی","Reseller traffic adjustment")}</b><small>{text(trafficRow,"name")} · {gbText(num(trafficRow,"traffic_balance_bytes"))}</small></div><button type="button" className="mini-btn" onClick={()=>setTrafficRow(null)}>×</button></div><label className="field"><span>{pick("مقدار حجم","Traffic amount")}</span><div className="input-with-unit"><input type="number" step="0.1" value={trafficGb} onChange={event=>setTrafficGb(event.target.value)} placeholder="100" autoFocus/><span>GB</span></div><small>{pick("برای کسر حجم عدد منفی وارد کنید.","Use a negative number to deduct traffic.")}</small></label><label className="field"><span>{pick("توضیح (اختیاری)","Note (optional)")}</span><input value={trafficNote} onChange={event=>setTrafficNote(event.target.value)}/></label><div className="action-row"><button className="primary" disabled={busy}>{pick("ثبت تغییر حجم","Save traffic")}</button><button type="button" className="ghost" onClick={()=>setTrafficRow(null)}>{pick("بستن","Close")}</button></div></form></Card></div>}
  </div></Shell>;
}
