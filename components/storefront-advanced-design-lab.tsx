"use client";

import {useMemo} from "react";
import {useI18n} from "../lib/i18n";
import {ADVANCED_LAYOUT_DEFAULTS,advancedDesignFallbacks} from "../lib/storefront-advanced-design";
import type {StoreTemplateOptionMap} from "../lib/store-template-options";
import styles from "./storefront-advanced-design-lab.module.css";

type Section="colors"|"style"|"layout";
type Choice={value:string;fa:string;en:string};
type Props={templateId:string;values:Record<string,unknown>;onChange:(key:string,value:string)=>void;section:Section};
type ColorSlot="secondary_bg"|"secondary_text"|"plan_bg"|"protocol_bg"|"service_bg"|"guide_bg"|"account_bg"|"faq_bg"|"contact_bg";

const COLOR_LABELS:Record<ColorSlot,{fa:string;en:string}>={
  secondary_bg:{fa:"دکمه دوم — پس‌زمینه",en:"Secondary button — background"},
  secondary_text:{fa:"دکمه دوم — متن",en:"Secondary button — text"},
  plan_bg:{fa:"کارت پلن",en:"Plan cards"},
  protocol_bg:{fa:"کارت پروتکل",en:"Protocol cards"},
  service_bg:{fa:"کارت خدمات",en:"Service cards"},
  guide_bg:{fa:"کارت آموزش",en:"Guide cards"},
  account_bg:{fa:"کارت حساب کاربری",en:"Account cards"},
  faq_bg:{fa:"کارت FAQ",en:"FAQ cards"},
  contact_bg:{fa:"کارت ارتباط و پشتیبانی",en:"Contact & support cards"},
};

const CARD_SIZE:Choice[]=[{value:"native",fa:"پیش‌فرض",en:"Default"},{value:"compact",fa:"جمع‌وجور",en:"Compact"},{value:"balanced",fa:"متعادل",en:"Balanced"},{value:"spacious",fa:"بزرگ",en:"Spacious"}];
const CARD_SHAPE:Choice[]=[{value:"native",fa:"پیش‌فرض",en:"Default"},{value:"sharp",fa:"تیز",en:"Sharp"},{value:"soft",fa:"نرم",en:"Soft"},{value:"round",fa:"گرد",en:"Round"}];
const CARD_EFFECT:Choice[]=[{value:"native",fa:"پیش‌فرض",en:"Default"},{value:"flat",fa:"Flat",en:"Flat"},{value:"bordered",fa:"خط‌دار",en:"Bordered"},{value:"shadow",fa:"سایه",en:"Shadow"},{value:"glass",fa:"شیشه‌ای",en:"Glass"}];
const BUTTON_SIZE:Choice[]=[{value:"native",fa:"پیش‌فرض",en:"Default"},{value:"compact",fa:"کوچک",en:"Compact"},{value:"balanced",fa:"متوسط",en:"Balanced"},{value:"large",fa:"بزرگ",en:"Large"}];
const BUTTON_SHAPE:Choice[]=[{value:"native",fa:"پیش‌فرض",en:"Default"},{value:"square",fa:"مربع نرم",en:"Soft square"},{value:"soft",fa:"گرد",en:"Soft round"},{value:"pill",fa:"کپسولی",en:"Pill"}];
const PLAN_LAYOUT:Choice[]=[{value:"native",fa:"پیش‌فرض",en:"Default"},{value:"one",fa:"۱ ستون",en:"1 column"},{value:"two",fa:"۲ ستون",en:"2 columns"},{value:"three",fa:"۳ ستون",en:"3 columns"}];
const PROTOCOL_LAYOUT:Choice[]=[{value:"native",fa:"پیش‌فرض",en:"Default"},{value:"one",fa:"۱ ستون",en:"1 column"},{value:"two",fa:"۲ ستون",en:"2 columns"},{value:"three",fa:"۳ ستون",en:"3 columns"},{value:"five",fa:"۵ ستون",en:"5 columns"}];
const SERVICE_LAYOUT:Choice[]=[{value:"native",fa:"پیش‌فرض",en:"Default"},{value:"one",fa:"۱ ستون",en:"1 column"},{value:"two",fa:"۲ ستون",en:"2 columns"},{value:"three",fa:"۳ ستون",en:"3 columns"}];

