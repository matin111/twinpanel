"use client";

import {useEffect,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {appearanceApi,type AppAppearance,type AppearanceReseller} from "../lib/central-app-appearance-api";
import {Shell} from "./ui";
import {PortalShell} from "./portal-shells";

type AppContact={
  logo_url:string|null;
  primary_color:string|null;
  secondary_color:string|null;
  telegram_url:string|null;
  renewal_url:string|null;
  support_phone:string|null;
  website_url:string|null;
};
const EMPTY:AppContact={
  logo_url:null,primary_color:null,secondary_color:null,telegram_url:null,
  renewal_url:null,support_phone:null,website_url:null,
};
type ContactKey=keyof AppContact;
const CONTACT_FIELDS:ReadonlyArray<[ContactKey,string,string]>= [
  ["logo_url","لوگو (آدرس HTTPS یا مسیر محلی)","Logo URL"],
  ["telegram_url","تلگرام پشتیبانی","Support Telegram URL"],
  ["renewal_url","لینک تمدید","Renewal URL"],
  ["support_phone","شماره پشتیبانی","Support phone"],
  ["website_url","آدرس وب‌سایت","Website URL"],
];
async function contactRequest(path:string,method="GET",body?:AppContact):Promise<AppContact>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const response=await fetch(`${API_BASE}/v1/central-app/${path}`,{
    method,cache:"no-store",
    headers:{Authorization:`Bearer ${token}`,...(body?{"Content-Type":"application/json"}:{})},
    ...(body?{body:JSON.stringify(body)}:{}),
  });
  if(!response.ok){
    let reason=`HTTP ${response.status}`;
    try{const payload=await response.json();reason=String(payload.detail||reason);}catch{}
    throw new Error(reason);
  }
  return response.json();
}

