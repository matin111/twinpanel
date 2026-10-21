"use client";

import Link from "next/link";
import {useEffect,useMemo,useState} from "react";
import {useI18n} from "../lib/i18n";
import {parityApi} from "../lib/admin-parity-api";
import {normalizeStorefrontSettings,STOREFRONT_SECTION_IDS,type StorefrontSectionId} from "../lib/storefront-config";
import {loadStoreTemplateSettings,saveStoreTemplateSettings} from "../lib/store-template-settings-api";
import styles from "./store-template-conversion-customizer.module.css";

type DraftValue=string|boolean|string[];
type Draft=Record<string,DraftValue>;
type Tab="colors"|"style"|"hero"|"content"|"layout";
type TextField={key:string;fa:string;en:string;long?:boolean};

type Palette={
  id:string;
  fa:string;
  en:string;
  accent:string;
  accent2:string;
  page:string;
  section:string;
  card:string;
  border:string;
  header:string;
  headerText:string;
  button:string;
  buttonText:string;
  text:string;
  muted:string;
};

const DESIGN_DEFAULTS:Draft={
  conversion_accent:"#8b5cf6",
  conversion_accent_2:"#6d28d9",
  conversion_page_bg:"#060915",
  conversion_section_bg:"#0b1020",
  conversion_card_bg:"#0f1526",
  conversion_card_border:"#202b42",
  conversion_header_bg:"#080c18",
  conversion_header_text:"#f7f8ff",
  conversion_button_bg:"#7c3aed",
  conversion_button_text:"#ffffff",
  conversion_text:"#f7f8ff",
  conversion_muted:"#9aa7bf",
  conversion_density:"balanced",
  conversion_header_style:"glass",
  conversion_button_style:"gradient",
  conversion_card_style:"glass",
  conversion_corner_style:"soft",
  conversion_glow:"soft",
  conversion_show_hero_visual:true,
};

const PALETTES:Palette[]=[
  {id:"violet",fa:"ویولت",en:"Violet",accent:"#8b5cf6",accent2:"#6d28d9",page:"#060915",section:"#0b1020",card:"#0f1526",border:"#202b42",header:"#080c18",headerText:"#f7f8ff",button:"#7c3aed",buttonText:"#ffffff",text:"#f7f8ff",muted:"#9aa7bf"},
  {id:"ocean",fa:"اقیانوسی",en:"Ocean",accent:"#38bdf8",accent2:"#2563eb",page:"#051018",section:"#081923",card:"#0b202b",border:"#18394a",header:"#06131c",headerText:"#eefaff",button:"#0284c7",buttonText:"#ffffff",text:"#f1fbff",muted:"#8fb4c5"},
  {id:"emerald",fa:"زمردی",en:"Emerald",accent:"#34d399",accent2:"#059669",page:"#04100d",section:"#071914",card:"#0b211b",border:"#183a30",header:"#061510",headerText:"#effdf7",button:"#059669",buttonText:"#ffffff",text:"#effdf7",muted:"#91b8a9"},
  {id:"sunset",fa:"غروب",en:"Sunset",accent:"#fb7185",accent2:"#f97316",page:"#13080b",section:"#1b0d10",card:"#241116",border:"#4a242d",header:"#16090d",headerText:"#fff4f5",button:"#e11d48",buttonText:"#ffffff",text:"#fff4f5",muted:"#c3a0a6"},
  {id:"mono",fa:"مینیمال",en:"Monochrome",accent:"#e5e7eb",accent2:"#9ca3af",page:"#08090b",section:"#101114",card:"#16181c",border:"#30333a",header:"#0b0c0f",headerText:"#f9fafb",button:"#f3f4f6",buttonText:"#111318",text:"#f9fafb",muted:"#a4a8b1"},
];

const TABS:{id:Tab;fa:string;en:string;icon:string}[]=[
  {id:"colors",fa:"رنگ‌ها",en:"Colors",icon:"◉"},
  {id:"style",fa:"استایل",en:"Style",icon:"◇"},
  {id:"hero",fa:"Hero",en:"Hero",icon:"01"},
  {id:"content",fa:"محتوا",en:"Content",icon:"02"},
  {id:"layout",fa:"چیدمان",en:"Layout",icon:"03"},
];

