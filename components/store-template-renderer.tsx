"use client";

import Link from "next/link";
import {useState,type ReactNode} from "react";
import {LanguageSwitch,useI18n} from "../lib/i18n";
import {ThemeSwitch} from "../lib/theme";
import {useBranding} from "../lib/branding";
import {planProtocols,StorePlan} from "../lib/store-runtime-api";
import {STORE_PROTOCOL_CATALOG,storeProtocolMeta} from "../lib/store-protocol-catalog";
import {
  StorefrontSectionId,
  StorefrontSettings,
  isStorefrontSectionVisible,
  storefrontText,
} from "../lib/storefront-config";
import {DEFAULT_STORE_TEMPLATE_ID,resolveStoreTemplateId} from "../lib/store-template-registry";
import {
  storeGuideAppImage,
  storeGuideContent,
  storeGuidePlatforms,
  storeGuideTutorialImage,
  type StoreGuidePlatform,
  type StoreGuideProtocol,
} from "../lib/store-guide-content";

export type StoreTemplateProps={
  settings:StorefrontSettings;
  plans:StorePlan[];
  loading:boolean;
  error:string;
  message:string;
  buying:number|null;
  onBuy:(plan:StorePlan)=>void;
};

type ProtocolMeta={name:string;short:string;icon:string;fa:string;en:string;tone:string};

const protocolMeta:Record<string,ProtocolMeta>={
  cisco:{name:"Cisco / OpenConnect",short:"Cisco",icon:"◫",tone:"blue",fa:"مناسب اتصال پایدار با نام کاربری و رمز و سازگاری گسترده.",en:"Stable username/password connectivity with broad compatibility."},
  openvpn:{name:"OpenVPN",short:"OpenVPN",icon:"◉",tone:"orange",fa:"پایدار، امن و قابل استفاده روی اکثر سیستم‌عامل‌ها.",en:"Stable, secure and widely supported across operating systems."},
  wireguard:{name:"WireGuard",short:"WireGuard",icon:"⌁",tone:"red",fa:"سبک، سریع و مناسب اتصال مدرن با فایل یا QR.",en:"Fast, lightweight and ideal for modern file or QR setup."},
  l2tp:{name:"L2TP / IPsec",short:"L2TP",icon:"⌬",tone:"green",fa:"بدون اپ اضافی روی بسیاری از دستگاه‌ها قابل راه‌اندازی است.",en:"Can be configured from built-in VPN settings on many devices."},
  v2ray:{name:"V2Ray / Xray",short:"V2Ray",icon:"V",tone:"violet",fa:"انعطاف‌پذیر برای شرایط مختلف شبکه و کاربران حرفه‌ای.",en:"Flexible connectivity for varied network conditions and power users."},
};

const guideProtocolOrder:StoreGuideProtocol[]=["cisco","openvpn","wireguard","l2tp","v2ray"];

