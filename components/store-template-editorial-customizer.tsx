"use client";

import Link from "next/link";
import {useEffect,useMemo,useState} from "react";
import {useI18n} from "../lib/i18n";
import {
  loadStoreTemplateSettings,
  resetStoreTemplateSettings,
  saveStoreTemplateSettings,
} from "../lib/store-template-settings-api";
import {STOREFRONT_SECTION_IDS,type StorefrontSectionId} from "../lib/storefront-config";
import styles from "./store-template-editorial-customizer.module.css";

type DraftValue=string|boolean|string[];
type Draft=Record<string,DraftValue>;
type Tab="design"|"hero"|"sales"|"content"|"layout";

type TextField={key:string;fa:string;en:string;long?:boolean};

type Choice={value:string;fa:string;en:string;descFa:string;descEn:string};

const EDITORIAL_DEFAULTS:Draft={
  theme_primary:"#8b5cf6",
  theme_secondary:"#6366f1",
  editorial_density:"balanced",
  editorial_hero_layout:"split",
  editorial_plan_layout:"spotlight",
  editorial_corner_style:"soft",
  editorial_header_style:"floating",
  editorial_show_status_board:true,
  editorial_show_trust_strip:true,
  editorial_show_section_numbers:true,
  editorial_show_plan_benefits:true,
  editorial_show_protocol_marks:true,
  editorial_show_guide_screenshots:true,
  editorial_status_label:"وضعیت شبکه",
  editorial_status_value:"ONLINE",
  editorial_delivery_label:"تحویل سرویس",
  editorial_delivery_value:"داخل پنل کاربری",
  editorial_recommended_label:"انتخاب پیشنهادی",
  editorial_protocol_available_label:"آماده استفاده",
  hero_kicker:"PRIVATE ACCESS / 2027",
  hero_title:"یک تجربه خرید دقیق برای اتصال حرفه‌ای،",
  hero_highlight:"ساده‌تر از همیشه.",
  hero_description:"پلن مناسب را سریع پیدا کنید، روش اتصال سازگار با دستگاهتان را ببینید و بعد از خرید همه‌چیز را از یک حساب مدیریت کنید.",
  hero_primary_button:"مشاهده پلن‌ها",
  hero_secondary_button:"راهنمای اتصال",
  hero_proof_1:"تحویل سریع",
  hero_proof_2:"چند روش اتصال",
  hero_proof_3:"مدیریت یکپارچه",
  plans_tag:"01 / SELECT",
  plans_title:"پلنی که واقعاً با مصرف شما هماهنگ است.",
  plans_description:"قیمت، حجم، مدت و محدودیت دستگاه را شفاف مقایسه کنید و بدون مراحل اضافی خرید را انجام دهید.",
  plan_feature_1:"تحویل اطلاعات اتصال داخل حساب",
  plan_feature_2:"نمایش پروتکل‌های فعال همان پلن",
  plan_feature_3:"پیگیری سفارش تا فعال‌سازی",
  protocols_tag:"02 / CONNECT",
  protocols_title:"برای هر شبکه، مسیر اتصال مناسب.",
  protocols_description:"روش‌های اتصال مختلف را بر اساس دستگاه و شرایط شبکه انتخاب کنید؛ بدون اینکه سرویس جداگانه بخرید.",
  services_tag:"03 / EXPERIENCE",
  services_title:"فروشگاه فقط نقطه خرید نیست؛ شروع مدیریت سرویس است.",
  services_description:"از پرداخت تا دریافت اطلاعات اتصال و پشتیبانی، همه‌چیز در یک مسیر روشن باقی می‌ماند.",
  guides_tag:"04 / GUIDE",
  guides_title:"از انتخاب دستگاه تا اتصال نهایی، مرحله‌به‌مرحله.",
  guides_description:"راهنمای متناسب با سیستم‌عامل و پروتکل را انتخاب کنید و مراحل واقعی را همان‌جا ببینید.",
  account_tag:"05 / ACCOUNT",
  account_title:"بعد از خرید، کنترل سرویس دست خودتان می‌ماند.",
  account_description:"اشتراک، حجم، پرداخت‌ها و اطلاعات اتصال را از یک پنل واحد مدیریت کنید.",
  account_primary_button:"ورود به حساب",
  account_secondary_button:"پشتیبانی آنلاین",
  faq_tag:"06 / FAQ",
  faq_title:"قبل از تصمیم، جواب سوال‌های مهم را ببینید.",
  faq_description:"اطلاعات کوتاه و کاربردی برای خرید، دستگاه‌ها، حجم، پروتکل‌ها و راه‌اندازی.",
  final_cta_tag:"READY WHEN YOU ARE",
  final_cta_title:"پلن را انتخاب کنید؛ ادامه مسیر داخل حساب شماست.",
  final_cta_description:"خرید را کامل کنید و وضعیت سفارش، سرویس و اطلاعات اتصال را از پنل دنبال کنید.",
  final_cta_button:"انتخاب پلن",
  contact_tag:"CONTACT",
  contact_title:"برای سوال‌های قبل و بعد از خرید، مستقیم در دسترسیم.",
  contact_description:"از کانال‌های فعال یا چت آنلاین برای پشتیبانی و راهنمایی استفاده کنید.",
  footer_tagline:"Premium connectivity, structured around clarity.",
  show_plans:true,
  show_protocols:true,
  show_services:true,
  show_guides:true,
  show_account:true,
  show_faq:true,
  show_final_cta:true,
  show_contact:true,
  section_order:[...STOREFRONT_SECTION_IDS],
};