const HERO_FIELDS:TextField[]=[
  {key:"hero_kicker",fa:"برچسب بالای Hero",en:"Hero eyebrow"},
  {key:"hero_title",fa:"عنوان اصلی",en:"Main headline"},
  {key:"hero_highlight",fa:"بخش برجسته عنوان",en:"Highlighted phrase"},
  {key:"hero_description",fa:"توضیح Hero",en:"Hero description",long:true},
  {key:"hero_primary_button",fa:"متن دکمه اصلی",en:"Primary CTA"},
  {key:"hero_secondary_button",fa:"متن دکمه دوم",en:"Secondary CTA"},
  {key:"hero_proof_1",fa:"نکته اعتماد ۱",en:"Proof 1"},
  {key:"hero_proof_2",fa:"نکته اعتماد ۲",en:"Proof 2"},
  {key:"hero_proof_3",fa:"نکته اعتماد ۳",en:"Proof 3"},
];

const CONTENT_FIELDS:TextField[]=[
  {key:"plans_tag",fa:"پلن‌ها — برچسب",en:"Plans — tag"},{key:"plans_title",fa:"پلن‌ها — عنوان",en:"Plans — title"},{key:"plans_description",fa:"پلن‌ها — توضیح",en:"Plans — description",long:true},
  {key:"protocols_tag",fa:"پروتکل‌ها — برچسب",en:"Protocols — tag"},{key:"protocols_title",fa:"پروتکل‌ها — عنوان",en:"Protocols — title"},{key:"protocols_description",fa:"پروتکل‌ها — توضیح",en:"Protocols — description",long:true},
  {key:"services_tag",fa:"خدمات — برچسب",en:"Services — tag"},{key:"services_title",fa:"خدمات — عنوان",en:"Services — title"},{key:"services_description",fa:"خدمات — توضیح",en:"Services — description",long:true},
  {key:"guides_tag",fa:"آموزش — برچسب",en:"Guides — tag"},{key:"guides_title",fa:"آموزش — عنوان",en:"Guides — title"},{key:"guides_description",fa:"آموزش — توضیح",en:"Guides — description",long:true},
  {key:"account_tag",fa:"حساب — برچسب",en:"Account — tag"},{key:"account_title",fa:"حساب — عنوان",en:"Account — title"},{key:"account_description",fa:"حساب — توضیح",en:"Account — description",long:true},
  {key:"faq_tag",fa:"FAQ — برچسب",en:"FAQ — tag"},{key:"faq_title",fa:"FAQ — عنوان",en:"FAQ — title"},{key:"faq_description",fa:"FAQ — توضیح",en:"FAQ — description",long:true},
  {key:"final_cta_tag",fa:"CTA نهایی — برچسب",en:"Final CTA — tag"},{key:"final_cta_title",fa:"CTA نهایی — عنوان",en:"Final CTA — title"},{key:"final_cta_description",fa:"CTA نهایی — توضیح",en:"Final CTA — description",long:true},{key:"final_cta_button",fa:"CTA نهایی — دکمه",en:"Final CTA — button"},
  {key:"contact_tag",fa:"ارتباط — برچسب",en:"Contact — tag"},{key:"contact_title",fa:"ارتباط — عنوان",en:"Contact — title"},{key:"contact_description",fa:"ارتباط — توضیح",en:"Contact — description",long:true},
  {key:"footer_tagline",fa:"توضیح کوتاه فوتر",en:"Footer tagline",long:true},
];

const SECTION_LABELS:Record<StorefrontSectionId,{fa:string;en:string}>={
  plans:{fa:"پلن‌ها",en:"Plans"},protocols:{fa:"پروتکل‌ها",en:"Protocols"},services:{fa:"خدمات",en:"Services"},guides:{fa:"آموزش",en:"Guides"},account:{fa:"حساب کاربری",en:"Account"},faq:{fa:"سوالات متداول",en:"FAQ"},
};