function Conversion2027Template({settings,plans,loading,error,message,buying,onBuy}:StoreTemplateProps){
  const {pick,lang}=useI18n();
  const {brand}=useBranding();
  const [mobileNavOpen,setMobileNavOpen]=useState(false);
  const [guidePlatform,setGuidePlatform]=useState<StoreGuidePlatform>("android");
  const [guideProtocol,setGuideProtocol]=useState<StoreGuideProtocol>("wireguard");

  const locale=lang==="en"?"en-US":"fa-IR";
  const content=(key:string)=>storefrontText(settings,key,lang);
  const number=(value:number,options?:Intl.NumberFormatOptions)=>Number(value||0).toLocaleString(locale,options);
  const openChat=()=>window.dispatchEvent(new Event("twinpanel:open-chat"));

  const availableProtocols=Object.keys(protocolMeta);
  const guideProtocolIds=guideProtocolOrder;

  const activeGuideProtocol:StoreGuideProtocol=guideProtocolIds.includes(guideProtocol)
    ?guideProtocol
    :guideProtocolIds[0];

  const visibleSections=settings.section_order.filter(section=>isStorefrontSectionVisible(settings,section));
  const navLabels:Partial<Record<StorefrontSectionId,string>>={
    plans:pick("پلن‌ها","Plans"),
    protocols:pick("پروتکل‌ها","Protocols"),
    services:pick("امکانات","Features"),
    guides:pick("آموزش","Guides"),
    account:pick("پنل کاربری","Customer panel"),
    faq:pick("سوالات متداول","FAQ"),
  };

  const selectedPlatform=storeGuidePlatforms.find(item=>item.id===guidePlatform)||storeGuidePlatforms[0];
  const selectedProtocol=protocolMeta[activeGuideProtocol]||protocolMeta.wireguard;
  const guide=storeGuideContent[activeGuideProtocol];
  const guideEntry=guide.systems[guidePlatform];
  const guideAppImage=storeGuideAppImage(guidePlatform,activeGuideProtocol);
  const guideTutorialImage=storeGuideTutorialImage(guidePlatform,activeGuideProtocol);
  const featuredPlanIndex=plans.length>2?Math.floor(plans.length/2):0;
  const faqItems=[1,2,3,4,5].map(index=>({
    question:content(`faq_${index}_question`),
    answer:content(`faq_${index}_answer`),
  }));

  const plansSection=<section className="tpStoreSection tpStorePlans" id="plans" key="plans">
    <div className="tpStoreSectionHead">
      <span className="tpStorePill">{content("plans_tag")}</span>
      <h2>{content("plans_title")}</h2>
      <p>{content("plans_description")}</p>
    </div>
    {loading?<div className="tpStoreState">{pick("در حال دریافت پلن‌های فعال...","Loading active plans...")}</div>:plans.length===0?<div className="tpStoreState">{pick("در حال حاضر پلن فعالی برای فروش وجود ندارد.","There are currently no active plans for sale.")}</div>:<div className="tpStorePlanGrid">{plans.map((plan,index)=>{
      const protocols=planProtocols(plan);
      const featured=index===featuredPlanIndex;
      return <article className={`tpStorePlanCard ${featured?"featured":""}`} key={plan.id}>
        {featured&&<span className="tpStorePlanRibbon">{pick("محبوب‌ترین انتخاب","Popular choice")}</span>}
        <div className="tpStorePlanTop"><div><small>{pick("اشتراک VPN","VPN subscription")}</small><h3>{plan.name}</h3></div><span className="tpStorePlanStatus">{pick("فعال","Active")}</span></div>
        {plan.description&&<p className="tpStorePlanDesc">{plan.description}</p>}
        <div className="tpStorePlanPrice"><strong>{number(plan.price_toman)}</strong><span>{pick("تومان","Toman")}</span></div>
        <div className="tpStorePlanFacts"><div><b>{number(plan.traffic_gb,{maximumFractionDigits:2})} GB</b><small>{pick("حجم","Traffic")}</small></div><div><b>{number(plan.duration_days)}</b><small>{pick("روز","days")}</small></div><div><b>{number(plan.device_limit)}</b><small>{pick("دستگاه","devices")}</small></div></div>
        <ul className="tpStorePlanList">
          <li><i>✓</i>{content("plan_feature_1")}</li>
          <li><i>✓</i>{content("plan_feature_2")}</li>
          <li><i>✓</i>{content("plan_feature_3")}</li>
        </ul>
        <div className="tpStorePlanProtocols">{protocols.slice(0,5).map(protocol=><span key={protocol}>{storeProtocolMeta(protocol)?.short||protocolMeta[protocol]?.short||protocol}</span>)}</div>
        <button className="tpStoreBuyButton" disabled={buying===plan.id} onClick={()=>onBuy(plan)}>{buying===plan.id?pick("در حال ثبت سفارش...","Creating order..."):pick("خرید اشتراک","Buy subscription")}<span>←</span></button>
      </article>;
    })}</div>}
  </section>;

  const protocolsSection=<section className="tpStoreSection tpStoreSoftSection" id="protocols" key="protocols">
    <div className="tpStoreSectionHead">
      <span className="tpStorePill">{content("protocols_tag")}</span>
      <h2>{content("protocols_title")}</h2>
      <p>{content("protocols_description")}</p>
    </div>
    <div className="tpStoreProtocolGrid">{availableProtocols.map(id=>{const protocol=protocolMeta[id];return <article className={`tpStoreProtocolCard ${protocol.tone}`} key={id}><span className="tpStoreProtocolIcon">{protocol.icon}</span><div><h3 dir="ltr">{protocol.name}</h3><p>{pick(protocol.fa,protocol.en)}</p></div><span className="tpStoreAvailable">{pick("قابل ارائه","Available")}</span></article>;})}</div>
  </section>;

  const guidesSection=<section className="tpStoreSection" id="guides" key="guides">
    <div className="tpStoreSectionHead">
      <span className="tpStorePill">{content("guides_tag")}</span>
      <h2>{content("guides_title")}</h2>
      <p>{content("guides_description")}</p>
    </div>

    <div className="tpRealGuideShell">
      <div className="tpRealGuideToolbar">
        <div className="tpRealGuideTabs">{guideProtocolIds.map(id=><button type="button" className={activeGuideProtocol===id?"active":""} key={id} onClick={()=>setGuideProtocol(id)}>{protocolMeta[id].name}</button>)}</div>
        <div className="tpRealGuideOsTabs">{storeGuidePlatforms.map(platform=><button type="button" key={platform.id} className={guidePlatform===platform.id?"active":""} onClick={()=>setGuidePlatform(platform.id)}><span>{platform.icon}</span>{pick(platform.fa,platform.en)}</button>)}</div>
      </div>

      <div className="tpRealGuideIntro">
        <div className="tpRealGuideIntroMain">
          <div className="tpRealGuideAppArt">
            <span>{selectedPlatform.icon}</span>
            {guideAppImage&&<img src={guideAppImage} alt={`${guideEntry.client} - ${selectedProtocol.name}`} loading="lazy" decoding="async" onError={event=>{event.currentTarget.style.display="none";}}/>}
          </div>
          <div>
            <small>{selectedProtocol.name} · {pick(selectedPlatform.fa,selectedPlatform.en)}</small>
            <h3>{guideEntry.client}</h3>
            <p>{guide.summary}</p>
          </div>
        </div>
        {guideEntry.downloadUrl?<a className="tpRealGuideDownload" href={guideEntry.downloadUrl} target="_blank" rel="noopener noreferrer">{guideEntry.downloadLabel}<span>↗</span></a>:<span className="tpRealGuideNoDownload">✓ {guideEntry.downloadLabel}</span>}
      </div>

      {guideEntry.warning&&<div className="tpRealGuideWarning"><span>⚠</span><div><b>{pick("قبل از شروع بخوان","Read before starting")}</b>{guideEntry.warning}</div></div>}

      <div className="tpRealGuideRequirements">
        <article><small>{pick("پروتکل","Protocol")}</small><b>{selectedProtocol.name}</b></article>
        <article><small>{pick("سیستم‌عامل","Operating system")}</small><b>{pick(selectedPlatform.fa,selectedPlatform.en)}</b></article>
        <article><small>{pick("اطلاعات لازم از حساب","Required account data")}</small><b dir="ltr">{guideEntry.credential}</b></article>
      </div>

      {guideTutorialImage&&<figure className="tpRealGuideScreenshot tpRealGuideTutorialSheet">
        <img src={guideTutorialImage} alt={`${selectedProtocol.name} - ${pick(selectedPlatform.fa,selectedPlatform.en)}`} loading="lazy" decoding="async"/>
        <figcaption>{pick("تصاویر واقعی مراحل آموزش از نسخه قبلی پنل","Real tutorial screenshots from the previous panel")}</figcaption>
      </figure>}

      <div className="tpRealGuideLayout">
        <div className="tpRealGuideSteps">
          <header><span><small>{pick("اجرای مرحله‌به‌مرحله","Step by step")}</small><h3>{pick("از نصب تا اتصال موفق","From install to successful connection")}</h3></span><em>{number(guideEntry.steps.length)} {pick("مرحله","steps")}</em></header>
          {guideEntry.steps.map((step,index)=>{
            return <article className="tpRealGuideStep" key={`${activeGuideProtocol}-${guidePlatform}-${step.title}`}>
              <i>{number(index+1)}</i>
              <div>
                <b>{step.title}</b>
                <p>{step.detail}</p>
              </div>
            </article>;
          })}
        </div>

        <aside className="tpRealGuideHelp">
          <header><span className="tpRealGuideHelpIcon">⌁</span><span><small>{pick("اگر وصل نشد","If it does not connect")}</small><h3>{pick("عیب‌یابی همین روش","Troubleshoot this setup")}</h3></span></header>
          {guideEntry.fixes.map(fix=><p key={fix}><i>✓</i>{fix}</p>)}
          <div className="tpRealGuideHelpNote"><b>{pick("اطلاعات اتصال را حدس نزن","Never guess connection credentials")}</b><small>{pick("Server، فایل، لینک، رمز و کلید را فقط از پنل کاربری همان اشتراک دریافت کن.","Get the server, file, link, password and keys only from that subscription in your customer panel.")}</small></div>
          <Link href="/panel" className="tpRealGuidePanelLink">{pick("رفتن به پنل و دریافت اطلاعات","Open panel and get connection details")}</Link>
        </aside>
      </div>
    </div>
  </section>;

  const servicesSection=<section className="tpStoreSection tpStoreSoftSection" id="services" key="services">
    <div className="tpStoreSectionHead">
      <span className="tpStorePill">{content("services_tag")}</span>
      <h2>{content("services_title")}</h2>
      <p>{content("services_description")}</p>
    </div>
    <div className="tpStoreBenefitsGrid">
      <article><span>⚡</span><div><b>{content("service_1_title")}</b><p>{content("service_1_description")}</p></div></article>
      <article><span>▥</span><div><b>{content("service_2_title")}</b><p>{content("service_2_description")}</p></div></article>
      <article><span>◎</span><div><b>{content("service_3_title")}</b><p>{content("service_3_description")}</p></div></article>
      <article><span>⌁</span><div><b>{content("service_4_title")}</b><p>{content("service_4_description")}</p></div></article>
      <article><span>✓</span><div><b>{content("service_5_title")}</b><p>{content("service_5_description")}</p></div></article>
      <article><span>↗</span><div><b>{content("service_6_title")}</b><p>{content("service_6_description")}</p></div></article>
    </div>
  </section>;

  const accountSection=<section className="tpStoreSection" id="account" key="account">
    <div className="tpStoreAccountPanel">
      <div><span className="tpStorePill">{content("account_tag")}</span><h2>{content("account_title")}</h2><p>{content("account_description")}</p><div className="tpStoreAccountActions"><Link href="/panel" className="tpStorePrimary">{content("account_primary_button")}</Link><button className="tpStoreSecondary" onClick={openChat}>{content("account_secondary_button")}</button></div></div>
      <div className="tpStoreAccountMiniGrid">
        <div><span>01</span><b>{content("account_item_1_title")}</b><small>{content("account_item_1_description")}</small></div>
        <div><span>02</span><b>{content("account_item_2_title")}</b><small>{content("account_item_2_description")}</small></div>
        <div><span>03</span><b>{content("account_item_3_title")}</b><small>{content("account_item_3_description")}</small></div>
        <div><span>04</span><b>{content("account_item_4_title")}</b><small>{content("account_item_4_description")}</small></div>
      </div>
    </div>
  </section>;

  const faqSection=<section className="tpStoreSection tpStoreFaq" id="faq" key="faq">
    <div className="tpStoreSectionHead">
      <span className="tpStorePill">{content("faq_tag")}</span>
      <h2>{content("faq_title")}</h2>
      <p>{content("faq_description")}</p>
    </div>
    <div className="tpStoreFaqList">{faqItems.map((item,index)=><details key={`${index}-${item.question}`} open={index===0}><summary>{item.question}<span>＋</span></summary><p>{item.answer}</p></details>)}</div>
  </section>;

  const sections:Record<StorefrontSectionId,ReactNode>={plans:plansSection,protocols:protocolsSection,services:servicesSection,guides:guidesSection,account:accountSection,faq:faqSection};

  return <div className="tpStore" data-store-template="conversion-2027" dir={lang==="fa"?"rtl":"ltr"}>
    <header className="tpStoreHeader">
      <div className="tpStoreHeaderInner">
        <button className="tpStoreMenuButton" type="button" onClick={()=>setMobileNavOpen(value=>!value)} aria-label={pick("باز کردن منو","Open menu")}><span/><span/><span/></button>
        <Link href="/store" className="tpStoreBrand"><img src={brand.logoUrl} alt={brand.name}/><b>{brand.name}</b></Link>
        <nav className="tpStoreNavLinks">{visibleSections.map(section=><a key={section} href={`#${section}`}>{navLabels[section]}</a>)}</nav>
        <div className="tpStoreHeaderActions"><LanguageSwitch compact/><ThemeSwitch compact/><Link href="/login" className="tpStoreLogin tpStoreLoginPrimary">{pick("ورود","Sign in")}</Link></div>
      </div>
      {mobileNavOpen&&<div className="tpStoreMobileNav">{visibleSections.map(section=><a key={section} href={`#${section}`} onClick={()=>setMobileNavOpen(false)}>{navLabels[section]}</a>)}<Link href="/login" onClick={()=>setMobileNavOpen(false)}>{pick("ورود به حساب","Sign in")}</Link></div>}
    </header>

    <main>
      <section className="tpStoreHero">
        <div className="tpStoreHeroGlow"/>
        <div className="tpStoreHeroCopy">
          <span className="tpStorePill">{content("hero_kicker")}</span>
          <h1>{content("hero_title")} <em>{content("hero_highlight")}</em></h1>
          <p>{content("hero_description")}</p>
          <div className="tpStoreHeroActions">{settings.show_plans&&<a href="#plans" className="tpStorePrimary">{content("hero_primary_button")}<span>←</span></a>}<Link href="/panel" className="tpStoreSecondary">{content("hero_secondary_button")}</Link></div>
          <div className="tpStoreHeroProof"><span><i>●</i>{content("hero_proof_1")}</span><span><i>●</i>{content("hero_proof_2")}</span><span><i>●</i>{content("hero_proof_3")}</span></div>
        </div>
        <div className="tpStoreHeroVisual" aria-hidden="true">
          <div className="tpStoreOrbit tpStoreOrbitOne"/><div className="tpStoreOrbit tpStoreOrbitTwo"/>
          <div className="tpStoreGlobe"><span className="tpStoreGlobeLine a"/><span className="tpStoreGlobeLine b"/><span className="tpStoreGlobeLine c"/></div>
          <div className="tpStorePhone">
            <div className="tpStorePhoneNotch"/>
            <div className="tpStorePhoneBrand"><img src={brand.logoUrl} alt=""/><b>{brand.name}</b><small>VPN Connected</small></div>
            <button className="tpStorePower">⌁</button>
            <div className="tpStorePhoneApps"><span>▶</span><span>◎</span><span>✦</span><span>G</span><span>N</span></div>
          </div>
          <div className="tpStoreOnlineToast"><span>●</span><div><b>{pick("اتصال موفق","Connected")}</b><small>{pick("آی‌پی شما تغییر کرد","Your IP changed")}</small></div></div>
        </div>
      </section>

      <section className="tpStoreTrustStrip">
        <article><span>⚡</span><div><b>{content("trust_speed_title")}</b><small>{content("trust_speed_description")}</small></div></article>
        <article><span>▥</span><div><b>{content("trust_uptime_value")}</b><small>{content("trust_uptime_description")}</small></div></article>
        <article><span>⌁</span><div><b>{content("trust_support_title")}</b><small>{content("trust_support_description")}</small></div></article>
        <article><span>◎</span><div><b>{number(STORE_PROTOCOL_CATALOG.length)}</b><small>{content("trust_protocols_description")}</small></div></article>
        <article><span>✓</span><div><b>{content("trust_payment_title")}</b><small>{content("trust_payment_description")}</small></div></article>
        <article><span>↗</span><div><b>{content("trust_activation_title")}</b><small>{content("trust_activation_description")}</small></div></article>
      </section>

      {error&&<div className="tpStoreAlert error">{error}</div>}
      {message&&<div className="tpStoreAlert success">{message}</div>}

      {visibleSections.map(section=>sections[section])}

      {settings.show_final_cta&&<section className="tpStoreFinalCta">
        <div className="tpStoreCtaOrb"/>
        <div><span className="tpStorePill">{content("final_cta_tag")}</span><h2>{content("final_cta_title")}</h2><p>{content("final_cta_description")}</p></div>
        <a href="#plans" className="tpStorePrimary">{content("final_cta_button")}<span>←</span></a>
      </section>}

      {settings.show_contact&&<section className="tpStoreContact" id="contact">
        <div className="tpStoreSectionHead"><span className="tpStorePill">{content("contact_tag")}</span><h2>{content("contact_title")}</h2><p>{content("contact_description")}</p></div>
        <div className="tpStoreSocialGrid">
          {settings.show_telegram&&<a href={settings.telegram_url} target="_blank" rel="noreferrer" className="telegram"><span>➤</span><div><b>{content("telegram_title")}</b><small>{content("telegram_description")}</small></div></a>}
          {settings.show_instagram&&<a href={settings.instagram_url} target="_blank" rel="noreferrer" className="instagram"><span>◎</span><div><b>{content("instagram_title")}</b><small>{content("instagram_description")}</small></div></a>}
          {settings.show_whatsapp&&<a href={settings.whatsapp_url} target="_blank" rel="noreferrer" className="whatsapp"><span>◉</span><div><b>{content("whatsapp_title")}</b><small>{content("whatsapp_description")}</small></div></a>}
        </div>
        <button className="tpStoreChatCard" type="button" onClick={openChat}><span className="tpStoreChatIcon">⌁</span><div><b>{content("chat_title")}</b><small>{content("chat_description")}</small></div><i>←</i></button>
      </section>}
    </main>

    <footer className="tpStoreFooter">
      <div className="tpStoreFooterBrand"><div className="tpStoreBrand"><img src={brand.logoUrl} alt={brand.name}/><b>{brand.name}</b></div><p>{content("footer_tagline")}</p></div>
      <div><b>{content("footer_quick_title")}</b>{settings.show_plans&&<a href="#plans">{pick("پلن‌ها","Plans")}</a>}{settings.show_guides&&<a href="#guides">{pick("آموزش اتصال","Setup guides")}</a>}<Link href="/panel">{pick("پنل کاربری","Customer panel")}</Link></div>
      <div><b>{content("footer_support_title")}</b><button onClick={openChat}>{content("chat_title")}</button>{settings.show_telegram&&<a href={settings.telegram_url} target="_blank" rel="noreferrer">{content("telegram_title")}</a>}<Link href="/login">{pick("ورود","Sign in")}</Link></div>
      <div><b>{content("footer_social_title")}</b>{settings.show_instagram&&<a href={settings.instagram_url} target="_blank" rel="noreferrer">{content("instagram_title")}</a>}{settings.show_whatsapp&&<a href={settings.whatsapp_url} target="_blank" rel="noreferrer">{content("whatsapp_title")}</a>}{settings.show_telegram&&<a href={settings.telegram_url} target="_blank" rel="noreferrer">{content("telegram_title")}</a>}</div>
      <div className="tpStoreFooterBottom"><span>© {new Date().getFullYear()} {brand.name}</span><span>{content("footer_rights")}</span></div>
    </footer>

    <button className="tpStoreFloatingChat" type="button" onClick={openChat} aria-label={pick("باز کردن چت آنلاین","Open live chat")}><span>•••</span></button>
    {plans.length>0&&<a className="tpStoreMobileBuy" href="#plans"><span>{content("hero_primary_button")}</span><b>{number(plans[0].price_toman)} {pick("تومان","Toman")}</b></a>}
  </div>;
}

const templateRenderers:Record<string,(props:StoreTemplateProps)=>ReactNode>={
  "conversion-2027":props=><Conversion2027Template {...props}/>,
};

export function StoreTemplateRenderer(props:StoreTemplateProps){
  const templateId=resolveStoreTemplateId(props.settings.active_template);
  const renderer=templateRenderers[templateId]||templateRenderers[DEFAULT_STORE_TEMPLATE_ID];
  return <>{renderer(props)}</>;
}