const TABS:{id:Tab;fa:string;en:string;icon:string}[]=[
  {id:"design",fa:"هویت بصری",en:"Art direction",icon:"◫"},
  {id:"hero",fa:"شروع صفحه",en:"Hero",icon:"01"},
  {id:"sales",fa:"فروش و پلن",en:"Commerce",icon:"02"},
  {id:"content",fa:"محتوای صفحه",en:"Content",icon:"03"},
  {id:"layout",fa:"چیدمان",en:"Layout",icon:"04"},
];

const SECTION_LABELS:Record<StorefrontSectionId,{fa:string;en:string}>={
  plans:{fa:"پلن‌ها",en:"Plans"},
  protocols:{fa:"روش‌های اتصال",en:"Protocols"},
  services:{fa:"تجربه و خدمات",en:"Experience"},
  guides:{fa:"راهنمای اتصال",en:"Guides"},
  account:{fa:"حساب کاربری",en:"Account"},
  faq:{fa:"سوالات متداول",en:"FAQ"},
};

const HERO_FIELDS:TextField[]=[
  {key:"hero_kicker",fa:"برچسب بالای Hero",en:"Hero eyebrow"},
  {key:"hero_title",fa:"تیتر اصلی",en:"Main headline"},
  {key:"hero_highlight",fa:"بخش برجسته تیتر",en:"Highlighted phrase"},
  {key:"hero_description",fa:"توضیح Hero",en:"Hero description",long:true},
  {key:"hero_primary_button",fa:"دکمه اصلی",en:"Primary CTA"},
  {key:"hero_secondary_button",fa:"دکمه دوم",en:"Secondary CTA"},
  {key:"hero_proof_1",fa:"اعتماد ۱",en:"Proof 1"},
  {key:"hero_proof_2",fa:"اعتماد ۲",en:"Proof 2"},
  {key:"hero_proof_3",fa:"اعتماد ۳",en:"Proof 3"},
];

const SALES_FIELDS:TextField[]=[
  {key:"plans_tag",fa:"برچسب بخش پلن‌ها",en:"Plans tag"},
  {key:"plans_title",fa:"عنوان بخش پلن‌ها",en:"Plans headline"},
  {key:"plans_description",fa:"توضیح بخش پلن‌ها",en:"Plans description",long:true},
  {key:"plan_feature_1",fa:"مزیت خرید ۱",en:"Purchase benefit 1"},
  {key:"plan_feature_2",fa:"مزیت خرید ۲",en:"Purchase benefit 2"},
  {key:"plan_feature_3",fa:"مزیت خرید ۳",en:"Purchase benefit 3"},
  {key:"editorial_recommended_label",fa:"متن نشان پیشنهادی",en:"Recommended badge"},
];