export function CentralAppBrandManager({role}:{role:"admin"|"reseller"}){
  const {pick}=useI18n();
  const [resellers,setResellers]=useState<AppearanceReseller[]>([]);
  const [resellerId,setResellerId]=useState(0);
  const [appearance,setAppearance]=useState<AppAppearance|null>(null);
  const [contact,setContact]=useState<AppContact>(EMPTY);
  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const target=role==="reseller"?"reseller/profile":resellerId>0?`admin/resellers/${resellerId}/profile`:"admin/profile";
  useEffect(()=>{
    if(role!=="admin")return;
    let active=true;
    appearanceApi.listResellers().then(rows=>{if(active)setResellers(rows)})
      .catch(e=>{if(active)setError(String(e))});
    return()=>{active=false};
  },[role]);
  useEffect(()=>{
    let active=true;
    setLoading(true);setError("");setNotice("");setAppearance(null);
    Promise.all([
      appearanceApi.load(role,resellerId),
      contactRequest(target),
    ]).then(([a,c])=>{if(active){setAppearance(a);setContact({...EMPTY,...c})}})
      .catch(e=>{if(active)setError(e instanceof Error?e.message:String(e))})
      .finally(()=>{if(active)setLoading(false)});
    return()=>{active=false};
  },[role,resellerId,target]);
  const updateAppearance=<K extends keyof AppAppearance>(key:K,value:AppAppearance[K])=>{
    setAppearance(current=>current?{...current,[key]:value}:current);
  };
  const updateContact=(key:ContactKey,value:string)=>{
    setContact(current=>({...current,[key]:value.trim()?value:null}));
  };
  const save=async()=>{
    if(!appearance||busy)return;
    setBusy(true);setError("");setNotice("");
    try{
      const a=await appearanceApi.save(role,appearance,resellerId);
      const c=await contactRequest(target,"PUT",{
        ...contact,
        primary_color:a.primary_color,
        secondary_color:a.secondary_color,
      });
      setAppearance(a);setContact({...EMPTY,...c});
      setNotice(pick("تنظیمات اپ ذخیره شد.","App settings saved."));
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  };
  const reset=async()=>{
    if(busy||!window.confirm(pick("ظاهر اپ به حالت پیش‌فرض برگردد؟","Reset app appearance to defaults?")))return;
    setBusy(true);setError("");setNotice("");
    try{
      setAppearance(await appearanceApi.reset(role,resellerId));
      setNotice(pick("ظاهر اپ بازنشانی شد. اطلاعات پشتیبانی تغییر نکرد.","Appearance reset. Contact settings were preserved."));
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  };
  const inputStyle:React.CSSProperties={width:"100%",minWidth:0,padding:"10px 12px",border:"1px solid var(--border)",borderRadius:10,background:"var(--surface)",color:"var(--text)"};
  const content=<div className="page" dir="rtl" style={{maxWidth:1050,margin:"0 auto",padding:"18px 12px"}}>
    <div className="page-head"><div><h1>{pick("مدیریت اپ هوشمند","Smart app management")}</h1>
      <small>{pick("برند و ظاهر اختصاصی TwinConnect برای هر پنل؛ بدون تغییر در کانفیگ‌های VPN","Configure each panel's TwinConnect brand without changing VPN configurations")}</small>
    </div></div>
    {role==="admin"&&<section className="card" style={{padding:18,marginBottom:14}}>
      <label htmlFor="app-brand-reseller">{pick("انتخاب برند پنل","Select panel brand")}</label>
      <select id="app-brand-reseller" style={inputStyle} value={resellerId} onChange={e=>setResellerId(Number(e.target.value))}>
        <option value={0}>{pick("پنل اصلی","Main panel")}</option>
        {resellers.map(r=><option key={r.id} value={r.id}>{r.name} (#{r.id})</option>)}
      </select>
    </section>}
    {error&&<div role="alert" className="runtime-error">{error}</div>}
    {notice&&<div role="status" className="runtime-message">{notice}</div>}
    {loading?<p>{pick("در حال دریافت تنظیمات…","Loading settings…")}</p>:appearance&&<>
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))",gap:14}}>
        <section className="card" style={{padding:18,display:"grid",gap:12}}>
          <h2 style={{margin:0,fontSize:17}}>{pick("ظاهر برنامه","Appearance")}</h2>
          {([
            ["primary_color","رنگ اصلی","Primary color"],
            ["secondary_color","رنگ دوم","Secondary color"],
            ["button_color","رنگ دکمه‌ها","Button color"],
            ["background_color","رنگ پس‌زمینه","Background color"],
            ["surface_color","رنگ کارت‌ها","Card color"],
          ] as const).map(([key,fa,en])=><label key={key} style={{display:"flex",alignItems:"center",justifyContent:"space-between",gap:12}}>
            <span>{pick(fa,en)}</span><input aria-label={pick(fa,en)} type="color" value={appearance[key]} onChange={e=>updateAppearance(key,e.target.value)} />
          </label>)}
          <label>{pick("حالت نمایش","Theme")}
            <select style={inputStyle} value={appearance.theme_mode} onChange={e=>updateAppearance("theme_mode",e.target.value as AppAppearance["theme_mode"])}>
              <option value="system">{pick("سیستم","System")}</option><option value="dark">{pick("تیره","Dark")}</option><option value="light">{pick("روشن","Light")}</option>
            </select>
          </label>
          <label>{pick("نوع پس‌زمینه","Background style")}
            <select style={inputStyle} value={appearance.background_style} onChange={e=>updateAppearance("background_style",e.target.value as AppAppearance["background_style"])}>
              <option value="solid">{pick("ساده","Solid")}</option><option value="gradient">{pick("گرادیان","Gradient")}</option><option value="image">{pick("عکس","Image")}</option>
            </select>
          </label>
          {appearance.background_style==="image"&&<label>{pick("آدرس HTTPS عکس پس‌زمینه","Background image HTTPS URL")}
            <input style={inputStyle} dir="ltr" value={appearance.background_image_url||""} onChange={e=>updateAppearance("background_image_url",e.target.value||null)}/>
          </label>}
        </section>
        <section className="card" style={{padding:18,display:"grid",gap:12}}>
          <h2 style={{margin:0,fontSize:17}}>{pick("لوگو و پشتیبانی","Logo and support")}</h2>
          {CONTACT_FIELDS.map(([key,fa,en])=><label key={key} style={{display:"grid",gap:5}}>
            <span>{pick(fa,en)}</span>
            <input style={inputStyle} dir="ltr" value={contact[key]||""} onChange={e=>updateContact(key,e.target.value)}/>
          </label>)}
          <div style={{padding:15,borderRadius:16,background:appearance.background_color,color:appearance.primary_color,border:`1px solid ${appearance.secondary_color}`}}>
            <b>{pick("پیش‌نمایش رنگ برند","Brand color preview")}</b>
            <div style={{marginTop:10,padding:12,borderRadius:10,background:appearance.surface_color,color:appearance.secondary_color}}>
              TwinConnect <span style={{display:"inline-block",borderRadius:8,padding:"6px 12px",background:appearance.button_color,color:"#fff"}}>{pick("اتصال","Connect")}</span>
            </div>
          </div>
        </section>
      </div>
      <div style={{display:"flex",gap:10,marginTop:16,flexWrap:"wrap"}}>
        <button type="button" className="primary" disabled={busy} onClick={()=>void save()}>{busy?"…":pick("ذخیره تنظیمات اپ","Save app settings")}</button>
        <button type="button" className="ghost" disabled={busy} onClick={()=>void reset()}>{pick("بازنشانی ظاهر","Reset appearance")}</button>
      </div>
    </>}
  </div>;
  return role==="admin"?<Shell active="/admin/smart-app">{content}</Shell>:<PortalShell type="reseller" active="/reseller/smart-app">{content}</PortalShell>;
}
