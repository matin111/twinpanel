"use client";

import {useCallback,useEffect,useMemo,useState} from "react";
import {API_BASE,api,endpoint} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {Badge,Card,PageHead,Shell,Stat} from "./ui";

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

const typeLabel:Record<DomainType,{fa:string;en:string}>={
  panel:{fa:"پنل",en:"Panel"},
  shop:{fa:"فروشگاه",en:"Store"},
  api:{fa:"API",en:"API"},
  subscription:{fa:"سابسکریپشن",en:"Subscription"}
};

async function domainRequest<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("نشست مدیر پیدا نشد؛ دوباره وارد شوید.");
  const headers=new Headers(init.headers);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  headers.set("Authorization",`Bearer ${token}`);
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  if(!response.ok){
    let detail="";
    try{const data=await response.json();detail=String(data?.detail||data?.message||"");}catch{}
    throw new Error(detail||`API ${response.status}`);
  }
  if(response.status===204)return undefined as T;
  return response.json() as Promise<T>;
}

function normalizeDomain(value:string){
  return value.trim().toLowerCase().replace(/^https?:\/\//,"").replace(/\/$/,"");
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

  const createDomain=async()=>{
    const clean=normalizeDomain(domain);
    if(!clean){setError(pick("دامنه را وارد کنید.","Enter a domain."));return;}
    setBusy("create");setError("");setSuccess("");
    try{
      await domainRequest<DomainRow>(api.admin.domains,{method:"POST",body:JSON.stringify({domain:clean,domain_type:domainType})});
      setDomain("");setShowAdd(false);setSuccess(pick("دامنه اضافه شد و تنظیم Nginx/SSL شروع شد.","Domain added and Nginx/SSL setup started."));
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

  return <Shell active="/admin/domains"><div className="page domains-runtime">
    <PageHead title={pick("دامنه و SSL","Domains & SSL")}/>

    {error&&<div className="runtime-alert error">{error}</div>}
    {success&&<div className="runtime-alert success">{success}</div>}

    <div className="stats">
      <Stat label={pick("دامنه فعال","Active domains")} value={loading?"…":String(stats.active)} delta={pick("ثبت‌شده","configured")}/>
      <Stat label={pick("SSL فعال","Active SSL")} value={loading?"…":String(stats.ssl)} delta={pick("گواهی معتبر","valid certificates")}/>
      <Stat label={pick("نقش‌های فعال","Configured roles")} value={loading?"…":`${stats.roles}/4`} delta="Panel · Store · API · Sub"/>
      <Stat label={pick("نیاز به بررسی","Needs attention")} value={loading?"…":String(stats.failed)} delta={stats.failed?pick("بررسی خطا","review errors"):"OK"}/>
    </div>

    <Card>
      <div className="card-head"><b>{pick("دامنه‌ها","Domains")}</b><button className="primary" type="button" onClick={()=>setShowAdd(v=>!v)}>＋ {pick("دامنه جدید","Add domain")}</button></div>

      {showAdd&&<div className="domain-add-grid">
        <label className="field"><span>{pick("دامنه","Domain")}</span><input value={domain} onChange={e=>setDomain(e.target.value)} placeholder="panel.example.com" dir="ltr"/></label>
        <label className="field"><span>{pick("نقش دامنه","Domain role")}</span><select value={domainType} onChange={e=>setDomainType(e.target.value as DomainType)}>
          {(Object.keys(typeLabel) as DomainType[]).map(type=><option key={type} value={type}>{pick(typeLabel[type].fa,typeLabel[type].en)}</option>)}
        </select></label>
        <button className="primary domain-save" type="button" onClick={()=>void createDomain()} disabled={busy==="create"}>{busy==="create"?pick("در حال ثبت…","Saving…"):pick("ثبت و راه‌اندازی","Save & configure")}</button>
      </div>}

      {loading?<div className="runtime-empty">{pick("در حال دریافت دامنه‌ها…","Loading domains…")}</div>:rows.length===0?<div className="runtime-empty">{pick("هنوز دامنه‌ای اضافه نشده است.","No domains configured yet.")}</div>:<div className="domain-list">
        {rows.map(row=>{
          const sslTone=row.ssl_status==="active"?"ok":row.ssl_status==="failed"?"bad":"warn";
          const nginxTone=row.nginx_status==="active"?"ok":row.nginx_status==="failed"?"bad":"warn";
          return <article className="domain-row" key={row.id}>
            <div className="domain-main"><b dir="ltr">{row.domain}</b><small>{row.target_host||"127.0.0.1"}:{row.target_port}</small></div>
            <select className="domain-role" value={row.domain_type} disabled={busy===row.id} onChange={e=>void changeType(row,e.target.value as DomainType)}>
              {(Object.keys(typeLabel) as DomainType[]).map(type=><option key={type} value={type}>{pick(typeLabel[type].fa,typeLabel[type].en)}</option>)}
            </select>
            <Badge tone={nginxTone}>{`Nginx: ${row.nginx_status||"pending"}`}</Badge>
            <Badge tone={sslTone}>{`SSL: ${row.ssl_status||"none"}`}</Badge>
            <div className="domain-actions"><button className="ghost" type="button" disabled={busy===`ssl-${row.id}`} onClick={()=>void issueSsl(row)}>{pick("SSL / تمدید","SSL / Renew")}</button><button className="danger-btn" type="button" disabled={busy===`delete-${row.id}`} onClick={()=>void removeDomain(row)}>{pick("حذف","Delete")}</button></div>
            {row.ssl_error&&<small className="domain-error">{row.ssl_error}</small>}
          </article>;
        })}
      </div>}
    </Card>

    <Card><div className="domain-role-help">
      {(Object.keys(typeLabel) as DomainType[]).map(type=><div key={type}><b>{pick(typeLabel[type].fa,typeLabel[type].en)}</b><small>{type==="panel"?pick("پنل مدیریت و کاربری","Admin and customer portal"):type==="shop"?pick("فروشگاه عمومی","Public storefront"):type==="api"?pick("API عمومی سرویس","Public API endpoint"):pick("لینک‌ها و فایل‌های اتصال","Subscription links and connection files")}</small></div>)}
    </div></Card>
  </div></Shell>;
}