const COLOR_FIELDS:{key:string;fa:string;en:string}[]=[
  {key:"conversion_accent",fa:"رنگ اصلی",en:"Primary accent"},{key:"conversion_accent_2",fa:"رنگ مکمل",en:"Secondary accent"},
  {key:"conversion_page_bg",fa:"پس‌زمینه صفحه",en:"Page background"},{key:"conversion_section_bg",fa:"پس‌زمینه سکشن‌ها",en:"Section background"},
  {key:"conversion_card_bg",fa:"پس‌زمینه کارت‌ها",en:"Card background"},{key:"conversion_card_border",fa:"خط دور کارت‌ها",en:"Card border"},
  {key:"conversion_header_bg",fa:"پس‌زمینه هدر",en:"Header background"},{key:"conversion_header_text",fa:"متن هدر",en:"Header text"},
  {key:"conversion_button_bg",fa:"رنگ دکمه اصلی",en:"Primary button"},{key:"conversion_button_text",fa:"متن دکمه اصلی",en:"Primary button text"},
  {key:"conversion_text",fa:"متن اصلی",en:"Main text"},{key:"conversion_muted",fa:"متن فرعی",en:"Muted text"},
];

function primitiveSettings(raw:unknown):Draft{
  const normalized=normalizeStorefrontSettings(raw) as unknown as Record<string,unknown>;
  const next:Draft={};
  for(const [key,value] of Object.entries(normalized)){
    if(typeof value==="string"||typeof value==="boolean")next[key]=value;
    else if(key==="section_order"&&Array.isArray(value))next[key]=value.map(String);
  }
  return next;
}

