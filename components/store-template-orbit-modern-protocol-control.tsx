"use client";

import {useEffect,useState} from "react";
import {useI18n} from "../lib/i18n";
import {ORBIT_TEMPLATE_ID} from "../lib/store-template-orbit-options";
import {loadStoreTemplateSettings,saveStoreTemplateSettings} from "../lib/store-template-settings-api";

const FA_KEY="modern_protocols_description";
const EN_KEY="modern_protocols_description_en";
const DEFAULT_FA="پروتکل‌های جدید TwinPanel در کنار گزینه‌های کلاسیک؛ برای هر شبکه مسیر مناسب‌تری در دسترس است.";
const DEFAULT_EN="TwinPanel's newer protocols alongside the classic options, giving each network a better-matched path.";

function own(source:Record<string,unknown>,key:string){
  return Object.prototype.hasOwnProperty.call(source,key);
}

export function OrbitModernProtocolDescriptionControl(){
  const {pick}=useI18n();
  const [fa,setFa]=useState(DEFAULT_FA);
  const [en,setEn]=useState(DEFAULT_EN);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState("");
  const [success,setSuccess]=useState(false);

  useEffect(()=>{
    let active=true;
    void loadStoreTemplateSettings().then(envelope=>{
      if(!active)return;
      const current=envelope.templates?.[ORBIT_TEMPLATE_ID]||{};
      if(own(current,FA_KEY))setFa(typeof current[FA_KEY]==="string"?current[FA_KEY] as string:"");
      if(own(current,EN_KEY))setEn(typeof current[EN_KEY]==="string"?current[EN_KEY] as string:"");
    }).catch(reason=>{
      if(active){
        setSuccess(false);
        setMessage(reason instanceof Error?reason.message:pick("خواندن مقدار فعلی ناموفق بود.","Could not load the current value."));
      }
    }).finally(()=>{
      if(active)setLoading(false);
    });
    return()=>{active=false;};
  },[pick]);

  const save=async()=>{
    if(busy)return;
    setBusy(true);
    setSuccess(false);
    setMessage("");
    try{
      const envelope=await loadStoreTemplateSettings();
      const current=envelope.templates?.[ORBIT_TEMPLATE_ID]||{};
      await saveStoreTemplateSettings(ORBIT_TEMPLATE_ID,{...current,[FA_KEY]:fa,[EN_KEY]:en});

      // Verify that the backend really persisted both values before showing success.
      const verified=await loadStoreTemplateSettings();
      const saved=verified.templates?.[ORBIT_TEMPLATE_ID]||{};
      const savedFa=typeof saved[FA_KEY]==="string"?saved[FA_KEY]:undefined;
      const savedEn=typeof saved[EN_KEY]==="string"?saved[EN_KEY]:undefined;
      if(savedFa!==fa||savedEn!==en){
        throw new Error(pick("ذخیره انجام نشد؛ مقدار ثبت‌شده از سرور تأیید نشد.","Save failed: the persisted value could not be verified."));
      }

      setSuccess(true);
      setMessage(pick("متن با موفقیت ذخیره شد. برای دیدن نتیجه، فروشگاه را تازه‌سازی کنید.","Saved successfully. Refresh the storefront to see the result."));
    }catch(reason){
      setSuccess(false);
      setMessage(reason instanceof Error?reason.message:String(reason));
    }finally{
      setBusy(false);
    }
  };

  return <section style={{
    margin:"0 0 18px",
    padding:"18px",
    border:"1px solid var(--line)",
    borderRadius:"20px",
    background:"var(--surface)",
    color:"var(--text)",
    boxShadow:"0 12px 34px rgba(0,0,0,.04)",
  }}>
    <div style={{display:"flex",gap:"14px",alignItems:"center",justifyContent:"space-between",flexWrap:"wrap",marginBottom:"14px"}}>
      <div>
        <strong style={{display:"block",marginBottom:"5px",fontSize:"15px",color:"var(--text)"}}>{pick("توضیح پروتکل‌های مدرن","Modern protocols description")}</strong>
        <small style={{color:"var(--muted)",lineHeight:1.8}}>{pick("فقط همین متن را تغییر می‌دهد و سایر تنظیمات قالب سوم را دست نمی‌زند.","Changes only this copy and leaves all other Template 3 settings untouched.")}</small>
      </div>
      <button type="button" onClick={()=>void save()} disabled={loading||busy} style={{
        padding:"10px 16px",
        border:"1px solid color-mix(in srgb,var(--purple) 78%,transparent)",
        borderRadius:"11px",
        background:loading||busy?"var(--surface-2)":"var(--purple)",
        color:loading||busy?"var(--muted)":"#fff",
        fontWeight:800,
        cursor:loading||busy?"not-allowed":"pointer",
        boxShadow:loading||busy?"none":"0 8px 20px color-mix(in srgb,var(--purple) 24%,transparent)",
      }}>
        {busy?pick("در حال ذخیره…","Saving…"):pick("ذخیره این متن","Save this text")}
      </button>
    </div>

    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))",gap:"12px"}}>
      <label style={{display:"grid",gap:"7px"}}>
        <span style={{fontSize:"13px",fontWeight:800,color:"var(--text)"}}>{pick("متن فارسی","Persian text")}</span>
        <textarea value={fa} onChange={event=>setFa(event.target.value)} disabled={loading} rows={3} dir="rtl" style={{
          width:"100%",resize:"vertical",padding:"12px 13px",borderRadius:"12px",
          border:"1px solid var(--line)",background:"var(--surface-2)",color:"var(--text)",outline:"none",lineHeight:1.9,
        }}/>
      </label>

      <label style={{display:"grid",gap:"7px"}}>
        <span style={{fontSize:"13px",fontWeight:800,color:"var(--text)"}}>{pick("متن انگلیسی","English text")}</span>
        <textarea value={en} onChange={event=>setEn(event.target.value)} disabled={loading} rows={3} dir="ltr" style={{
          width:"100%",resize:"vertical",padding:"12px 13px",borderRadius:"12px",
          border:"1px solid var(--line)",background:"var(--surface-2)",color:"var(--text)",outline:"none",lineHeight:1.8,
        }}/>
      </label>
    </div>

    <small style={{display:"block",marginTop:"10px",color:"var(--muted)"}}>{pick("برای حذف جمله، متن فارسی را کامل خالی کنید و ذخیره را بزنید.","Clear the field and save to hide the sentence.")}</small>
    {message?<p style={{
      margin:"12px 0 0",padding:"10px 12px",borderRadius:"10px",fontSize:"13px",fontWeight:700,
      border:`1px solid ${success?"color-mix(in srgb,#16a34a 35%,transparent)":"color-mix(in srgb,#dc2626 35%,transparent)"}`,
      background:success?"color-mix(in srgb,#16a34a 8%,var(--surface))":"color-mix(in srgb,#dc2626 8%,var(--surface))",
      color:success?"#15803d":"#b91c1c",
    }}>{message}</p>:null}
  </section>;
}
