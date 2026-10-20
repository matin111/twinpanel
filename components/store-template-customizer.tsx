"use client";

import Link from "next/link";
import {useEffect,useMemo,useState} from "react";
import {useI18n} from "../lib/i18n";
import {parityApi} from "../lib/admin-parity-api";
import {normalizeStorefrontSettings} from "../lib/storefront-config";
import {
  normalizeStoreTemplateOptions,
  storeTemplateOptionDefinition,
  type StoreTemplateOptionField,
  type StoreTemplateOptionMap,
} from "../lib/store-template-options";
import {
  loadStoreTemplateSettings,
  resetStoreTemplateSettings,
  saveStoreTemplateSettings,
} from "../lib/store-template-settings-api";
import styles from "./store-template-customizer.module.css";

const SECTION_LABELS:Record<string,{fa:string;en:string}>={
  plans:{fa:"پلن‌ها",en:"Plans"},
  protocols:{fa:"پروتکل‌ها",en:"Protocols"},
  services:{fa:"خدمات",en:"Services"},
  guides:{fa:"آموزش اتصال",en:"Guides"},
  account:{fa:"پنل کاربری",en:"Account"},
  faq:{fa:"سوالات متداول",en:"FAQ"},
};

type Props={
  templateId:string;
  onClose:()=>void;
};

