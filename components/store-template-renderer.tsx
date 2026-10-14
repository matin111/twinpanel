"use client";

import Link from "next/link";
import {ComponentType,useMemo,useState} from "react";
import {Badge,Card} from "./ui";
import {LanguageSwitch,useI18n} from "../lib/i18n";
import {ThemeSwitch} from "../lib/theme";
import {useBranding} from "../lib/branding";
import {planProtocols,StorePlan} from "../lib/store-runtime-api";
import {
  StorefrontSectionId,
  StorefrontSettings,
  isStorefrontSectionVisible,
  storefrontText,
} from "../lib/storefront-config";
import {DEFAULT_STORE_TEMPLATE_ID,resolveStoreTemplateId} from "../lib/store-template-registry";

export type StoreTemplateProps={
  settings:StorefrontSettings;
  plans:StorePlan[];
  loading:boolean;
  error:string;
  message:string;
  buying:number|null;
  onBuy:(plan:StorePlan)=>void;
};

const protocolMeta:Record<string,{name:string;icon:string;fa:string;en:string}>={
  cisco:{name:"Cisco / OpenConnect",icon:"◉",fa:"اتصال ساده با نام کاربری و رمز و سازگاری مناسب برای استفاده روزمره.",en:"Simple username/password access with broad day-to-day compatibility."},
  openvpn:{name:"OpenVPN",icon:"△",fa:"کانفیگ قابل حمل و پشتیبانی گسترده روی سیستم‌عامل‌های مختلف.",en:"Portable configuration with broad operating-system support."},
  wireguard:{name:"WireGuard",icon:"⚡",fa:"سبک و سریع با فایل یا QR برای اتصال ساده‌تر.",en:"Fast lightweight connectivity with file or QR delivery."},
  l2tp:{name:"L2TP / IPsec",icon:"◎",fa:"قابل استفاده از تنظیمات داخلی بسیاری از دستگاه‌ها.",en:"Works through built-in VPN settings on many devices."},
  v2ray:{name:"V2Ray / Xray",icon:"◇",fa:"گزینه انعطاف‌پذیر برای شرایط متفاوت شبکه.",en:"Flexible connectivity for changing network conditions."},
};

const platforms=["Windows","Android","iPhone / iPad","macOS","Linux"];

