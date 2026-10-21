"use client";

import Link from "next/link";
import {useEffect,useMemo,useState} from "react";
import {useI18n} from "../lib/i18n";
import {STOREFRONT_SECTION_IDS,type StorefrontSectionId} from "../lib/storefront-config";
import {
  ORBIT_DEFAULTS,
  ORBIT_MEDIA_SLOTS,
  ORBIT_SECTION_LABELS,
  ORBIT_TEMPLATE_ID,
  normalizeOrbitThemeDraft,
  type OrbitThemeDraft,
} from "../lib/store-template-orbit-options";
import {
  deleteStoreTemplateMedia,
  loadStoreTemplateSettings,
  resetStoreTemplateSettings,
  saveStoreTemplateSettings,
  uploadStoreTemplateMedia,
} from "../lib/store-template-settings-api";
import styles from "./store-template-orbit-customizer.module.css";

type Tab="design"|"media"|"hero"|"commerce"|"content"|"layout";
type TextField={key:string;fa:string;en:string;long?:boolean};
type ColorField={key:string;fa:string;en:string;fallback:string;helpFa:string;helpEn:string};
type Choice={value:string;fa:string;en:string;descFa:string;descEn:string};

const TABS:{id:Tab;fa:string;en:string;icon:string}[]=[
  {id:"design",fa:"استایل و رنگ",en:"Style & colors",icon:"✦"},
  {id:"media",fa:"تصاویر و بنرها",en:"Media & banners",icon:"▧"},
  {id:"hero",fa:"Hero و بنر",en:"Hero & banner",icon:"01"},
  {id:"commerce",fa:"فروش و پلن‌ها",en:"Commerce",icon:"02"},
  {id:"content",fa:"محتوای بخش‌ها",en:"Content",icon:"03"},
  {id:"layout",fa:"چیدمان",en:"Layout",icon:"04"},
];

const COLORS:ColorField[]=[
  {key:"theme_primary",fa:"Accent اصلی",en:"Primary accent",fallback:"#6d5dfc",helpFa:"رنگ اصلی CTA، Badge و Highlightهای Orbit.",helpEn:"Primary CTA, badge and Orbit highlight color."},
  {key:"theme_secondary",fa:"Accent مکمل",en:"Secondary accent",fallback:"#22d3ee",helpFa:"رنگ دوم برای Gradient، Glow و جزئیات فضایی.",helpEn:"Secondary color used by gradients, glow and spatial details."},
  {key:"orbit_dark_page",fa:"Dark — پس‌زمینه صفحه",en:"Dark — page",fallback:"#05060a",helpFa:"Canvas اصلی در حالت تیره.",helpEn:"Main dark-mode canvas."},
  {key:"orbit_dark_surface",fa:"Dark — سطح کارت",en:"Dark — surface",fallback:"#0c0f16",helpFa:"کارت‌ها و پنل‌های اصلی در Dark Mode.",helpEn:"Primary cards and panels in dark mode."},
  {key:"orbit_dark_surface_alt",fa:"Dark — سطح فرعی",en:"Dark — alternate surface",fallback:"#131824",helpFa:"Hover، Rail و سطح‌های داخلی.",helpEn:"Hover, rails and nested surfaces."},
  {key:"orbit_dark_text",fa:"Dark — متن اصلی",en:"Dark — text",fallback:"#f8fafc",helpFa:"تیتر و متن اصلی در Dark Mode.",helpEn:"Primary dark-mode text."},
  {key:"orbit_dark_muted",fa:"Dark — متن فرعی",en:"Dark — muted",fallback:"#9aa4b5",helpFa:"توضیحات و Metadata در Dark Mode.",helpEn:"Secondary copy and metadata in dark mode."},
  {key:"orbit_dark_border",fa:"Dark — Border",en:"Dark — border",fallback:"#253043",helpFa:"خطوط و جداکننده‌های حالت تیره.",helpEn:"Dark-mode outlines and separators."},
  {key:"orbit_light_page",fa:"Light — پس‌زمینه صفحه",en:"Light — page",fallback:"#f4f6fb",helpFa:"Canvas اصلی در حالت روشن.",helpEn:"Main light-mode canvas."},
  {key:"orbit_light_surface",fa:"Light — سطح کارت",en:"Light — surface",fallback:"#ffffff",helpFa:"کارت‌ها و پنل‌های اصلی در Light Mode.",helpEn:"Primary cards and panels in light mode."},
  {key:"orbit_light_surface_alt",fa:"Light — سطح فرعی",en:"Light — alternate surface",fallback:"#edf1f8",helpFa:"Rail، Hover و سطح‌های داخلی Light Mode.",helpEn:"Rails, hover and nested light-mode surfaces."},
  {key:"orbit_light_text",fa:"Light — متن اصلی",en:"Light — text",fallback:"#10131a",helpFa:"تیترها و متن اصلی در Light Mode.",helpEn:"Primary light-mode text."},
  {key:"orbit_light_muted",fa:"Light — متن فرعی",en:"Light — muted",fallback:"#667085",helpFa:"توضیحات و Metadata در Light Mode.",helpEn:"Secondary copy and metadata in light mode."},
  {key:"orbit_light_border",fa:"Light — Border",en:"Light — border",fallback:"#d9e0ec",helpFa:"خطوط و جداکننده‌های Light Mode.",helpEn:"Light-mode outlines and separators."},
  {key:"orbit_button_text",fa:"متن دکمه اصلی",en:"Primary button text",fallback:"#ffffff",helpFa:"Foreground دکمه‌های اصلی.",helpEn:"Foreground for primary actions."},
];

