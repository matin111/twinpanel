import {STOREFRONT_SECTION_IDS,type StorefrontSectionId} from "./storefront-config";

export const ORBIT_TEMPLATE_ID="orbit-neo-2027";

export type OrbitThemeValue=string|boolean|string[];
export type OrbitThemeDraft=Record<string,OrbitThemeValue>;

export type OrbitMediaSlot={
  key:string;
  fa:string;
  en:string;
  helpFa:string;
  helpEn:string;
  aspect:string;
};

export const ORBIT_MEDIA_SLOTS:readonly OrbitMediaSlot[]=[
  {key:"orbit_banner_image",fa:"تصویر بنر بالای سایت",en:"Top banner image",helpFa:"برای نوار تبلیغ/اعلان بالای هدر. تصویر عریض و سبک پیشنهاد می‌شود.",helpEn:"Used in the announcement strip above the header. A lightweight wide image is recommended.",aspect:"1920×320"},
  {key:"orbit_hero_image",fa:"تصویر اصلی Hero",en:"Hero main image",helpFa:"تصویر شاخص سمت تصویری Hero؛ مهم‌ترین تصویر قالب.",helpEn:"Primary visual inside the hero media stage; the most prominent theme image.",aspect:"1400×1100"},
  {key:"orbit_story_image",fa:"تصویر شاخص امکانات",en:"Features story image",helpFa:"تصویر بزرگ بخش Bento امکانات و تجربه سرویس.",helpEn:"Large feature image used inside the services Bento composition.",aspect:"1200×900"},
  {key:"orbit_protocol_image",fa:"تصویر بخش پروتکل‌ها",en:"Protocols image",helpFa:"تصویر مرکزی بخش روش‌های اتصال و پروتکل‌ها.",helpEn:"Central visual for the connection-methods/protocol section.",aspect:"1000×1000"},
  {key:"orbit_guides_image",fa:"تصویر بخش آموزش",en:"Guides image",helpFa:"کاور یا تصویر برندشده کنار آموزش‌های واقعی اتصال.",helpEn:"Cover/brand visual shown beside the real connection guides.",aspect:"1200×900"},
  {key:"orbit_account_image",fa:"تصویر پنل کاربری",en:"Account image",helpFa:"تصویر بخش مدیریت اشتراک و پنل کاربری.",helpEn:"Visual used in the account/subscription-management section.",aspect:"1200×900"},
  {key:"orbit_cta_image",fa:"پس‌زمینه CTA نهایی",en:"Final CTA background",helpFa:"تصویر تمام‌عرض CTA انتهای صفحه؛ روی آن Overlay خوانا قرار می‌گیرد.",helpEn:"Full-width final CTA background; a readable overlay is applied automatically.",aspect:"1920×900"},
  {key:"orbit_footer_image",fa:"تصویر تزئینی فوتر",en:"Footer decorative image",helpFa:"تصویر یا Artwork کوچک برای امضای بصری فوتر.",helpEn:"Small artwork used as the footer visual signature.",aspect:"1000×700"},
] as const;

export const ORBIT_SECTION_LABELS:Record<StorefrontSectionId,{fa:string;en:string}>={
  plans:{fa:"پلن‌ها",en:"Plans"},
  protocols:{fa:"پروتکل‌ها",en:"Protocols"},
  services:{fa:"امکانات",en:"Features"},
  guides:{fa:"آموزش اتصال",en:"Guides"},
  account:{fa:"پنل کاربری",en:"Account"},
  faq:{fa:"سوالات متداول",en:"FAQ"},
};