function Conversion2027Template({settings,plans,loading,error,message,buying,onBuy}:StoreTemplateProps){
  const {pick,lang}=useI18n();
  const {brand}=useBranding();
  const [guideProtocol,setGuideProtocol]=useState("wireguard");
  const [guidePlatform,setGuidePlatform]=useState("Windows");
  const locale=lang==="en"?"en-US":"fa-IR";
  const content=(key:string)=>storefrontText(settings,key,lang);
  const number=(value:number,options?:Intl.NumberFormatOptions)=>Number(value||0).toLocaleString(locale,options);

  const availableProtocols=useMemo(()=>{
    const set=new Set<string>();
    plans.forEach(plan=>planProtocols(plan).forEach(protocol=>set.add(protocol)));
    return Object.keys(protocolMeta).filter(protocol=>set.size===0||set.has(protocol));
  },[plans]);

  const visibleSections=settings.section_order.filter(section=>isStorefrontSectionVisible(settings,section));
  const navLabels:Partial<Record<StorefrontSectionId,string>>={
    plans:pick("پلن‌ها","Plans"),protocols:pick("پروتکل‌ها","Protocols"),services:pick("خدمات","Services"),guides:pick("آموزش اتصال","Setup guides"),account:pick("پنل کاربری","Customer panel"),faq:"FAQ",
  };

  const plansSection=<section className="store-block plans-section" id="plans" key="plans">
    <div className="section-title left"><small>{content("plans_tag")}</small><h2>{content("plans_title")}</h2><p>{content("plans_description")}</p></div>
    {loading?<div className="runtime-loading">{pick("در حال دریافت پلن‌ها...","Loading plans...")}</div>:plans.length===0?<Card><p>{pick("در حال حاضر پلن فعالی برای فروش وجود ندارد.","There are currently no active plans for sale.")}</p></Card>:<div className="pricing pricing-pro conversion-pricing">{plans.map((plan,index)=>{
      const protocols=planProtocols(plan);const featured=index===Math.floor(plans.length/2)&&plans.length>1;
      return <Card key={plan.id} className={`${featured?"featured ":""}sales-plan`}>
        {featured&&<div className="recommend-ribbon">{pick("انتخاب متعادل","Balanced option")}</div>}
        <div className="plan-head"><Badge tone={featured?"violet":"ok"}>{pick("فعال","Active")}</Badge><span>{number(plan.duration_days)} {pick("روز","days")}</span></div>
        <h3>{plan.name}</h3>{plan.description&&<p className="muted">{plan.description}</p>}
        <div className="plan-price"><strong>{number(plan.price_toman)}</strong><span>{pick("تومان","Toman")}</span></div>
        <div className="plan-facts"><span><b>{number(plan.traffic_gb,{maximumFractionDigits:2})} GB</b>{pick("حجم","Traffic")}</span><span><b>{number(plan.device_limit)}</b>{pick("دستگاه","Devices")}</span></div>
        <ul>{protocols.map(protocol=><li key={protocol}><i>✓</i>{protocolMeta[protocol]?.name||protocol}</li>)}</ul>
        <button className={featured?"primary full xl":"ghost full xl"} disabled={buying===plan.id} onClick={()=>onBuy(plan)}>{buying===plan.id?pick("در حال ثبت سفارش...","Creating order..."):pick("انتخاب و ادامه خرید","Choose and continue")}</button>
        <small className="plan-note">#{plan.id} · {number(protocols.length)} {pick("پروتکل","protocols")}</small>
      </Card>;
    })}</div>}
  </section>;

  const protocolsSection=<section className="store-block" id="protocols" key="protocols"><div className="section-title"><small>{content("protocols_tag")}</small><h2>{content("protocols_title")}</h2><p>{content("protocols_description")}</p></div><div className="protocol-grid">{availableProtocols.map(id=>{const protocol=protocolMeta[id];return <Card key={id}><span className="protocol-icon">{protocol.icon}</span><h3>{protocol.name}</h3><p>{pick(protocol.fa,protocol.en)}</p><Badge tone="ok">{pick("قابل ارائه","Available")}</Badge></Card>})}</div></section>;

  const servicesSection=<section className="store-block" id="services" key="services"><div className="section-title"><small>{content("services_tag")}</small><h2>{content("services_title")}</h2><p>{content("services_description")}</p></div><div className="module-grid three"><Card><span className="module-icon">◉</span><h3>{pick("تحویل اتصال","Connection delivery")}</h3><p>{pick("فایل، QR، لینک یا اطلاعات ورود متناسب با پروتکل داخل حساب کاربری قرار می‌گیرد.","Files, QR codes, links or credentials are delivered inside the customer account based on protocol.")}</p></Card><Card><span className="module-icon">◫</span><h3>{pick("مدیریت اشتراک","Subscription management")}</h3><p>{pick("حجم، تاریخ انقضا و وضعیت سرویس از پنل کاربری قابل مشاهده و مدیریت است.","Traffic, expiry and service status stay visible and manageable from the customer panel.")}</p></Card><Card><span className="module-icon">◇</span><h3>{pick("خرید و پرداخت","Purchase & payment")}</h3><p>{pick("سفارش و وضعیت پرداخت به حساب شما متصل است تا مسیر خرید قابل پیگیری بماند.","Orders and payment status stay linked to your account for a traceable purchase flow.")}</p></Card></div></section>;

  const guidesSection=<section className="store-block guide-studio" id="guides" key="guides"><div className="section-title"><small>{content("guides_tag")}</small><h2>{content("guides_title")}</h2><p>{content("guides_description")}</p></div><div className="guide-pickers"><div>{platforms.map(platform=><button key={platform} className={guidePlatform===platform?"active":""} onClick={()=>setGuidePlatform(platform)}>{platform}</button>)}</div><div>{availableProtocols.map(id=><button key={id} className={guideProtocol===id?"active":""} onClick={()=>setGuideProtocol(id)}>{protocolMeta[id].name}</button>)}</div></div><div className="module-grid three"><Card><span className="module-icon">1</span><h3>{pick("کلاینت مناسب را نصب کن","Install a compatible client")}</h3><p>{guidePlatform}</p></Card><Card><span className="module-icon">2</span><h3>{pick("اطلاعات اتصال را از پنل بگیر","Get connection details from the panel")}</h3><p>{protocolMeta[guideProtocol]?.name}</p></Card><Card><span className="module-icon">3</span><h3>{pick("کانفیگ را اضافه و متصل شو","Import the config and connect")}</h3><p>{pick("فایل، QR، لینک یا اطلاعات ورود بر اساس پروتکل نمایش داده می‌شود.","File, QR, link or credentials are shown based on the protocol.")}</p></Card></div></section>;

  const accountSection=<section className="store-block" id="account" key="account"><div className="section-title"><small>{content("account_tag")}</small><h2>{content("account_title")}</h2><p>{content("account_description")}</p></div><Card className="hero-product-card"><div className="delivery-list"><div><span>01</span><b>{pick("اشتراک‌ها","Subscriptions")}</b><small>{pick("مشاهده و مدیریت سرویس‌ها","View and manage services")}</small></div><div><span>02</span><b>{pick("کیف پول و پرداخت‌ها","Wallet & payments")}</b><small>{pick("سوابق مالی در یک حساب","Financial history in one account")}</small></div><div><span>03</span><b>{pick("اطلاعات اتصال","Connection details")}</b><small>{pick("تحویل امن داخل پنل","Secure in-panel delivery")}</small></div></div><Link className="primary full xl" href="/panel">{pick("ورود به پنل کاربری","Open customer panel")}</Link></Card></section>;

  const faqSection=<section className="store-block" id="faq" key="faq"><div className="section-title"><small>{content("faq_tag")}</small><h2>{content("faq_title")}</h2><p>{content("faq_description")}</p></div><div className="faq-grid"><Card><h3>{pick("بعد از خرید چه می‌شود؟","What happens after purchase?")}</h3><p>{pick("سفارش در پنل کاربری ثبت می‌شود و وضعیت پرداخت، ساخت اشتراک و اطلاعات اتصال همان‌جا نمایش داده می‌شود.","The order appears in your customer panel, where payment, provisioning and connection delivery are tracked.")}</p></Card><Card><h3>{pick("قیمت‌ها از کجا می‌آیند؟","Where do prices come from?")}</h3><p>{pick("مستقیم از پلن‌های فعال Backend؛ فروشگاه قیمت نمونه یا آزمایشی ندارد.","Directly from active backend plans; the storefront does not use sample pricing.")}</p></Card><Card><h3>{pick("برای خرید باید حساب داشته باشم؟","Do I need an account to buy?")}</h3><p>{pick("بله. سفارش به حساب کاربری متصل است تا پرداخت و تحویل امن و قابل پیگیری باشد.","Yes. Orders are linked to your account so payment and delivery remain secure and traceable.")}</p></Card></div></section>;

  const sections:Record<StorefrontSectionId,React.ReactNode>={plans:plansSection,protocols:protocolsSection,services:servicesSection,guides:guidesSection,account:accountSection,faq:faqSection};

  return <div className="store store2027 store-conversion" data-store-template="conversion-2027">
    <header className="store-nav"><div className="brand"><img src={brand.logoUrl} alt={brand.name}/><div><b>{brand.name}</b></div></div><nav>{visibleSections.map(section=><a key={section} href={`#${section}`}>{navLabels[section]}</a>)}<Link href="/reseller">{pick("نمایندگی","Reseller")}</Link></nav><div className="store-actions"><LanguageSwitch compact/><ThemeSwitch compact/><Link className="ghost" href="/login">{pick("ورود","Sign in")}</Link>{settings.show_plans&&<a className="primary" href="#plans">{content("hero_primary_button")}</a>}</div></header>
    <main>
      <section className="store-hero-pro"><div className="hero-copy"><div className="eyebrow"><span className="live-dot"/>{content("hero_kicker")}</div><h1>{content("hero_title")} <span>{content("hero_highlight")}</span></h1><p>{content("hero_description")}</p><div className="hero-actions">{settings.show_plans&&<a href="#plans" className="primary xl">{content("hero_primary_button")}</a>}<Link href="/panel" className="ghost xl">{content("hero_secondary_button")}</Link></div><div className="proof-grid"><div><b>{plans.length||"—"}</b><span>{pick("پلن فعال","active plans")}</span></div><div><b>{availableProtocols.length||"—"}</b><span>{pick("پروتکل موجود","available protocols")}</span></div><div><b>QR / File</b><span>{pick("تحویل اتصال","connection delivery")}</span></div><div><b>FA / EN</b><span>{pick("رابط دو زبانه","bilingual UI")}</span></div></div></div><Card className="hero-product-card"><div className="hero-card-top"><span>{pick("مسیر خرید","Purchase flow")}</span><Badge tone="violet">Live API</Badge></div><div className="delivery-list"><div><span>01</span><b>{pick("انتخاب پلن","Choose plan")}</b><small>{pick("اطلاعات واقعی Backend","Live backend data")}</small></div><div><span>02</span><b>{pick("ثبت سفارش","Create order")}</b><small>{pick("داخل حساب کاربری","Inside your account")}</small></div><div><span>03</span><b>{pick("پرداخت و تحویل","Pay & receive")}</b><small>{pick("پیگیری در پنل کاربری","Track in customer panel")}</small></div></div><Link className="primary full xl" href="/login?next=%2Fstore">{pick("ورود و شروع خرید","Sign in and start")}</Link></Card></section>
      {error&&<div className="runtime-error">{error}</div>}{message&&<div className="runtime-success">{message}</div>}
      {visibleSections.map(section=>sections[section])}
    </main>
    <footer className="store-footer"><div className="brand"><img src={brand.logoUrl} alt={brand.name}/><b>{brand.name}</b></div><div><Link href="/login">{pick("ورود","Sign in")}</Link><Link href="/panel">{pick("پنل کاربری","Customer panel")}</Link><Link href="/reseller">{pick("نمایندگی","Reseller")}</Link></div></footer>
  </div>;
}

const STORE_TEMPLATE_RENDERERS:Record<string,ComponentType<StoreTemplateProps>>={
  "conversion-2027":Conversion2027Template,
};

export function StoreTemplateRenderer(props:StoreTemplateProps){
  const templateId=resolveStoreTemplateId(props.settings.active_template);
  const Renderer=STORE_TEMPLATE_RENDERERS[templateId]||STORE_TEMPLATE_RENDERERS[DEFAULT_STORE_TEMPLATE_ID];
  return <Renderer {...props}/>;
}
