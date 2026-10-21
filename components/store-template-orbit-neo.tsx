"use client";

import Link from "next/link";
import {useState,type CSSProperties,type ReactNode} from "react";
import {LanguageSwitch,useI18n} from "../lib/i18n";
import {ThemeSwitch} from "../lib/theme";
import {useBranding} from "../lib/branding";
import {planProtocols,type StorePlan} from "../lib/store-runtime-api";
import {STORE_PROTOCOL_CATALOG,storeProtocolMeta} from "../lib/store-protocol-catalog";
import {storefrontText,type StorefrontSectionId} from "../lib/storefront-config";
import {
  ORBIT_DEFAULTS,
  type OrbitThemeDraft,
} from "../lib/store-template-orbit-options";
import type {StoreTemplateOptionMap} from "../lib/store-template-options";
import {
  storeGuideAppImage,
  storeGuideContent,
  storeGuidePlatforms,
  type StoreGuidePlatform,
  type StoreGuideProtocol,
} from "../lib/store-guide-content";
import type {StoreTemplateProps} from "./store-template-renderer";
import styles from "./store-template-orbit-neo.module.css";

type Props=StoreTemplateProps&{themeOptions:StoreTemplateOptionMap};
type ProtocolMeta={name:string;short:string;symbol:string;fa:string;en:string};

const PROTOCOLS:Record<string,ProtocolMeta>={
  cisco:{name:"Cisco / OpenConnect",short:"Cisco",symbol:"C",fa:"اتصال کاربری پایدار و سازگار با دستگاه‌های مختلف.",en:"Stable account-based connectivity across many devices."},
  openvpn:{name:"OpenVPN",short:"OpenVPN",symbol:"O",fa:"روش کلاسیک و مطمئن با پشتیبانی گسترده.",en:"A proven classic with broad platform support."},
  wireguard:{name:"WireGuard",short:"WireGuard",symbol:"W",fa:"سبک، سریع و مناسب اتصال مدرن.",en:"Fast, lightweight and ideal for modern connectivity."},
  l2tp:{name:"L2TP / IPsec",short:"L2TP",symbol:"L",fa:"راه‌اندازی از تنظیمات داخلی بسیاری از دستگاه‌ها.",en:"Built into the VPN settings of many devices."},
  v2ray:{name:"V2Ray / Xray",short:"V2Ray",symbol:"V",fa:"انعطاف‌پذیر برای سناریوهای شبکه متنوع.",en:"Flexible for varied network scenarios."},
};
const GUIDE_ORDER:StoreGuideProtocol[]=["cisco","openvpn","wireguard","l2tp","v2ray"];
const GUIDE_POSTER_COPY:Record<StoreGuideProtocol,{fa:string;en:string}>={
  cisco:{fa:"افزودن سرور، ورود حساب و اتصال نهایی",en:"Add the server, sign in, and connect"},
  openvpn:{fa:"دریافت فایل OVPN، افزودن پروفایل و اتصال نهایی",en:"Import the OVPN file, add the profile, and connect"},
  wireguard:{fa:"دریافت کانفیگ، افزودن Tunnel و اتصال نهایی",en:"Import config, create tunnel, and connect"},
  l2tp:{fa:"افزودن VPN، ورود اطلاعات حساب و اتصال نهایی",en:"Add the VPN, enter account details, and connect"},
  v2ray:{fa:"دریافت اطلاعات اتصال، افزودن پروفایل و اتصال نهایی",en:"Import connection details, add the profile, and connect"},
};

function stringOption(options:StoreTemplateOptionMap,key:string,fallback:string){
  const value=options[key];
  return typeof value==="string"&&value.trim()?value:fallback;
}
function booleanOption(options:StoreTemplateOptionMap,key:string,fallback:boolean){
  return typeof options[key]==="boolean"?Boolean(options[key]):fallback;
}
function image(options:StoreTemplateOptionMap,key:string){
  const value=options[key];
  return typeof value==="string"&&value.trim()?value:"";
}

