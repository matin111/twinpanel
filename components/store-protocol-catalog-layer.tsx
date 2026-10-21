"use client";

import {useEffect,useState} from "react";
import {createPortal} from "react-dom";
import {useI18n} from "../lib/i18n";
import {STORE_MODERN_PROTOCOLS,type StoreProtocolCategory} from "../lib/store-protocol-catalog";
import styles from "./store-protocol-catalog-layer.module.css";

const categoryLabel:Record<Exclude<StoreProtocolCategory,"classic">,{fa:string;en:string}>={
  recommended:{fa:"پیشنهادی مدرن",en:"Modern recommended"},
  camouflage:{fa:"استتار و سازگاری",en:"Camouflage & compatibility"},
  standalone:{fa:"Runtime مستقل",en:"Standalone runtime"},
};

export function StoreProtocolCatalogLayer({templateId}:{templateId:string}){
  const {pick}=useI18n();
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
    <section className={styles.extension} data-template={templateId} aria-label={pick("پروتکل‌های مدرن","Modern protocols")}>
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
              <h4>{protocol.name}</h4>
              <p>{pick(protocol.fa,protocol.en)}</p>
            </div>
            <div className={styles.meta}>
              <span>{protocol.transport}</span>
              {protocol.defaultPort&&<span>Port {protocol.defaultPort}</span>}
            </div>
          </article>;
        })}
      </div>
    </section>,
    target,
  );
}
