"use client";

import Link from "next/link";
import {useMemo,useState,type ReactNode} from "react";
import {LanguageSwitch,useI18n} from "../lib/i18n";
import {ThemeSwitch} from "../lib/theme";
import {useBranding} from "../lib/branding";
import {planProtocols,type StorePlan} from "../lib/store-runtime-api";
import {
  isStorefrontSectionVisible,
  storefrontText,
  type StorefrontSectionId,
  type StorefrontSettings,
} from "../lib/storefront-config";
import type {StoreTemplateOptionMap} from "../lib/store-template-options";
import {
  storeGuideAppImage,
  storeGuideContent,
  storeGuidePlatforms,
  storeGuideScreenshot,
  type StoreGuidePlatform,
  type StoreGuideProtocol,
} from "../lib/store-guide-content";
import styles from "./store-template-editorial-pro.module.css";

type EditorialProProps={
  settings:StorefrontSettings;
  themeOptions:StoreTemplateOptionMap;
  plans:StorePlan[];
  loading:boolean;
  error:string;
  message:string;
  buying:number|null;
  onBuy:(plan:StorePlan)=>void;
};

type ProtocolMeta={name:string;short:string;mark:string;fa:string;en:string};

const PROTOCOLS:Record<string,ProtocolMeta>={
  cisco:{name:"Cisco / OpenConnect",short:"Cisco",mark:"CO",fa:"ورود ساده با نام کاربری و رمز؛ مناسب استفاده روزمره و سازگاری گسترده.",en:"Simple username/password access with broad compatibility."},
  openvpn:{name:"OpenVPN",short:"OpenVPN",mark:"OV",fa:"پروتکل کلاسیک و قابل اتکا برای سیستم‌عامل‌ها و شبکه‌های مختلف.",en:"A proven protocol for many operating systems and networks."},
  wireguard:{name:"WireGuard",short:"WireGuard",mark:"WG",fa:"اتصال سبک و سریع با فایل یا QR برای تجربه مدرن‌تر.",en:"Fast, lightweight connectivity with file or QR setup."},
  l2tp:{name:"L2TP / IPsec",short:"L2TP",mark:"L2",fa:"راه‌اندازی مستقیم از تنظیمات داخلی بسیاری از دستگاه‌ها.",en:"Built-in setup on many devices without an extra client."},
  v2ray:{name:"V2Ray / Xray",short:"V2Ray",mark:"VX",fa:"گزینه منعطف برای شرایط شبکه متفاوت و سناریوهای حرفه‌ای‌تر.",en:"Flexible connectivity for varied network conditions."},
};

const GUIDE_PROTOCOL_ORDER:StoreGuideProtocol[]=["cisco","openvpn","wireguard","l2tp","v2ray"];