const CONTENT_FIELDS:TextField[]=[
  {key:"protocols_tag",fa:"پروتکل‌ها — برچسب",en:"Protocols — tag"},
  {key:"protocols_title",fa:"پروتکل‌ها — عنوان",en:"Protocols — title"},
  {key:"protocols_description",fa:"پروتکل‌ها — توضیح",en:"Protocols — description",long:true},
  {key:"editorial_protocol_available_label",fa:"وضعیت هر پروتکل",en:"Protocol availability label"},
  {key:"services_tag",fa:"تجربه — برچسب",en:"Experience — tag"},
  {key:"services_title",fa:"تجربه — عنوان",en:"Experience — title"},
  {key:"services_description",fa:"تجربه — توضیح",en:"Experience — description",long:true},
  {key:"guides_tag",fa:"آموزش — برچسب",en:"Guides — tag"},
  {key:"guides_title",fa:"آموزش — عنوان",en:"Guides — title"},
  {key:"guides_description",fa:"آموزش — توضیح",en:"Guides — description",long:true},
  {key:"account_tag",fa:"حساب — برچسب",en:"Account — tag"},
  {key:"account_title",fa:"حساب — عنوان",en:"Account — title"},
  {key:"account_description",fa:"حساب — توضیح",en:"Account — description",long:true},
  {key:"account_primary_button",fa:"حساب — دکمه اصلی",en:"Account — primary CTA"},
  {key:"account_secondary_button",fa:"حساب — دکمه پشتیبانی",en:"Account — support CTA"},
  {key:"faq_tag",fa:"FAQ — برچسب",en:"FAQ — tag"},
  {key:"faq_title",fa:"FAQ — عنوان",en:"FAQ — title"},
  {key:"faq_description",fa:"FAQ — توضیح",en:"FAQ — description",long:true},
  {key:"final_cta_tag",fa:"CTA نهایی — برچسب",en:"Final CTA — tag"},
  {key:"final_cta_title",fa:"CTA نهایی — عنوان",en:"Final CTA — title"},
  {key:"final_cta_description",fa:"CTA نهایی — توضیح",en:"Final CTA — description",long:true},
  {key:"final_cta_button",fa:"CTA نهایی — دکمه",en:"Final CTA — button"},
  {key:"contact_tag",fa:"ارتباط — برچسب",en:"Contact — tag"},
  {key:"contact_title",fa:"ارتباط — عنوان",en:"Contact — title"},
  {key:"contact_description",fa:"ارتباط — توضیح",en:"Contact — description",long:true},
  {key:"footer_tagline",fa:"توضیح کوتاه فوتر",en:"Footer tagline",long:true},
];

const CHOICES:Record<string,Choice[]>={
  editorial_density:[
    {value:"compact",fa:"فشرده",en:"Compact",descFa:"فاصله کمتر و تمرکز بیشتر روی فروش",descEn:"Tighter spacing and faster scanning"},
    {value:"balanced",fa:"متعادل",en:"Balanced",descFa:"تعادل بین فضای سفید و تراکم محتوا",descEn:"Balanced whitespace and density"},
    {value:"airy",fa:"لوکس",en:"Airy",descFa:"فضای سفید بیشتر برای حس مجله‌ای",descEn:"More whitespace for a luxury editorial feel"},
  ],
  editorial_hero_layout:[
    {value:"split",fa:"دو بخشی",en:"Split",descFa:"تیتر و داشبورد وضعیت کنار هم",descEn:"Headline with a live status board"},
    {value:"statement",fa:"تیتر محوری",en:"Statement",descFa:"تیتر بزرگ با داشبورد کوچک‌تر زیر آن",descEn:"Large headline with compact metrics"},
    {value:"compact",fa:"فروش‌محور",en:"Commerce",descFa:"Hero کوتاه‌تر برای رسیدن سریع‌تر به پلن‌ها",descEn:"Shorter hero that reaches plans faster"},
  ],
  editorial_plan_layout:[
    {value:"spotlight",fa:"Spotlight",en:"Spotlight",descFa:"پلن پیشنهادی با تمرکز بصری بیشتر",descEn:"Strong visual emphasis on the recommended plan"},
    {value:"equal",fa:"کارت‌های برابر",en:"Equal cards",descFa:"همه پلن‌ها با وزن بصری یکسان",descEn:"All plans get equal visual weight"},
    {value:"list",fa:"لیست مقایسه‌ای",en:"Comparison list",descFa:"خواندن سریع‌تر در تعداد پلن بالا",descEn:"Faster scanning for larger plan catalogs"},
  ],
  editorial_corner_style:[
    {value:"sharp",fa:"تیز",en:"Sharp",descFa:"ساختاری و ادیتوریال",descEn:"Strict editorial geometry"},
    {value:"soft",fa:"نرم",en:"Soft",descFa:"مدرن و کاربرپسند",descEn:"Modern and approachable"},
    {value:"round",fa:"گرد",en:"Rounded",descFa:"دوستانه‌تر برای فروشگاه عمومی",descEn:"Friendlier consumer storefront"},
  ],
  editorial_header_style:[
    {value:"line",fa:"خطی",en:"Line",descFa:"هدر تخت و مینیمال",descEn:"Flat minimal header"},
    {value:"floating",fa:"شناور",en:"Floating",descFa:"هدر مدرن با سطح مستقل",descEn:"Modern elevated navigation surface"},
    {value:"compact",fa:"فشرده",en:"Compact",descFa:"ارتفاع کمتر و فضای بیشتر برای محتوا",descEn:"Shorter navigation for more content space"},
  ],
};

