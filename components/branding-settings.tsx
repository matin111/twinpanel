"use client";

import {useEffect,useState} from "react";
import {Card,PageHead,Shell} from "./ui";
import {useI18n} from "../lib/i18n";
import {BrandingConfig,useBranding} from "../lib/branding";

export function BrandingSettingsPage(){
  const {pick}=useI18n();
  const {brand,updateBrand,resetBrand}=useBranding();
  const [draft,setDraft]=useState<BrandingConfig>(brand);
  const [saved,setSaved]=useState(false);

  useEffect(()=>setDraft(brand),[brand]);
  const set=<K extends keyof BrandingConfig>(key:K,value:BrandingConfig[K])=>setDraft(v=>({...v,[key]:value}));
  const save=()=>{updateBrand(draft);setSaved(true);window.setTimeout(()=>setSaved(false),1800)};
  const reset=()=>{resetBrand();setSaved(false)};

  return <Shell active="/admin/branding"><div className="page">
    <PageHead title={pick("برندینگ","Branding")} sub={pick("تنها مرجع نام، لوگو و هویت عمومی پنل","The single source of truth for product name, logo and public identity")}/>
    <div className="module-grid two">
      <Card>
        <h3>{pick("هویت برند","Brand identity")}</h3>
        <label className="field"><span>{pick("نام عمومی","Public name")}</span><input value={draft.name} onChange={e=>set("name",e.target.value)}/></label>
        <label className="field"><span>{pick("نام کوتاه","Short name")}</span><input value={draft.shortName} onChange={e=>set("shortName",e.target.value)}/></label>
        <label className="field"><span>{pick("زیرعنوان","Tagline")}</span><input value={draft.tagline} onChange={e=>set("tagline",e.target.value)}/></label>
        <label className="field"><span>{pick("لینک پشتیبانی","Support link")}</span><input value={draft.supportLink} onChange={e=>set("supportLink",e.target.value)}/></label>
        <label className="field"><span>{pick("مسیر لوگو","Logo path / URL")}</span><input value={draft.logoUrl} onChange={e=>set("logoUrl",e.target.value)}/></label>
        <label className="field"><span>{pick("رنگ Accent","Accent color")}</span><input type="color" value={draft.accent} onChange={e=>set("accent",e.target.value)}/></label>
        <div className="action-row"><button className="primary" onClick={save}>{saved?pick("ذخیره شد","Saved"):pick("ذخیره برند","Save branding")}</button><button className="ghost" onClick={reset}>{pick("بازنشانی","Reset")}</button></div>
      </Card>
      <Card>
        <h3>{pick("پیش‌نمایش زنده","Live preview")}</h3>
        <div className="brand-preview"><img src={draft.logoUrl} alt={draft.name}/><div><b>{draft.name||pick("بدون نام","Unnamed")}</b><small>{draft.tagline}</small></div></div>
        <div className="brand-preview-meta"><span>{pick("نام کوتاه","Short name")}</span><b>{draft.shortName||"—"}</b></div>
        <div className="brand-preview-meta"><span>{pick("لینک پشتیبانی","Support link")}</span><b>{draft.supportLink||"—"}</b></div>
        <p className="muted">{pick("پس از ذخیره، همین هویت در منوی ادمین، پنل کاربری، نمایندگی، ورود، فروشگاه و عنوان مرورگر استفاده می‌شود.","After saving, this identity is used by Admin, Customer, Reseller, Login, Store and the browser title.")}</p>
      </Card>
    </div>
  </div></Shell>;
}