export function ConversionTemplateCustomizer({onClose}:{onClose:()=>void}){
  const {pick}=useI18n();
  const [tab,setTab]=useState<Tab>("colors");
  const [locale,setLocale]=useState<"fa"|"en">("fa");
  const [draft,setDraft]=useState<Draft>({...DESIGN_DEFAULTS});
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  useEffect(()=>{
    let active=true;
    const run=async()=>{
      setLoading(true);setError("");
      try{
        const [envelope,sharedRaw]=await Promise.all([loadStoreTemplateSettings(),parityApi.storefrontSettings()]);
        if(!active)return;
        const raw=envelope.templates?.["conversion-2027"]||{};
        setDraft({...primitiveSettings(sharedRaw),...DESIGN_DEFAULTS,...raw} as Draft);
      }catch(reason){if(active)setError(reason instanceof Error?reason.message:String(reason));}
      finally{if(active)setLoading(false);}
    };
    void run();
    return()=>{active=false;};
  },[]);

  const localizedKey=(key:string)=>locale==="en"?`${key}_en`:key;
  const value=(key:string)=>draft[localizedKey(key)]??draft[key]??"";
  const setValue=(key:string,next:DraftValue)=>setDraft(current=>({...current,[key]:next}));
  const setText=(key:string,next:string)=>setDraft(current=>({...current,[localizedKey(key)]:next}));

  const applyPalette=(palette:Palette)=>setDraft(current=>({...current,
    conversion_accent:palette.accent,conversion_accent_2:palette.accent2,conversion_page_bg:palette.page,conversion_section_bg:palette.section,
    conversion_card_bg:palette.card,conversion_card_border:palette.border,conversion_header_bg:palette.header,conversion_header_text:palette.headerText,
    conversion_button_bg:palette.button,conversion_button_text:palette.buttonText,conversion_text:palette.text,conversion_muted:palette.muted,
  }));

  const save=async()=>{
    if(busy)return;
    setBusy(true);setError("");setOk("");
    try{
      await saveStoreTemplateSettings("conversion-2027",draft as unknown as Record<string,unknown>);
      setOk(pick("تغییرات قالب ذخیره شد.","Theme changes saved."));
      window.setTimeout(()=>setOk(""),2500);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const restoreDesign=()=>{
    setDraft(current=>({...current,...DESIGN_DEFAULTS}));
    setOk(pick("رنگ‌ها و استایل پیش‌فرض بارگذاری شد.","Default colors and style loaded."));
    window.setTimeout(()=>setOk(""),2200);
  };

  const renderTextFields=(fields:TextField[])=><div className={styles.grid2}>{fields.map(field=><label key={`${locale}-${field.key}`} className={`${styles.field} ${field.long?styles.wide:""}`}><span>{pick(field.fa,field.en)}</span>{field.long?<textarea rows={4} value={String(value(field.key))} onChange={event=>setText(field.key,event.target.value)}/>:<input type="text" value={String(value(field.key))} onChange={event=>setText(field.key,event.target.value)}/>}</label>)}</div>;

  const sectionOrder=useMemo(()=>Array.isArray(draft.section_order)?draft.section_order.map(String) as StorefrontSectionId[]:[...STOREFRONT_SECTION_IDS],[draft.section_order]);
  const moveSection=(index:number,delta:number)=>{
    const order=[...sectionOrder];const target=index+delta;if(target<0||target>=order.length)return;
    [order[index],order[target]]=[order[target],order[index]];setValue("section_order",order);
  };

  return <div className={styles.root}>
    <div className={styles.topbar}>
      <div className={styles.identity}><span className={styles.mark}>CV</span><div><h1>Conversion 2027</h1><p>{pick("طراحی، رنگ‌ها و محتوای فروشگاه","Store design, colors and content")}</p></div></div>
      <div className={styles.actions}><button type="button" onClick={onClose}>{pick("بازگشت","Back")}</button><Link href="/store" target="_blank">{pick("مشاهده فروشگاه","Open storefront")} ↗</Link><button type="button" onClick={restoreDesign}>{pick("بازنشانی ظاهر","Reset style")}</button><button type="button" className={styles.primary} onClick={()=>void save()} disabled={busy}>{busy?"…":pick("ذخیره تغییرات","Save changes")}</button></div>
    </div>

    {error&&<div className={styles.error}>{error}</div>}{ok&&<div className={styles.success}>{ok}</div>}

    {loading?<div className={styles.loading}>{pick("در حال دریافت تنظیمات...","Loading settings...")}</div>:<div className={styles.workspace}>
      <aside className={styles.sidebar}>{TABS.map(item=><button type="button" key={item.id} className={tab===item.id?styles.active:""} onClick={()=>setTab(item.id)}><span>{item.icon}</span>{pick(item.fa,item.en)}</button>)}</aside>

      <section className={styles.panel}>
        <div className={styles.panelHead}><div><h2>{pick(TABS.find(item=>item.id===tab)?.fa||"",TABS.find(item=>item.id===tab)?.en||"")}</h2></div>{(tab==="hero"||tab==="content")&&<div className={styles.locale}><button type="button" className={locale==="fa"?styles.active:""} onClick={()=>setLocale("fa")}>FA</button><button type="button" className={locale==="en"?styles.active:""} onClick={()=>setLocale("en")}>EN</button></div>}</div>

        <div className={styles.body}>
          {tab==="colors"&&<>
            <div className={styles.section}><div className={styles.sectionHead}><b>{pick("پالت آماده","Color presets")}</b></div><div className={styles.palettes}>{PALETTES.map(palette=><button type="button" key={palette.id} onClick={()=>applyPalette(palette)}><span className={styles.swatches}><i style={{background:palette.accent}}/><i style={{background:palette.page}}/><i style={{background:palette.card}}/></span><b>{pick(palette.fa,palette.en)}</b></button>)}</div></div>
            <div className={styles.section}><div className={styles.sectionHead}><b>{pick("رنگ‌های قالب","Theme colors")}</b></div><div className={styles.colorGrid}>{COLOR_FIELDS.map(field=>{const raw=String(draft[field.key]||"#000000");const safe=/^#[0-9a-fA-F]{6}$/.test(raw)?raw:"#000000";return <label className={styles.field} key={field.key}><span>{pick(field.fa,field.en)}</span><div className={styles.colorRow}><input type="color" value={safe} onChange={e=>setValue(field.key,e.target.value)}/><input type="text" dir="ltr" value={raw} onChange={e=>setValue(field.key,e.target.value)}/></div></label>;})}</div></div>
          </>}

          {tab==="style"&&<>
            <ChoiceGroup title={pick("تراکم صفحه","Page density")} value={String(draft.conversion_density)} onChange={value=>setValue("conversion_density",value)} choices={[["compact",pick("فشرده","Compact")],["balanced",pick("متعادل","Balanced")],["airy",pick("باز","Airy")]]}/>
            <ChoiceGroup title={pick("هدر","Header")} value={String(draft.conversion_header_style)} onChange={value=>setValue("conversion_header_style",value)} choices={[["glass",pick("شیشه‌ای","Glass")],["solid",pick("یکدست","Solid")],["minimal",pick("مینیمال","Minimal")]]}/>
            <ChoiceGroup title={pick("دکمه اصلی","Primary buttons")} value={String(draft.conversion_button_style)} onChange={value=>setValue("conversion_button_style",value)} choices={[["gradient",pick("گرادیان","Gradient")],["solid",pick("ساده","Solid")],["outline",pick("خطی","Outline")]]}/>
            <ChoiceGroup title={pick("کارت‌ها","Cards")} value={String(draft.conversion_card_style)} onChange={value=>setValue("conversion_card_style",value)} choices={[["glass",pick("شیشه‌ای","Glass")],["solid",pick("یکدست","Solid")],["bordered",pick("خط‌دار","Bordered")]]}/>
            <ChoiceGroup title={pick("گوشه‌ها","Corners")} value={String(draft.conversion_corner_style)} onChange={value=>setValue("conversion_corner_style",value)} choices={[["sharp",pick("تیز","Sharp")],["soft",pick("نرم","Soft")],["round",pick("گرد","Rounded")]]}/>
            <ChoiceGroup title={pick("نور پس‌زمینه","Background glow")} value={String(draft.conversion_glow)} onChange={value=>setValue("conversion_glow",value)} choices={[["off",pick("خاموش","Off")],["soft",pick("ملایم","Soft")],["strong",pick("قوی","Strong")]]}/>
          </>}

          {tab==="hero"&&<><div className={styles.section}><label className={styles.toggle}><span>{pick("نمایش تصویر Hero","Show hero visual")}</span><input type="checkbox" checked={Boolean(draft.conversion_show_hero_visual)} onChange={e=>setValue("conversion_show_hero_visual",e.target.checked)}/></label></div><div className={styles.section}><div className={styles.sectionHead}><b>{pick("متن Hero","Hero copy")}</b></div>{renderTextFields(HERO_FIELDS)}</div></>}

          {tab==="content"&&<div className={styles.section}><div className={styles.sectionHead}><b>{pick("متن‌های اصلی فروشگاه","Storefront copy")}</b></div>{renderTextFields(CONTENT_FIELDS)}</div>}

          {tab==="layout"&&<>
            <div className={styles.section}><div className={styles.sectionHead}><b>{pick("نمایش بخش‌ها","Section visibility")}</b></div><div className={styles.toggles}>{STOREFRONT_SECTION_IDS.map(section=><label className={styles.toggle} key={section}><span>{pick(SECTION_LABELS[section].fa,SECTION_LABELS[section].en)}</span><input type="checkbox" checked={Boolean(draft[`show_${section}`])} onChange={e=>setValue(`show_${section}`,e.target.checked)}/></label>)}<label className={styles.toggle}><span>{pick("CTA نهایی","Final CTA")}</span><input type="checkbox" checked={Boolean(draft.show_final_cta)} onChange={e=>setValue("show_final_cta",e.target.checked)}/></label><label className={styles.toggle}><span>{pick("ارتباط و پشتیبانی","Contact")}</span><input type="checkbox" checked={Boolean(draft.show_contact)} onChange={e=>setValue("show_contact",e.target.checked)}/></label></div></div>
            <div className={styles.section}><div className={styles.sectionHead}><b>{pick("ترتیب بخش‌ها","Section order")}</b></div><div className={styles.order}>{sectionOrder.map((section,index)=><div className={styles.orderRow} key={section}><span>{String(index+1).padStart(2,"0")}</span><b>{pick(SECTION_LABELS[section].fa,SECTION_LABELS[section].en)}</b><div><button type="button" disabled={index===0} onClick={()=>moveSection(index,-1)}>↑</button><button type="button" disabled={index===sectionOrder.length-1} onClick={()=>moveSection(index,1)}>↓</button></div></div>)}</div></div>
          </>}
        </div>
      </section>
    </div>}
  </div>;
}

function ChoiceGroup({title,value,onChange,choices}:{title:string;value:string;onChange:(value:string)=>void;choices:string[][]}){
  return <div className={styles.section}><div className={styles.sectionHead}><b>{title}</b></div><div className={styles.choices}>{choices.map(choice=><button type="button" key={choice[0]} className={value===choice[0]?styles.active:""} onClick={()=>onChange(choice[0])}>{choice[1]}</button>)}</div></div>;
}
