"use client";

import {useEffect,useMemo,useState} from "react";
import {useI18n} from "../lib/i18n";
import {parityApi} from "../lib/admin-parity-api";
import {normalizeStorefrontSettings,type StorefrontSettings} from "../lib/storefront-config";
import {
  STORE_TEMPLATE_SEO_KEYS,
  loadStoreTemplateSettings,
  resetStoreTemplateSeo,
  saveStoreTemplateSeo,
  type StoreTemplateSeoSettings,
} from "../lib/store-template-settings-api";
import styles from "./store-template-seo-panel.module.css";

type SeoDraft={
  seo_title:string;
  seo_description:string;
  seo_keywords:string;
  canonical_url:string;
  og_title:string;
  og_description:string;
  og_image:string;
  robots_index:boolean;
  robots_follow:boolean;
};

const TEMPLATE_NAMES:Record<string,string>={
  "conversion-2027":"Conversion 2027",
  "editorial-grid-2027":"Editorial Pro 2027",
  "orbit-neo-2027":"Orbit Neo 2027",
};

function hasOwn(source:Record<string,unknown>,key:string){
  return Object.prototype.hasOwnProperty.call(source,key);
}

function seoDraft(fallback:StorefrontSettings,raw:Record<string,unknown>):SeoDraft{
  const base=fallback as unknown as Record<string,unknown>;
  const value=(key:keyof SeoDraft)=>hasOwn(raw,key)?raw[key]:base[key];
  return {
    seo_title:typeof value("seo_title")==="string"?String(value("seo_title")):fallback.seo_title,
    seo_description:typeof value("seo_description")==="string"?String(value("seo_description")):fallback.seo_description,
    seo_keywords:typeof value("seo_keywords")==="string"?String(value("seo_keywords")):fallback.seo_keywords,
    canonical_url:typeof value("canonical_url")==="string"?String(value("canonical_url")):fallback.canonical_url,
    og_title:typeof value("og_title")==="string"?String(value("og_title")):fallback.og_title,
    og_description:typeof value("og_description")==="string"?String(value("og_description")):fallback.og_description,
    og_image:typeof value("og_image")==="string"?String(value("og_image")):fallback.og_image,
    robots_index:typeof value("robots_index")==="boolean"?Boolean(value("robots_index")):fallback.robots_index,
    robots_follow:typeof value("robots_follow")==="boolean"?Boolean(value("robots_follow")):fallback.robots_follow,
  };
}

