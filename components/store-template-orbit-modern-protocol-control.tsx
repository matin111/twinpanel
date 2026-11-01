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

  useEffect(()=>{
    let active=true;
    void loadStoreTemplateSettings().then(envelope=>{
      if(!active)return;
      const current=envelope.templates?.[ORBIT_TEMPLATE_ID]||{};
      if(own(current,FA_KEY))setFa(typeof current[FA_KEY]==="string"?current[FA_KEY] as string:"");
      if(own(current,EN_KEY))setEn(typeof current[EN_KEY]==="string"?current[EN_KEY] as string:"");
    }).catch(()=>{
      if(active)setMessage(pick("خواندن مقدار فعلی ناموفق بود.","Could not load the current value."));
    }).finally(()=>{
      if(active)setLoading(false);
    });
    return()=>{active=false;};
  },[pick]);

  const save=async()=>{
    if(busy)return;
    setBusy(true);
    setMessage("");
    try{
      // Re-read the latest server payload immediately before saving so this
      // isolated control cannot roll back any other Template 3 customization.
      const envelope=await loadStoreTemplateSettings();
      const current=envelope.templates?.[ORBIT_TEMPLATE_ID]||{};
      await saveStoreTemplateSettings(ORBIT_TEMPLATE_ID,{...current,[FA_KEY]:fa,[EN_KEY]:en});
      setMessage(pick("ذخیره شد؛ سایر تنظیمات قالب بدون تغییر ماندند.","Saved without changing other template settings."));
    }catch(reason){
      setMessage(reason instanceof Error?reason.message:String(reason));
    }finally{
      setBusy(false);
    }
  };

  return <section style={{margin:"0 0 16px",padding:"16px",border:"1px solid rgba(148,163,184,.22)",borderRadius:"18px",background:"rgba(15,23,42,.55)"}}>
    <div style={{display:"flex",gap:"12px",alignItems:"center",justifyContent:"space-between",flexWrap:"wrap",marginBottom:"12px"}}>
      <div>
        <strong style={{display:"block",marginBottom:"4px"}}>{pick("توضیح پروتکل‌های مدرن","Modern protocols description")}</strong>
        <small style={{opacity:.72}}>{pick("فقط همین متن را تغییر می‌دهد و تنظیمات دیگر قالب ۳ را بازنویسی نمی‌کند.","Changes only this copy and does not overwrite other Template 3 settings.")}</small>
      </div>
      <button type="button" onClick={()=>void save()} disabled={loading||busy} style={{padding:"9px 14px",border:0,borderRadius:"10px",fontWeight:700,cursor:loading||busy?"not-allowed":"pointer"}}>
        {busy?pick("در حال ذخیره…","Saving…"):pick("ذخیره این متن","Save this text")}
      </button>
    </div>

    <label style={{display:"grid",gap:"6px",marginBottom:"10px"}}>
      <span style={{fontSize:"13px",fontWeight:700}}>{pick("متن فارسی","Persian text")}</span>
      <textarea value={fa} onChange={event=>setFa(event.target.value)} disabled={loading} rows={3} style={{width:"100%",resize:"vertical",padding:"10px 12px",borderRadius:"10px",border:"1px solid rgba(148,163,184,.25)",background:"rgba(2,6,23,.35)",color:"inherit"}}/>
    </label>

    <label style={{display:"grid",gap:"6px"}}>
      <span style={{fontSize:"13px",fontWeight:700}}>{pick("متن انگلیسی","English text")}</span>
      <textarea value={en} onChange={event=>setEn(event.target.value)} disabled={loading} rows={3} dir="ltr" style={{width:"100%",resize:"vertical",padding:"10px 12px",borderRadius:"10px",border:"1px solid rgba(148,163,184,.25)",background:"rgba(2,6,23,.35)",color:"inherit"}}/>
    </label>

    <small style={{display:"block",marginTop:"9px",opacity:.72}}>{pick("برای حذف جمله، کادر فارسی را خالی و ذخیره کنید.","Clear the field and save to hide the sentence.")}</small>
    {message?<p style={{margin:"10px 0 0",fontSize:"13px"}}>{message}</p>:null}
  </section>;
}