const HERO_FIELDS:TextField[]=[
  {key:"orbit_banner_title",fa:"متن بنر بالا",en:"Top banner text"},
  {key:"orbit_banner_action",fa:"CTA بنر بالا",en:"Top banner CTA"},
  {key:"hero_kicker",fa:"Kicker بالای Hero",en:"Hero kicker"},
  {key:"hero_title",fa:"عنوان اصلی Hero",en:"Hero headline",long:true},
  {key:"hero_highlight",fa:"Highlight زیر عنوان",en:"Hero highlight",long:true},
  {key:"hero_description",fa:"توضیح Hero",en:"Hero description",long:true},
  {key:"hero_primary_button",fa:"دکمه اصلی Hero",en:"Hero primary CTA"},
  {key:"hero_secondary_button",fa:"دکمه دوم Hero",en:"Hero secondary CTA"},
  {key:"hero_proof_1",fa:"Proof شماره ۱",en:"Proof 1"},
  {key:"hero_proof_2",fa:"Proof شماره ۲",en:"Proof 2"},
  {key:"hero_proof_3",fa:"Proof شماره ۳",en:"Proof 3"},
];

const COMMERCE_FIELDS:TextField[]=[
  {key:"plans_tag",fa:"برچسب پلن‌ها",en:"Plans tag"},
  {key:"plans_title",fa:"عنوان پلن‌ها",en:"Plans title",long:true},
  {key:"plans_description",fa:"توضیح پلن‌ها",en:"Plans description",long:true},
  {key:"plan_feature_1",fa:"مزیت خرید ۱",en:"Plan benefit 1"},
  {key:"plan_feature_2",fa:"مزیت خرید ۲",en:"Plan benefit 2"},
  {key:"plan_feature_3",fa:"مزیت خرید ۳",en:"Plan benefit 3"},
  {key:"protocols_tag",fa:"برچسب پروتکل‌ها",en:"Protocols tag"},
  {key:"protocols_title",fa:"عنوان پروتکل‌ها",en:"Protocols title",long:true},
  {key:"protocols_description",fa:"توضیح پروتکل‌ها",en:"Protocols description",long:true},
];

