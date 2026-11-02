"use client";

import {useEffect,useState} from "react";
import {Badge,Card,Shell} from "./ui";
import {generalSettingsApi,MotherAccessSettings,SettingsReseller} from "../lib/general-settings-api";
import {useI18n} from "../lib/i18n";

const emptyMother:MotherAccessSettings={admin_enabled:true,reseller_enabled:false,reseller_overrides:{},mother_node_id:0,mother_name:"",mother_public_domain:"",mother_public_ip:""};

function Toggle({label,checked,disabled,onChange}:{label:string;checked:boolean;disabled?:boolean;onChange:(value:boolean)=>void}){
  return <label className="toggle module-toggle"><span>{label}</span><input type="checkbox" checked={checked} disabled={disabled} onChange={e=>onChange(e.target.checked)}/><i/></label>;
}

export function MotherAccessRuntimeV3(){
  const {pick}=useI18n();
  const [mother,setMother]=useState<MotherAccessSettings>(emptyMother);
  const [resellers,setResellers]=useState<SettingsReseller[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const load=async()=>{
    setLoading(true);setError("");
    const [m,r]=await Promise.allSettled([generalSettingsApi.motherAccess(),generalSettingsApi.resellers()]);
    if(m.status==="fulfilled")setMother(m.value);else setError(m.reason instanceof Error?m.reason.message:String(m.reason));
    if(r.status==="fulfilled")setResellers(r.value);
    setLoading(false);
  };
  useEffect(()=>{void load();},[]);

  const save=async()=>{
    if(busy||!mother.mother_name.trim())return;
    setBusy("save");setError("");setOk("");
    try{
      const result=await generalSettingsApi.saveMotherAccess({
        admin_enabled:mother.admin_enabled,
        reseller_enabled:mother.reseller_enabled,
        mother_name:mother.mother_name.trim(),
        public_domain:mother.mother_public_domain.trim(),
      });
      setMother(v=>({...v,...result}));
      setOk(pick("تنظیمات سرور مادر ذخیره شد.","Mother server settings saved."));
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy("");}
  };

  const setReseller=async(id:number,enabled:boolean)=>{
    if(busy)return;
    setBusy(`reseller:${id}`);setError("");setOk("");
    try{
      await generalSettingsApi.setResellerMotherAccess(id,enabled);
      setMother(v=>({...v,reseller_overrides:{...v.reseller_overrides,[String(id)]:enabled}}));
      setOk(pick("دسترسی نماینده ذخیره شد.","Reseller access saved."));
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy("");}
  };

  return <Shell active="/admin/mother-access"><div className="page">
    <div className="page-head"><div><h1>{pick("سرور مادر","Mother Server")}</h1><small>{pick("Provisioning همیشه حفظ می‌شود؛ این تنظیمات فقط نمایش سرور مادر در سرورهای تکی اشتراک را کنترل می‌کنند. سرور مادر هیچ‌وقت وارد Multi-Link نمی‌شود.","Provisioning is always preserved. These controls only manage Mother visibility in individual subscription servers. Mother never participates in Multi-Link.")}</small></div><button className="ghost" disabled={loading||Boolean(busy)} onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div>
    {error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}{loading&&<div className="runtime-loading">{pick("در حال دریافت تنظیمات...","Loading settings...")}</div>}

    <div className="module-grid two">
      <Card>
        <div className="card-head"><div><b>{pick("نام و دامنه سرور مادر","Mother name & domain")}</b><small>{pick("نام و دامنه فقط هویت سرور مادر هستند و از نام برند پنل جدا می‌مانند.","Mother identity is independent from panel branding.")}</small></div><Badge tone="violet">#{mother.mother_node_id||"—"}</Badge></div>
        <div className="setting-grid">
          <label className="field"><span>{pick("نام سرور مادر","Mother server name")}</span><input maxLength={120} value={mother.mother_name} onChange={e=>setMother(v=>({...v,mother_name:e.target.value}))} placeholder={pick("سرور مرکزی","Central server")}/></label>
          <label className="field"><span>{pick("دامنه عمومی سرور مادر","Mother public domain")}</span><input dir="ltr" value={mother.mother_public_domain} onChange={e=>setMother(v=>({...v,mother_public_domain:e.target.value}))} placeholder="vpn.example.com"/></label>
        </div>
        <div className="runtime-info-list"><div><span>{pick("IP فعلی","Current IP")}</span><b dir="ltr">{mother.mother_public_ip||"—"}</b></div></div>
      </Card>

      <Card>
        <div className="card-head"><div><b>{pick("دسترسی در اشتراک‌ها","Subscription visibility")}</b><small>{pick("خاموش‌کردن دسترسی Credentialهای ساخته‌شده را حذف نمی‌کند.","Disabling visibility does not delete provisioned credentials.")}</small></div></div>
        <Toggle label={pick("نمایش سرور مادر در اشتراک‌های مدیر","Show Mother in admin subscriptions")} checked={mother.admin_enabled} onChange={v=>setMother(s=>({...s,admin_enabled:v}))}/>
        <Toggle label={pick("نمایش سرور مادر در اشتراک‌های نمایندگان","Show Mother in reseller subscriptions")} checked={mother.reseller_enabled} onChange={v=>setMother(s=>({...s,reseller_enabled:v}))}/>
        <div className="runtime-info-list"><div><span>Multi-Link</span><Badge tone="ok">{pick("همیشه بدون سرور مادر","Mother always excluded")}</Badge></div></div>
        <button className="primary" disabled={Boolean(busy)||loading||!mother.mother_name.trim()} onClick={()=>void save()}>{busy==="save"?"…":pick("ذخیره تنظیمات","Save settings")}</button>
      </Card>
    </div>

    <Card>
      <div className="card-head"><div><b>{pick("دسترسی نمایندگان","Reseller access")}</b><small>{pick("Override هر نماینده فقط روی سرورهای تکی اشتراک او اثر دارد.","Per-reseller overrides affect only individual server delivery.")}</small></div></div>
      {resellers.length?resellers.map(r=>{const has=Object.prototype.hasOwnProperty.call(mother.reseller_overrides||{},String(r.id));const enabled=has?Boolean(mother.reseller_overrides[String(r.id)]):mother.reseller_enabled;return <div className="module-row" key={r.id}><div className="grow"><b>{r.name}</b><small>{r.code||""}{r.email?` · ${r.email}`:""}</small></div><Badge tone={enabled?"ok":"warn"}>{enabled?pick("فعال","Enabled"):pick("غیرفعال","Disabled")}</Badge><Toggle label="" checked={enabled} disabled={!mother.reseller_enabled||Boolean(busy)} onChange={v=>void setReseller(r.id,v)}/></div>; }):<div className="runtime-empty">{pick("نماینده‌ای ثبت نشده است.","No resellers found.")}</div>}
    </Card>
  </div></Shell>;
}