export function StoreTemplateCustomizer({templateId,onClose}:Props){
  const {pick}=useI18n();
  const definition=useMemo(()=>storeTemplateOptionDefinition(templateId),[templateId]);
  const [locale,setLocale]=useState<"fa"|"en">("fa");
  const [draft,setDraft]=useState<StoreTemplateOptionMap>({});
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  useEffect(()=>{
    let active=true;
    const run=async()=>{
      setLoading(true);setError("");setOk("");
      try{
        const [envelope,sharedRaw]=await Promise.all([
          loadStoreTemplateSettings(),
          parityApi.storefrontSettings(),
        ]);
        if(!active)return;
        const raw=envelope.templates?.[templateId]||{};
        const normalized=normalizeStoreTemplateOptions(templateId,raw);
        if(Object.keys(raw).length===0&&definition){
          const shared=normalizeStorefrontSettings(sharedRaw) as unknown as Record<string,unknown>;
          for(const [key,fallback] of Object.entries(definition.defaults)){
            if(key in shared)normalized[key]=shared[key] as string|number|boolean|string[];
            if(typeof fallback==="string"){
              const localizedKey=`${key}_en`;
              if(localizedKey in shared&&typeof shared[localizedKey]==="string")normalized[localizedKey]=shared[localizedKey] as string;
            }
          }
          setDraft(normalized);
        }else{
          setDraft({...normalized,...raw} as StoreTemplateOptionMap);
        }
      }catch(reason){
        if(active)setError(reason instanceof Error?reason.message:String(reason));
      }finally{
        if(active)setLoading(false);
      }
    };
    void run();
    return()=>{active=false;};
  },[templateId,definition]);

  if(!definition)return null;

  const actualKey=(field:StoreTemplateOptionField)=>locale==="en"&&["text","textarea"].includes(field.type)?`${field.key}_en`:field.key;
  const valueOf=(field:StoreTemplateOptionField)=>draft[actualKey(field)];
  const setValue=(field:StoreTemplateOptionField,value:string|boolean|string[])=>setDraft(current=>({...current,[actualKey(field)]:value}));

  const save=async()=>{
    if(busy)return;
    setBusy(true);setError("");setOk("");
    try{
      await saveStoreTemplateSettings(templateId,draft as unknown as Record<string,unknown>);
      setOk(pick("تنظیمات همین قالب ذخیره شد.","This template's settings were saved."));
      window.setTimeout(()=>setOk(""),3000);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const reset=async()=>{
    if(busy||!window.confirm(pick("تنظیمات این قالب به حالت پیش‌فرض خودش برگردد؟","Reset this template to its own defaults?")))return;
    setBusy(true);setError("");setOk("");
    try{
      await resetStoreTemplateSettings(templateId);
      setDraft(normalizeStoreTemplateOptions(templateId,{}));
      setOk(pick("تنظیمات قالب به پیش‌فرض خودش برگشت.","Template settings were reset to its own defaults."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const moveSection=(field:StoreTemplateOptionField,index:number,delta:number)=>{
    const key=actualKey(field);
    const order=Array.isArray(draft[key])?[...(draft[key] as string[])]:[];
    const target=index+delta;
    if(target<0||target>=order.length)return;
    [order[index],order[target]]=[order[target],order[index]];
    setDraft(current=>({...current,[key]:order}));
  };

  const renderField=(field:StoreTemplateOptionField)=>{
    const key=actualKey(field);
    const value=valueOf(field);
    if(field.type==="toggle")return <label className={styles.toggle} key={key}><span>{pick(field.fa,field.en)}</span><input type="checkbox" checked={Boolean(value)} onChange={event=>setValue(field,event.target.checked)}/></label>;
    if(field.type==="color"){
      const color=typeof value==="string"&&/^#[0-9a-fA-F]{6}$/.test(value)?value:"#7c3aed";
      return <label className={styles.field} key={key}><span>{pick(field.fa,field.en)}</span><div className={styles.colorRow}><input type="color" value={color} onChange={event=>setValue(field,event.target.value)}/><input type="text" dir="ltr" value={String(value||"")} onChange={event=>setValue(field,event.target.value)}/></div></label>;
    }
    if(field.type==="select")return <label className={styles.field} key={key}><span>{pick(field.fa,field.en)}</span><select value={String(value||"")} onChange={event=>setValue(field,event.target.value)}>{(field.choices||[]).map(choice=><option value={choice.value} key={choice.value}>{pick(choice.fa,choice.en)}</option>)}</select></label>;
    if(field.type==="section-order"){
      const order=Array.isArray(value)?value.map(String):[];
      return <div className={styles.field} key={key}><span>{pick(field.fa,field.en)}</span><div className={styles.order}>{order.map((section,index)=>{const label=SECTION_LABELS[section]||{fa:section,en:section};return <div className={styles.orderRow} key={section}><span>{index+1}</span><b>{pick(label.fa,label.en)}</b><div className={styles.orderActions}><button type="button" disabled={index===0} onClick={()=>moveSection(field,index,-1)}>↑</button><button type="button" disabled={index===order.length-1} onClick={()=>moveSection(field,index,1)}>↓</button></div></div>;})}</div></div>;
    }
    if(field.type==="textarea")return <label className={styles.field} key={key}><span>{pick(field.fa,field.en)}</span><textarea rows={4} value={String(value||"")} onChange={event=>setValue(field,event.target.value)}/></label>;
    return <label className={styles.field} key={key}><span>{pick(field.fa,field.en)}</span><input type="text" value={String(value||"")} onChange={event=>setValue(field,event.target.value)}/></label>;
  };

  return <section className={styles.root}>
    <div className={styles.header}>
      <div>
        <h2>{pick("شخصی‌سازی مستقل قالب","Independent template customizer")}</h2>
        <p>{pick("از اینجا ظاهر، متن‌ها، بخش‌ها و ترتیب همین قالب را مدیریت کنید. این داده‌ها جدا از قالب‌های دیگر ذخیره می‌شوند و با تعویض قالب یا آپدیت از بین نمی‌روند.","Manage this template's appearance, copy, sections and ordering here. These values are stored separately from other templates and survive template switches and updates.")}</p>
      </div>
      <div className={styles.headerActions}>
        <button type="button" onClick={onClose}>{pick("بستن","Close")}</button>
        <button type="button" onClick={()=>void reset()} disabled={busy}>{pick("بازنشانی پیش‌فرض","Reset defaults")}</button>
        <Link href="/store" target="_blank">{pick("مشاهده فروشگاه","Open storefront")} ↗</Link>
        <button type="button" className={styles.primary} onClick={()=>void save()} disabled={busy}>{busy?"…":pick("ذخیره قالب","Save template")}</button>
      </div>
    </div>
    <div className={styles.notice}>{pick("اطلاعات تجاری زنده مثل پلن‌ها، قیمت، حجم، مدت، دستگاه‌ها و مسیر خرید همچنان از Backend می‌آیند. چیزی که اینجا ذخیره می‌شود لایه نمایش و محتوای اختصاصی همین قالب است.","Live business data such as plans, prices, traffic, duration, devices and purchase flow still comes from the backend. This customizer stores only the presentation and template-specific content layer.")}</div>
    {error&&<div className={styles.error}>{error}</div>}
    {ok&&<div className={styles.success}>{ok}</div>}
    {loading?<div className={styles.loading}>{pick("در حال دریافت تنظیمات قالب...","Loading template settings...")}</div>:<>
      <div className={styles.toolbar}><div className={styles.locale}><button type="button" className={locale==="fa"?styles.active:""} onClick={()=>setLocale("fa")}>FA</button><button type="button" className={locale==="en"?styles.active:""} onClick={()=>setLocale("en")}>EN</button></div><small>Theme settings schema v{definition.version}</small></div>
      <div className={styles.groups}>{definition.groups.map(group=><section className={styles.group} key={group.id}><div className={styles.groupHead}><b>{pick(group.fa,group.en)}</b>{(group.descriptionFa||group.descriptionEn)&&<p>{pick(group.descriptionFa||"",group.descriptionEn||"")}</p>}</div><div className={styles.fields}>{group.fields.map(renderField)}</div></section>)}</div>
    </>}
  </section>;
}