export function OrbitNeo2027Template({themeOptions,settings,plans,loading,error,message,buying,onBuy}:Props){
  const {pick,lang}=useI18n();
  const {brand}=useBranding();
  const [mobileOpen,setMobileOpen]=useState(false);
  const [guidePlatform,setGuidePlatform]=useState<StoreGuidePlatform>("android");
  const [guideProtocol,setGuideProtocol]=useState<StoreGuideProtocol>("wireguard");
  const defaults=ORBIT_DEFAULTS as OrbitThemeDraft;
  const locale=lang==="en"?"en-US":"fa-IR";

  const copy=(key:string)=>{
    const localized=lang==="en"?`${key}_en`:key;
    const direct=themeOptions[localized];
    if(typeof direct==="string"&&direct.trim())return direct;
    const themeFallback=defaults[localized]??defaults[key];
    if(typeof themeFallback==="string"&&themeFallback.trim())return themeFallback;
    return storefrontText(settings,key,lang);
  };
  const number=(value:number,options?:Intl.NumberFormatOptions)=>Number(value||0).toLocaleString(locale,options);
  const openChat=()=>window.dispatchEvent(new Event("twinpanel:open-chat"));

  const availableProtocols=Object.keys(PROTOCOLS);
  const guideProtocolIds=GUIDE_ORDER;
  const activeGuideProtocol=guideProtocolIds.includes(guideProtocol)?guideProtocol:guideProtocolIds[0];
  const selectedPlatform=storeGuidePlatforms.find(item=>item.id===guidePlatform)||storeGuidePlatforms[0];
  const selectedProtocol=PROTOCOLS[activeGuideProtocol]||{name:activeGuideProtocol,short:activeGuideProtocol,symbol:"•",fa:"",en:""};
  const guide=storeGuideContent[activeGuideProtocol];
  const guideEntry=guide.systems[guidePlatform];
  const guideAppImage=storeGuideAppImage(guidePlatform,activeGuideProtocol);
  const posterCopy=GUIDE_POSTER_COPY[activeGuideProtocol];

  const order=Array.isArray(themeOptions.section_order)
    ?themeOptions.section_order.map(String).filter(section=>["plans","protocols","services","guides","account","faq"].includes(section)) as StorefrontSectionId[]
    :["plans","protocols","services","guides","account","faq"] as StorefrontSectionId[];
  const visible=(section:StorefrontSectionId)=>booleanOption(themeOptions,`show_${section}`,true);
  const visibleOrder=order.filter(visible);
  const navLabels:Record<StorefrontSectionId,string>={
    plans:pick("پلن‌ها","Plans"),protocols:pick("پروتکل‌ها","Protocols"),services:pick("امکانات","Features"),guides:pick("آموزش","Guides"),account:pick("پنل کاربری","Account"),faq:pick("سوالات","FAQ"),
  };

  const style={
    "--orbit-primary":stringOption(themeOptions,"theme_primary",String(defaults.theme_primary)),
    "--orbit-secondary":stringOption(themeOptions,"theme_secondary",String(defaults.theme_secondary)),
    "--orbit-dark-page":stringOption(themeOptions,"orbit_dark_page",String(defaults.orbit_dark_page)),
    "--orbit-dark-surface":stringOption(themeOptions,"orbit_dark_surface",String(defaults.orbit_dark_surface)),
    "--orbit-dark-surface-alt":stringOption(themeOptions,"orbit_dark_surface_alt",String(defaults.orbit_dark_surface_alt)),
    "--orbit-dark-text":stringOption(themeOptions,"orbit_dark_text",String(defaults.orbit_dark_text)),
    "--orbit-dark-muted":stringOption(themeOptions,"orbit_dark_muted",String(defaults.orbit_dark_muted)),
    "--orbit-dark-border":stringOption(themeOptions,"orbit_dark_border",String(defaults.orbit_dark_border)),
    "--orbit-light-page":stringOption(themeOptions,"orbit_light_page",String(defaults.orbit_light_page)),
    "--orbit-light-surface":stringOption(themeOptions,"orbit_light_surface",String(defaults.orbit_light_surface)),
    "--orbit-light-surface-alt":stringOption(themeOptions,"orbit_light_surface_alt",String(defaults.orbit_light_surface_alt)),
    "--orbit-light-text":stringOption(themeOptions,"orbit_light_text",String(defaults.orbit_light_text)),
    "--orbit-light-muted":stringOption(themeOptions,"orbit_light_muted",String(defaults.orbit_light_muted)),
    "--orbit-light-border":stringOption(themeOptions,"orbit_light_border",String(defaults.orbit_light_border)),
    "--orbit-button-text":stringOption(themeOptions,"orbit_button_text",String(defaults.orbit_button_text)),
  } as CSSProperties;

  const media={
    banner:image(themeOptions,"orbit_banner_image"),
    hero:image(themeOptions,"orbit_hero_image"),
    story:image(themeOptions,"orbit_story_image"),
    protocol:image(themeOptions,"orbit_protocol_image"),
    guides:image(themeOptions,"orbit_guides_image"),
    account:image(themeOptions,"orbit_account_image"),
    cta:image(themeOptions,"orbit_cta_image"),
    footer:image(themeOptions,"orbit_footer_image"),
  };
  const showMediaLabels=booleanOption(themeOptions,"orbit_show_media_labels",true);
  const featuredIndex=plans.length>2?Math.floor(plans.length/2):0;

  const plansSection=<section className={styles.section} id="plans" key="plans">
    <SectionHeading index="01" tag={copy("plans_tag")} title={copy("plans_title")} description={copy("plans_description")}/>
    {loading?<div className={styles.state}>{pick("در حال دریافت پلن‌های فعال...","Loading active plans...")}</div>:plans.length===0?<div className={styles.state}>{pick("در حال حاضر پلن فعالی برای فروش وجود ندارد.","There are currently no active plans for sale.")}</div>:<div className={styles.planRail} data-style={stringOption(themeOptions,"orbit_plan_style","tickets")}>{plans.map((plan,index)=><PlanCard key={plan.id} plan={plan} index={index} featured={index===featuredIndex} buying={buying===plan.id} number={number} pick={pick} copy={copy} onBuy={()=>onBuy(plan)}/>)}</div>}
    {error&&<div className={styles.errorState}>{error}</div>}{message&&<div className={styles.messageState}>{message}</div>}
  </section>;

  const protocolsSection=<section className={`${styles.section} ${styles.protocolSection}`} id="protocols" key="protocols">
    <SectionHeading index="02" tag={copy("protocols_tag")} title={copy("protocols_title")} description={copy("protocols_description")}/>
    <div className={styles.protocolStage}>
      <div className={styles.protocolMedia}>{media.protocol?<img src={media.protocol} alt={copy("protocols_title")}/>:<div className={styles.generatedOrb}><span>ORBIT</span><b>{availableProtocols.length}</b><small>{pick("روش اتصال کلاسیک","classic connection methods")}</small></div>}{showMediaLabels&&<em>{pick("CONNECTION MAP","CONNECTION MAP")}</em>}</div>
      <div className={styles.protocolGrid}>{availableProtocols.map((id,index)=>{const protocol=PROTOCOLS[id]||{name:id,short:id,symbol:"•",fa:"",en:""};return <article className={styles.protocolCard} key={id}><div className={styles.protocolIndex}>{String(index+1).padStart(2,"0")}</div><span className={styles.protocolSymbol}>{protocol.symbol}</span><div><h3 dir="ltr">{protocol.name}</h3><p>{pick(protocol.fa,protocol.en)}</p></div><small>{pick("فعال در پلن‌های سازگار","Available on supported plans")}</small></article>;})}</div>
    </div>
  </section>;

  const servicesSection=<section className={styles.section} id="services" key="services">
    <SectionHeading index="03" tag={copy("services_tag")} title={copy("services_title")} description={copy("services_description")}/>
    <div className={styles.bento}>
      <article className={styles.storyCard}>{media.story?<img src={media.story} alt={copy("services_title")}/>:<div className={styles.storyFallback}><span>✦</span><b>{pick("فضای تصویری امکانات","Feature visual stage")}</b></div>}<div className={styles.storyOverlay}><small>{copy("services_tag")}</small><strong>{copy("service_1_title")}</strong><p>{copy("service_1_description")}</p></div></article>
      {[2,3,4,5,6].map((item,index)=><article className={styles.bentoCard} key={item}><span>{["⌁","◎","▤","↗","◈"][index]}</span><div><small>0{item}</small><h3>{copy(`service_${item}_title`)}</h3><p>{copy(`service_${item}_description`)}</p></div></article>)}
    </div>
  </section>;

  const guidesSection=<section className={styles.section} id="guides" key="guides">
    <SectionHeading index="04" tag={copy("guides_tag")} title={copy("guides_title")} description={copy("guides_description")}/>
    <div className={styles.guideShell}>
      <aside className={styles.guideVisual}>{media.guides?<><img src={media.guides} alt={copy("guides_title")}/><div className={styles.guideVisualMeta}><small>{pick(selectedPlatform.fa,selectedPlatform.en)}</small><strong dir="ltr">{selectedProtocol.name}</strong><span>{guideEntry.client}</span></div></>:<div className={styles.guideFallback} role="img" aria-label={`${selectedProtocol.name} ${pick(selectedPlatform.fa,selectedPlatform.en)}`}><span>{pick(`آموزش اتصال ${selectedProtocol.name}`,`${selectedProtocol.name} Setup Guide`)}</span><strong>{pick(`برای ${selectedPlatform.fa}`,`for ${selectedPlatform.en}`)}</strong><small>{pick(posterCopy.fa,posterCopy.en)}</small></div>}</aside>
      <div className={styles.guideContent}>
        <div className={styles.guideSelectors}><div>{guideProtocolIds.map(protocol=><button type="button" key={protocol} className={protocol===activeGuideProtocol?styles.activeChip:""} onClick={()=>setGuideProtocol(protocol)}>{PROTOCOLS[protocol]?.short||protocol}</button>)}</div><div>{storeGuidePlatforms.map(platform=><button type="button" key={platform.id} className={platform.id===guidePlatform?styles.activeChip:""} onClick={()=>setGuidePlatform(platform.id)}><span>{platform.icon}</span>{pick(platform.fa,platform.en)}</button>)}</div></div>
        <div className={styles.guideApp}><div className={styles.guideAppIcon}>{guideAppImage?<img src={guideAppImage} alt={guideEntry.client}/>:<span>{selectedPlatform.icon}</span>}</div><div><small>{pick("نرم‌افزار / روش پیشنهادی","Recommended client / method")}</small><h3>{guideEntry.client}</h3><p>{guide.summary}</p></div>{guideEntry.downloadUrl?<a href={guideEntry.downloadUrl} target="_blank" rel="noopener noreferrer">{guideEntry.downloadLabel} ↗</a>:<span className={styles.noDownload}>✓ {guideEntry.downloadLabel}</span>}</div>
        {guideEntry.warning&&<div className={styles.guideWarning}><b>⚠</b><span>{guideEntry.warning}</span></div>}
        <div className={styles.steps}>{guideEntry.steps.map((step,index)=><article key={`${step.title}-${index}`}><i>{String(index+1).padStart(2,"0")}</i><div><b>{step.title}</b><p>{step.detail}</p></div></article>)}</div>
        <div className={styles.guideFoot}><div><small>{pick("اطلاعات موردنیاز","Required account data")}</small><b dir="ltr">{guideEntry.credential}</b></div><Link href="/panel">{pick("دریافت اطلاعات از پنل","Get details from panel")} ↗</Link></div>
      </div>
    </div>
  </section>;

  const accountSection=<section className={styles.section} id="account" key="account">
    <div className={styles.accountShell}>
      <div className={styles.accountCopy}><span className={styles.tag}>{copy("account_tag")}</span><h2>{copy("account_title")}</h2><p>{copy("account_description")}</p><div className={styles.accountActions}><Link href="/panel" className={styles.primaryButton}>{copy("account_primary_button")} ↗</Link><button type="button" className={styles.secondaryButton} onClick={openChat}>{copy("account_secondary_button")}</button></div><div className={styles.accountFacts}>{[1,2,3,4].map(index=><div key={index}><b>{storefrontText(settings,`account_item_${index}_title`,lang)}</b><small>{storefrontText(settings,`account_item_${index}_description`,lang)}</small></div>)}</div></div>
      <div className={styles.accountMedia}>{media.account?<img src={media.account} alt={copy("account_title")}/>:<div className={styles.controlDeck}><span>CONTROL DECK</span><strong>01</strong><i/><i/><i/><small>{pick("اشتراک · حجم · پرداخت · اتصال","Subscription · usage · payments · access")}</small></div>}</div>
    </div>
  </section>;

  const faqSection=<section className={styles.section} id="faq" key="faq">
    <SectionHeading index="06" tag={copy("faq_tag")} title={copy("faq_title")} description={copy("faq_description")}/>
    <div className={styles.faqGrid}>{[1,2,3,4,5].map((item,index)=><details className={styles.faqItem} key={item} open={index===0}><summary><span>0{item}</span><b>{copy(`faq_${item}_question`)}</b><i>＋</i></summary><p>{copy(`faq_${item}_answer`)}</p></details>)}</div>
  </section>;

  const sections:Record<StorefrontSectionId,ReactNode>={plans:plansSection,protocols:protocolsSection,services:servicesSection,guides:guidesSection,account:accountSection,faq:faqSection};
  const social=[
    settings.show_telegram&&settings.telegram_url?{name:"Telegram",url:settings.telegram_url,mark:"TG"}:null,
    settings.show_instagram&&settings.instagram_url?{name:"Instagram",url:settings.instagram_url,mark:"IG"}:null,
    settings.show_whatsapp&&settings.whatsapp_url?{name:"WhatsApp",url:settings.whatsapp_url,mark:"WA"}:null,
  ].filter(Boolean) as {name:string;url:string;mark:string}[];

  return <div className={styles.root} style={style} data-motion={booleanOption(themeOptions,"orbit_motion",true)?"on":"off"} data-shape={stringOption(themeOptions,"orbit_card_shape","round")} data-header={stringOption(themeOptions,"orbit_header_style","dock")}>
    {booleanOption(themeOptions,"orbit_show_top_banner",true)&&<a href="#plans" className={styles.topBanner} style={media.banner?{backgroundImage:`linear-gradient(90deg,rgba(5,6,10,.86),rgba(5,6,10,.48)),url(${media.banner})`}:undefined}><span>✦</span><b>{copy("orbit_banner_title")}</b><em>{copy("orbit_banner_action")} ↗</em></a>}
    <header className={styles.header}>
      <Link href="/store" className={styles.brand}>{brand.logoUrl?<img src={brand.logoUrl} alt={brand.name}/>:<span>{String(brand.name||"T").slice(0,1)}</span>}<div><b>{brand.name}</b><small>ORBIT NEO / 2027</small></div></Link>
      <nav className={mobileOpen?styles.navOpen:""}>{visibleOrder.map(section=><a key={section} href={`#${section}`} onClick={()=>setMobileOpen(false)}>{navLabels[section]}</a>)}</nav>
      <div className={styles.headerActions}><LanguageSwitch/><ThemeSwitch/><Link href="/panel" className={styles.panelLink}>{pick("حساب من","My account")}</Link><button type="button" className={styles.menuButton} onClick={()=>setMobileOpen(value=>!value)} aria-label={pick("منو","Menu")}>☰</button></div>
    </header>

    <main>
      <section className={styles.hero}>
        <div className={styles.heroCopy}><span className={styles.tag}>{copy("hero_kicker")}</span><h1>{copy("hero_title")}<strong>{copy("hero_highlight")}</strong></h1><p>{copy("hero_description")}</p><div className={styles.heroActions}><a href="#plans" className={styles.primaryButton}>{copy("hero_primary_button")} ↗</a><a href="#guides" className={styles.secondaryButton}>{copy("hero_secondary_button")}</a></div><div className={styles.proofs}>{[1,2,3].map(index=><span key={index}><i>✓</i>{copy(`hero_proof_${index}`)}</span>)}</div></div>
        <div className={styles.heroMedia}>{media.hero?<img src={media.hero} alt={copy("hero_title")}/>:<div className={styles.heroGenerated}><div className={styles.heroOrbitRing}/><span>ORBIT</span><strong>{plans.length||"∞"}</strong><small>{pick("پلن / مسیر زنده","live plans / routes")}</small></div>}{showMediaLabels&&<div className={styles.mediaLabel}><span>LIVE STOREFRONT</span><b>{pick("تصویر Hero قابل آپلود","Uploadable hero media")}</b></div>}{booleanOption(themeOptions,"orbit_show_metrics",true)&&<div className={styles.metrics}><div><small>{pick("پروتکل","Protocols")}</small><b>{STORE_PROTOCOL_CATALOG.length}</b></div><div><small>{pick("پلن فعال","Live plans")}</small><b>{plans.length}</b></div><div><small>{pick("مدیریت","Control")}</small><b>24/7</b></div></div>}</div>
      </section>

      <div className={styles.marquee}><span>PRIVATE ACCESS</span><i/> <span>MULTI PROTOCOL</span><i/> <span>REAL PLANS</span><i/> <span>SETUP LAB</span><i/> <span>ACCOUNT CONTROL</span></div>
      {visibleOrder.map(section=>sections[section])}

      {booleanOption(themeOptions,"show_final_cta",true)&&<section className={styles.finalCta} style={media.cta?{backgroundImage:`linear-gradient(90deg,rgba(5,6,10,.9),rgba(5,6,10,.38)),url(${media.cta})`}:undefined}><div><span className={styles.tag}>{copy("final_cta_tag")}</span><h2>{copy("final_cta_title")}</h2><p>{copy("final_cta_description")}</p></div><a href="#plans" className={styles.ctaButton}>{copy("final_cta_button")} ↗</a></section>}

      {booleanOption(themeOptions,"show_contact",true)&&<section className={`${styles.section} ${styles.contactSection}`} id="contact"><SectionHeading index="07" tag={copy("contact_tag")} title={copy("contact_title")} description={copy("contact_description")}/><div className={styles.contactGrid}>{social.map(item=><a href={item.url} target="_blank" rel="noopener noreferrer" key={item.name}><span>{item.mark}</span><div><b>{item.name}</b><small>{pick("باز کردن کانال ارتباطی","Open contact channel")}</small></div><i>↗</i></a>)}<button type="button" onClick={openChat}><span>LIVE</span><div><b>{storefrontText(settings,"chat_title",lang)}</b><small>{storefrontText(settings,"chat_description",lang)}</small></div><i>↗</i></button></div></section>}
    </main>

    <footer className={styles.footer}><div className={styles.footerBrand}>{media.footer?<img src={media.footer} alt="Orbit footer artwork"/>:<span>✦</span>}<div><b>{brand.name}</b><p>{copy("footer_tagline")}</p></div></div><div className={styles.footerLinks}><a href="#plans">{pick("پلن‌ها","Plans")}</a><a href="#guides">{pick("آموزش","Guides")}</a><Link href="/panel">{pick("پنل کاربری","Account")}</Link><button type="button" onClick={openChat}>{pick("پشتیبانی","Support")}</button></div><small>© {new Date().getFullYear()} {brand.name}. {copy("footer_rights")}</small></footer>
  </div>;
}

