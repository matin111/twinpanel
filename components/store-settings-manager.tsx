"use client";

import Link from "next/link";
import {useEffect,useState} from "react";
import {Badge,Card,Shell} from "./ui";
import {AnyRow,parityApi} from "../lib/admin-parity-api";
import {useI18n} from "../lib/i18n";
import {
  DEFAULT_STOREFRONT_SETTINGS,
  StorefrontSettings,
  normalizeStorefrontSettings,
} from "../lib/storefront-config";
import {
  STORE_TEMPLATE_CATALOG,
  installedStoreTemplate,
} from "../lib/store-template-registry";

function payloadOf(settings:StorefrontSettings){
  const {updated_at:_,...payload}=settings;
  return payload as unknown as AnyRow;
}

export function StoreSettingsManager(){
  const {pick}=useI18n();
  const [settings,setSettings]=useState<StorefrontSettings>(DEFAULT_STOREFRONT_SETTINGS);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const load=async()=>{
    setLoading(true);setError("");
    try{setSettings(normalizeStorefrontSettings(await parityApi.storefrontSettings()));}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setLoading(false);}
  };
  useEffect(()=>{void load();},[]);

  const activateTemplate=async(templateId:string)=>{
    if(busy)return;
    const next={...settings,active_template:templateId};
    setSettings(next);
    setBusy(true);setError("");setOk("");
    try{
      const saved=await parityApi.saveStorefrontSettings(payloadOf(next));
      setSettings(normalizeStorefrontSettings(saved));
      setOk(pick("قالب فروشگاه فعال شد.","Storefront template activated."));
      window.setTimeout(()=>setOk(""),3000);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const activeTemplate=installedStoreTemplate(settings.active_template);
  const unknownTemplate=Boolean(settings.active_template&&!activeTemplate);

  return <Shell active="/admin/store-settings"><div className="page storeAdminManager">
    <div className="page-head">
      <div>
        <h1>{pick("قالب‌های فروشگاه","Storefront templates")}</h1>
        <small>{pick("قالب را فعال کنید یا برای تنظیمات اختصاصی وارد صفحه شخصی‌سازی همان قالب شوید.","Activate a template or open its dedicated customization page.")}</small>
      </div>
      <div className="action-row">
        <Link className="ghost" href="/store" target="_blank">{pick("مشاهده فروشگاه","Open storefront")} ↗</Link>
        <button className="ghost" onClick={()=>void load()} disabled={loading||busy}>{pick("بازخوانی","Reload")}</button>
      </div>
    </div>

    {error&&<div className="runtime-error">{error}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}
    {loading?<div className="runtime-loading">{pick("در حال دریافت قالب‌های فروشگاه...","Loading storefront templates...")}</div>:null}

    {!loading&&<>
      <Card className="storeAdminIntro">
        <div>
          <b>{pick("قالب‌های مستقل فروشگاه","Independent storefront templates")}</b>
          <p>{pick("هر قالب تنظیمات مستقل خودش را دارد. تنظیمات عمومی قدیمی از این صفحه حذف شده‌اند و شخصی‌سازی هر قالب فقط در صفحه اختصاصی همان قالب انجام می‌شود.","Each template owns its independent settings. The legacy shared-settings editor has been removed from this screen, and every template is customized only on its dedicated page.")}</p>
        </div>
        <Badge tone="violet">{STORE_TEMPLATE_CATALOG.length} {pick("قالب نصب‌شده","installed")}</Badge>
      </Card>

      {unknownTemplate&&<div className="runtime-warning">{pick(`قالب ذخیره‌شده «${settings.active_template}» در این نسخه نصب نیست؛ فروشگاه از قالب پیش‌فرض استفاده می‌کند.`,`Saved template “${settings.active_template}” is not installed in this version; the storefront falls back to the default template.`)}</div>}

      <div className="storeTemplateGrid">{STORE_TEMPLATE_CATALOG.map(template=>{
        const active=settings.active_template===template.id||(!activeTemplate&&template.id==="conversion-2027");
        return <Card className={`storeTemplateCard ${active?"active":""}`} key={template.id}>
          <div className="storeTemplatePreview"><span>◈</span><small>{template.id}</small></div>
          <div className="card-head">
            <div><b>{pick(template.nameFa,template.nameEn)}</b><small>v{template.version} · {template.author}</small></div>
            {active?<Badge tone="ok">{pick("فعال","Active")}</Badge>:<Badge tone="violet">{pick("نصب‌شده","Installed")}</Badge>}
          </div>
          <p>{pick(template.descriptionFa,template.descriptionEn)}</p>
          <div className="storeTemplateMeta">
            <span>◐ {pick("دارک","Dark")}</span>
            <span>☀ {pick("لایت","Light")}</span>
            <span>{template.builtIn?pick("داخلی","Built-in"):pick("افزونه","Extension")}</span>
          </div>
          <div className="action-row">
            <button className={active?"ghost":"primary"} disabled={active||busy} onClick={()=>void activateTemplate(template.id)}>{active?pick("قالب فعال","Active template"):pick("فعال‌سازی قالب","Activate template")}</button>
            <Link className="ghost" href={`/admin/store-settings/templates/${template.id}`}>{pick("شخصی‌سازی قالب","Customize")}</Link>
            <Link className="ghost" href="/store" target="_blank">{pick("پیش‌نمایش زنده","Live preview")}</Link>
          </div>
        </Card>;
      })}</div>
    </>}
  </div></Shell>;
}
