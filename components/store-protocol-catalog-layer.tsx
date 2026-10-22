"use client";

import {useEffect,useState,type CSSProperties} from "react";
import {createPortal} from "react-dom";
import {useI18n} from "../lib/i18n";
import {STORE_MODERN_PROTOCOLS,type StoreProtocolCategory} from "../lib/store-protocol-catalog";
import type {StoreTemplateOptionMap} from "../lib/store-template-options";
import styles from "./store-protocol-catalog-layer.module.css";

const categoryLabel:Record<Exclude<StoreProtocolCategory,"classic">,{fa:string;en:string}>={
  recommended:{fa:"پیشنهادی مدرن",en:"Modern recommended"},
  camouflage:{fa:"استتار و سازگاری",en:"Camouflage & compatibility"},
  standalone:{fa:"Runtime مستقل",en:"Standalone runtime"},
};

type ProtocolStyle=CSSProperties&Record<`--${string}`,string>;

function option(options:StoreTemplateOptionMap,key:string,fallback:string){
  const value=options[key];
  return typeof value==="string"&&value.trim()?value:fallback;
}

function protocolThemeStyle(templateId:string,options:StoreTemplateOptionMap):ProtocolStyle{
  if(templateId==="editorial-grid-2027"){
    return {
      "--protocol-accent":option(options,"theme_primary","#8b5cf6"),
      "--protocol-accent-2":option(options,"theme_secondary","#6366f1"),
      "--protocol-dark-surface":option(options,"editorial_surface_bg","#15171c"),
      "--protocol-dark-surface-alt":option(options,"editorial_surface_alt","#1b1e24"),
      "--protocol-dark-border":option(options,"editorial_border","#30343b"),
      "--protocol-dark-text":option(options,"editorial_text","#f7f3ec"),
      "--protocol-dark-muted":option(options,"editorial_muted","#a8a29a"),
      "--protocol-light-surface":"#fffdf9",
      "--protocol-light-surface-alt":"#f8f4ed",
      "--protocol-light-border":"#d8d1c8",
      "--protocol-light-text":"#171719",
      "--protocol-light-muted":"#67635d",
    } as ProtocolStyle;
  }

  if(templateId==="orbit-neo-2027"){
    return {
      "--protocol-accent":option(options,"theme_primary","#6d5dfc"),
      "--protocol-accent-2":option(options,"theme_secondary","#22d3ee"),
      "--protocol-dark-surface":option(options,"orbit_dark_surface","#0c0f16"),
      "--protocol-dark-surface-alt":option(options,"orbit_dark_surface_alt","#131824"),
      "--protocol-dark-border":option(options,"orbit_dark_border","#253043"),
      "--protocol-dark-text":option(options,"orbit_dark_text","#f8fafc"),
      "--protocol-dark-muted":option(options,"orbit_dark_muted","#9aa4b5"),
      "--protocol-light-surface":option(options,"orbit_light_surface","#ffffff"),
      "--protocol-light-surface-alt":option(options,"orbit_light_surface_alt","#edf1f8"),
      "--protocol-light-border":option(options,"orbit_light_border","#d9e0ec"),
      "--protocol-light-text":option(options,"orbit_light_text","#10131a"),
      "--protocol-light-muted":option(options,"orbit_light_muted","#667085"),
    } as ProtocolStyle;
  }

  return {
    "--protocol-accent":option(options,"conversion_accent","#8b5cf6"),
    "--protocol-accent-2":option(options,"conversion_accent_2","#6d28d9"),
    "--protocol-dark-surface":option(options,"conversion_card_bg","#0f1526"),
    "--protocol-dark-surface-alt":option(options,"conversion_section_bg","#0b1020"),
    "--protocol-dark-border":option(options,"conversion_card_border","#202b42"),
    "--protocol-dark-text":option(options,"conversion_text","#f7f8ff"),
    "--protocol-dark-muted":option(options,"conversion_muted","#9aa7bf"),
    "--protocol-light-surface":"#ffffff",
    "--protocol-light-surface-alt":"#f1f5f9",
    "--protocol-light-border":"#d7dee8",
    "--protocol-light-text":"#111827",
    "--protocol-light-muted":"#667085",
  } as ProtocolStyle;
}

export function StoreProtocolCatalogLayer({templateId,themeOptions}:{templateId:string;themeOptions:StoreTemplateOptionMap}){
  const {pick,lang}=useI18n();
  const [target,setTarget]=useState<HTMLElement|null>(null);

  useEffect(()=>{
    const section=document.getElementById("protocols");
    if(!section)return;

    const existing=section.querySelector<HTMLElement>("[data-store-modern-protocols]");
    if(existing){
      setTarget(existing);
      return;
    }

    const mount=document.createElement("div");
    mount.dataset.storeModernProtocols="true";
    section.appendChild(mount);
    setTarget(mount);

    return()=>{
      setTarget(null);
      mount.remove();
    };
  },[templateId]);

  if(!target)return null;

  return createPortal(
    <section className={styles.extension} style={protocolThemeStyle(templateId,themeOptions)} data-template={templateId} dir={lang==="en"?"ltr":"rtl"} aria-label={pick("پروتکل‌های مدرن","Modern protocols")}>
      <header className={styles.heading}>
        <div>
          <span className={styles.eyebrow}>{pick("نسل جدید اتصال","NEXT-GEN CONNECTIVITY")}</span>
          <h3>{pick("پروتکل‌های مدرن","Modern protocols")}</h3>
        </div>
        <p>{pick(
          "پروتکل‌های جدید TwinPanel در کنار گزینه‌های کلاسیک؛ برای هر شبکه مسیر مناسب‌تری در دسترس است.",
          "TwinPanel's newer protocols alongside the classic options, giving each network a better-matched path."
        )}</p>
      </header>

      <div className={styles.grid}>
        {STORE_MODERN_PROTOCOLS.map((protocol,index)=>{
          const label=categoryLabel[protocol.category as Exclude<StoreProtocolCategory,"classic">];
          return <article className={styles.card} data-category={protocol.category} key={protocol.id}>
            <div className={styles.cardTop}>
              <span className={styles.mark} aria-hidden="true">{protocol.mark}</span>
              <span className={styles.index}>{String(index+6).padStart(2,"0")}</span>
            </div>
            <div className={styles.cardBody}>
              <small>{pick(label.fa,label.en)}</small>
              <h4 dir="ltr">{protocol.name}</h4>
              <p>{pick(protocol.fa,protocol.en)}</p>
            </div>
            <div className={styles.meta} dir="ltr">
              <span>{protocol.transport}</span>
            </div>
          </article>;
        })}
      </div>
    </section>,
    target,
  );
}