export function EditorialPro2027Template({settings,themeOptions,plans,loading,error,message,buying,onBuy}:EditorialProProps){
  const {pick,lang}=useI18n();
  const {brand}=useBranding();
  const [menuOpen,setMenuOpen]=useState(false);
  const [guidePlatform,setGuidePlatform]=useState<StoreGuidePlatform>("android");
  const [guideProtocol,setGuideProtocol]=useState<StoreGuideProtocol>("wireguard");

  const locale=lang==="en"?"en-US":"fa-IR";
  const content=(key:string)=>storefrontText(settings,key,lang);
  const option=(key:string,fallback:string)=>{
    const localized=lang==="en"?themeOptions[`${key}_en`]:undefined;
    const raw=localized??themeOptions[key];
    return typeof raw==="string"&&raw.trim()?raw:fallback;
  };
  const flag=(key:string,fallback:boolean)=>typeof themeOptions[key]==="boolean"?Boolean(themeOptions[key]):fallback;
  const mode=(key:string,fallback:string)=>typeof themeOptions[key]==="string"?String(themeOptions[key]):fallback;
  const number=(value:number,options?:Intl.NumberFormatOptions)=>Number(value||0).toLocaleString(locale,options);
  const openChat=()=>window.dispatchEvent(new Event("twinpanel:open-chat"));

  const density=mode("editorial_density","balanced");
  const heroLayout=mode("editorial_hero_layout","split");
  const planLayout=mode("editorial_plan_layout","spotlight");
  const corners=mode("editorial_corner_style","soft");
  const headerStyle=mode("editorial_header_style","floating");
  const showStatusBoard=flag("editorial_show_status_board",true);
  const showTrustStrip=flag("editorial_show_trust_strip",true);
  const showSectionNumbers=flag("editorial_show_section_numbers",true);
  const showPlanBenefits=flag("editorial_show_plan_benefits",true);
  const showProtocolMarks=flag("editorial_show_protocol_marks",true);
  const showGuideScreenshots=flag("editorial_show_guide_screenshots",true);

  const availableProtocols=useMemo(()=>{
    const found=new Set<string>();
    plans.forEach(plan=>planProtocols(plan).forEach(protocol=>found.add(protocol)));
    const ordered=Object.keys(PROTOCOLS).filter(protocol=>found.size===0||found.has(protocol));
    return ordered.length?ordered:Object.keys(PROTOCOLS);
  },[plans]);

  const visibleSections=settings.section_order.filter(section=>isStorefrontSectionVisible(settings,section));
  const navLabels:Partial<Record<StorefrontSectionId,string>>={
    plans:pick("پلن‌ها","Plans"),protocols:pick("اتصال","Connect"),services:pick("امکانات","Experience"),guides:pick("راهنما","Guides"),account:pick("حساب","Account"),faq:pick("سوالات","FAQ"),
  };

  const guideProtocolIds=GUIDE_PROTOCOL_ORDER.filter(protocol=>availableProtocols.includes(protocol));
  const activeGuideProtocol=(guideProtocolIds.includes(guideProtocol)?guideProtocol:(guideProtocolIds[0]||"wireguard")) as StoreGuideProtocol;
  const selectedPlatform=storeGuidePlatforms.find(item=>item.id===guidePlatform)||storeGuidePlatforms[0];
  const selectedProtocol=PROTOCOLS[activeGuideProtocol]||PROTOCOLS.wireguard;
  const guide=storeGuideContent[activeGuideProtocol];
  const guideEntry=guide.systems[guidePlatform];
  const guideAppImage=storeGuideAppImage(guidePlatform,activeGuideProtocol);
  const faqItems=[1,2,3,4,5].map(index=>({question:content(`faq_${index}_question`),answer:content(`faq_${index}_answer`)}));
  const featuredPlanIndex=plans.length>2?1:0;

  const sectionIntro=(numberText:string,tag:string,title:string,description:string)=><div className={styles.sectionIntro}>
    {showSectionNumbers&&<span className={styles.sectionIndex}>{numberText}</span>}
    <div className={styles.sectionTitle}><small>{tag}</small><h2>{title}</h2></div>
    <p>{description}</p>
  </div>;

  const plansSection=<section className={styles.section} id="plans" key="plans">
    {sectionIntro("01",content("plans_tag"),content("plans_title"),content("plans_description"))}
    {loading?<div className={styles.state}>{pick("در حال دریافت پلن‌های فعال...","Loading active plans...")}</div>:plans.length===0?<div className={styles.state}>{pick("در حال حاضر پلن فعالی برای فروش وجود ندارد.","There are currently no active plans for sale.")}</div>:<div className={styles.planGrid} data-layout={planLayout} data-count={Math.min(plans.length,4)}>{plans.map((plan,index)=>{
      const protocols=planProtocols(plan);
      const featured=planLayout==="spotlight"&&index===featuredPlanIndex;
      return <article className={`${styles.planCard} ${featured?styles.planFeatured:""}`} key={plan.id}>
        <div className={styles.planTop}><span className={styles.planNumber}>{String(index+1).padStart(2,"0")}</span>{featured&&<span className={styles.recommended}>{option("editorial_recommended_label",pick("انتخاب پیشنهادی","Recommended"))}</span>}</div>
        <div className={styles.planMain}><div className={styles.planName}><small>{pick("اشتراک","Subscription")}</small><h3>{plan.name}</h3>{plan.description&&<p>{plan.description}</p>}</div><div className={styles.price}><strong>{number(plan.price_toman)}</strong><span>{pick("تومان","Toman")}</span></div></div>
        <div className={styles.planFacts}><div><small>{pick("حجم","Traffic")}</small><b>{number(plan.traffic_gb,{maximumFractionDigits:2})} GB</b></div><div><small>{pick("مدت","Duration")}</small><b>{number(plan.duration_days)} {pick("روز","days")}</b></div><div><small>{pick("دستگاه","Devices")}</small><b>{number(plan.device_limit)}</b></div></div>
        <div className={styles.planBottom}>{showProtocolMarks&&<div className={styles.protocolChips}>{protocols.slice(0,5).map(protocol=><span key={protocol}>{PROTOCOLS[protocol]?.short||protocol}</span>)}</div>}{showPlanBenefits&&<ul className={styles.planBenefits}><li>{content("plan_feature_1")}</li><li>{content("plan_feature_2")}</li><li>{content("plan_feature_3")}</li></ul>}<button className={styles.buyButton} disabled={buying===plan.id} onClick={()=>onBuy(plan)}><span>{buying===plan.id?pick("در حال ثبت سفارش...","Creating order..."):pick("انتخاب این پلن","Choose this plan")}</span><i>↗</i></button></div>
      </article>;
    })}</div>}
  </section>;

  const protocolsSection=<section className={styles.section} id="protocols" key="protocols">
    {sectionIntro("02",content("protocols_tag"),content("protocols_title"),content("protocols_description"))}
    <div className={styles.protocolList}>{availableProtocols.map((id,index)=>{const protocol=PROTOCOLS[id];return <article key={id}><span className={styles.protocolIndex}>{String(index+1).padStart(2,"0")}</span>{showProtocolMarks&&<span className={styles.protocolMark}>{protocol.mark}</span>}<div><h3>{protocol.name}</h3><p>{pick(protocol.fa,protocol.en)}</p></div><span className={styles.protocolAvailable}>{option("editorial_protocol_available_label",pick("آماده استفاده","Available"))}</span></article>;})}</div>
  </section>;

  const servicesSection=<section className={styles.section} id="services" key="services">
    {sectionIntro("03",content("services_tag"),content("services_title"),content("services_description"))}
    <div className={styles.serviceGrid}>{[1,2,3,4,5,6].map((item,index)=><article key={item}><span>{showSectionNumbers?String(index+1).padStart(2,"0"):"•"}</span><div><h3>{content(`service_${item}_title`)}</h3><p>{content(`service_${item}_description`)}</p></div></article>)}</div>
  </section>;

  const guidesSection=<section className={styles.section} id="guides" key="guides">
    {sectionIntro("04",content("guides_tag"),content("guides_title"),content("guides_description"))}
    <div className={styles.guideLayout}><aside className={styles.guideRail}><div><small>{pick("پروتکل","Protocol")}</small>{guideProtocolIds.map(id=><button key={id} className={activeGuideProtocol===id?styles.active:""} type="button" onClick={()=>setGuideProtocol(id)}><span>{PROTOCOLS[id].mark}</span>{PROTOCOLS[id].short}</button>)}</div><div><small>{pick("سیستم‌عامل","Operating system")}</small>{storeGuidePlatforms.map(platform=><button key={platform.id} className={guidePlatform===platform.id?styles.active:""} type="button" onClick={()=>setGuidePlatform(platform.id)}><span>{platform.icon}</span>{pick(platform.fa,platform.en)}</button>)}</div></aside>
      <div className={styles.guideArticle}><header><div className={styles.guideApp}>{guideAppImage?<img src={guideAppImage} alt={`${guideEntry.client} - ${selectedProtocol.name}`} loading="lazy" decoding="async" onError={event=>{event.currentTarget.style.display="none";}}/>:<span>{selectedPlatform.icon}</span>}</div><div><small>{selectedProtocol.name} / {pick(selectedPlatform.fa,selectedPlatform.en)}</small><h3>{guideEntry.client}</h3><p>{guide.summary}</p></div>{guideEntry.downloadUrl?<a href={guideEntry.downloadUrl} target="_blank" rel="noopener noreferrer">{guideEntry.downloadLabel}<span>↗</span></a>:<em>✓ {guideEntry.downloadLabel}</em>}</header>
        {guideEntry.warning&&<div className={styles.guideWarning}><b>{pick("قبل از شروع","Before you start")}</b><span>{guideEntry.warning}</span></div>}
        <div className={styles.guideMeta}><div><small>{pick("پروتکل","Protocol")}</small><b>{selectedProtocol.name}</b></div><div><small>{pick("سیستم‌عامل","Operating system")}</small><b>{pick(selectedPlatform.fa,selectedPlatform.en)}</b></div><div><small>{pick("اطلاعات لازم","Required data")}</small><b dir="ltr">{guideEntry.credential}</b></div></div>
        <div className={styles.guideSteps}>{guideEntry.steps.map((step,index)=>{const screenshot=storeGuideScreenshot(guidePlatform,activeGuideProtocol,index);return <article key={`${activeGuideProtocol}-${guidePlatform}-${step.title}`}><span>{String(index+1).padStart(2,"0")}</span><div><h4>{step.title}</h4><p>{step.detail}</p>{showGuideScreenshots&&<figure><img src={screenshot} alt={`${step.title} - ${selectedProtocol.name}`} loading="lazy" decoding="async" onError={event=>{const figure=event.currentTarget.closest("figure");if(figure instanceof HTMLElement)figure.style.display="none";}}/></figure>}</div></article>;})}</div>
        <div className={styles.troubleshoot}><div><small>{pick("اگر وصل نشد","If it does not connect")}</small><h3>{pick("عیب‌یابی سریع","Quick troubleshooting")}</h3></div><ul>{guideEntry.fixes.map(fix=><li key={fix}>{fix}</li>)}</ul><Link href="/panel">{pick("اطلاعات اتصال از پنل","Connection details from panel")} ↗</Link></div>
      </div></div>
  </section>;

  const accountSection=<section className={`${styles.section} ${styles.accountSection}`} id="account" key="account"><div className={styles.accountIntro}>{showSectionNumbers&&<span className={styles.sectionIndex}>05</span>}<small>{content("account_tag")}</small><h2>{content("account_title")}</h2><p>{content("account_description")}</p><div><Link href="/panel">{content("account_primary_button")}</Link><button type="button" onClick={openChat}>{content("account_secondary_button")}</button></div></div><div className={styles.accountItems}>{[1,2,3,4].map(item=><article key={item}><span>0{item}</span><b>{content(`account_item_${item}_title`)}</b><small>{content(`account_item_${item}_description`)}</small></article>)}</div></section>;

  const faqSection=<section className={styles.section} id="faq" key="faq">{sectionIntro("06",content("faq_tag"),content("faq_title"),content("faq_description"))}<div className={styles.faqList}>{faqItems.map((item,index)=><details key={`${index}-${item.question}`} open={index===0}><summary><span>{String(index+1).padStart(2,"0")}</span><b>{item.question}</b><i>＋</i></summary><p>{item.answer}</p></details>)}</div></section>;

  const sections:Record<StorefrontSectionId,ReactNode>={plans:plansSection,protocols:protocolsSection,services:servicesSection,guides:guidesSection,account:accountSection,faq:faqSection};

  return <div className={styles.root} data-store-template="editorial-grid-2027" data-density={density} data-hero={heroLayout} data-corners={corners} data-header={headerStyle} dir={lang==="fa"?"rtl":"ltr"}>
    <header className={styles.header}><div className={styles.headerInner}><Link href="/store" className={styles.brand}><img src={brand.logoUrl} alt={brand.name}/><div><b>{brand.name}</b><small>{pick("فروشگاه رسمی","Official Store")}</small></div></Link><nav>{visibleSections.map(section=><a key={section} href={`#${section}`}>{navLabels[section]}</a>)}</nav><div className={styles.headerActions}><LanguageSwitch compact/><ThemeSwitch compact/><Link href="/login">{pick("ورود","Sign in")}</Link><button className={styles.menuButton} type="button" onClick={()=>setMenuOpen(value=>!value)} aria-label={pick("منو","Menu")}>☰</button></div></div>{menuOpen&&<div className={styles.mobileMenu}>{visibleSections.map(section=><a key={section} href={`#${section}`} onClick={()=>setMenuOpen(false)}>{navLabels[section]}</a>)}<Link href="/login" onClick={()=>setMenuOpen(false)}>{pick("ورود به حساب","Sign in")}</Link></div>}</header>

    <main>
      <section className={styles.hero}><div className={styles.heroCopy}><div className={styles.heroMeta}><span>{content("hero_kicker")}</span><small>EDITORIAL PRO / 2027</small></div><h1>{content("hero_title")} <em>{content("hero_highlight")}</em></h1><p>{content("hero_description")}</p><div className={styles.heroActions}>{settings.show_plans&&<a href="#plans">{content("hero_primary_button")}<span>↗</span></a>}<a href="#guides">{content("hero_secondary_button")}</a></div><div className={styles.heroProof}><span>{content("hero_proof_1")}</span><span>{content("hero_proof_2")}</span><span>{content("hero_proof_3")}</span></div></div>
        {showStatusBoard&&<div className={styles.heroBoard}><div className={styles.boardTop}><span>{option("editorial_status_label",pick("وضعیت شبکه","Network status"))}</span><b>{option("editorial_status_value","ONLINE")}</b></div><div className={styles.boardMetric}><strong>{String(availableProtocols.length).padStart(2,"0")}</strong><span>{pick("روش اتصال فعال","active connection methods")}</span></div><div className={styles.boardStats}><div><small>{pick("پایداری","Uptime")}</small><b>{content("trust_uptime_value")}</b></div><div><small>{option("editorial_delivery_label",pick("تحویل سرویس","Delivery"))}</small><b>{option("editorial_delivery_value",pick("داخل پنل کاربری","In your account"))}</b></div></div><span className={styles.boardStamp}>{brand.shortName}</span></div>}
      </section>

      {showTrustStrip&&<section className={styles.trustStrip}><article><span>01</span><b>{content("trust_speed_title")}</b><small>{content("trust_speed_description")}</small></article><article><span>02</span><b>{content("trust_uptime_value")}</b><small>{content("trust_uptime_description")}</small></article><article><span>03</span><b>{content("trust_support_title")}</b><small>{content("trust_support_description")}</small></article><article><span>04</span><b>{number(availableProtocols.length)}</b><small>{content("trust_protocols_description")}</small></article></section>}
      {error&&<div className={`${styles.alert} ${styles.alertError}`}>{error}</div>}{message&&<div className={`${styles.alert} ${styles.alertSuccess}`}>{message}</div>}
      {visibleSections.map(section=>sections[section])}
      {settings.show_final_cta&&<section className={styles.finalCta}><small>{content("final_cta_tag")}</small><h2>{content("final_cta_title")}</h2><p>{content("final_cta_description")}</p><a href="#plans">{content("final_cta_button")}<i>↗</i></a></section>}
      {settings.show_contact&&<section className={styles.contact} id="contact"><div><small>{content("contact_tag")}</small><h2>{content("contact_title")}</h2><p>{content("contact_description")}</p><button type="button" onClick={openChat}>{content("chat_title")}<span>↗</span></button></div><div className={styles.contactLinks}>{settings.show_telegram&&<a href={settings.telegram_url} target="_blank" rel="noreferrer"><span>01</span><b>{content("telegram_title")}</b><small>{content("telegram_description")}</small></a>}{settings.show_instagram&&<a href={settings.instagram_url} target="_blank" rel="noreferrer"><span>02</span><b>{content("instagram_title")}</b><small>{content("instagram_description")}</small></a>}{settings.show_whatsapp&&<a href={settings.whatsapp_url} target="_blank" rel="noreferrer"><span>03</span><b>{content("whatsapp_title")}</b><small>{content("whatsapp_description")}</small></a>}</div></section>}
    </main>

    <footer className={styles.footer}><div className={styles.footerBrand}><img src={brand.logoUrl} alt={brand.name}/><div><b>{brand.name}</b><p>{content("footer_tagline")}</p></div></div><div><b>{content("footer_quick_title")}</b>{settings.show_plans&&<a href="#plans">{pick("پلن‌ها","Plans")}</a>}{settings.show_guides&&<a href="#guides">{pick("راهنمای اتصال","Setup guides")}</a>}<Link href="/panel">{pick("پنل کاربری","Customer panel")}</Link></div><div><b>{content("footer_support_title")}</b><button onClick={openChat}>{content("chat_title")}</button>{settings.show_telegram&&<a href={settings.telegram_url} target="_blank" rel="noreferrer">{content("telegram_title")}</a>}<Link href="/login">{pick("ورود","Sign in")}</Link></div><div className={styles.footerBottom}><span>© {new Date().getFullYear()} {brand.name}</span><span>{content("footer_rights")}</span></div></footer>

    <button className={styles.chatButton} type="button" onClick={openChat} aria-label={pick("باز کردن چت آنلاین","Open live chat")}>{pick("پشتیبانی","Support")}<span>↗</span></button>{plans.length>0&&<a className={styles.mobileBuy} href="#plans"><span>{content("hero_primary_button")}</span><b>{number(plans[0].price_toman)} {pick("تومان","Toman")}</b></a>}
  </div>;
}