export const ORBIT_DEFAULTS:OrbitThemeDraft={
  theme_primary:"#6d5dfc",
  theme_secondary:"#22d3ee",
  orbit_dark_page:"#05060a",
  orbit_dark_surface:"#0c0f16",
  orbit_dark_surface_alt:"#131824",
  orbit_dark_text:"#f8fafc",
  orbit_dark_muted:"#9aa4b5",
  orbit_dark_border:"#253043",
  orbit_light_page:"#f4f6fb",
  orbit_light_surface:"#ffffff",
  orbit_light_surface_alt:"#edf1f8",
  orbit_light_text:"#10131a",
  orbit_light_muted:"#667085",
  orbit_light_border:"#d9e0ec",
  orbit_button_text:"#ffffff",
  orbit_header_style:"dock",
  orbit_card_shape:"round",
  orbit_plan_style:"tickets",
  orbit_motion:true,
  orbit_show_top_banner:true,
  orbit_show_metrics:true,
  orbit_show_media_labels:true,

  orbit_banner_title:"نسل جدید فروشگاه اتصال آماده است",
  orbit_banner_title_en:"A new storefront experience is ready",
  orbit_banner_action:"مشاهده پلن‌ها",
  orbit_banner_action_en:"Explore plans",

  hero_kicker:"ORBIT / ACCESS 2027",
  hero_kicker_en:"ORBIT / ACCESS 2027",
  hero_title:"اتصال حرفه‌ای، با تجربه‌ای که شبیه فروشگاه‌های معمولی نیست.",
  hero_title_en:"Professional connectivity, presented unlike a typical storefront.",
  hero_highlight:"یک مدار برای خرید، آموزش و مدیریت.",
  hero_highlight_en:"One orbit for purchase, setup and control.",
  hero_description:"پلن واقعی را انتخاب کنید، روش‌های اتصال همان پلن را ببینید، آموزش مناسب دستگاهتان را پیدا کنید و بعد از خرید همه‌چیز را داخل حساب خود مدیریت کنید.",
  hero_description_en:"Choose a live plan, inspect its available connection methods, follow the right device guide and manage everything from your account after purchase.",
  hero_primary_button:"شروع انتخاب پلن",
  hero_primary_button_en:"Choose a plan",
  hero_secondary_button:"دیدن آموزش اتصال",
  hero_secondary_button_en:"Open setup guides",
  hero_proof_1:"تحویل داخل حساب",
  hero_proof_1_en:"Delivered in your account",
  hero_proof_2:"چند روش اتصال",
  hero_proof_2_en:"Multiple connection methods",
  hero_proof_3:"پشتیبانی آنلاین",
  hero_proof_3_en:"Live support",

  plans_tag:"LIVE PLANS",
  plans_tag_en:"LIVE PLANS",
  plans_title:"پلن‌ها را مثل یک کاتالوگ زنده مقایسه کنید.",
  plans_title_en:"Compare plans like a live catalog.",
  plans_description:"قیمت، حجم، مدت، تعداد دستگاه و پروتکل‌های فعال مستقیماً از Backend خوانده می‌شوند؛ کارت‌ها فقط ظاهر متفاوت Orbit را دارند.",
  plans_description_en:"Price, traffic, duration, device limits and available protocols come directly from the backend; Orbit only changes the presentation.",
  plan_feature_1:"اطلاعات اتصال بعد از خرید داخل حساب",
  plan_feature_1_en:"Connection details delivered to your account",
  plan_feature_2:"پروتکل‌های فعال همان پلن",
  plan_feature_2_en:"Only protocols enabled for that plan",
  plan_feature_3:"قابل پیگیری از سفارش تا سرویس",
  plan_feature_3_en:"Traceable from order to active service",

  protocols_tag:"CONNECTION CONSTELLATION",
  protocols_tag_en:"CONNECTION CONSTELLATION",
  protocols_title:"هر پروتکل یک مسیر؛ همه در یک سرویس.",
  protocols_title_en:"Each protocol is a route; all inside one service.",
  protocols_description:"روش‌های در دسترس بر اساس پلن‌های واقعی فروشگاه نمایش داده می‌شوند تا کاربر قبل از خرید بداند چه انتخاب‌هایی دارد.",
  protocols_description_en:"Available methods are derived from live storefront plans so customers can see their real choices before buying.",

  services_tag:"WHY ORBIT",
  services_tag_en:"WHY ORBIT",
  services_title:"یک Bento زنده از مزیت‌هایی که بعد از خرید واقعاً استفاده می‌کنید.",
  services_title_en:"A live Bento of benefits you actually use after purchase.",
  services_description:"از سرعت و پایداری تا تحویل اطلاعات اتصال، مدیریت سفارش و پشتیبانی؛ هر بخش جای مشخص خودش را دارد.",
  services_description_en:"From speed and stability to delivery, order management and support, every part has a clear place.",
  service_1_title:"سرعت بالا",service_1_title_en:"Fast routes",service_1_description:"مسیرهای بهینه برای استفاده روزمره.",service_1_description_en:"Optimized routes for everyday use.",
  service_2_title:"پایداری قابل اتکا",service_2_title_en:"Reliable stability",service_2_description:"تجربه اتصال پایدار در سناریوهای مختلف.",service_2_description_en:"A dependable connection experience across scenarios.",
  service_3_title:"چند پروتکل",service_3_title_en:"Multi-protocol",service_3_description:"روش اتصال مناسب دستگاه و شبکه را انتخاب کنید.",service_3_description_en:"Choose the method that fits your device and network.",
  service_4_title:"پنل یکپارچه",service_4_title_en:"Unified account",service_4_description:"اشتراک، سفارش و اطلاعات اتصال در یک حساب.",service_4_description_en:"Subscriptions, orders and connection details in one account.",
  service_5_title:"پشتیبانی سریع",service_5_title_en:"Fast support",service_5_description:"دسترسی مستقیم به چت و کانال‌های ارتباطی.",service_5_description_en:"Direct access to chat and support channels.",
  service_6_title:"پرداخت قابل پیگیری",service_6_title_en:"Traceable payment",service_6_description:"وضعیت سفارش و پرداخت از همان حساب قابل مشاهده است.",service_6_description_en:"Track order and payment status from the same account.",

  guides_tag:"REAL SETUP LAB",
  guides_tag_en:"REAL SETUP LAB",
  guides_title:"آموزش اتصال را از حالت مقاله خارج کردیم.",
  guides_title_en:"Setup guides, redesigned beyond a normal article.",
  guides_description:"سیستم‌عامل و پروتکل را انتخاب کنید؛ مراحل، نرم‌افزار پیشنهادی، اطلاعات لازم و رفع خطا همان‌جا عوض می‌شوند.",
  guides_description_en:"Choose an operating system and protocol; steps, recommended client, required data and troubleshooting update in place.",

  account_tag:"CONTROL DECK",
  account_tag_en:"CONTROL DECK",
  account_title:"بعد از خرید، کنترل سرویس به یک فضای مدیریتی منتقل می‌شود.",
  account_title_en:"After purchase, control moves into a dedicated management space.",
  account_description:"اشتراک‌ها، مصرف، سفارش‌ها، پرداخت و اطلاعات اتصال را از پنل کاربری دنبال کنید.",
  account_description_en:"Track subscriptions, usage, orders, payments and connection details from the customer panel.",
  account_primary_button:"ورود به پنل کاربری",
  account_primary_button_en:"Open customer panel",
  account_secondary_button:"پشتیبانی آنلاین",
  account_secondary_button_en:"Live support",

  faq_tag:"FAQ / QUICK ANSWERS",
  faq_tag_en:"FAQ / QUICK ANSWERS",
  faq_title:"سوال‌های پرتکرار، بدون شلوغی.",
  faq_title_en:"Frequent questions, without the clutter.",
  faq_description:"پاسخ‌های کوتاه درباره خرید، دستگاه، حجم، پروتکل‌ها و راه‌اندازی.",
  faq_description_en:"Short answers about purchase, devices, traffic, protocols and setup.",
  faq_1_question:"بعد از خرید سرویس کجا تحویل می‌شود؟",faq_1_question_en:"Where is the service delivered after purchase?",faq_1_answer:"وضعیت سفارش و اطلاعات اتصال از پنل کاربری همان حساب قابل پیگیری است.",faq_1_answer_en:"Order status and connection details are available from the same customer account.",
  faq_2_question:"آیا همه پلن‌ها پروتکل‌های یکسان دارند؟",faq_2_question_en:"Do all plans include the same protocols?",faq_2_answer:"خیر؛ پروتکل‌های فعال هر پلن از اطلاعات واقعی همان پلن نمایش داده می‌شوند.",faq_2_answer_en:"No. Each card shows the protocols actually enabled for that plan.",
  faq_3_question:"تعداد دستگاه مجاز چطور مشخص می‌شود؟",faq_3_question_en:"How is the device limit determined?",faq_3_answer:"محدودیت دستگاه مستقیماً روی کارت پلن از Backend نمایش داده می‌شود.",faq_3_answer_en:"The live device limit is shown directly on each plan card from the backend.",
  faq_4_question:"برای نصب برنامه و اتصال راهنما هست؟",faq_4_question_en:"Are setup and client-install guides included?",faq_4_answer:"بله؛ بخش آموزش برای سیستم‌عامل و پروتکل‌های مختلف مراحل واقعی و لینک نرم‌افزار را نمایش می‌دهد.",faq_4_answer_en:"Yes. The guide lab shows real steps and client links by operating system and protocol.",
  faq_5_question:"اگر قبل از خرید سوال داشته باشم چه؟",faq_5_question_en:"What if I have a question before buying?",faq_5_answer:"از چت آنلاین یا شبکه‌های اجتماعی فعال فروشگاه استفاده کنید.",faq_5_answer_en:"Use live chat or any active storefront social channel.",

  final_cta_tag:"READY TO ENTER ORBIT?",
  final_cta_tag_en:"READY TO ENTER ORBIT?",
  final_cta_title:"پلن را انتخاب کنید؛ بقیه مسیر از داخل حساب ادامه پیدا می‌کند.",
  final_cta_title_en:"Choose a plan; the rest continues inside your account.",
  final_cta_description:"ظاهر متفاوت است، اما قیمت، سفارش، پرداخت و تحویل سرویس همان جریان واقعی TwinPanel باقی می‌ماند.",
  final_cta_description_en:"The presentation is different, while pricing, orders, payments and service delivery remain the real TwinPanel flow.",
  final_cta_button:"مشاهده پلن‌ها",
  final_cta_button_en:"Explore plans",

  contact_tag:"SIGNAL / SUPPORT",
  contact_tag_en:"SIGNAL / SUPPORT",
  contact_title:"هر زمان لازم بود، یک مسیر مستقیم برای ارتباط دارید.",
  contact_title_en:"Whenever you need it, there is a direct support route.",
  contact_description:"تلگرام، اینستاگرام، واتس‌اپ و چت آنلاین فقط زمانی نمایش داده می‌شوند که آدرس آن‌ها در تنظیمات اصلی فعال باشد.",
  contact_description_en:"Telegram, Instagram, WhatsApp and live chat are surfaced from the storefront's real integration settings.",
  footer_tagline:"Orbit Neo — a spatial storefront for modern connectivity.",
  footer_tagline_en:"Orbit Neo — a spatial storefront for modern connectivity.",
  footer_rights:"تمامی حقوق محفوظ است.",
  footer_rights_en:"All rights reserved.",

  show_plans:true,
  show_protocols:true,
  show_services:true,
  show_guides:true,
  show_account:true,
  show_faq:true,
  show_final_cta:true,
  show_contact:true,
  section_order:[...STOREFRONT_SECTION_IDS],

  orbit_banner_image:"",
  orbit_hero_image:"",
  orbit_story_image:"",
  orbit_protocol_image:"",
  orbit_guides_image:"",
  orbit_account_image:"",
  orbit_cta_image:"",
  orbit_footer_image:"",
};

