"use client";

import {useI18n} from "../lib/i18n";
import {storefrontText,type StorefrontSettings} from "../lib/storefront-config";
import styles from "./store-template-editorial-theme-bridge.module.css";

export function EditorialFooterSocial({settings}:{settings:StorefrontSettings}){
  const {lang}=useI18n();
  const content=(key:string)=>storefrontText(settings,key,lang);
  const links=[
    settings.show_telegram&&settings.telegram_url?{id:"telegram",index:"01",href:settings.telegram_url,title:content("telegram_title")} : null,
    settings.show_instagram&&settings.instagram_url?{id:"instagram",index:"02",href:settings.instagram_url,title:content("instagram_title")} : null,
    settings.show_whatsapp&&settings.whatsapp_url?{id:"whatsapp",index:"03",href:settings.whatsapp_url,title:content("whatsapp_title")} : null,
  ].filter(Boolean) as {id:string;index:string;href:string;title:string}[];

  if(links.length===0)return null;

  return <section className={styles.socialFooter} aria-label={content("footer_social_title")}>
    <div className={styles.socialFooterHead}><small>SOCIAL</small><b>{content("footer_social_title")}</b></div>
    <div className={styles.socialFooterLinks}>{links.map(link=><a key={link.id} href={link.href} target="_blank" rel="noreferrer"><span>{link.index}</span><b>{link.title}</b><i>↗</i></a>)}</div>
  </section>;
}
