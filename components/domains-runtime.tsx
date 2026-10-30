"use client";

import {useCallback,useEffect,useMemo,useState} from "react";
import {API_BASE,api,endpoint} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {Shell} from "./ui";

type DomainType="panel"|"shop"|"api"|"subscription";
type DomainRow={
  id:number;
  domain:string;
  domain_type:DomainType;
  ssl_status:"none"|"pending"|"active"|"failed"|string;
  ssl_expires_at?:string|null;
  target_host?:string|null;
  target_port:number;
  nginx_status?:string|null;
  ssl_error?:string|null;
  is_active?:boolean;
};

type IconName="globe"|"shield"|"layers"|"attention"|"search"|"plus"|"refresh"|"trash"|"panel"|"shop"|"api"|"subscription"|"external"|"lock"|"server"|"check";

const typeLabel:Record<DomainType,{fa:string;en:string}>={
  panel:{fa:"پنل",en:"Panel"},
  shop:{fa:"فروشگاه",en:"Store"},
  api:{fa:"API",en:"API"},
  subscription:{fa:"سابسکریپشن",en:"Subscription"}
};

const roleDescription:Record<DomainType,{fa:string;en:string}>={
  panel:{fa:"پنل مدیریت و کاربری",en:"Admin and customer portal"},
  shop:{fa:"فروشگاه عمومی",en:"Public storefront"},
  api:{fa:"API عمومی سرویس",en:"Public API endpoint"},
  subscription:{fa:"لینک‌ها و فایل‌های اتصال",en:"Subscription links and connection files"}
};

function Icon({name,size=20}:{name:IconName;size?:number}){
  const common={width:size,height:size,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:1.8,strokeLinecap:"round" as const,strokeLinejoin:"round" as const,"aria-hidden":true};
  switch(name){
    case "globe": return <svg {...common}><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/></svg>;
    case "shield": return <svg {...common}><path d="M12 3 20 6v5c0 5-3.4 8.5-8 10-4.6-1.5-8-5-8-10V6l8-3Z"/><path d="m8.5 12 2.2 2.2 4.8-5"/></svg>;
    case "layers": return <svg {...common}><path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/></svg>;
    case "attention": return <svg {...common}><path d="M12 3 2.8 20h18.4L12 3Z"/><path d="M12 9v4M12 17h.01"/></svg>;
    case "search": return <svg {...common}><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>;
    case "plus": return <svg {...common}><path d="M12 5v14M5 12h14"/></svg>;
    case "refresh": return <svg {...common}><path d="M20 6v5h-5M4 18v-5h5"/><path d="M6.1 9A7 7 0 0 1 18 6l2 5M17.9 15A7 7 0 0 1 6 18l-2-5"/></svg>;
    case "trash": return <svg {...common}><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5"/></svg>;
    case "panel": return <svg {...common}><rect x="4" y="3" width="16" height="18" rx="3"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>;
    case "shop": return <svg {...common}><path d="M4 10h16l-1-5H5l-1 5Z"/><path d="M5 10v9h14v-9M9 19v-5h6v5"/></svg>;
    case "api": return <svg {...common}><path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 5l-4 14"/></svg>;
    case "subscription": return <svg {...common}><path d="M10 13a5 5 0 0 0 7.1.1l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1"/><path d="M14 11a5 5 0 0 0-7.1-.1l-2 2A5 5 0 0 0 12 20l1.1-1.1"/></svg>;
    case "external": return <svg {...common}><path d="M14 4h6v6M20 4l-9 9"/><path d="M18 13v6H5V6h6"/></svg>;
    case "lock": return <svg {...common}><rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>;
    case "server": return <svg {...common}><rect x="3" y="4" width="18" height="6" rx="2"/><rect x="3" y="14" width="18" height="6" rx="2"/><path d="M7 7h.01M7 17h.01M11 7h6M11 17h6"/></svg>;
    case "check": return <svg {...common}><path d="m5 12 4 4L19 6"/></svg>;
  }
}

function readableApiError(value:unknown):string{
  if(typeof value==="string")return value;
  if(!value||typeof value!=="object")return "";
  const record=value as Record<string,unknown>;
  for(const key of ["message","error","reason","code"]){
    const candidate=record[key];
    if(typeof candidate==="string"&&candidate.trim())return candidate;
  }
  try{return JSON.stringify(value);}catch{return "";}
}