export function orbitOption(draft:OrbitThemeDraft,key:string){
  const value=draft[key];
  return typeof value==="string"?value:"";
}

export function normalizeOrbitThemeDraft(raw:unknown):OrbitThemeDraft{
  const source=raw&&typeof raw==="object"&&!Array.isArray(raw)?raw as Record<string,unknown>:{};
  const result:OrbitThemeDraft={...ORBIT_DEFAULTS};
  for(const [key,fallback] of Object.entries(ORBIT_DEFAULTS)){
    const value=source[key];
    if(typeof fallback==="boolean"){
      result[key]=typeof value==="boolean"?value:fallback;
    }else if(Array.isArray(fallback)){
      const order=Array.isArray(value)?value.map(String):fallback.map(String);
      const normalized:StorefrontSectionId[]=[];
      for(const item of order){
        const section=item as StorefrontSectionId;
        if(STOREFRONT_SECTION_IDS.includes(section)&&!normalized.includes(section))normalized.push(section);
      }
      for(const section of STOREFRONT_SECTION_IDS)if(!normalized.includes(section))normalized.push(section);
      result[key]=normalized;
    }else{
      result[key]=typeof value==="string"?value:String(fallback??"");
    }
  }
  for(const [key,value] of Object.entries(source)){
    if(!(key in result)&&(typeof value==="string"||typeof value==="boolean"||Array.isArray(value)))result[key]=Array.isArray(value)?value.map(String):value as string|boolean;
  }
  return result;
}