const CONTENT_FIELDS:TextField[]=[
  {key:"services_tag",fa:"امکانات — برچسب",en:"Features — tag"},{key:"services_title",fa:"امکانات — عنوان",en:"Features — title",long:true},{key:"services_description",fa:"امکانات — توضیح",en:"Features — description",long:true},
  ...[1,2,3,4,5,6].flatMap(index=>[{key:`service_${index}_title`,fa:`امکانات ${index} — عنوان`,en:`Feature ${index} — title`},{key:`service_${index}_description`,fa:`امکانات ${index} — توضیح`,en:`Feature ${index} — description`,long:true}] as TextField[]),
  {key:"guides_tag",fa:"آموزش — برچسب",en:"Guides — tag"},{key:"guides_title",fa:"آموزش — عنوان",en:"Guides — title",long:true},{key:"guides_description",fa:"آموزش — توضیح",en:"Guides — description",long:true},
  {key:"account_tag",fa:"پنل کاربری — برچسب",en:"Account — tag"},{key:"account_title",fa:"پنل کاربری — عنوان",en:"Account — title",long:true},{key:"account_description",fa:"پنل کاربری — توضیح",en:"Account — description",long:true},{key:"account_primary_button",fa:"پنل کاربری — دکمه اصلی",en:"Account — primary CTA"},{key:"account_secondary_button",fa:"پنل کاربری — دکمه پشتیبانی",en:"Account — support CTA"},
  {key:"faq_tag",fa:"FAQ — برچسب",en:"FAQ — tag"},{key:"faq_title",fa:"FAQ — عنوان",en:"FAQ — title",long:true},{key:"faq_description",fa:"FAQ — توضیح",en:"FAQ — description",long:true},
  ...[1,2,3,4,5].flatMap(index=>[{key:`faq_${index}_question`,fa:`FAQ ${index} — سوال`,en:`FAQ ${index} — question`},{key:`faq_${index}_answer`,fa:`FAQ ${index} — جواب`,en:`FAQ ${index} — answer`,long:true}] as TextField[]),
  {key:"final_cta_tag",fa:"CTA نهایی — برچسب",en:"Final CTA — tag"},{key:"final_cta_title",fa:"CTA نهایی — عنوان",en:"Final CTA — title",long:true},{key:"final_cta_description",fa:"CTA نهایی — توضیح",en:"Final CTA — description",long:true},{key:"final_cta_button",fa:"CTA نهایی — دکمه",en:"Final CTA — button"},
  {key:"contact_tag",fa:"ارتباط — برچسب",en:"Contact — tag"},{key:"contact_title",fa:"ارتباط — عنوان",en:"Contact — title",long:true},{key:"contact_description",fa:"ارتباط — توضیح",en:"Contact — description",long:true},{key:"footer_tagline",fa:"متن امضای فوتر",en:"Footer tagline",long:true},{key:"footer_rights",fa:"حقوق فوتر",en:"Footer rights"},
];

const HEADER_CHOICES:Choice[]=[
  {value:"dock",fa:"Dock شناور",en:"Floating dock",descFa:"هدر کپسولی شناور با فضای خالی دو طرف.",descEn:"Pill-shaped floating navigation dock."},
  {value:"full",fa:"تمام‌عرض",en:"Full width",descFa:"هدر تمام‌عرض و مینیمال.",descEn:"Minimal full-width header."},
  {value:"glass",fa:"Glass Layer",en:"Glass layer",descFa:"لایه شیشه‌ای با Blur بیشتر.",descEn:"Higher-blur glass navigation layer."},
];
const PLAN_CHOICES:Choice[]=[
  {value:"tickets",fa:"Ticket Rail",en:"Ticket rail",descFa:"کارت‌های پلن شبیه Ticket با شماره و برش بصری.",descEn:"Numbered ticket-like plan cards."},
  {value:"stack",fa:"Stack",en:"Stack",descFa:"پلن‌ها به‌صورت کارت‌های روی‌هم و متراکم‌تر.",descEn:"Denser stacked plan cards."},
  {value:"panels",fa:"Panels",en:"Panels",descFa:"کارت‌های بزرگ و ساده برای قیمت‌گذاری شفاف.",descEn:"Large clean pricing panels."},
];
const SHAPE_CHOICES:Choice[]=[
  {value:"round",fa:"گرد مدرن",en:"Modern round",descFa:"گوشه‌های نرم و مدرن.",descEn:"Soft modern rounding."},
  {value:"capsule",fa:"کپسولی",en:"Capsule",descFa:"گوشه‌های بسیار گرد و فضایی.",descEn:"Very rounded spatial surfaces."},
  {value:"cut",fa:"برش‌دار",en:"Cut",descFa:"گوشه‌های کوچک‌تر و صنعتی‌تر.",descEn:"Tighter, more industrial geometry."},
];

