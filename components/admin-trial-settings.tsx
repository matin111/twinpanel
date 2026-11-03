"use client";

import {useEffect,useMemo,useState} from "react";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {Card,PageHead,Shell} from "./ui";

type TrialSettings={enabled:boolean;template_plan_id:number|null;duration_days:number;traffic_mb:number;scope:string};
type PlanRow={id:number;name:string;is_active:boolean};

function errorText(value:unknown):string{
  if(typeof value==="string")return value;
  if(Array.isArray(value))return value.map(errorText).filter(Boolean).join(" | ")||"خطا در انجام عملیات";
  if(value&&typeof value==="object"){
    const row=value as Record<string,unknown>;
    return errorText(row.message??row.detail??row.error??row.code??JSON.stringify(row));
  }
  return String(value??"خطا در انجام عملیات");
}

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const response=await fetch(path,{...init,headers,cache:"no-store"});
  if(!response.ok){let detail=`API error ${response.status}`;try{const payload=await response.json() as {detail?:unknown};detail=errorText(payload.detail??payload);}catch{}throw new Error(detail);}
  return response.json() as Promise<T>;
}

export function AdminTrialSettings(){
  const {pick}=useI18n();
  const [settings,setSettings]=useState<TrialSettings|null>(null);
  const [plans,setPlans]=useState<PlanRow[]>([]);
  const [loading,setLoading]=useState(true);
  const [saving,setSaving]=useState(false);
  const [message,setMessage]=useState("");
  const [error,setError]=useState("");

  useEffect(()=>{let alive=true;Promise.all([request<TrialSettings>("/v1/trial/admin/main"),request<PlanRow[]>("/v1/plans")]).then(([trial,rows])=>{if(!alive)return;const active=(Array.isArray(rows)?rows:[]).filter(row=>row.is_active);setPlans(active);setSettings({...trial,template_plan_id:trial.template_plan_id??active[0]?.id??null});}).catch(reason=>alive&&setError(reason instanceof Error?reason.message:String(reason))).finally(()=>alive&&setLoading(false));return()=>{alive=false};},[]);

  const selectedPlan=useMemo(()=>plans.find(row=>row.id===settings?.template_plan_id),[plans,settings?.template_plan_id]);
  const save=async()=>{if(!settings)return;if(settings.enabled&&!settings.template_plan_id&&plans.length===0){setError(pick("برای فعال‌کردن اکانت تست حداقل یک پلن فعال لازم است.","At least one active plan is required to enable Trial."));return;}setSaving(true);setError("");setMessage("");try{const next=await request<TrialSettings>("/v1/trial/admin/main",{method:"PUT",body:JSON.stringify({enabled:settings.enabled,template_plan_id:settings.template_plan_id,duration_days:settings.duration_days,traffic_mb:settings.traffic_mb})});setSettings(next);setMessage(pick("تنظیمات اکانت تست ذخیره شد.","Trial settings saved."));}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setSaving(false);}};

  return <Shell active="/admin/trial"><div className="page"><PageHead title={pick("اکانت تست","Trial Account")}/>{loading&&<Card><p>{pick("در حال بارگذاری...","Loading...")}</p></Card>}{error&&<div className="customer-buy-alert error">{error}</div>}{message&&<div className="customer-buy-alert">{message}</div>}{settings&&<Card className="trial-settings-card"><div className="trial-settings-intro"><div><h2>{pick("تنظیمات مستقل اکانت تست","Standalone Trial Settings")}</h2><p>{pick("پلن الگو فقط برای انتخاب پروتکل‌ها و سرورهاست. هر کاربر فقط یک‌بار می‌تواند اکانت تست اصلی دریافت کند.","The template plan is only used for protocols and servers. Each user can claim the main Trial once.")}</p></div><label className="toggle-row"><input type="checkbox" checked={settings.enabled} onChange={event=>setSettings({...settings,enabled:event.target.checked})}/><span>{pick("فعال بودن اکانت تست","Enable Trial Account")}</span></label></div><div className="form-grid"><label><span>{pick("پلن الگو","Template Plan")}</span><select value={settings.template_plan_id??""} onChange={event=>setSettings({...settings,template_plan_id:event.target.value?Number(event.target.value):null})}><option value="">{pick("انتخاب پلن الگو","Select template plan")}</option>{plans.map(plan=><option key={plan.id} value={plan.id}>{plan.name}</option>)}</select></label><label><span>{pick("مدت اعتبار (روز)","Duration (days)")}</span><input type="number" min={1} max={30} value={settings.duration_days} onChange={event=>setSettings({...settings,duration_days:Number(event.target.value||1)})}/></label><label><span>{pick("حجم (MB)","Traffic (MB)")}</span><input type="number" min={1} max={10240} value={settings.traffic_mb} onChange={event=>setSettings({...settings,traffic_mb:Number(event.target.value||1)})}/></label></div>{!selectedPlan&&<div className="trial-template-warning">{pick("پلن الگو انتخاب نشده؛ هنگام فعال‌سازی اولین پلن فعال به‌صورت خودکار انتخاب می‌شود.","No template selected; the first active plan will be selected automatically when enabling Trial.")}</div>}<div className="trial-settings-summary"><b>{pick("تنظیم فعلی:","Current setup:")}</b> {selectedPlan?.name||pick("انتخاب خودکار","Auto select")} • {settings.duration_days} {pick("روز","days")} • {settings.traffic_mb} MB</div><div className="form-actions"><button type="button" className="primary" disabled={saving} onClick={()=>void save()}>{saving?pick("در حال ذخیره...","Saving..."):pick("ذخیره تنظیمات","Save settings")}</button></div></Card>}</div></Shell>;
}