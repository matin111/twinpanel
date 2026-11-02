"use client";

import {useEffect,useState} from "react";
import {Badge,Card,Shell} from "./ui";
import {AnyRow,MotherAccessSettings,parityApi} from "../lib/admin-parity-api";
import {useI18n} from "../lib/i18n";

const text=(row:AnyRow,...keys:string[])=>{for(const key of keys){const value=row?.[key];if(value!==undefined&&value!==null)return String(value);}return "";};

function Notice({error,ok}:{error:string;ok:string}){return <>{error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}</>;}
function Toggle({label,checked,onChange}:{label:string;checked:boolean;onChange:(value:boolean)=>void}){return <label className="toggle module-toggle"><span>{label}</span><input type="checkbox" checked={checked} onChange={e=>onChange(e.target.checked)}/><i/></label>;}
function StatusBadge({value}:{value:unknown}){const s=String(value||"unknown").toLowerCase();return <Badge tone={["online","active","ok","healthy"].includes(s)?"ok":["offline","failed","error","disabled"].includes(s)?"bad":"warn"}>{String(value||"—")}</Badge>;}

export function MotherAccessRuntimeV2(){
  const {pick}=useI18n();
  const [settings,setSettings]=useState<MotherAccessSettings|null>(null);
  const [resellers,setResellers]=useState<AnyRow[]>([]);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const load=async()=>{
    setError("");
    const [s,r]=await Promise.allSettled([parityApi.motherAccess(),parityApi.resellers()]);
    if(s.status==="fulfilled")setSettings(s.value);
    if(r.status==="fulfilled")setResellers(r.value);
    const failed=[s,r].find(x=>x.status==="rejected");
    if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));
  };
  useEffect(()=>{void load();},[]);

  const act=async(label:string,fn:()=>Promise<unknown>)=>{
    if(busy)return;
    setBusy(true);setError("");setOk("");
    try{await fn();setOk(label);await load();}
    catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  };

  if(!settings)return <Shell active="/admin/mother-access"><div className="page"><h1>{pick("دسترسی مادر","Mother Access")}</h1><Notice error={error} ok={ok}/><div className="runtime-loading">{pick("در حال دریافت تنظیمات...","Loading settings...")}</div></div></Shell>;

  const save=()=>void act(
    pick("تنظیمات سرور مادر ذخیره شد","Mother server settings saved"),
    ()=>parityApi.saveMotherAccess({
      admin_enabled:settings.admin_enabled,
      reseller_enabled:settings.reseller_enabled,
      mother_name:settings.mother_name.trim(),
      public_domain:settings.mother_public_domain.trim(),
    }),
  );

  return <Shell active="/admin/mother-access"><div className="page">
    <div className="page-head"><div><h1>{pick("سرور مادر","Mother Server")}</h1></div><button className="ghost" onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div>
    <Notice error={error} ok={ok}/>
    <div className="module-grid two">
      <Card>
        <div className="card-head"><div><b>{pick("هویت و دامنه سرور مادر","Mother identity & domain")}</b><small>{pick("این نام و دامنه در کانفیگ‌های تکی سرور مادر استفاده می‌شوند.","This name and domain are used by individual Mother-server configs.")}</small></div></div>
        <div className="setting-grid">
          <label className="field"><span>{pick("نام سرور مادر","Mother server name")}</span><input maxLength={120} value={settings.mother_name||""} onChange={e=>setSettings(s=>s?{...s,mother_name:e.target.value}:s)}/></label>
          <label className="field"><span>{pick("دامنه عمومی","Public domain")}</span><input dir="ltr" placeholder="vpn.example.com" value={settings.mother_public_domain||""} onChange={e=>setSettings(s=>s?{...s,mother_public_domain:e.target.value}:s)}/></label>
        </div>
        <div className="runtime-info-list">
          <div><span>Node ID</span><b>#{settings.mother_node_id}</b></div>
          <div><span>{pick("IP فعلی","Current IP")}</span><b dir="ltr">{settings.mother_public_ip||"—"}</b></div>
        </div>
        <Toggle label={pick("ادمین مجاز به استفاده از سرور مادر در Multi-Link","Admin may use Mother in Multi-Link")} checked={settings.admin_enabled} onChange={v=>setSettings(s=>s?{...s,admin_enabled:v}:s)}/>
        <Toggle label={pick("نمایندگان به‌صورت پیش‌فرض مجاز باشند","Resellers enabled by default")} checked={settings.reseller_enabled} onChange={v=>setSettings(s=>s?{...s,reseller_enabled:v}:s)}/>
        <button className="primary" disabled={busy||!settings.mother_name.trim()} onClick={save}>{pick("ذخیره تنظیمات","Save settings")}</button>
      </Card>
      <Card>
        <div className="card-head"><div><b>{pick("وضعیت استفاده","Usage policy")}</b></div></div>
        <div className="runtime-info-list">
          <div><b>{pick("ادمین","Admin")}</b><StatusBadge value={settings.admin_enabled?"active":"disabled"}/></div>
          <div><b>{pick("پیش‌فرض نماینده","Reseller default")}</b><StatusBadge value={settings.reseller_enabled?"active":"disabled"}/></div>
          <div><b>{pick("Override اختصاصی","Per-reseller overrides")}</b><span>{Object.keys(settings.reseller_overrides||{}).length}</span></div>
        </div>
      </Card>
    </div>
    <Card>
      <div className="card-head"><div><b>{pick("دسترسی نمایندگان","Reseller overrides")}</b><small>{pick("Override هر نماینده مستقل از مقدار پیش‌فرض ذخیره می‌شود.","Each reseller override is stored independently from the default.")}</small></div></div>
      {resellers.length?resellers.map((r,i)=>{const rid=Number(r.id||0);const effective=Object.prototype.hasOwnProperty.call(settings.reseller_overrides||{},String(rid))?Boolean(settings.reseller_overrides[String(rid)]):settings.reseller_enabled;return <div className="module-row" key={rid||i}><div className="grow"><b>{text(r,"name")||`#${rid}`}</b><small>{text(r,"code")} · {text(r,"email")}</small></div><StatusBadge value={effective?"active":"disabled"}/><button className="mini-btn" disabled={busy} onClick={()=>void act(pick("دسترسی نماینده تغییر کرد","Reseller access updated"),()=>parityApi.setResellerMotherAccess(rid,!effective))}>{effective?pick("قطع دسترسی","Disable"):pick("اعطای دسترسی","Enable")}</button></div>}):<div className="runtime-empty">{pick("نماینده‌ای ثبت نشده است.","No resellers found.")}</div>}
    </Card>
  </div></Shell>;
}