export function OrbitTemplateCustomizer({onClose}:{onClose:()=>void}){
  const {pick}=useI18n();
  const [tab,setTab]=useState<Tab>("design");
  const [locale,setLocale]=useState<"fa"|"en">("fa");
  const [draft,setDraft]=useState<OrbitThemeDraft>({...ORBIT_DEFAULTS});
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [uploading,setUploading]=useState("");
  const [hasSaved,setHasSaved]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  useEffect(()=>{
    let active=true;
    void loadStoreTemplateSettings().then(envelope=>{
      if(!active)return;
      const raw=envelope.templates?.[ORBIT_TEMPLATE_ID]||{};
      setHasSaved(Object.keys(raw).length>0);
      setDraft(normalizeOrbitThemeDraft(raw));
    }).catch(reason=>active&&setError(reason instanceof Error?reason.message:String(reason))).finally(()=>active&&setLoading(false));
    return()=>{active=false;};
  },[]);

  const localizedKey=(key:string)=>locale==="en"?`${key}_en`:key;
  const textValue=(key:string)=>String(draft[localizedKey(key)]??draft[key]??"");
  const setText=(key:string,value:string)=>setDraft(current=>({...current,[localizedKey(key)]:value}));
  const setValue=(key:string,value:string|boolean|string[])=>setDraft(current=>({...current,[key]:value}));

  const save=async()=>{
    if(busy)return;
    setBusy(true);setError("");setOk("");
    try{
      await saveStoreTemplateSettings(ORBIT_TEMPLATE_ID,draft as unknown as Record<string,unknown>);
      setHasSaved(true);
      setOk(pick("تنظیمات Orbit Neo ذخیره شد.","Orbit Neo settings saved."));
      window.setTimeout(()=>setOk(""),3000);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const reset=async()=>{
    if(busy||!hasSaved)return;
    if(!window.confirm(pick("همه تنظیمات و تصاویر اختصاصی Orbit Neo حذف شوند؟","Remove all Orbit Neo settings and uploaded media?")))return;
    setBusy(true);setError("");setOk("");
    try{
      await Promise.allSettled(ORBIT_MEDIA_SLOTS.map(slot=>deleteStoreTemplateMedia(ORBIT_TEMPLATE_ID,slot.key)));
      await resetStoreTemplateSettings(ORBIT_TEMPLATE_ID);
      setDraft({...ORBIT_DEFAULTS});
      setHasSaved(false);
      setOk(pick("Orbit Neo به تنظیمات اولیه برگشت.","Orbit Neo was reset to defaults."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const upload=async(slot:string,file:File|null)=>{
    if(!file||uploading)return;
    setUploading(slot);setError("");setOk("");
    try{
      const uploaded=await uploadStoreTemplateMedia(ORBIT_TEMPLATE_ID,slot,file);
      setDraft(current=>({...current,[slot]:uploaded.url}));
      setOk(pick("تصویر آپلود شد؛ برای ثبت نهایی «ذخیره قالب» را بزنید.","Image uploaded. Use Save template to persist the reference."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setUploading("");}
  };

  const removeMedia=async(slot:string)=>{
    if(uploading)return;
    setUploading(slot);setError("");
    try{
      await deleteStoreTemplateMedia(ORBIT_TEMPLATE_ID,slot);
      setDraft(current=>({...current,[slot]:""}));
      setOk(pick("تصویر حذف شد؛ تنظیمات قالب را ذخیره کنید.","Image removed. Save the template settings."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setUploading("");}
  };

  const moveSection=(index:number,delta:number)=>{
    const order=Array.isArray(draft.section_order)?[...draft.section_order]:[...STOREFRONT_SECTION_IDS];
    const target=index+delta;
    if(target<0||target>=order.length)return;
    [order[index],order[target]]=[order[target],order[index]];
    setValue("section_order",order);
  };

  const renderTextFields=(fields:TextField[])=>fields.map(field=><label className={styles.field} key={`${locale}-${field.key}`}><span>{pick(field.fa,field.en)}</span>{field.long?<textarea rows={4} value={textValue(field.key)} onChange={event=>setText(field.key,event.target.value)}/>:<input type="text" value={textValue(field.key)} onChange={event=>setText(field.key,event.target.value)}/>}</label>);
  const order=useMemo(()=>Array.isArray(draft.section_order)?draft.section_order.map(String) as StorefrontSectionId[]:[...STOREFRONT_SECTION_IDS],[draft.section_order]);

  if(loading)return <section className={styles.root}><div className={styles.loading}>{pick("در حال بارگذاری Orbit Neo...","Loading Orbit Neo...")}</div></section>;

  return <section className={styles.root}>
    <header className={styles.header}>
      <div><span className={styles.eyebrow}>ORBIT NEO / 2027</span><h1>{pick("ویرایشگر قالب سوم — Orbit Neo","Third theme editor — Orbit Neo")}</h1><p>{pick("قالبی مستقل، تصویرمحور و Spatial با Media Studio داخلی. پلن، قیمت، سفارش و خرید همچنان از Backend واقعی می‌آیند.","An independent, image-led spatial storefront with a built-in Media Studio. Plans, pricing, orders and checkout remain backend-driven.")}</p></div>
      <div className={styles.actions}><button type="button" onClick={onClose}>{pick("بازگشت","Back")}</button><button type="button" onClick={()=>void reset()} disabled={busy||!hasSaved}>{pick("بازنشانی","Reset")}</button><Link href="/store" target="_blank">{pick("مشاهده فروشگاه","Open storefront")} ↗</Link><button type="button" className={styles.primary} disabled={busy} onClick={()=>void save()}>{busy?"…":pick("ذخیره قالب","Save template")}</button></div>
    </header>

    <div className={styles.statusBar}><span className={hasSaved?styles.saved:styles.inherit}>{hasSaved?pick("تنظیمات مستقل فعال","Independent settings active"):pick("تنظیمات پیش‌فرض Orbit Neo","Orbit Neo defaults")}</span><div className={styles.locale}><button type="button" className={locale==="fa"?styles.active:""} onClick={()=>setLocale("fa")}>FA</button><button type="button" className={locale==="en"?styles.active:""} onClick={()=>setLocale("en")}>EN</button></div></div>
    {error&&<div className={styles.error}>{error}</div>}
    {ok&&<div className={styles.success}>{ok}</div>}

    <div className={styles.workspace}>
      <aside className={styles.tabs}>{TABS.map(item=><button type="button" key={item.id} className={tab===item.id?styles.tabActive:""} onClick={()=>setTab(item.id)}><i>{item.icon}</i><span>{pick(item.fa,item.en)}</span></button>)}</aside>
      <main className={styles.panel}>
        {tab==="design"&&<>
          <div className={styles.panelHead}><div><small>VISUAL SYSTEM</small><h2>{pick("هویت بصری مستقل","Independent visual system")}</h2><p>{pick("رنگ‌های Dark و Light جدا هستند تا هیچ حالتی قربانی حالت دیگر نشود.","Dark and Light palettes are independent so neither mode compromises the other.")}</p></div></div>
          <div className={styles.choiceGrid}>
            <ChoiceField title={pick("نوع Header","Header style")} value={String(draft.orbit_header_style||"dock")} choices={HEADER_CHOICES} pick={pick} onChange={value=>setValue("orbit_header_style",value)}/>
            <ChoiceField title={pick("فرم کارت‌ها","Card geometry")} value={String(draft.orbit_card_shape||"round")} choices={SHAPE_CHOICES} pick={pick} onChange={value=>setValue("orbit_card_shape",value)}/>
            <ChoiceField title={pick("نمایش پلن‌ها","Plan presentation")} value={String(draft.orbit_plan_style||"tickets")} choices={PLAN_CHOICES} pick={pick} onChange={value=>setValue("orbit_plan_style",value)}/>
          </div>
          <div className={styles.toggleGrid}><Toggle checked={Boolean(draft.orbit_motion)} label={pick("Motion و حرکت‌های نرم","Motion & micro-interactions")} onChange={value=>setValue("orbit_motion",value)}/><Toggle checked={Boolean(draft.orbit_show_top_banner)} label={pick("بنر بالای Header","Top announcement banner")} onChange={value=>setValue("orbit_show_top_banner",value)}/><Toggle checked={Boolean(draft.orbit_show_metrics)} label={pick("Metricهای شناور Hero","Floating hero metrics")} onChange={value=>setValue("orbit_show_metrics",value)}/><Toggle checked={Boolean(draft.orbit_show_media_labels)} label={pick("Label روی تصاویر","Media labels")} onChange={value=>setValue("orbit_show_media_labels",value)}/></div>
          <div className={styles.colorGrid}>{COLORS.map(field=>{const raw=String(draft[field.key]||field.fallback);const color=/^#[0-9a-fA-F]{6}$/.test(raw)?raw:field.fallback;return <label className={styles.colorField} key={field.key}><div><b>{pick(field.fa,field.en)}</b><small>{pick(field.helpFa,field.helpEn)}</small></div><div className={styles.colorInput}><input type="color" value={color} onChange={event=>setValue(field.key,event.target.value)}/><input dir="ltr" value={raw} onChange={event=>setValue(field.key,event.target.value)}/></div></label>;})}</div>
        </>}

        {tab==="media"&&<>
          <div className={styles.panelHead}><div><small>MEDIA STUDIO</small><h2>{pick("آپلود واقعی تصویر برای تمام نقاط تصویری قالب","Real uploads for every image-led theme area")}</h2><p>{pick("PNG / JPG / WebP تا ۸ مگابایت. تصاویر با Slot ثابت ذخیره می‌شوند و با آپلود مجدد جایگزین می‌شوند.","PNG / JPG / WebP up to 8 MB. Assets use deterministic slots and are replaced on the next upload.")}</p></div></div>
          <div className={styles.mediaGrid}>{ORBIT_MEDIA_SLOTS.map(slot=>{const url=String(draft[slot.key]||"");return <article className={styles.mediaCard} key={slot.key}><div className={styles.mediaPreview}>{url?<img src={url} alt={pick(slot.fa,slot.en)}/>:<div><span>▧</span><b>{pick("هنوز تصویری آپلود نشده","No image uploaded")}</b></div>}</div><div className={styles.mediaMeta}><div><b>{pick(slot.fa,slot.en)}</b><small>{pick(slot.helpFa,slot.helpEn)}</small><em>{slot.aspect}</em></div><div className={styles.mediaActions}><label className={styles.uploadButton}>{uploading===slot.key?"…":pick(url?"جایگزینی":"آپلود تصویر",url?"Replace":"Upload image")}<input type="file" accept="image/png,image/jpeg,image/webp" disabled={Boolean(uploading)} onChange={event=>{const file=event.target.files?.[0]||null;void upload(slot.key,file);event.currentTarget.value="";}}/></label>{url&&<button type="button" disabled={Boolean(uploading)} onClick={()=>void removeMedia(slot.key)}>{pick("حذف","Remove")}</button>}</div></div></article>;})}</div>
        </>}

        {tab==="hero"&&<><div className={styles.panelHead}><div><small>OPENING SCENE</small><h2>{pick("بنر و Hero","Banner & Hero")}</h2><p>{pick("متن‌ها برای FA و EN جدا ذخیره می‌شوند.","FA and EN copy are stored independently.")}</p></div></div><div className={styles.formGrid}>{renderTextFields(HERO_FIELDS)}</div></>}
        {tab==="commerce"&&<><div className={styles.panelHead}><div><small>COMMERCE LAYER</small><h2>{pick("فروش، پلن و پروتکل","Plans, commerce & protocols")}</h2><p>{pick("این متن‌ها فقط Presentation هستند؛ قیمت و مشخصات پلن از Backend می‌آیند.","These fields only control presentation; live plan facts remain backend-driven.")}</p></div></div><div className={styles.formGrid}>{renderTextFields(COMMERCE_FIELDS)}</div></>}
        {tab==="content"&&<><div className={styles.panelHead}><div><small>STORY LAYER</small><h2>{pick("امکانات، آموزش، حساب، FAQ و CTA","Features, guides, account, FAQ & CTA")}</h2></div></div><div className={styles.formGrid}>{renderTextFields(CONTENT_FIELDS)}</div></>}

        {tab==="layout"&&<>
          <div className={styles.panelHead}><div><small>PAGE COMPOSER</small><h2>{pick("نمایش و ترتیب بخش‌ها","Section visibility & ordering")}</h2><p>{pick("Orbit ترتیب خودش را مستقل از دو قالب دیگر ذخیره می‌کند.","Orbit stores its own section order independently of the other themes.")}</p></div></div>
          <div className={styles.toggleGrid}>{STOREFRONT_SECTION_IDS.map(section=><Toggle key={section} checked={Boolean(draft[`show_${section}`])} label={pick(`نمایش ${ORBIT_SECTION_LABELS[section].fa}`,`Show ${ORBIT_SECTION_LABELS[section].en}`)} onChange={value=>setValue(`show_${section}`,value)}/>)}</div>
          <div className={styles.orderList}>{order.map((section,index)=><div className={styles.orderRow} key={section}><span>{String(index+1).padStart(2,"0")}</span><b>{pick(ORBIT_SECTION_LABELS[section].fa,ORBIT_SECTION_LABELS[section].en)}</b><div><button type="button" disabled={index===0} onClick={()=>moveSection(index,-1)}>↑</button><button type="button" disabled={index===order.length-1} onClick={()=>moveSection(index,1)}>↓</button></div></div>)}</div>
          <div className={styles.toggleGrid}><Toggle checked={Boolean(draft.show_final_cta)} label={pick("نمایش CTA نهایی","Show final CTA")} onChange={value=>setValue("show_final_cta",value)}/><Toggle checked={Boolean(draft.show_contact)} label={pick("نمایش ارتباط و فوتر","Show contact & footer")} onChange={value=>setValue("show_contact",value)}/></div>
        </>}
      </main>
    </div>
  </section>;
}

function ChoiceField({title,value,choices,pick,onChange}:{title:string;value:string;choices:Choice[];pick:(fa:string,en:string)=>string;onChange:(value:string)=>void}){
  return <div className={styles.choiceField}><b>{title}</b><div>{choices.map(choice=><button type="button" key={choice.value} className={value===choice.value?styles.choiceActive:""} onClick={()=>onChange(choice.value)}><strong>{pick(choice.fa,choice.en)}</strong><small>{pick(choice.descFa,choice.descEn)}</small></button>)}</div></div>;
}

function Toggle({checked,label,onChange}:{checked:boolean;label:string;onChange:(value:boolean)=>void}){
  return <label className={styles.toggle}><span>{label}</span><input type="checkbox" checked={checked} onChange={event=>onChange(event.target.checked)}/><i/></label>;
}
