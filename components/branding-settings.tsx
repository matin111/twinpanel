"use client";

import Link from "next/link";
import {useEffect,useState,type ChangeEvent,type CSSProperties} from "react";
import {Card,PageHead,Shell} from "./ui";
import {brandingApi,type BrandingAssetKind} from "../lib/branding-api";
import {DEFAULT_BRANDING,useBranding} from "../lib/branding";
import {useI18n} from "../lib/i18n";

type Draft={
  name:string;
  primaryColor:string;
  secondaryColor:string;
};

const HEX_COLOR=/^#[0-9A-Fa-f]{6}$/;

function draftOf(name:string,primaryColor:string,secondaryColor:string):Draft{
  return {name,primaryColor,secondaryColor};
}

export function BrandingSettingsPage(){
  const {pick}=useI18n();
  const {brand,replaceBrand,reloadBrand}=useBranding();
  const [draft,setDraft]=useState<Draft>(()=>draftOf(brand.name,brand.primaryColor,brand.secondaryColor));
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  useEffect(()=>{
    setDraft(draftOf(brand.name,brand.primaryColor,brand.secondaryColor));
  },[brand.name,brand.primaryColor,brand.secondaryColor]);

  const begin=(key:string)=>{
    if(busy)return false;
    setBusy(key);setError("");setOk("");
    return true;
  };
  const finish=()=>setBusy("");
  const fail=(reason:unknown)=>setError(reason instanceof Error?reason.message:String(reason));

  const save=async()=>{
    if(!draft.name.trim()){
      setError(pick("نام برند نمی‌تواند خالی باشد.","Brand name cannot be empty."));
      return;
    }
    if(!HEX_COLOR.test(draft.primaryColor)||!HEX_COLOR.test(draft.secondaryColor)){
      setError(pick("رنگ‌ها باید به فرمت HEX مثل #7C3AED باشند.","Colors must use a HEX value such as #7C3AED."));
      return;
    }
    if(!begin("save"))return;
    try{
      const record=await brandingApi.save({
        brand_name:draft.name.trim(),
        primary_color:draft.primaryColor.toUpperCase(),
        secondary_color:draft.secondaryColor.toUpperCase(),
      });
      replaceBrand(record);
      setOk(pick("هویت برند روی سرور ذخیره شد.","Brand identity was saved on the server."));
    }catch(reason){fail(reason);}finally{finish();}
  };

  const uploadAsset=async(kind:BrandingAssetKind,file:File)=>{
    const max=kind==="logo"?4*1024*1024:1024*1024;
    if(file.size>max){
      setError(kind==="logo"?pick("حجم لوگو حداکثر ۴ مگابایت است.","Logo size is limited to 4 MB."):pick("حجم Favicon حداکثر ۱ مگابایت است.","Favicon size is limited to 1 MB."));
      return;
    }
    if(!begin(`upload:${kind}`))return;
    try{
      const record=await brandingApi.uploadAsset(kind,file);
      replaceBrand(record);
      setOk(kind==="logo"?pick("لوگو آپلود و ذخیره شد.","Logo uploaded and saved."):pick("Favicon آپلود و ذخیره شد.","Favicon uploaded and saved."));
    }catch(reason){fail(reason);}finally{finish();}
  };

  const chooseAsset=(kind:BrandingAssetKind)=>(event:ChangeEvent<HTMLInputElement>)=>{
    const file=event.target.files?.[0]||null;
    event.target.value="";
    if(file)void uploadAsset(kind,file);
  };

  const removeAsset=async(kind:BrandingAssetKind)=>{
    const label=kind==="logo"?pick("لوگو","logo"):"Favicon";
    if(!window.confirm(pick(`آیا ${label} حذف شود؟`,`Remove the ${label}?`)))return;
    if(!begin(`delete:${kind}`))return;
    try{
      const record=await brandingApi.deleteAsset(kind);
      replaceBrand(record);
      setOk(kind==="logo"?pick("لوگوی سفارشی حذف شد.","Custom logo removed."):pick("Favicon سفارشی حذف شد.","Custom favicon removed."));
    }catch(reason){fail(reason);}finally{finish();}
  };

  const reload=async()=>{
    if(!begin("reload"))return;
    try{
      await reloadBrand();
      setOk(pick("تنظیمات برند از سرور بازخوانی شد.","Brand settings reloaded from the server."));
    }catch(reason){fail(reason);}finally{finish();}
  };

  const previewStyle={
    "--brand-preview-primary":HEX_COLOR.test(draft.primaryColor)?draft.primaryColor:DEFAULT_BRANDING.primaryColor,
    "--brand-preview-secondary":HEX_COLOR.test(draft.secondaryColor)?draft.secondaryColor:DEFAULT_BRANDING.secondaryColor,
  } as CSSProperties;

  return <Shell active="/admin/branding"><div className="page brandingAdminPage">
    <div className="brandingPageHead">
      <PageHead title={pick("برندینگ","Branding")}/>
      <div className="action-row">
        <button className="ghost" type="button" onClick={()=>void reload()} disabled={Boolean(busy)}>{pick("بازخوانی","Reload")}</button>
        <button className="primary" type="button" onClick={()=>void save()} disabled={Boolean(busy)}>{busy==="save"?pick("در حال ذخیره...","Saving..."):pick("ذخیره برند","Save branding")}</button>
      </div>
    </div>

    {error&&<div className="runtime-error">{error}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}

    <div className="brandingAdminGrid">
      <div className="brandingAdminColumn">
        <Card className="brandingCard">
          <div className="card-head"><div><b>{pick("هویت اصلی","Brand identity")}</b><small>{pick("نام و نشان سراسری پنل، صفحه ورود و فروشگاه","Global name and mark used by the panel, sign-in and storefront")}</small></div></div>
          <label className="field"><span>{pick("نام برند","Brand name")}</span><input value={draft.name} maxLength={120} onChange={event=>setDraft(current=>({...current,name:event.target.value}))}/></label>

          <div className="brandingAssetBox">
            <div className="brandingAssetPreview brandingLogoPreview">
              <img src={brand.logoUrl||DEFAULT_BRANDING.logoUrl} alt={draft.name||brand.name}/>
            </div>
            <div className="brandingAssetBody">
              <b>{pick("لوگو","Logo")}</b>
              <small>{pick("PNG، JPG یا WEBP · حداکثر ۴ مگابایت","PNG, JPG or WEBP · up to 4 MB")}</small>
              <div className="action-row">
                <label className={`ghost brandingUploadButton ${busy==="upload:logo"?"disabled":""}`}>
                  <input type="file" accept="image/png,image/jpeg,image/webp" disabled={Boolean(busy)} onChange={chooseAsset("logo")}/>
                  {busy==="upload:logo"?pick("در حال آپلود...","Uploading..."):pick("انتخاب و آپلود لوگو","Choose & upload logo")}
                </label>
                {brand.logoUrl!==DEFAULT_BRANDING.logoUrl&&<button className="ghost" type="button" disabled={Boolean(busy)} onClick={()=>void removeAsset("logo")}>{pick("حذف لوگوی سفارشی","Remove custom logo")}</button>}
              </div>
            </div>
          </div>

          <div className="brandingAssetBox compact">
            <div className="brandingAssetPreview brandingFaviconPreview">
              {brand.faviconUrl?<img src={brand.faviconUrl} alt="Favicon"/>:<span>{(draft.name.trim()||"T").slice(0,1).toUpperCase()}</span>}
            </div>
            <div className="brandingAssetBody">
              <b>Favicon</b>
              <small>{pick("PNG، WEBP یا ICO · حداکثر ۱ مگابایت","PNG, WEBP or ICO · up to 1 MB")}</small>
              <div className="action-row">
                <label className={`ghost brandingUploadButton ${busy==="upload:favicon"?"disabled":""}`}>
                  <input type="file" accept="image/png,image/webp,image/x-icon,image/vnd.microsoft.icon,.ico" disabled={Boolean(busy)} onChange={chooseAsset("favicon")}/>
                  {busy==="upload:favicon"?pick("در حال آپلود...","Uploading..."):pick("انتخاب Favicon","Choose favicon")}
                </label>
                {brand.faviconUrl&&<button className="ghost" type="button" disabled={Boolean(busy)} onClick={()=>void removeAsset("favicon")}>{pick("حذف","Remove")}</button>}
              </div>
            </div>
          </div>
        </Card>

        <Card className="brandingCard">
          <div className="card-head"><div><b>{pick("رنگ‌های برند","Brand colors")}</b><small>{pick("رنگ اصلی و مکمل برای اجزای تعاملی و فروشگاه","Primary and secondary colors for interactive UI and storefront accents")}</small></div></div>
          <div className="brandingColorGrid">
            <label className="brandingColorField">
              <span>{pick("رنگ اصلی","Primary color")}</span>
              <div><input type="color" value={HEX_COLOR.test(draft.primaryColor)?draft.primaryColor:DEFAULT_BRANDING.primaryColor} onChange={event=>setDraft(current=>({...current,primaryColor:event.target.value.toUpperCase()}))}/><input dir="ltr" maxLength={7} value={draft.primaryColor} onChange={event=>setDraft(current=>({...current,primaryColor:event.target.value.toUpperCase()}))}/></div>
            </label>
            <label className="brandingColorField">
              <span>{pick("رنگ مکمل","Secondary color")}</span>
              <div><input type="color" value={HEX_COLOR.test(draft.secondaryColor)?draft.secondaryColor:DEFAULT_BRANDING.secondaryColor} onChange={event=>setDraft(current=>({...current,secondaryColor:event.target.value.toUpperCase()}))}/><input dir="ltr" maxLength={7} value={draft.secondaryColor} onChange={event=>setDraft(current=>({...current,secondaryColor:event.target.value.toUpperCase()}))}/></div>
            </label>
          </div>
          <div className="brandingPaletteStrip" style={previewStyle}><i/><i/><i/><i/></div>
          <button className="ghost" type="button" disabled={Boolean(busy)} onClick={()=>setDraft(current=>({...current,primaryColor:DEFAULT_BRANDING.primaryColor,secondaryColor:DEFAULT_BRANDING.secondaryColor}))}>{pick("قرار دادن رنگ‌های پیش‌فرض","Use default colors")}</button>
        </Card>

        <Card className="brandingStoreBoundary">
          <div><b>{pick("محتوای فروشگاه جدا مدیریت می‌شود","Storefront content is managed separately")}</b><small>{pick("متن‌ها، شبکه‌های اجتماعی، فوتر، ترتیب بخش‌ها و SEO در تنظیمات فروشگاه باقی می‌مانند تا تنظیم تکراری نداشته باشیم.","Copy, social links, footer, section order and SEO stay in Store Settings so the same setting is not duplicated.")}</small></div>
          <Link className="ghost" href="/admin/store-settings">{pick("رفتن به تنظیمات فروشگاه","Open Store Settings")} ←</Link>
        </Card>
      </div>

      <div className="brandingAdminColumn previewColumn">
        <Card className="brandingPreviewCard">
          <div className="card-head"><div><b>{pick("پیش‌نمایش زنده","Live preview")}</b><small>{pick("پیش‌نمایش قبل از ذخیره رنگ‌ها","Preview colors before saving")}</small></div></div>
          <div className="brandingProductPreview" style={previewStyle}>
            <header>
              <div className="brandingPreviewBrand"><img src={brand.logoUrl||DEFAULT_BRANDING.logoUrl} alt=""/><b>{draft.name.trim()||pick("بدون نام","Unnamed")}</b></div>
              <span className="brandingPreviewNav">{pick("داشبورد","Dashboard")}</span>
              <span className="brandingPreviewNav active">{pick("اشتراک‌ها","Subscriptions")}</span>
            </header>
            <main>
              <span className="brandingPreviewEyebrow">{pick("هویت برند","BRAND IDENTITY")}</span>
              <h3>{draft.name.trim()||pick("بدون نام","Unnamed")}</h3>
              <p>{pick("رنگ‌های انتخابی روی دکمه‌ها، حالت‌های فعال و Accentهای محصول اعمال می‌شوند.","Selected colors drive buttons, active states and product accents.")}</p>
              <div className="brandingPreviewActions"><button type="button">{pick("دکمه اصلی","Primary action")}</button><span>{pick("فعال","Active")}</span></div>
              <div className="brandingPreviewStats"><article><i/><b>99.9%</b><small>{pick("پایداری","Uptime")}</small></article><article><i/><b>24/7</b><small>{pick("پشتیبانی","Support")}</small></article></div>
            </main>
          </div>
          <div className="brandingPreviewMeta"><span>{pick("ذخیره‌سازی","Persistence")}</span><b>{pick("سرور / دیتابیس","Server / database")}</b></div>
          <div className="brandingPreviewMeta"><span>{pick("دامنه اعمال","Applies to")}</span><b>{pick("پنل، ورود و فروشگاه","Panel, sign-in & store")}</b></div>
        </Card>
      </div>
    </div>
  </div></Shell>;
}
