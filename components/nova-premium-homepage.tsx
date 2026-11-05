"use client";
import Link from "next/link";
import type {StorePlan} from "../lib/store-runtime-api";
import type {StoreTemplateOptionMap} from "../lib/store-template-options";
import {STORE_PROTOCOL_CATALOG} from "../lib/store-protocol-catalog";
import styles from "./nova-premium-homepage.module.css";

type Props={
 plans:StorePlan[];
 loading:boolean;
 buying:number|null;
 onBuy:(plan:StorePlan)=>void;
 options:StoreTemplateOptionMap;
 support:string;
 brandName:string;
};
const fa=(n:number)=>Number(n||0).toLocaleString("fa-IR");
const displayPrice=(n:number)=>fa(n);
const homePerks=[
 {icon:"⚡",title:"اتصال چندپروتکلی",body:"انتخاب روش اتصال متناسب با اینترنت"},
 {icon:"◈",title:"مدیریت اشتراک",body:"دریافت لینک و تمدید از حساب کاربری"},
 {icon:"◎",title:"راهنمای مخصوص",body:"برنامه هر پروتکل داخل ساب‌لینک"},
 {icon:"◇",title:"پشتیبانی آنلاین",body:"پیگیری خرید و مشکلات اتصال"}
];
const resellerTiers=[
 {id:"economy",icon:"▤",title:"پنل اقتصادی",subtitle:"شروع فروش با امکانات ضروری",benefits:["دسترسی به محصولات اقتصادی تعیین‌شده","مدیریت مشتریان و سفارش‌ها","استفاده از ابزارهای فعال‌شده نمایندگی"],cta:"مشاوره پنل اقتصادی"},
 {id:"special",icon:"♛",title:"پنل ویژه",subtitle:"برای مجموعه‌های فروش حرفه‌ای",benefits:["دسترسی به محصولات ویژه تعیین‌شده","مناسب فروشندگان با نیاز گسترده‌تر","مدیریت اشتراک و پیگیری سفارش"],cta:"مشاوره پنل ویژه"}
] as const;
const channels=[
 {icon:"◉",name:"آی‌پی ثابت",body:"برای مدیریت حساب‌های مهم، ترید مجاز و کارهای نیازمند خروجی پایدار",link:"/vpn-static-ip",cta:"اطلاعات آی‌پی ثابت"},
 {icon:"⬡",name:"۱۵ پروتکل اتصال",body:"همه روش‌های پشتیبانی‌شده و راهنمای برنامه اختصاصی هر پروتکل",link:"/vpn-services#protocols",cta:"مشاهده پروتکل‌ها"},
 {icon:"▤",name:"آموزش و دانلود",body:"برنامه سازگار را از ساب‌لینک دریافت و با راهنمای همان پروتکل وصل شوید",link:"/vpn-guides",cta:"آموزش اتصال"},
 {icon:"?",name:"سوالات متداول",body:"پاسخ درباره خرید، تمدید، تحویل لینک، نمایندگی و اتصال",link:"/vpn-faq",cta:"پرسش و پاسخ"}
];
export function NovaResellerTiers({support}:{support:string}){
 return <section className={styles.resellerTierDetail} aria-label="مقایسه پنل‌های اقتصادی و ویژه">
  <div className={styles.sectionTitle}><div><span>دو مدل نمایندگی</span><h2>پنل اقتصادی یا پنل ویژه؟</h2><p>دو گروه مجزا با تعرفه، سرورها و پروتکل‌های قابل عرضه متفاوت؛ مدیر اصلی هنگام ایجاد نماینده سطح دسترسی را مشخص می‌کند.</p></div></div>
  <div className={styles.resellerCards}>{resellerTiers.map(t=><article key={t.id} className={t.id==="economy"?styles.economyCard:styles.specialCard}>
   <span className={styles.resellerGlyph}>{t.icon}</span><div><small>{t.subtitle}</small><h3>{t.title}</h3>
   <p className={styles.tierNotice}>فقط پلن‌ها، سرورها و پروتکل‌های مجاز همین سطح قابل فروش‌اند؛ تعرفه همکاری جداگانه تعیین می‌شود.</p>
   <ul>{t.benefits.map(b=><li key={b}>{b}</li>)}</ul>
   <a href={support} target={support.startsWith("http")?"_blank":undefined} rel="noopener noreferrer">{t.cta} ←</a>
   </div></article>)}</div>
  <p className={styles.tierFoot}>هر دو سطح بر اساس اعتبار نمایندگی عمل می‌کنند؛ قیمت هر گروه، حجم اعتبار و محصولات قابل فروش در پنل مدیریت تنظیم می‌شود.</p>
 </section>;
}
export default function NovaPremiumHomepage({plans,loading,buying,onBuy,options,support,brandName}:Props){
 const option=(key:string,fallback:string)=>typeof options[key]==="string"&&String(options[key]).trim()?String(options[key]):fallback;
 const first=plans[0];
 const featured=plans.slice(0,4);
 const heroImage=option("nova_hero_image","");
 const customImage=/^https:\/\/\S+$/i.test(heroImage)||/^\/[a-zA-Z0-9_./-]+(?:\?[a-zA-Z0-9=&_-]+)?$/.test(heroImage)?heroImage:"";
 return <div className={styles.home}>
  <section className={styles.hero} aria-label="معرفی خدمات و خرید سریع">
   <div className={styles.heroCopy}>
    <span className={styles.eyebrow}><span className={styles.liveDot}/> {option("nova_eyebrow","تجربه هوشمند خدمات VPN")}</span>
    <h1>{option("nova_hero_title","اتصال مطمئن با")} <em>{option("nova_hero_highlight","انتخابی حرفه‌ای")}</em></h1>
    <p>{option("nova_hero_description","خرید اشتراک VPN، دریافت ساب‌لینک هر پروتکل، راهنمای اتصال و مدیریت سرویس از یک حساب کاربری؛ مناسب استفاده شخصی و کاری.")}</p>
    <div className={styles.heroActions}><Link href="/vpn-services#plans" className={styles.primary}>{option("nova_primary_label","مشاهده اشتراک‌ها")} <span>←</span></Link><Link href="/vpn-reseller" className={styles.outline}>{option("nova_secondary_label","درخواست نمایندگی")}</Link></div>
    <div className={styles.heroBenefits}><span>✦ ۱۵ روش اتصال</span><span>◈ پنل کاربری</span><span>◎ راهنمای اختصاصی</span></div>
   </div>
   <div className={styles.heroArt} aria-label="تصویر گرافیکی سرورها و شبکه جهانی">
    <div className={styles.halo}/>
    <img src={customImage||"/nova/server-globe.svg"} alt="سرورهای محافظت‌شده در شبکه جهانی" loading="eager" className={styles.serverIllustration}/>
    <span className={styles.artBubbleTop}>◈ انتخاب هوشمند پروتکل</span><span className={styles.artBubbleBottom}>✦ مدیریت در یک پنل</span>
   </div>
   <div className={styles.quickBuy}>
     <div className={styles.quickTop}><span>◈ خرید سریع اشتراک</span><span className={styles.quickIcon}>✦</span></div>
     {first?<><div className={styles.quickPlan}><small>پلن منتخب از فهرست فعال</small><h2>{first.name}</h2><p>{first.description||"مشخصات اشتراک را قبل از خرید بررسی کنید."}</p></div>
      <div className={styles.quickPrice}><strong>{displayPrice(first.price_toman)}</strong><span>تومان</span></div>
      <div className={styles.quickFacts}><span>◷ {fa(first.duration_days)} روز</span><span>◉ {fa(first.traffic_gb)} گیگ</span><span>◈ {first.device_limit===0?"نامحدود":fa(first.device_limit)+" دستگاه"}</span></div>
      <button type="button" className={styles.buyButton} disabled={buying===first.id} onClick={()=>onBuy(first)}>{buying===first.id?"در حال ثبت سفارش…":"انتخاب و خرید اشتراک ←"}</button>
     </>:<div className={styles.quickEmpty}>{loading?"در حال دریافت پلن‌های فروشگاه…":"در حال حاضر پلن فعالی موجود نیست."}<Link href="/vpn-services">صفحه همه خدمات</Link></div>}
     <p className={styles.quickFoot}>قیمت و موجودی مستقیم از پنل فروشگاه</p>
   </div>
  </section>
  <div className={styles.trustBar} aria-label="امکانات و سازگاری">
   <span>◉ سازگار با اندروید، آیفون، ویندوز، مک و لینوکس</span><span>✦ برنامه مخصوص داخل ساب‌لینک</span><span>◇ چندین روش اتصال بر اساس پلن</span>
  </div>
  <section className={styles.section} aria-label="مزیت‌های خدمات">
    <div className={styles.perkGrid}>{homePerks.map(p=><article key={p.title} className={styles.perk}><div className={styles.perkIcon}>{p.icon}</div><div><h3>{p.title}</h3><p>{p.body}</p></div></article>)}</div>
  </section>
  <section className={styles.section} id="featured-plans" aria-label="پلن‌های اشتراک">
    <div className={styles.sectionTitle}><div><span>پلن‌های فعال فروشگاه</span><h2>انتخاب پلن مناسب شما</h2><p>قیمت، حجم و مدت اعتبار از اطلاعات واقعی فروشگاه دریافت می‌شود.</p></div><Link href="/vpn-services#plans" className={styles.sectionLink}>همه پلن‌ها ←</Link></div>
    {featured.length?<div className={styles.featuredPlans}>{featured.map((p,i)=><article key={p.id} className={styles.featuredPlan}><div className={styles.featuredHeading}><span className={styles.planSymbol}>{["✦","◈","⬡","◇"][i]}</span><b>{p.name}</b></div><strong>{displayPrice(p.price_toman)} <small>تومان</small></strong><div className={styles.featuredDetails}><span>{fa(p.duration_days)} روز</span><span>{fa(p.traffic_gb)} گیگ</span><span>{p.device_limit===0?"کاربر نامحدود":fa(p.device_limit)+" دستگاه"}</span></div><button type="button" onClick={()=>onBuy(p)} disabled={buying===p.id}>{buying===p.id?"در حال ثبت…":"انتخاب پلن ←"}</button></article>)}</div>:<p className={styles.emptyPlans}>{loading?"در حال بارگذاری پلن‌ها…":"در حال حاضر پلنی برای نمایش وجود ندارد."}</p>}
  </section>
  <section className={styles.resellerBand} id="reseller-tiers" aria-label="انواع نمایندگی فروش">
    <div className={styles.resellerIntro}><span>◈ همکاری در فروش</span><h2>دو سطح پنل نمایندگی</h2><p>اقتصادی یا ویژه؛ سطح دسترسی، نوع محصولات و شرایط مالی توسط مدیریت تعیین می‌شود.</p><Link href="/vpn-reseller" className={styles.primary}>جزئیات نمایندگی ←</Link></div>
    <div className={styles.resellerCards}>{resellerTiers.map(t=><article key={t.id} className={t.id==="economy"?styles.economyCard:styles.specialCard}><span className={styles.resellerGlyph}>{t.icon}</span><div><small>{t.subtitle}</small><h3>{t.title}</h3><ul>{t.benefits.map(b=><li key={b}>{b}</li>)}</ul><a href={support} target={support.startsWith("http")?"_blank":undefined} rel="noopener noreferrer">{t.cta} ←</a></div></article>)}</div>
  </section>
  <section className={styles.section} aria-label="بیشتر درباره خدمات"><div className={styles.serviceCards}>{channels.map(c=><Link key={c.name} href={c.link} className={styles.serviceCard}><span className={styles.serviceIcon}>{c.icon}</span><h3>{c.name}</h3><p>{c.body}</p><b>{c.cta} ←</b></Link>)}</div></section>
  <section className={styles.bottomBanner}><div><span>راهنمای اتصال</span><h2>برای هر پروتکل، برنامه مناسب همان پروتکل در ساب‌لینک معرفی شده است.</h2><p>ساب‌لینک اشتراک را باز کنید، پروتکل دلخواه را انتخاب کنید و لینک برنامه سازگار با دستگاه خود را بردارید.</p></div><Link href="/vpn-guides" className={styles.primary}>مشاهده راهنماها ←</Link></section>
  <div className={styles.protocolCaption}>پشتیبانی سامانه از {fa(STORE_PROTOCOL_CATALOG.length)} پروتکل؛ دسترسی هر کاربر متناسب با پلن خریداری‌شده است. <Link href="/vpn-services#protocols">مشاهده همه پروتکل‌ها ←</Link></div>
 </div>;
}