function isHex(value:unknown):value is string{return typeof value==="string"&&/^#[0-9a-fA-F]{6}$/.test(value);}

export function StorefrontAdvancedDesignControls({templateId,values,onChange,section}:Props){
  const {pick}=useI18n();
  const options=values as StoreTemplateOptionMap;
  const fallback=useMemo(()=>advancedDesignFallbacks(templateId,"dark",options),[templateId,options]);

  const colorValue=(slot:ColorSlot)=>{
    const unified=values[`ui_${slot}`];
    if(isHex(unified))return unified;
    const legacyDark=values[`ui_dark_${slot}`];
    if(isHex(legacyDark))return legacyDark;
    const legacyLight=values[`ui_light_${slot}`];
    if(isHex(legacyLight))return legacyLight;
    return fallback[`ui_dark_${slot}`]||"#000000";
  };
  const setColor=(slot:ColorSlot,value:string)=>onChange(`ui_${slot}`,value);
  const layoutValue=(key:keyof typeof ADVANCED_LAYOUT_DEFAULTS)=>typeof values[key]==="string"?String(values[key]):ADVANCED_LAYOUT_DEFAULTS[key];
  const renderChoice=(key:keyof typeof ADVANCED_LAYOUT_DEFAULTS,choices:Choice[])=><div className={styles.choice}>{choices.map(choice=><button type="button" key={choice.value} data-active={layoutValue(key)===choice.value} onClick={()=>onChange(key,choice.value)}>{pick(choice.fa,choice.en)}</button>)}</div>;
  const colorFields=(slots:ColorSlot[])=>slots.map(slot=><label className={styles.field} key={slot}><span>{pick(COLOR_LABELS[slot].fa,COLOR_LABELS[slot].en)}</span><div className={styles.colorRow}><input type="color" value={colorValue(slot)} onChange={event=>setColor(slot,event.target.value)}/><input type="text" dir="ltr" maxLength={7} value={colorValue(slot)} onChange={event=>setColor(slot,event.target.value)}/></div></label>);

  if(section==="colors")return <div className={styles.controls}>
    <div className={styles.group}><b>{pick("رنگ اختصاصی کارت‌ها","Card colors")}</b><div className={styles.colorGrid}>{colorFields(["plan_bg","protocol_bg","service_bg","guide_bg","account_bg","faq_bg","contact_bg"])}</div></div>
    <div className={styles.group}><b>{pick("دکمه دوم","Secondary button")}</b><div className={styles.colorGrid}>{colorFields(["secondary_bg","secondary_text"])}</div></div>
  </div>;

  if(section==="style")return <div className={styles.controls}>
    <div className={styles.group}><b>{pick("کارت‌ها","Cards")}</b><div className={styles.optionGrid}><div><span>{pick("اندازه","Size")}</span>{renderChoice("ui_card_size",CARD_SIZE)}</div><div><span>{pick("گوشه‌ها","Corners")}</span>{renderChoice("ui_card_shape",CARD_SHAPE)}</div><div><span>{pick("مدل نمایش","Presentation")}</span>{renderChoice("ui_card_effect",CARD_EFFECT)}</div></div></div>
    <div className={styles.group}><b>{pick("دکمه‌ها","Buttons")}</b><div className={styles.optionGrid}><div><span>{pick("اندازه","Size")}</span>{renderChoice("ui_button_size",BUTTON_SIZE)}</div><div><span>{pick("فرم","Shape")}</span>{renderChoice("ui_button_shape",BUTTON_SHAPE)}</div></div></div>
  </div>;

  return <div className={styles.controls}><div className={styles.group}><b>{pick("چیدمان کارت‌ها","Card layout")}</b><div className={styles.optionGrid}><div><span>{pick("پلن‌ها","Plans")}</span>{renderChoice("ui_plan_layout",PLAN_LAYOUT)}</div><div><span>{pick("پروتکل‌ها","Protocols")}</span>{renderChoice("ui_protocol_layout",PROTOCOL_LAYOUT)}</div><div><span>{pick("خدمات","Services")}</span>{renderChoice("ui_service_layout",SERVICE_LAYOUT)}</div></div></div></div>;
}