async function domainRequest<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("نشست مدیر پیدا نشد؛ دوباره وارد شوید.");
  const headers=new Headers(init.headers);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  headers.set("Authorization",`Bearer ${token}`);
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  if(!response.ok){
    let detail="";
    try{
      const data=await response.json();
      detail=readableApiError(data?.detail??data?.message??data);
    }catch{}
    throw new Error(detail||`API ${response.status}`);
  }
  if(response.status===204)return undefined as T;
  return response.json() as Promise<T>;
}

function normalizeDomain(value:string){
  return value.trim().toLowerCase().replace(/^https?:\/\//,"").replace(/\/$/,"");
}

function roleIcon(type:DomainType):IconName{
  if(type==="shop")return "shop";
  if(type==="api")return "api";
  if(type==="subscription")return "subscription";
  return "panel";
}

function statusClass(value:string|undefined|null){
  if(value==="active")return "is-active";
  if(value==="failed")return "is-failed";
  return "is-pending";
}

export function DomainsRuntimePage(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<DomainRow[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState<number|string|null>(null);
  const [error,setError]=useState("");
  const [success,setSuccess]=useState("");
  const [showAdd,setShowAdd]=useState(false);
  const [domain,setDomain]=useState("");
  const [domainType,setDomainType]=useState<DomainType>("panel");
  const [query,setQuery]=useState("");

  const load=useCallback(async()=>{
    setLoading(true);setError("");
    try{setRows(await domainRequest<DomainRow[]>(api.admin.domains));}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setLoading(false);}
  },[]);

  useEffect(()=>{void load();},[load]);

  const stats=useMemo(()=>{
    const active=rows.filter(x=>x.is_active!==false).length;
    const ssl=rows.filter(x=>x.ssl_status==="active").length;
    const failed=rows.filter(x=>x.ssl_status==="failed"||x.nginx_status==="failed").length;
    const roles=new Set(rows.map(x=>x.domain_type)).size;
    return {active,ssl,failed,roles};
  },[rows]);

  const filteredRows=useMemo(()=>{
    const clean=query.trim().toLowerCase();
    if(!clean)return rows;
    return rows.filter(row=>{
      const role=typeLabel[row.domain_type];
      return row.domain.toLowerCase().includes(clean)||row.domain_type.includes(clean)||role.fa.includes(clean)||role.en.toLowerCase().includes(clean);
    });
  },[query,rows]);

  const createDomain=async()=>{
    const clean=normalizeDomain(domain);
    if(!clean){setError(pick("دامنه را وارد کنید.","Enter a domain."));return;}
    setBusy("create");setError("");setSuccess("");
    try{
      await domainRequest<DomainRow>(api.admin.domains,{method:"POST",body:JSON.stringify({domain:clean,domain_type:domainType})});
      setDomain("");setShowAdd(false);setSuccess(pick("دامنه اضافه شد و Nginx تنظیم شد. SSL را جداگانه فعال کنید.","Domain added and Nginx configured. Enable SSL separately."));
      await load();
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(null);}
  };

  const changeType=async(row:DomainRow,next:DomainType)=>{
    setBusy(row.id);setError("");setSuccess("");
    try{
      await domainRequest<DomainRow>(endpoint.domain(row.id),{method:"PUT",body:JSON.stringify({domain_type:next})});
      setSuccess(pick("نقش دامنه بروزرسانی شد.","Domain role updated."));await load();
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(null);}
  };

  const issueSsl=async(row:DomainRow)=>{
    setBusy(`ssl-${row.id}`);setError("");setSuccess("");
    try{
      await domainRequest(endpoint.domainSsl(row.id),{method:"POST"});
      setSuccess(pick("درخواست SSL انجام شد.","SSL request completed."));await load();
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(null);}
  };

  const removeDomain=async(row:DomainRow)=>{
    if(!window.confirm(pick(`دامنه ${row.domain} حذف شود؟`,`Delete ${row.domain}?`)))return;
    setBusy(`delete-${row.id}`);setError("");setSuccess("");
    try{
      await domainRequest(endpoint.domain(row.id),{method:"DELETE"});
      setSuccess(pick("دامنه حذف شد.","Domain removed."));await load();
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(null);}
  };

  const statsCards=[
    {key:"active",label:pick("دامنه فعال","Active domains"),value:loading?"…":String(stats.active),hint:pick("دامنه ثبت‌شده","configured domains"),icon:"globe" as IconName,tone:"violet"},
    {key:"ssl",label:pick("SSL فعال","Active SSL"),value:loading?"…":String(stats.ssl),hint:pick("گواهی معتبر","valid certificates"),icon:"shield" as IconName,tone:"green"},
    {key:"roles",label:pick("نقش‌های فعال","Configured roles"),value:loading?"…":`${stats.roles}/4`,hint:"Panel · Store · API · Sub",icon:"server" as IconName,tone:"cyan"},
    {key:"attention",label:pick("در انتظار بررسی","Needs attention"),value:loading?"…":String(stats.failed),hint:stats.failed?pick("نیازمند بررسی","review required"):pick("همه‌چیز سالم است","all systems healthy"),icon:"attention" as IconName,tone:stats.failed?"red":"violet"}
  ];

  return <Shell active="/admin/domains">
    <div className="page domains-runtime domains-runtime-v2">
      <section className="domains-hero">
        <div className="domains-hero-copy">
          <div className="domains-breadcrumb">{pick("شبکه و زیرساخت  /  دامنه و SSL","Network & Infrastructure / Domains & SSL")}</div>
          <div className="domains-title-row">
            <span className="domains-title-icon"><Icon name="globe" size={28}/></span>
            <div>
              <h1>{pick("دامنه و SSL","Domains & SSL")}</h1>
              <p>{pick("مدیریت دامنه‌ها، گواهی‌های SSL و مسیر سرویس‌های TwinPanel","Manage domains, SSL certificates and TwinPanel service routing")}</p>
            </div>
          </div>
        </div>
        <div className="domains-hero-visual" aria-hidden="true">
          <span className="domains-orbit domains-orbit-one"/>
          <span className="domains-orbit domains-orbit-two"/>
          <span className="domains-hero-globe"><Icon name="globe" size={64}/></span>
          <span className="domains-float-chip ssl"><Icon name="lock" size={15}/> SSL <i/></span>
          <span className="domains-float-chip nginx"><Icon name="shield" size={15}/> Nginx <i/></span>
        </div>
      </section>

      {error&&<div className="runtime-alert error"><span className="alert-icon"><Icon name="attention" size={17}/></span><span>{error}</span></div>}
      {success&&<div className="runtime-alert success"><span className="alert-icon"><Icon name="check" size={17}/></span><span>{success}</span></div>}

      <section className="domains-stat-grid">
        {statsCards.map(card=><article className={`domain-stat-card tone-${card.tone}`} key={card.key}>
          <span className="domain-stat-icon"><Icon name={card.icon} size={24}/></span>
          <div className="domain-stat-copy"><small>{card.label}</small><strong>{card.value}</strong><em>{card.hint}</em></div>
          <span className="domain-stat-arrow">‹</span>
        </article>)}
      </section>

      <section className="domains-panel">
        <header className="domains-panel-head">
          <div className="domains-panel-title">
            <span className="domains-panel-icon"><Icon name="globe" size={21}/></span>
            <div><div className="domains-panel-title-line"><h2>{pick("دامنه‌ها","Domains")}</h2><span>{rows.length} {pick("دامنه","domains")}</span></div><p>{pick("مدیریت دامنه‌ها و وضعیت SSL سرویس‌های شما","Manage service domains, routing and SSL status")}</p></div>
          </div>
          <div className="domains-panel-tools">
            <label className="domain-search"><Icon name="search" size={18}/><input value={query} onChange={event=>setQuery(event.target.value)} placeholder={pick("جستجو در دامنه‌ها...","Search domains...")}/>{query&&<button type="button" onClick={()=>setQuery("")} aria-label={pick("پاک کردن جستجو","Clear search")}>×</button>}</label>
            <button className="domain-add-button" type="button" onClick={()=>setShowAdd(v=>!v)} aria-expanded={showAdd}><Icon name="plus" size={20}/><span>{pick("دامنه جدید","Add domain")}</span></button>
          </div>
        </header>

        {showAdd&&<div className="domain-add-panel">
          <div className="domain-add-heading"><span className="domain-add-icon"><Icon name="plus" size={18}/></span><div><b>{pick("افزودن دامنه جدید","Add a new domain")}</b><small>{pick("دامنه را ثبت کنید؛ تنظیم Nginx به‌صورت خودکار انجام می‌شود.","Register a domain; Nginx will be configured automatically.")}</small></div></div>
          <div className="domain-add-grid">
            <label className="field"><span>{pick("نام دامنه","Domain name")}</span><input value={domain} onChange={e=>setDomain(e.target.value)} placeholder="panel.example.com" dir="ltr" autoComplete="off"/></label>
            <label className="field"><span>{pick("نقش دامنه","Domain role")}</span><select value={domainType} onChange={e=>setDomainType(e.target.value as DomainType)}>{(Object.keys(typeLabel) as DomainType[]).map(type=><option key={type} value={type}>{pick(typeLabel[type].fa,typeLabel[type].en)}</option>)}</select></label>
            <button className="domain-save" type="button" onClick={()=>void createDomain()} disabled={busy==="create"}><Icon name={busy==="create"?"refresh":"check"} size={18}/>{busy==="create"?pick("در حال ثبت…","Saving…"):pick("ثبت و راه‌اندازی","Save & configure")}</button>
          </div>
        </div>}

        <div className="domains-table-head" aria-hidden="true">
          <span>{pick("دامنه","Domain")}</span>
          <span>{pick("نوع سرویس","Service type")}</span>
          <span>{pick("وضعیت SSL","SSL status")}</span>
          <span>{pick("وضعیت Nginx","Nginx status")}</span>
          <span>{pick("عملیات","Actions")}</span>
        </div>

        {loading?<div className="runtime-empty"><span className="loading-ring"/>{pick("در حال دریافت دامنه‌ها…","Loading domains…")}</div>:filteredRows.length===0?<div className="runtime-empty"><span className="empty-icon"><Icon name="search" size={25}/></span>{query?pick("دامنه‌ای با این جستجو پیدا نشد.","No domain matches this search."):pick("هنوز دامنه‌ای اضافه نشده است.","No domains configured yet.")}</div>:<div className="domain-list">
          {filteredRows.map(row=>{
            const role=typeLabel[row.domain_type];
            const sslStatus=row.ssl_status||"none";
            const nginxStatus=row.nginx_status||"pending";
            return <article className="domain-row" key={row.id}>
              <div className="domain-main">
                <div className="domain-name-line"><b dir="ltr">{row.domain}</b>{row.ssl_status==="active"&&<a className="domain-external" href={`https://${row.domain}`} target="_blank" rel="noreferrer" aria-label={pick("باز کردن دامنه","Open domain")}><Icon name="external" size={15}/></a>}</div>
                <small dir="ltr">{row.target_host||"127.0.0.1"}:{row.target_port}</small>
              </div>

              <div className="domain-role-cell">
                <span className="domain-role-icon"><Icon name={roleIcon(row.domain_type)} size={18}/></span>
                <select className="domain-role" aria-label={pick("نقش دامنه","Domain role")} value={row.domain_type} disabled={busy===row.id} onChange={e=>void changeType(row,e.target.value as DomainType)}>{(Object.keys(typeLabel) as DomainType[]).map(type=><option key={type} value={type}>{pick(typeLabel[type].fa,typeLabel[type].en)}</option>)}</select>
              </div>

              <div className={`domain-status ${statusClass(sslStatus)}`}><span className="status-icon"><Icon name="lock" size={14}/></span><div><b>SSL: {sslStatus}</b><small>{sslStatus==="active"?pick("گواهی معتبر","certificate valid"):sslStatus==="failed"?pick("خطا در گواهی","certificate error"):pick("در انتظار","pending")}</small></div></div>
              <div className={`domain-status ${statusClass(nginxStatus)}`}><span className="status-icon"><Icon name="server" size={14}/></span><div><b>Nginx: {nginxStatus}</b><small>{nginxStatus==="active"?pick("پیکربندی فعال","configuration active"):nginxStatus==="failed"?pick("خطای پیکربندی","configuration error"):pick("در انتظار","pending")}</small></div></div>

              <div className="domain-actions">
                <button className="domain-action renew" type="button" disabled={busy===`ssl-${row.id}`} onClick={()=>void issueSsl(row)} title={pick("صدور یا تمدید SSL","Issue or renew SSL")}><Icon name="refresh" size={16}/><span>{busy===`ssl-${row.id}`?pick("در حال اجرا…","Working…"):pick("SSL / تمدید","SSL / Renew")}</span></button>
                <button className="domain-action delete" type="button" disabled={busy===`delete-${row.id}`} onClick={()=>void removeDomain(row)} title={pick("حذف دامنه","Delete domain")}><Icon name="trash" size={16}/><span>{pick("حذف","Delete")}</span></button>
              </div>

              {row.ssl_error&&<div className="domain-error"><Icon name="attention" size={14}/><span>{row.ssl_error}</span></div>}
            </article>;
          })}
        </div>}
      </section>

      <section className="domain-role-help">
        {(Object.keys(typeLabel) as DomainType[]).map(type=><article key={type} className={`domain-role-card role-${type}`}>
          <span className="domain-role-card-icon"><Icon name={roleIcon(type)} size={22}/></span>
          <div><b>{pick(typeLabel[type].fa,typeLabel[type].en)}</b><small>{pick(roleDescription[type].fa,roleDescription[type].en)}</small></div>
          <span className="domain-role-card-arrow">‹</span>
        </article>)}
      </section>
    </div>
  </Shell>;
}
