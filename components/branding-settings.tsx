"use client";

import Link from "next/link";
import {useEffect,useState,type ChangeEvent,type CSSProperties} from "react";
import {Card,PageHead,Shell} from "./ui";
import {useI18n} from "../lib/i18n";
import {
  DEFAULT_BRANDING,
  configFromBrandingRecord,
  useBranding,
  type BrandingConfig,
} from "../lib/branding";
import {brandingApi,type BrandingAssetKind,type BrandingRecord} from "../lib/branding-api";

const COLOR_PRESETS=[
  ["#7C3AED","#4F46E5"],
  ["#2563EB","#0891B2"],
  ["#059669","#0D9488"],
  ["#DB2777","#7C3AED"],
  ["#EA580C","#D97706"],
] as const;

function colorInputValue(value:string,fallback:string){
  return /^#[0-9a-fA-F]{6}$/.test(value)?value:fallback;
}

export function BrandingSettingsPage(){
  const {pick}=useI18n();
  const {brand,ready,updateBrand,reloadBrand}=useBranding();
  const [draft,setDraft]=useState<BrandingConfig>(brand);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  useEffect(()=>setDraft(brand),[brand]);

  const set=<K extends keyof BrandingConfig>(key:K,value:BrandingConfig[K])=>setDraft(current=>({...current,[key]:value}));
  const begin=(key:string)=>{if(busy)return false;setBusy(key);setError("");setOk("");return true;};
  const finish=()=>setBusy("");
  const fail=(reason:unknown)=>setError(reason instanceof Error?reason.message:String(reason));
  const success=(message:string)=>{setOk(message);window.setTimeout(()=>setOk(""),2600);};

  const applyRecord=(record:BrandingRecord)=>{
    const next=configFromBrandingRecord(record);
    setDraft(next);
    updateBrand(next);
    return next;
  };

  const save=async()=>{
    if(!begin("save"))return;
    const name=draft.name.trim();
    if(!name){setError(pick("نام برند نمی‌تواند خالی باشد.","Brand name cannot be empty."));finish();return;}
    try{
      applyRecord(await brandingApi.save({
        brand_name:name,
        site_title:name,
        primary_color:draft.accent,
        secondary_color:draft.secondaryColor,
      }));
      success(pick("هویت برند روی سرور ذخیره شد.","Brand identity was saved on the server."));
    }catch(reason){fail(reason);}finally{finish();}
  };

  const upload=async(kind:BrandingAssetKind,event:ChangeEvent<HTMLInputElement>)=>{
    const file=event.target.files?.[0];
    event.target.value="";
    if(!file||!begin(`upload-${kind}`))return;
    try{
      applyRecord(await brandingApi.uploadAsset(kind,file));
      success(kind==="logo"?pick("لوگو آپلود و فعال شد.","Logo uploaded and activated."):pick("Favicon آپلود و فعال شد.","Favicon uploaded and activated."));
    }catch(reason){fail(reason);}finally{finish();}
  };

  const removeAsset=async(kind:BrandingAssetKind)=>{
    if(!begin(`delete-${kind}`))return;
    try{
      applyRecord(await brandingApi.deleteAsset(kind));
      success(kind==="logo"?pick("لوگوی سفارشی حذف شد.","Custom logo removed."):pick("Favicon سفارشی حذف شد.","Custom favicon removed."));
    }catch(reason){fail(reason);}finally{finish();}
  };

  const refresh=async()=>{
    if(!begin("reload"))return;
    try{
      const next=await reloadBrand();
      setDraft(next);
      success(pick("تنظیمات برند از سرور بازخوانی شد.","Brand settings reloaded from the server."));
    }catch(reason){fail(reason);}finally{finish();}
  };

  const reset=async()=>{
    if(!window.confirm(pick("هویت برند به تنظیمات پیش‌فرض برگردد؟ لوگو و Favicon سفارشی هم حذف می‌شوند.","Reset brand identity to defaults? Custom logo and favicon will also be removed.")))return;
    if(!begin("reset"))return;
    try{
      await brandingApi.deleteAsset("logo");
      await brandingApi.deleteAsset("favicon");
      applyRecord(await brandingApi.save({
        brand_name:DEFAULT_BRANDING.name,
        site_title:DEFAULT_BRANDING.name,
        primary_color:DEFAULT_BRANDING.accent,
        secondary_color:DEFAULT_BRANDING.secondaryColor,
      }));
      success(pick("برندینگ به حالت پیش‌فرض بازگشت.","Branding reset to defaults."));
    }catch(reason){fail(reason);}finally{finish();}
  };

  const customLogo=draft.logoUrl!==DEFAULT_BRANDING.logoUrl;
  const customFavicon=draft.faviconUrl!==DEFAULT_BRANDING.faviconUrl;
  const previewStyle={
    "--preview-primary":draft.accent,
    "--preview-secondary":draft.secondaryColor,
  } as CSSProperties;

  return <Shell active="/admin/branding"><div className="page brandingStudio">
    <div className="brandingStudioHead">
      <PageHead title={pick("برندینگ","Branding")}/>
      <div className="action-row brandingHeadActions">
        <button className="ghost" onClick={()=>void refresh()} disabled={Boolean(busy)}>{busy==="reload"?"…":pick("بازخوانی","Reload")}</button>
        <button className="primary" onClick={()=>void save()} disabled={Boolean(busy)||!ready}>{busy==="save"?pick("در حال ذخیره...","Saving..."):pick("ذخیره برند","Save branding")}</button>
      </div>
    </div>

    {error&&<div className="runtime-error">{error}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}
    {!ready&&<div className="runtime-loading">{pick("در حال دریافت هویت برند...","Loading brand identity...")}</div>}

    <div className="brandingLayout">
      <div className="brandingEditorColumn">
        <Card className="brandingIdentityCard">
          <div className="card-head"><div><b>{pick("هویت اصلی","Core identity")}</b><small>{pick("این موارد در پنل مدیریت، ورود و فروشگاه به‌صورت سراسری استفاده می‌شوند.","These values are used globally across admin, login and storefront surfaces.")}</small></div><span className="brandingServerBadge">{pick("ذخیره روی سرور","Server persisted")}</span></div>
          <label className="field"><span>{pick("نام عمومی برند","Public brand name")}</span><input value={draft.name} maxLength={120} onChange={event=>set("name",event.target.value)}/></label>
        </Card>

        <Card className="brandingAssetCard">
          <div className="card-head"><div><b>{pick("دارایی‌های تصویری","Brand assets")}</b><small>{pick("فایل‌ها در فضای مدیریت‌شده TwinPanel نگهداری می‌شوند؛ نیازی به وارد کردن مسیر دستی نیست.","Files are stored in TwinPanel managed storage; no manual path is required.")}</small></div></div>
          <div className="brandAssetGrid">
            <div className="brandAssetItem">
              <div className="brandAssetPreview logo"><img src={draft.logoUrl} alt={draft.name}/></div>
              <div className="brandAssetCopy"><b>{pick("لوگوی اصلی","Primary logo")}</b><small>{pick("PNG، WebP یا JPG · حداکثر 2MB","PNG, WebP or JPG · max 2MB")}</small></div>
              <div className="brandAssetActions"><label className={`ghost brandUploadButton ${busy?"disabled":""}`}><input type="file" accept="image/png,image/webp,image/jpeg" disabled={Boolean(busy)} onChange={event=>void upload("logo",event)}/>{busy==="upload-logo"?pick("در حال آپلود...","Uploading..."):customLogo?pick("جایگزینی","Replace"):pick("آپلود لوگو","Upload logo")}</label>{customLogo&&<button className="ghost" disabled={Boolean(busy)} onClick={()=>void removeAsset("logo")}>{pick("حذف","Remove")}</button>}</div>
            </div>
            <div className="brandAssetItem">
              <div className="brandAssetPreview favicon"><img src={draft.faviconUrl} alt=""/></div>
              <div className="brandAssetCopy"><b>Favicon</b><small>{pick("PNG، WebP یا ICO · حداکثر 2MB","PNG, WebP or ICO · max 2MB")}</small></div>
              <div className="brandAssetActions"><label className={`ghost brandUploadButton ${busy?"disabled":""}`}><input type="file" accept="image/png,image/webp,image/x-icon,.ico" disabled={Boolean(busy)} onChange={event=>void upload("favicon",event)}/>{busy==="upload-favicon"?pick("در حال آپلود...","Uploading..."):customFavicon?pick("جایگزینی","Replace"):pick("آپلود Favicon","Upload favicon")}</label>{customFavicon&&<button className="ghost" disabled={Boolean(busy)} onClick={()=>void removeAsset("favicon")}>{pick("حذف","Remove")}</button>}</div>
            </div>
          </div>
        </Card>

        <Card className="brandingColorCard">
          <div className="card-head"><div><b>{pick("رنگ‌های برند","Brand colors")}</b><small>{pick("رنگ اصلی و ثانویه بعد از ذخیره روی کنترل‌های پنل و اجزای کلیدی فروشگاه اعمال می‌شوند.","Primary and secondary colors are applied to panel controls and key storefront surfaces after saving.")}</small></div></div>
          <div className="brandColorGrid">
            <label className="brandColorField"><span>{pick("رنگ اصلی","Primary")}</span><div><input type="color" value={colorInputValue(draft.accent,DEFAULT_BRANDING.accent)} onChange={event=>set("accent",event.target.value.toUpperCase())}/><input dir="ltr" value={draft.accent} maxLength={7} onChange={event=>set("accent",event.target.value)}/></div></label>
            <label className="brandColorField"><span>{pick("رنگ ثانویه","Secondary")}</span><div><input type="color" value={colorInputValue(draft.secondaryColor,DEFAULT_BRANDING.secondaryColor)} onChange={event=>set("secondaryColor",event.target.value.toUpperCase())}/><input dir="ltr" value={draft.secondaryColor} maxLength={7} onChange={event=>set("secondaryColor",event.target.value)}/></div></label>
          </div>
          <div className="brandPresetRow"><span>{pick("پالت‌های سریع","Quick palettes")}</span><div>{COLOR_PRESETS.map(([primary,secondary])=><button type="button" key={`${primary}-${secondary}`} title={`${primary} · ${secondary}`} style={{background:`linear-gradient(135deg,${primary},${secondary})`}} onClick={()=>setDraft(current=>({...current,accent:primary,secondaryColor:secondary}))}/>)}</div></div>
        </Card>

        <Card className="brandingOwnershipCard">
          <div className="card-head"><div><b>{pick("تنظیمات مربوط به فروشگاه","Storefront-owned settings")}</b><small>{pick("برای جلوگیری از دو منبع تنظیمات، متن‌ها، فوتر، شبکه‌های اجتماعی و SEO فقط از بخش تنظیمات فروشگاه مدیریت می‌شوند.","To avoid duplicate sources of truth, copy, footer, social links and SEO are managed only in Store Settings.")}</small></div></div>
          <div className="brandingOwnershipTags"><span>{pick("محتوا","Content")}</span><span>{pick("فوتر","Footer")}</span><span>{pick("شبکه‌های اجتماعی","Social links")}</span><span>SEO</span></div>
          <Link className="ghost brandingStoreLink" href="/admin/store-settings">{pick("رفتن به تنظیمات فروشگاه","Open Store Settings")} ←</Link>
        </Card>

        <div className="brandingDangerRow"><button className="ghost" disabled={Boolean(busy)} onClick={()=>void reset()}>{busy==="reset"?pick("در حال بازنشانی...","Resetting..."):pick("بازنشانی برند","Reset branding")}</button></div>
      </div>

      <Card className="brandingPreviewCard">
        <div className="card-head"><div><b>{pick("پیش‌نمایش زنده","Live preview")}</b><small>{pick("پیش‌نمایش با تغییرات ذخیره‌نشده همین فرم به‌روزرسانی می‌شود.","Preview updates from the unsaved values in this form.")}</small></div></div>
        <div className="brandLiveSurface" style={previewStyle}>
          <div className="brandLiveTopbar"><div className="brandLiveIdentity"><img src={draft.logoUrl} alt={draft.name}/><div><b>{draft.name||pick("بدون نام","Unnamed")}</b><small>{draft.shortName}</small></div></div><div className="brandLiveTools"><span/><span/><span/></div></div>
          <div className="brandLiveBody">
            <div className="brandLiveSidebar"><i/><i className="active"/><i/><i/></div>
            <div className="brandLiveContent">
              <div className="brandLiveHero"><span>{pick("هویت سراسری","GLOBAL IDENTITY")}</span><h3>{draft.name||pick("نام برند","Brand name")}</h3><p>{pick("رنگ‌ها و لوگوی برند روی نقاط اصلی تجربه کاربری اعمال می‌شوند.","Brand colors and assets flow into the main product experience.")}</p><button type="button">{pick("دکمه اصلی","Primary action")}</button></div>
              <div className="brandLiveCards"><div><i/><b>{pick("کارت نمونه","Sample card")}</b><small>{pick("Accent اصلی","Primary accent")}</small></div><div><i/><b>{pick("وضعیت","Status")}</b><small>{pick("رنگ ثانویه","Secondary color")}</small></div></div>
            </div>
          </div>
        </div>
        <div className="brandPreviewMeta"><div><span>{pick("لوگو","Logo")}</span><b>{customLogo?pick("سفارشی","Custom"):pick("پیش‌فرض","Default")}</b></div><div><span>Favicon</span><b>{customFavicon?pick("سفارشی","Custom"):pick("پیش‌فرض","Default")}</b></div><div><span>{pick("رنگ اصلی","Primary")}</span><b dir="ltr">{draft.accent}</b></div><div><span>{pick("رنگ ثانویه","Secondary")}</span><b dir="ltr">{draft.secondaryColor}</b></div></div>
      </Card>
    </div>
  </div></Shell>;
}