export function StoreTemplateSeoPanel({templateId}:{templateId:string}){
  const {pick}=useI18n();
  const [draft,setDraft]=useState<SeoDraft|null>(null);
  const [fallback,setFallback]=useState<StorefrontSettings|null>(null);
  const [inherited,setInherited]=useState(true);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  useEffect(()=>{
    let active=true;
    const run=async()=>{
      setLoading(true);setError("");
      try{
        const [envelope,globalRaw]=await Promise.all([
          loadStoreTemplateSettings(),
          parityApi.storefrontSettings(),
        ]);
        if(!active)return;
        const globalSettings=normalizeStorefrontSettings(globalRaw);
        const raw=envelope.templates?.[templateId]||{};
        setFallback(globalSettings);
        setDraft(seoDraft(globalSettings,raw));
        setInherited(!STORE_TEMPLATE_SEO_KEYS.some(key=>hasOwn(raw,key)));
      }catch(reason){
        if(active)setError(reason instanceof Error?reason.message:String(reason));
      }finally{
        if(active)setLoading(false);
      }
    };
    void run();
    return()=>{active=false;};
  },[templateId]);

  const templateName=TEMPLATE_NAMES[templateId]||templateId;
  const titleCount=draft?.seo_title.length||0;
  const descriptionCount=draft?.seo_description.length||0;
  const robots=useMemo(()=>draft?`${draft.robots_index?"index":"noindex"}, ${draft.robots_follow?"follow":"nofollow"}`:"",[draft]);

  const setText=(key:keyof SeoDraft,value:string)=>setDraft(current=>current?{...current,[key]:value}:current);
  const setFlag=(key:"robots_index"|"robots_follow",value:boolean)=>setDraft(current=>current?{...current,[key]:value}:current);

  const save=async()=>{
    if(!draft||busy)return;
    setBusy(true);setError("");setOk("");
    try{
      await saveStoreTemplateSeo(templateId,draft as StoreTemplateSeoSettings);
      setInherited(false);
      setOk(pick("تنظیمات SEO این قالب ذخیره شد.","SEO settings for this template were saved."));
      window.setTimeout(()=>setOk(""),2600);
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{setBusy(false);}
  };

  const reset=async()=>{
    if(!fallback||busy)return;
    setBusy(true);setError("");setOk("");
    try{
      await resetStoreTemplateSeo(templateId);
      setDraft(seoDraft(fallback,{}));
      setInherited(true);
      setOk(pick("SEO اختصاصی این قالب حذف شد و مقادیر عمومی به‌عنوان fallback استفاده می‌شوند.","Template-specific SEO was removed and global values are now used as fallback."));
      window.setTimeout(()=>setOk(""),3200);
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{setBusy(false);}
  };

  return <section className={styles.root} id="store-template-seo" aria-labelledby={`store-template-seo-${templateId}`}>
    <div className={styles.head}>
      <div>
        <div className={styles.eyebrow}>SEO / SEARCH & SHARE</div>
        <h2 id={`store-template-seo-${templateId}`}>{pick("سئوی اختصاصی قالب","Template SEO")} · {templateName}</h2>
        <p>{pick("این تنظیمات فقط زمانی روی فروشگاه اعمال می‌شوند که همین قالب فعال باشد. ذخیره رنگ، محتوا یا چیدمان این مقادیر را تغییر نمی‌دهد.","These settings apply only while this template is active. Saving colors, content or layout will not overwrite them.")}</p>
      </div>
      <div className={styles.headActions}>
        <span className={`${styles.status} ${inherited?styles.inherited:styles.custom}`}>{inherited?pick("Fallback عمومی","Global fallback"):pick("SEO اختصاصی","Custom SEO")}</span>
        <button type="button" className={styles.secondary} onClick={()=>void reset()} disabled={busy||loading}>{pick("بازنشانی SEO","Reset SEO")}</button>
        <button type="button" className={styles.primary} onClick={()=>void save()} disabled={busy||loading||!draft}>{busy?"…":pick("ذخیره SEO","Save SEO")}</button>
      </div>
    </div>

    {error&&<div className={styles.error}>{error}</div>}
    {ok&&<div className={styles.success}>{ok}</div>}
    {loading||!draft?<div className={styles.loading}>{pick("در حال دریافت تنظیمات SEO...","Loading SEO settings...")}</div>:<>
      <div className={styles.grid}>
        <label className={styles.field}>
          <span>{pick("عنوان SEO","SEO title")}</span>
          <input type="text" value={draft.seo_title} onChange={event=>setText("seo_title",event.target.value)} maxLength={180}/>
          <small className={titleCount>65?styles.warn:""}>{titleCount}/60 · {pick("عنوان نتیجه جستجو و عنوان تب مرورگر","Search result and browser-tab title")}</small>
        </label>

        <label className={`${styles.field} ${styles.wide}`}>
          <span>{pick("توضیحات Meta","Meta description")}</span>
          <textarea rows={3} value={draft.seo_description} onChange={event=>setText("seo_description",event.target.value)} maxLength={500}/>
          <small className={descriptionCount>165?styles.warn:""}>{descriptionCount}/160 · {pick("خلاصه پیشنهادی برای موتورهای جستجو","Suggested search-engine summary")}</small>
        </label>

        <label className={`${styles.field} ${styles.wide}`}>
          <span>{pick("کلمات کلیدی","Keywords")}</span>
          <textarea rows={2} value={draft.seo_keywords} onChange={event=>setText("seo_keywords",event.target.value)} placeholder={pick("VPN, خرید VPN, WireGuard, ...","VPN, WireGuard, OpenVPN, ...")}/>
          <small>{pick("با کاما جدا کنید. این فیلد مکمل است و جای محتوای باکیفیت را نمی‌گیرد.","Separate with commas. This is supplementary and does not replace quality content.")}</small>
        </label>

        <label className={styles.field}>
          <span>Canonical URL</span>
          <input type="url" dir="ltr" value={draft.canonical_url} onChange={event=>setText("canonical_url",event.target.value)} placeholder="https://example.com/store"/>
          <small>{pick("اگر خالی باشد، آدرس فعلی صفحه فروشگاه در Runtime استفاده می‌شود.","When blank, the current storefront URL is used at runtime.")}</small>
        </label>

        <label className={styles.field}>
          <span>Open Graph Title</span>
          <input type="text" value={draft.og_title} onChange={event=>setText("og_title",event.target.value)} maxLength={180}/>
          <small>{pick("عنوان هنگام اشتراک‌گذاری لینک در شبکه‌های اجتماعی","Title used when the storefront link is shared")}</small>
        </label>

        <label className={`${styles.field} ${styles.wide}`}>
          <span>Open Graph Description</span>
          <textarea rows={3} value={draft.og_description} onChange={event=>setText("og_description",event.target.value)} maxLength={500}/>
        </label>

        <label className={`${styles.field} ${styles.wide}`}>
          <span>Open Graph Image URL</span>
          <input type="url" dir="ltr" value={draft.og_image} onChange={event=>setText("og_image",event.target.value)} placeholder="https://example.com/og-cover.jpg"/>
          <small>{pick("برای نمایش بهتر در پیام‌رسان‌ها و شبکه‌های اجتماعی، تصویر افقی عمومی HTTPS استفاده کنید.","Use a public HTTPS landscape image for richer social previews.")}</small>
        </label>
      </div>

      <div className={styles.robots}>
        <div>
          <b>Robots</b>
          <p>{pick("کنترل ایندکس شدن فروشگاه و دنبال شدن لینک‌ها توسط موتورهای جستجو.","Control storefront indexing and whether crawlers may follow links.")}</p>
        </div>
        <label className={styles.toggle}><span>{pick("اجازه Index","Allow indexing")}</span><input type="checkbox" checked={draft.robots_index} onChange={event=>setFlag("robots_index",event.target.checked)}/></label>
        <label className={styles.toggle}><span>{pick("اجازه Follow","Allow link following")}</span><input type="checkbox" checked={draft.robots_follow} onChange={event=>setFlag("robots_follow",event.target.checked)}/></label>
        <code>{robots}</code>
      </div>

      <div className={styles.preview}>
        <div className={styles.previewLabel}>{pick("پیش‌نمایش نتیجه جستجو","Search preview")}</div>
        <strong>{draft.seo_title||pick("عنوان فروشگاه","Storefront title")}</strong>
        <span dir="ltr">{draft.canonical_url||pick("آدرس فعلی فروشگاه","Current storefront URL")}</span>
        <p>{draft.seo_description||pick("توضیحات Meta اینجا نمایش داده می‌شود.","Meta description preview appears here.")}</p>
      </div>
    </>}
  </section>;
}
