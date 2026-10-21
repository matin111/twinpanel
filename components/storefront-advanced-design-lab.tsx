"use client";

import {useEffect,useMemo,useState} from "react";
import {useI18n} from "../lib/i18n";
import {
  ADVANCED_COLOR_SLOTS,
  ADVANCED_DESIGN_KEYS,
  ADVANCED_LAYOUT_DEFAULTS,
  advancedDesignFallbacks,
  type AdvancedDesignMode,
} from "../lib/storefront-advanced-design";
import type {StoreTemplateOptionMap} from "../lib/store-template-options";
import {loadStoreTemplateSettings,saveStoreTemplateSettings} from "../lib/store-template-settings-api";
import styles from "./storefront-advanced-design-lab.module.css";

type Draft=Record<string,string>;

type ColorSlot=(typeof ADVANCED_COLOR_SLOTS)[number];

type Choice={value:string;fa:string;en:string};

const COLOR_LABELS:Record<ColorSlot,{fa:string;en:string}>={
  primary_bg:{fa:"دکمه اصلی — پس‌زمینه",en:"Primary button — background"},
  primary_text:{fa:"دکمه اصلی — متن",en:"Primary button — text"},
  secondary_bg:{fa:"دکمه دوم — پس‌زمینه",en:"Secondary button — background"},
  secondary_text:{fa:"دکمه دوم — متن",en:"Secondary button — text"},
  plan_bg:{fa:"کارت پلن",en:"Plan cards"},
  protocol_bg:{fa:"کارت پروتکل",en:"Protocol cards"},
  service_bg:{fa:"کارت خدمات",en:"Service cards"},
  guide_bg:{fa:"کارت آموزش",en:"Guide cards"},
  account_bg:{fa:"کارت حساب کاربری",en:"Account cards"},
  faq_bg:{fa:"کارت FAQ",en:"FAQ cards"},
  contact_bg:{fa:"کارت ارتباط و پشتیبانی",en:"Contact & support cards"},
  card_text:{fa:"متن اصلی کارت‌ها",en:"Card primary text"},
  muted:{fa:"متن فرعی کارت‌ها",en:"Card muted text"},
  border:{fa:"Border کارت‌ها",en:"Card borders"},
};

const CARD_SIZE:Choice[]=[
  {value:"native",fa:"پیش‌فرض قالب",en:"Theme default"},{value:"compact",fa:"جمع‌وجور",en:"Compact"},{value:"balanced",fa:"متعادل",en:"Balanced"},{value:"spacious",fa:"بزرگ و باز",en:"Spacious"},
];
const CARD_SHAPE:Choice[]=[
  {value:"native",fa:"پیش‌فرض قالب",en:"Theme default"},{value:"sharp",fa:"تیز",en:"Sharp"},{value:"soft",fa:"نرم",en:"Soft"},{value:"round",fa:"گرد",en:"Round"},
];
const CARD_EFFECT:Choice[]=[
  {value:"native",fa:"پیش‌فرض قالب",en:"Theme default"},{value:"flat",fa:"Flat",en:"Flat"},{value:"bordered",fa:"Bordered",en:"Bordered"},{value:"shadow",fa:"Shadow",en:"Shadow"},{value:"glass",fa:"Glass",en:"Glass"},
];
const BUTTON_SIZE:Choice[]=[
  {value:"native",fa:"پیش‌فرض",en:"Default"},{value:"compact",fa:"کوچک",en:"Compact"},{value:"balanced",fa:"متوسط",en:"Balanced"},{value:"large",fa:"بزرگ",en:"Large"},
];
const BUTTON_SHAPE:Choice[]=[
  {value:"native",fa:"پیش‌فرض",en:"Default"},{value:"square",fa:"مربع نرم",en:"Soft square"},{value:"soft",fa:"گرد متوسط",en:"Soft round"},{value:"pill",fa:"کپسولی",en:"Pill"},
];
const PLAN_LAYOUT:Choice[]=[
  {value:"native",fa:"چیدمان قالب",en:"Theme layout"},{value:"one",fa:"تک‌ستونه",en:"1 column"},{value:"two",fa:"دو ستونه",en:"2 columns"},{value:"three",fa:"سه ستونه",en:"3 columns"},
];
const PROTOCOL_LAYOUT:Choice[]=[
  {value:"native",fa:"چیدمان قالب",en:"Theme layout"},{value:"one",fa:"تک‌ستونه",en:"1 column"},{value:"two",fa:"دو ستونه",en:"2 columns"},{value:"three",fa:"سه ستونه",en:"3 columns"},{value:"five",fa:"پنج ستونه",en:"5 columns"},
];
const SERVICE_LAYOUT:Choice[]=[
  {value:"native",fa:"چیدمان قالب",en:"Theme layout"},{value:"one",fa:"تک‌ستونه",en:"1 column"},{value:"two",fa:"دو ستونه",en:"2 columns"},{value:"three",fa:"سه ستونه",en:"3 columns"},
];