function localizedKey(key:string,locale:"fa"|"en"){
  return locale==="en"?`${key}_en`:key;
}

export function EditorialTemplateCustomizer({onClose}:{onClose:()=>void}){
  const {pick}=useI18n();
  const [tab,setTab]=useState<Tab>("design");
  const [locale,setLocale]=useState<"fa"|"en">("fa");
  const [draft,setDraft]=useState<Draft>(EDITORIAL_DEFAULTS);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [saved,setSaved]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  useEffect(()=>{
    let active=true;
    void loadStoreTemplateSettings().then(envelope=>{
      if(!active)return;
      const raw=envelope.templates?.["editorial-grid-2027"]||{};
      setSaved(Object.keys(raw).length>0);
      setDraft({...EDITORIAL_DEFAULTS,...raw} as Draft);
    }).catch(reason=>{
      if(active)setError(reason instanceof Error?reason.message:String(reason));
    }).finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;};
  },[]);

  const value=(key:string)=>draft[localizedKey(key,locale)]??draft[key]??"";
  const setText=(key:string,next:string)=>setDraft(current=>({...current,[localizedKey(key,locale)]:next}));
  const setValue=(key:string,next:DraftValue)=>setDraft(current=>({...current,[key]:next}));

  const save=async()=>{
    if(busy)return;
    setBusy(true);setError("");setOk("");
    try{
      await saveStoreTemplateSettings("editorial-grid-2027",draft as unknown as Record<string,unknown>);
      setSaved(true);
      setOk(pick("تنظیمات اختصاصی Editorial Pro ذخیره شد.","Editorial Pro settings saved."));
      window.setTimeout(()=>setOk(""),3000);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const restoreDefaults=()=>{
    if(!window.confirm(pick("طراحی Editorial Pro به تنظیمات حرفه‌ای پیش‌فرض برگردد؟ هنوز برای اعمال باید ذخیره کنید.","Restore the professional Editorial Pro defaults? You will still need to save.")))return;
    setDraft(EDITORIAL_DEFAULTS);
    setOk(pick("پیش‌فرض حرفه‌ای بارگذاری شد؛ برای اعمال، ذخیره کنید.","Professional defaults loaded; save to apply."));
  };

  const inheritShared=async()=>{
    if(!saved||busy)return;
    if(!window.confirm(pick("تنظیمات اختصاصی این قالب حذف شود و دوباره از تنظیمات عمومی ارث‌بری کند؟","Remove this theme's independent settings and inherit shared storefront values again?")))return;
    setBusy(true);setError("");setOk("");
    try{
      await resetStoreTemplateSettings("editorial-grid-2027");
      setDraft(EDITORIAL_DEFAULTS);
      setSaved(false);
      setOk(pick("شخصی‌سازی مستقل حذف شد.","Independent customization removed."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const renderTextFields=(fields:TextField[])=><div className={styles.grid2}>{fields.map(field=><label key={`${locale}-${field.key}`} className={`${styles.field} ${field.long?styles.wide:""}`}><span>{pick(field.fa,field.en)}</span>{field.long?<textarea rows={4} value={String(value(field.key))} onChange={event=>setText(field.key,event.target.value)}/>:<input type="text" value={String(value(field.key))} onChange={event=>setText(field.key,event.target.value)}/>}</label>)}</div>;

  const renderChoices=(key:string)=><div className={styles.choices}>{CHOICES[key].map(choice=><button type="button" key={choice.value} className={`${styles.choice} ${draft[key]===choice.value?styles.active:""}`} onClick={()=>setValue(key,choice.value)}><b>{pick(choice.fa,choice.en)}</b><small>{pick(choice.descFa,choice.descEn)}</small></button>)}</div>;

  const sectionOrder=useMemo(()=>Array.isArray(draft.section_order)?draft.section_order.map(String) as StorefrontSectionId[]:[...STOREFRONT_SECTION_IDS],[draft.section_order]);
  const moveSection=(index:number,delta:number)=>{
    const order=[...sectionOrder];const target=index+delta;
    if(target<0||target>=order.length)return;
    [order[index],order[target]]=[order[target],order[index]];
    setValue("section_order",order);
  };

  return <div className={styles.root}>
    <div className={styles.topbar}>
      <div className={styles.identity}><span className={styles.mark}>ED</span><div><h1>{pick("Editorial Pro 2027","Editorial Pro 2027")}</h1><p>{pick("ویرایشگر اختصاصی قالب دوم — مستقل از Conversion 2027","A dedicated editor for the second theme — independent from Conversion 2027")}</p></div></div>
      <div className={styles.actions}><button type="button" onClick={onClose}>{pick("بازگشت","Back")}</button><Link href="/store" target="_blank">{pick("مشاهده فروشگاه","Open storefront")} ↗</Link><button type="button" className={styles.primary} onClick={()=>void save()} disabled={busy}>{busy?"…":pick("ذخیره Editorial Pro","Save Editorial Pro")}</button></div>
    </div>

    <div className={styles.notice}>{pick("این قالب دیگر از همان مدل تنظیمات قالب اول استفاده نمی‌کند. کنترل‌های زیر مخصوص ساختار ادیتوریال، تراکم صفحه، Hero، نحوه نمایش پلن‌ها و تجربه راهنما هستند. داده‌های تجاری مثل قیمت و حجم همچنان زنده از Backend می‌آیند.","This theme no longer uses the same editing model as the first theme. These controls are specific to its editorial composition, density, hero, plan presentation and guide experience. Live commerce data still comes from the backend.")}</div>
    {error&&<div className={styles.error}>{error}</div>}
    {ok&&<div className={styles.success}>{ok}</div>}

    {loading?<div className={styles.panel}><div className={styles.loading}>{pick("در حال دریافت تنظیمات Editorial Pro...","Loading Editorial Pro settings...")}</div></div>:<div className={styles.workspace}>
      <aside className={styles.sidebar}><small>{pick("تنظیمات اختصاصی قالب","Theme-specific controls")}</small>{TABS.map(item=><button type="button" key={item.id} className={tab===item.id?styles.active:""} onClick={()=>setTab(item.id)}><span>{item.icon}</span>{pick(item.fa,item.en)}</button>)}</aside>

      <section className={styles.panel}>
        <div className={styles.panelHead}><div><h2>{pick(TABS.find(item=>item.id===tab)?.fa||"",TABS.find(item=>item.id===tab)?.en||"")}</h2><p>{tab==="design"?pick("حس کلی قالب را بدون دست‌زدن به قالب اول تنظیم کنید.","Tune the visual character without touching the first theme."):tab==="hero"?pick("شروع صفحه را برای خوانایی و تبدیل بهتر کنترل کنید.","Control the opening composition for clarity and conversion."):tab==="sales"?pick("نمایش پلن‌ها و پیام‌های خرید را برای تصمیم‌گیری سریع‌تر تنظیم کنید.","Tune plan presentation and purchase messaging for faster decisions."):tab==="content"?pick("متن‌های کلیدی قالب دوم را مستقل از قالب اول مدیریت کنید.","Manage the second theme's key copy independently."):pick("ترتیب و اجزای صفحه را متناسب با این قالب تنظیم کنید.","Control page order and editorial modules for this theme.")}</p></div>{tab!=="design"&&tab!=="layout"?<div className={styles.locale}><button type="button" className={locale==="fa"?styles.active:""} onClick={()=>setLocale("fa")}>FA</button><button type="button" className={locale==="en"?styles.active:""} onClick={()=>setLocale("en")}>EN</button></div>:null}</div>

        <div className={styles.body}>
          {tab==="design"&&<>
            <div className={styles.section}><div className={styles.sectionHead}><b>{pick("پالت و شخصیت بصری","Palette & visual character")}</b><p>{pick("این رنگ‌ها فقط روی Editorial Pro اعمال می‌شوند.","These colors apply only to Editorial Pro.")}</p></div><div className={styles.grid2}><label className={styles.field}><span>{pick("رنگ Accent اصلی","Primary accent")}</span><div className={styles.colorRow}><input type="color" value={String(draft.theme_primary||"#8b5cf6")} onChange={e=>setValue("theme_primary",e.target.value)}/><input type="text" dir="ltr" value={String(draft.theme_primary||"")} onChange={e=>setValue("theme_primary",e.target.value)}/></div></label><label className={styles.field}><span>{pick("رنگ Accent دوم","Secondary accent")}</span><div className={styles.colorRow}><input type="color" value={String(draft.theme_secondary||"#6366f1")} onChange={e=>setValue("theme_secondary",e.target.value)}/><input type="text" dir="ltr" value={String(draft.theme_secondary||"")} onChange={e=>setValue("theme_secondary",e.target.value)}/></div></label></div></div>
            <div className={styles.section}><div className={styles.sectionHead}><b>{pick("تراکم صفحه","Page density")}</b></div>{renderChoices("editorial_density")}</div>
            <div className={styles.section}><div className={styles.sectionHead}><b>{pick("فرم گوشه‌ها","Corner language")}</b></div>{renderChoices("editorial_corner_style")}</div>
            <div className={styles.section}><div className={styles.sectionHead}><b>{pick("سبک هدر","Header treatment")}</b></div>{renderChoices("editorial_header_style")}</div>
          </>}

          {tab==="hero"&&<>
            <div className={styles.section}><div className={styles.sectionHead}><b>{pick("ترکیب Hero","Hero composition")}</b></div>{renderChoices("editorial_hero_layout")}</div>
            <div className={styles.section}><div className={styles.sectionHead}><b>{pick("داشبورد وضعیت","Status board")}</b></div><div className={styles.toggles}><label className={styles.toggle}><span>{pick("نمایش داشبورد وضعیت","Show status board")}</span><input type="checkbox" checked={Boolean(draft.editorial_show_status_board)} onChange={e=>setValue("editorial_show_status_board",e.target.checked)}/></label><label className={styles.toggle}><span>{pick("نمایش نوار اعتماد زیر Hero","Show trust strip")}</span><input type="checkbox" checked={Boolean(draft.editorial_show_trust_strip)} onChange={e=>setValue("editorial_show_trust_strip",e.target.checked)}/></label></div><div className={`${styles.grid2}`} style={{marginTop:12}}><label className={styles.field}><span>{pick("عنوان وضعیت","Status label")}</span><input type="text" value={String(value("editorial_status_label"))} onChange={e=>setText("editorial_status_label",e.target.value)}/></label><label className={styles.field}><span>{pick("مقدار وضعیت","Status value")}</span><input type="text" value={String(value("editorial_status_value"))} onChange={e=>setText("editorial_status_value",e.target.value)}/></label><label className={styles.field}><span>{pick("عنوان تحویل","Delivery label")}</span><input type="text" value={String(value("editorial_delivery_label"))} onChange={e=>setText("editorial_delivery_label",e.target.value)}/></label><label className={styles.field}><span>{pick("مقدار تحویل","Delivery value")}</span><input type="text" value={String(value("editorial_delivery_value"))} onChange={e=>setText("editorial_delivery_value",e.target.value)}/></label></div></div>
            <div className={styles.section}><div className={styles.sectionHead}><b>{pick("متن Hero","Hero copy")}</b></div>{renderTextFields(HERO_FIELDS)}</div>
          </>}

          {tab==="sales"&&<>
            <div className={styles.section}><div className={styles.sectionHead}><b>{pick("نحوه نمایش پلن‌ها","Plan presentation")}</b><p>{pick("این انتخاب فقط ظاهر فروش را تغییر می‌دهد؛ قیمت و مشخصات از Backend می‌آیند.","This changes presentation only; price and plan facts still come from the backend.")}</p></div>{renderChoices("editorial_plan_layout")}</div>
            <div className={styles.section}><div className={styles.sectionHead}><b>{pick("جزئیات فروش","Commerce details")}</b></div><div className={styles.toggles}><label className={styles.toggle}><span>{pick("نمایش مزیت‌های خرید داخل کارت","Show benefits in plan cards")}</span><input type="checkbox" checked={Boolean(draft.editorial_show_plan_benefits)} onChange={e=>setValue("editorial_show_plan_benefits",e.target.checked)}/></label><label className={styles.toggle}><span>{pick("نمایش نشان پروتکل‌ها","Show protocol marks")}</span><input type="checkbox" checked={Boolean(draft.editorial_show_protocol_marks)} onChange={e=>setValue("editorial_show_protocol_marks",e.target.checked)}/></label></div></div>
            <div className={styles.section}><div className={styles.sectionHead}><b>{pick("پیام‌های فروش","Sales copy")}</b></div>{renderTextFields(SALES_FIELDS)}</div>
          </>}

          {tab==="content"&&<div className={styles.section}><div className={styles.sectionHead}><b>{pick("متن‌های کلیدی Editorial Pro","Editorial Pro copy")}</b><p>{pick("فقط متن‌هایی که در ساختار این قالب اهمیت دارند اینجا نگه داشته شده‌اند؛ قالب اول ویرایش نمی‌شود.","Only copy that matters to this editorial composition is exposed here; the first theme is untouched.")}</p></div>{renderTextFields(CONTENT_FIELDS)}</div>}

          {tab==="layout"&&<>
            <div className={styles.section}><div className={styles.sectionHead}><b>{pick("اجزای ادیتوریال","Editorial modules")}</b></div><div className={styles.toggles}><label className={styles.toggle}><span>{pick("شماره‌گذاری سکشن‌ها","Section numbering")}</span><input type="checkbox" checked={Boolean(draft.editorial_show_section_numbers)} onChange={e=>setValue("editorial_show_section_numbers",e.target.checked)}/></label><label className={styles.toggle}><span>{pick("تصاویر مراحل آموزش","Guide screenshots")}</span><input type="checkbox" checked={Boolean(draft.editorial_show_guide_screenshots)} onChange={e=>setValue("editorial_show_guide_screenshots",e.target.checked)}/></label></div></div>
            <div className={styles.section}><div className={styles.sectionHead}><b>{pick("نمایش بخش‌ها","Section visibility")}</b></div><div className={styles.toggles}>{STOREFRONT_SECTION_IDS.map(section=><label className={styles.toggle} key={section}><span>{pick(SECTION_LABELS[section].fa,SECTION_LABELS[section].en)}</span><input type="checkbox" checked={Boolean(draft[`show_${section}`])} onChange={e=>setValue(`show_${section}`,e.target.checked)}/></label>)}<label className={styles.toggle}><span>{pick("CTA نهایی","Final CTA")}</span><input type="checkbox" checked={Boolean(draft.show_final_cta)} onChange={e=>setValue("show_final_cta",e.target.checked)}/></label><label className={styles.toggle}><span>{pick("بخش ارتباط","Contact section")}</span><input type="checkbox" checked={Boolean(draft.show_contact)} onChange={e=>setValue("show_contact",e.target.checked)}/></label></div></div>
            <div className={styles.section}><div className={styles.sectionHead}><b>{pick("ترتیب بخش‌ها","Section order")}</b></div><div className={styles.order}>{sectionOrder.map((section,index)=><div className={styles.orderRow} key={section}><span>{index+1}</span><b>{pick(SECTION_LABELS[section].fa,SECTION_LABELS[section].en)}</b><div className={styles.orderActions}><button type="button" disabled={index===0} onClick={()=>moveSection(index,-1)}>↑</button><button type="button" disabled={index===sectionOrder.length-1} onClick={()=>moveSection(index,1)}>↓</button></div></div>)}</div></div>
          </>}
        </div>

        <div className={styles.footerBar}><small>{saved?pick("این قالب تنظیمات مستقل ذخیره‌شده دارد.","This theme has saved independent settings."):pick("هنوز تنظیمات مستقل ذخیره نشده؛ ذخیره، Editorial Pro را از قالب اول جدا می‌کند.","No independent settings are saved yet; saving separates Editorial Pro from the first theme.")}</small><div><button type="button" onClick={restoreDefaults}>{pick("پیش‌فرض حرفه‌ای","Professional defaults")}</button><button type="button" onClick={()=>void inheritShared()} disabled={!saved||busy}>{pick("حذف شخصی‌سازی","Remove customization")}</button><button type="button" className={styles.primary} onClick={()=>void save()} disabled={busy}>{pick("ذخیره","Save")}</button></div></div>
      </section>
    </div>}
  </div>;
}