function SectionHeading({index,tag,title,description}:{index:string;tag:string;title:string;description:string}){
  return <header className={styles.sectionHead}><div className={styles.sectionNumber}>{index}</div><div><span className={styles.tag}>{tag}</span><h2>{title}</h2><p>{description}</p></div></header>;
}

function PlanCard({plan,index,featured,buying,number,pick,copy,onBuy}:{plan:StorePlan;index:number;featured:boolean;buying:boolean;number:(value:number,options?:Intl.NumberFormatOptions)=>string;pick:(fa:string,en:string)=>string;copy:(key:string)=>string;onBuy:()=>void}){
  const protocols=planProtocols(plan);
  return <article className={`${styles.planCard} ${featured?styles.planFeatured:""}`}>
    <header><span>{String(index+1).padStart(2,"0")}</span>{featured&&<em>{pick("پیشنهادی","Recommended")}</em>}<small>{pick("VPN SUBSCRIPTION","VPN SUBSCRIPTION")}</small></header>
    <div className={styles.planName}><h3>{plan.name}</h3>{plan.description&&<p>{plan.description}</p>}</div>
    <div className={styles.planPrice}><strong>{number(plan.price_toman)}</strong><span>{pick("تومان","Toman")}</span></div>
    <div className={styles.planFacts}><div><small>{pick("حجم","Traffic")}</small><b>{number(plan.traffic_gb,{maximumFractionDigits:2})} GB</b></div><div><small>{pick("مدت","Duration")}</small><b>{number(plan.duration_days)} {pick("روز","days")}</b></div><div><small>{pick("دستگاه","Devices")}</small><b>{number(plan.device_limit)}</b></div></div>
    <div className={styles.planBenefits}>{[1,2,3].map(item=><span key={item}>✓ {copy(`plan_feature_${item}`)}</span>)}</div>
    <div className={styles.planProtocols}>{protocols.slice(0,6).map(protocol=><span key={protocol}>{storeProtocolMeta(protocol)?.short||PROTOCOLS[protocol]?.short||protocol}</span>)}</div>
    <button type="button" disabled={buying} onClick={onBuy}>{buying?pick("در حال ثبت سفارش...","Creating order..."):pick("خرید این پلن","Buy this plan")}<span>↗</span></button>
  </article>;
}