function isHex(value:string){return /^#[0-9a-fA-F]{6}$/.test(value);}

export function StorefrontAdvancedDesignLab({templateId}:{templateId:string}){
  const {pick}=useI18n();
  const [mode,setMode]=useState<AdvancedDesignMode>("dark");
  const [options,setOptions]=useState<StoreTemplateOptionMap>({});
  const [draft,setDraft]=useState<Draft>({});
  const [touched,setTouched]=useState<Record<string,boolean>>({});
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [ok,setOk]=useState("");
  const [error,setError]=useState("");

  useEffect(()=>{
    let active=true;
    setLoading(true);setError("");
    void loadStoreTemplateSettings().then(envelope=>{
      if(!active)return;
      const current=(envelope.templates?.[templateId]||{}) as StoreTemplateOptionMap;
      setOptions(current);
      const values:Draft={};
      for(const key of ADVANCED_DESIGN_KEYS){
        const value=current[key];
        if(typeof value==="string")values[key]=value;
      }
      setDraft(values);setTouched({});
    }).catch(reason=>active&&setError(reason instanceof Error?reason.message:String(reason))).finally(()=>active&&setLoading(false));
    return()=>{active=false;};
  },[templateId]);

  const fallbacks=useMemo(()=>advancedDesignFallbacks(templateId,mode,options),[templateId,mode,options]);
  const dirty=Object.keys(touched).length>0;

  const setValue=(key:string,value:string)=>{
    setDraft(current=>({...current,[key]:value}));
    setTouched(current=>({...current,[key]:true}));
    setOk("");setError("");
  };

  const colorValue=(slot:ColorSlot)=>{
    const key=`ui_${mode}_${slot}`;
    const value=draft[key];
    return typeof value==="string"&&isHex(value)?value:(fallbacks[key]||"#000000");
  };

  const colorTextValue=(slot:ColorSlot)=>{
    const key=`ui_${mode}_${slot}`;
    return draft[key]||fallbacks[key]||"#000000";
  };

  const isExplicit=(key:string)=>typeof draft[key]==="string"&&draft[key].trim().length>0;
  const layoutValue=(key:keyof typeof ADVANCED_LAYOUT_DEFAULTS)=>draft[key]||ADVANCED_LAYOUT_DEFAULTS[key];

  const save=async()=>{
    if(busy||!dirty)return;
    for(const key of Object.keys(touched)){
      if((key.startsWith("ui_dark_")||key.startsWith("ui_light_"))&&!isHex(draft[key]||"")){
        setError(pick("یکی از رنگ‌ها HEX معتبر نیست. نمونه صحیح: #7c3aed","One color is not a valid HEX value. Example: #7c3aed"));
        return;
      }
    }
    setBusy(true);setError("");setOk("");
    try{
      const latest=await loadStoreTemplateSettings();
      const merged:{[key:string]:unknown}={...(latest.templates?.[templateId]||{})};
      for(const key of Object.keys(touched))merged[key]=draft[key];
      await saveStoreTemplateSettings(templateId,merged);
      setOptions(merged as StoreTemplateOptionMap);
      setTouched({});
      setOk(pick("تنظیمات پیشرفته ذخیره شد.","Advanced design settings were saved."));
      window.setTimeout(()=>setOk(""),2600);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const resetAdvanced=async()=>{
    if(busy)return;
    setBusy(true);setError("");setOk("");
    try{
      const latest=await loadStoreTemplateSettings();
      const merged:{[key:string]:unknown}={...(latest.templates?.[templateId]||{})};
      for(const key of ADVANCED_DESIGN_KEYS)delete merged[key];
      await saveStoreTemplateSettings(templateId,merged);
      setOptions(merged as StoreTemplateOptionMap);setDraft({});setTouched({});
      setOk(pick("فقط تنظیمات پیشرفته به حالت خود قالب برگشت؛ محتوای قالب حفظ شد.","Only advanced design settings were reset; template content was preserved."));
      window.setTimeout(()=>setOk(""),3000);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const renderChoice=(key:keyof typeof ADVANCED_LAYOUT_DEFAULTS,choices:Choice[])=><div className={styles.choice}>{choices.map(choice=><button type="button" key={choice.value} data-active={layoutValue(key)===choice.value} onClick={()=>setValue(key,choice.value)}>{pick(choice.fa,choice.en)}</button>)}</div>;

  const buttonSlots:ColorSlot[]=["primary_bg","primary_text","secondary_bg","secondary_text"];
  const cardSlots:ColorSlot[]=["plan_bg","protocol_bg","service_bg","guide_bg","account_bg","faq_bg","contact_bg"];
  const textSlots:ColorSlot[]=["card_text","muted","border"];

  if(loading)return <section className={styles.lab}><div className={styles.headCopy}><span className={styles.eyebrow}>ADVANCED DESIGN LAB</span><h2>{pick("در حال بارگذاری تنظیمات عمیق…","Loading advanced design settings…")}</h2></div></section>;

  const colorFields=(slots:ColorSlot[])=>slots.map(slot=>{
    const key=`ui_${mode}_${slot}`;
    return <label className={styles.field} key={key}>
      <div className={styles.fieldTop}><span>{pick(COLOR_LABELS[slot].fa,COLOR_LABELS[slot].en)}</span><small className={styles.inherit}>{isExplicit(key)?pick("اختصاصی","Custom"):pick("از قالب","Inherited")}</small></div>
      <div className={styles.colorRow}>
        <input type="color" value={colorValue(slot)} onChange={event=>setValue(key,event.target.value)}/>
        <input type="text" value={colorTextValue(slot)} maxLength={7} onChange={event=>setValue(key,event.target.value)} aria-label={pick(COLOR_LABELS[slot].fa,COLOR_LABELS[slot].en)}/>
      </div>
    </label>;
  });

  return <section className={styles.lab}>
    <header className={styles.head}>
      <div className={styles.headCopy}>
        <span className={styles.eyebrow}>ADVANCED DESIGN LAB / 2027</span>
        <h2>{pick("کنترل عمیق کارت‌ها، دکمه‌ها و چیدمان","Deep control for cards, buttons and layout")}</h2>
        <p>{pick("این بخش روی همان قالب فعال کار می‌کند. Dark و Light مستقل‌اند و اگر گزینه‌ای را تغییر ندهید، ظاهر اصلی قالب دست‌نخورده می‌ماند.","This panel works on the active theme. Dark and Light are independent, and untouched controls keep the theme's native presentation.")}</p>
      </div>
      <div className={styles.status}><span className={styles.badge}>{templateId}</span>{dirty?<span className={`${styles.badge} ${styles.dirty}`}>{pick("تغییر ذخیره‌نشده","Unsaved changes")}</span>:<span className={`${styles.badge} ${styles.saved}`}>{pick("همگام","Synced")}</span>}</div>
    </header>

    <div className={styles.modeTabs}>
      <button type="button" data-active={mode==="dark"} onClick={()=>setMode("dark")}>{pick("حالت تیره","Dark mode")}</button>
      <button type="button" data-active={mode==="light"} onClick={()=>setMode("light")}>{pick("حالت روشن","Light mode")}</button>
    </div>

    <div className={styles.section}>
      <div className={styles.sectionHead}><div><b>{pick("دکمه‌ها","Buttons")}</b><small>{pick("رنگ دکمه اصلی و ثانویه با متن مستقل.","Independent primary/secondary button and text colors.")}</small></div></div>
      <div className={styles.colorGrid}>{colorFields(buttonSlots)}</div>
    </div>

    <div className={styles.section}>
      <div className={styles.sectionHead}><div><b>{pick("سطح هر نوع کارت","Card surfaces by section")}</b><small>{pick("هر بخش می‌تواند رنگ کارت خودش را داشته باشد؛ پروتکل‌های Classic و Modern یک کنترل مشترک می‌گیرند.","Each section can have its own card surface; Classic and Modern protocols share the same control.")}</small></div></div>
      <div className={styles.colorGrid}>{colorFields(cardSlots)}</div>
    </div>

    <div className={styles.section}>
      <div className={styles.sectionHead}><div><b>{pick("خوانایی کارت","Card readability")}</b><small>{pick("متن اصلی، متن فرعی و Border مستقل از پس‌زمینه.","Primary text, muted text and borders independently from surfaces.")}</small></div></div>
      <div className={styles.colorGrid}>{colorFields(textSlots)}</div>
    </div>

    <div className={styles.section}>
      <div className={styles.sectionHead}><div><b>{pick("مدل و اندازه کارت‌ها","Card model & sizing")}</b><small>{pick("بدون Rewrite قالب، Presentation کارت‌ها را روی مدل دلخواه تنظیم کنید.","Adjust card presentation without rewriting the theme.")}</small></div></div>
      <div className={styles.groups}>
        <div className={styles.group}><h3>{pick("اندازه کارت","Card size")}</h3>{renderChoice("ui_card_size",CARD_SIZE)}</div>
        <div className={styles.group}><h3>{pick("فرم گوشه‌ها","Corner shape")}</h3>{renderChoice("ui_card_shape",CARD_SHAPE)}</div>
        <div className={styles.group}><h3>{pick("افکت سطح","Surface effect")}</h3>{renderChoice("ui_card_effect",CARD_EFFECT)}</div>
        <div className={styles.group}><h3>{pick("اندازه دکمه","Button size")}</h3>{renderChoice("ui_button_size",BUTTON_SIZE)}</div>
        <div className={styles.group}><h3>{pick("فرم دکمه","Button shape")}</h3>{renderChoice("ui_button_shape",BUTTON_SHAPE)}</div>
      </div>
    </div>

    <div className={styles.section}>
      <div className={styles.sectionHead}><div><b>{pick("مدل نمایش Grid","Grid presentation")}</b><small>{pick("پلن‌ها، پروتکل‌ها و خدمات می‌توانند تعداد ستون مستقل داشته باشند؛ موبایل همیشه ایمن به تک‌ستون برمی‌گردد.","Plans, protocols and services can use independent column counts; mobile safely falls back to one column.")}</small></div></div>
      <div className={styles.groups}>
        <div className={styles.group}><h3>{pick("پلن‌ها","Plans")}</h3>{renderChoice("ui_plan_layout",PLAN_LAYOUT)}</div>
        <div className={styles.group}><h3>{pick("پروتکل‌ها","Protocols")}</h3>{renderChoice("ui_protocol_layout",PROTOCOL_LAYOUT)}</div>
        <div className={styles.group}><h3>{pick("خدمات","Services")}</h3>{renderChoice("ui_service_layout",SERVICE_LAYOUT)}</div>
      </div>
    </div>

    {ok&&<div className={`${styles.message} ${styles.ok}`}>{ok}</div>}
    {error&&<div className={`${styles.message} ${styles.error}`}>{error}</div>}

    <div className={styles.actions}>
      <div className={styles.actionsInfo}><b>{pick("Advanced Design فقط روی Presentation اثر می‌گذارد","Advanced Design affects presentation only")}</b><small>{pick("هیچ تنظیم VPN، پلن، پرداخت یا Runtime تغییر نمی‌کند.","VPN, plan, payment and runtime settings are not changed.")}</small></div>
      <div className={styles.actionsButtons}><button type="button" className={styles.reset} onClick={resetAdvanced} disabled={busy}>{pick("بازگشت به ظاهر قالب","Reset advanced")}</button><button type="button" className={styles.save} onClick={save} disabled={busy||!dirty}>{busy?pick("در حال ذخیره…","Saving…"):pick("ذخیره طراحی پیشرفته","Save advanced design")}</button></div>
    </div>
  </section>;
}
