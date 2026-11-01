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
  {key:"orbit_banner_image",fa:"تصویر بنر بالای سایت",en:"Top banner image",helpFa:"برای نوار تبلیغ یا اطلاع‌رسانی بالای سایت.",helpEn:"Used for the announcement strip above the storefront.",aspect:"عرض 1920 × ارتفاع 80 پیکسل"},
  {key:"orbit_hero_image",fa:"تصویر اصلی فروشگاه",en:"Main storefront image",helpFa:"تصویر اصلی بخش معرفی سرویس.",helpEn:"Primary image used in the service introduction section.",aspect:"عرض 1200 × ارتفاع 1300 پیکسل"},
  {key:"orbit_story_image",fa:"تصویر بخش امکانات",en:"Features image",helpFa:"تصویر اصلی بخش امکانات و مزایا.",helpEn:"Main image used in the features section.",aspect:"عرض 1200 × ارتفاع 1300 پیکسل"},
  {key:"orbit_protocol_image",fa:"تصویر بخش روش‌های اتصال",en:"Connection methods image",helpFa:"تصویر بخش روش‌های اتصال و پروتکل‌ها.",helpEn:"Image used in the connection methods section.",aspect:"عرض 1200 × ارتفاع 1200 پیکسل"},
  {key:"orbit_guides_image",fa:"تصویر بخش آموزش",en:"Guides image",helpFa:"تصویر کنار آموزش‌های اتصال.",helpEn:"Image shown beside connection guides.",aspect:"عرض 1000 × ارتفاع 1600 پیکسل"},
  {key:"orbit_account_image",fa:"تصویر پنل کاربری",en:"Account image",helpFa:"تصویر بخش مدیریت اشتراک و حساب کاربری.",helpEn:"Image used in the subscription and account section.",aspect:"عرض 1200 × ارتفاع 1100 پیکسل"},
  {key:"orbit_cta_image",fa:"پس‌زمینه بخش خرید",en:"Purchase section background",helpFa:"تصویر پس‌زمینه بخش پایانی خرید.",helpEn:"Background image for the final purchase section.",aspect:"عرض 1920 × ارتفاع 720 پیکسل"},
  {key:"orbit_footer_image",fa:"تصویر فوتر",en:"Footer image",helpFa:"تصویر کوچک برای فوتر فروشگاه.",helpEn:"Small image used in the storefront footer.",aspect:"عرض 1000 × ارتفاع 1000 پیکسل"},
] as const;

export const ORBIT_SECTION_LABELS:Record<StorefrontSectionId,{fa:string;en:string}>={
  plans:{fa:"پلن‌ها",en:"Plans"},
  protocols:{fa:"روش‌های اتصال",en:"Connection methods"},
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

  orbit_banner_title:"اتصال سریع و پایدار برای همه دستگاه‌ها",
  orbit_banner_title_en:"Fast, reliable VPN access for all your devices",
  orbit_banner_action:"مشاهده پلن‌ها",
  orbit_banner_action_en:"View plans",

  hero_kicker:"VPN پرسرعت و امن",
  hero_kicker_en:"FAST & SECURE VPN",
  hero_title:"اتصال سریع، پایدار و مطمئن",
  hero_title_en:"Fast, stable and reliable VPN access",
  hero_highlight:"روی همه دستگاه‌های شما.",
  hero_highlight_en:"across all your devices.",
  hero_description:"یک اشتراک برای ویندوز، اندروید، آیفون، مک و لینوکس. پلن مناسب را انتخاب کنید و اطلاعات اتصال را بعد از خرید از پنل کاربری دریافت کنید.",
  hero_description_en:"One subscription for Windows, Android, iPhone, macOS and Linux. Choose your plan and receive connection details in your account after purchase.",
  hero_primary_button:"خرید اشتراک",
  hero_primary_button_en:"Buy subscription",
  hero_secondary_button:"آموزش اتصال",
  hero_secondary_button_en:"Setup guides",
  hero_proof_1:"تحویل داخل پنل",
  hero_proof_1_en:"Delivered in your account",
  hero_proof_2:"۱۵ روش اتصال",
  hero_proof_2_en:"15 connection methods",
  hero_proof_3:"پشتیبانی آنلاین",
  hero_proof_3_en:"Live support",

  plans_tag:"پلن‌های VPN",
  plans_tag_en:"VPN PLANS",
  plans_title:"پلن مناسب مصرف خود را انتخاب کنید.",
  plans_title_en:"Choose the VPN plan that fits your usage.",
  plans_description:"حجم، مدت و تعداد دستگاه هر پلن را مقایسه کنید و اشتراک مناسب خود را مستقیم خریداری کنید.",
  plans_description_en:"Compare traffic, duration and device limits, then choose the subscription that fits your needs.",
  plan_feature_1:"فعال‌سازی سریع بعد از پرداخت",
  plan_feature_1_en:"Fast activation after payment",
  plan_feature_2:"مناسب ویندوز، اندروید، آیفون، مک و لینوکس",
  plan_feature_2_en:"Works with Windows, Android, iPhone, macOS and Linux",
  plan_feature_3:"اطلاعات اتصال داخل پنل کاربری",
  plan_feature_3_en:"Connection details inside your account",

  protocols_tag:"روش‌های اتصال",
  protocols_tag_en:"CONNECTION METHODS",
  protocols_title:"برای هر دستگاه و شبکه، روش اتصال مناسب دارید.",
  protocols_title_en:"The right connection method for every device and network.",
  protocols_description:"اشتراک‌ها از چند روش اتصال پشتیبانی می‌کنند تا در شرایط مختلف شبکه بتوانید گزینه مناسب را انتخاب کنید.",
  protocols_description_en:"Subscriptions support multiple connection methods so you can choose the best option for your device and network conditions.",

  services_tag:"چرا این سرویس؟",
  services_tag_en:"WHY CHOOSE US",
  services_title:"همه چیز برای یک اتصال راحت و پایدار آماده است.",
  services_title_en:"Everything you need for a simple and reliable VPN experience.",
  services_description:"از سرعت و پایداری تا پشتیبانی چند دستگاه، تحویل سریع اطلاعات اتصال و پشتیبانی آنلاین.",
  services_description_en:"From speed and stability to multi-device support, quick delivery and live assistance.",
  service_1_title:"سرعت بالا",service_1_title_en:"High speed",service_1_description:"مسیرهای مناسب برای وب‌گردی، دانلود و استفاده روزمره.",service_1_description_en:"Optimized routes for browsing, downloads and everyday use.",
  service_2_title:"پایداری اتصال",service_2_title_en:"Reliable connection",service_2_description:"اتصال پایدار برای استفاده مداوم در شبکه‌های مختلف.",service_2_description_en:"Stable connectivity for everyday use across different networks.",
  service_3_title:"۱۵ روش اتصال",service_3_title_en:"15 connection methods",service_3_description:"برای دستگاه و شرایط شبکه خود گزینه مناسب را انتخاب کنید.",service_3_description_en:"Choose the method that best fits your device and network.",
  service_4_title:"پشتیبانی همه دستگاه‌ها",service_4_title_en:"Multi-device support",service_4_description:"قابل استفاده روی ویندوز، اندروید، آیفون، مک و لینوکس.",service_4_description_en:"Use your service on Windows, Android, iPhone, macOS and Linux.",
  service_5_title:"پشتیبانی آنلاین",service_5_title_en:"Live support",service_5_description:"برای خرید، نصب و اتصال می‌توانید مستقیم راهنمایی بگیرید.",service_5_description_en:"Get direct help with purchasing, setup and connectivity.",
  service_6_title:"مدیریت از پنل",service_6_title_en:"Account management",service_6_description:"اشتراک، سفارش، پرداخت و اطلاعات اتصال را از یک حساب مدیریت کنید.",service_6_description_en:"Manage subscriptions, orders, payments and connection details from one account.",

  guides_tag:"آموزش اتصال",
  guides_tag_en:"SETUP GUIDES",
  guides_title:"روی هر دستگاه، مرحله‌به‌مرحله متصل شوید.",
  guides_title_en:"Connect on every device with step-by-step guides.",
  guides_description:"سیستم‌عامل و روش اتصال را انتخاب کنید تا برنامه پیشنهادی، اطلاعات موردنیاز و مراحل راه‌اندازی را ببینید.",
  guides_description_en:"Choose your operating system and connection method to see the recommended app, required details and setup steps.",

  account_tag:"پنل کاربری",
  account_tag_en:"CUSTOMER PANEL",
  account_title:"اشتراک و اطلاعات اتصال همیشه در دسترس شماست.",
  account_title_en:"Your subscription and connection details stay within reach.",
  account_description:"اشتراک‌ها، حجم، سفارش‌ها، پرداخت‌ها و اطلاعات اتصال را از پنل کاربری مدیریت کنید.",
  account_description_en:"Manage subscriptions, traffic, orders, payments and connection details from your customer panel.",
  account_primary_button:"ورود به پنل کاربری",
  account_primary_button_en:"Open customer panel",
  account_secondary_button:"پشتیبانی آنلاین",
  account_secondary_button_en:"Live support",

  faq_tag:"سوالات متداول",
  faq_tag_en:"FAQ",
  faq_title:"قبل از خرید، جواب سوال‌های مهم را ببینید.",
  faq_title_en:"Answers to common questions before you buy.",
  faq_description:"اطلاعات کوتاه و کاربردی درباره خرید، دستگاه‌ها، حجم، اتصال و پشتیبانی.",
  faq_description_en:"Quick answers about purchasing, devices, traffic, connectivity and support.",
  faq_1_question:"بعد از خرید سرویس کجا تحویل می‌شود؟",faq_1_question_en:"Where do I receive the service after purchase?",faq_1_answer:"بعد از تکمیل خرید، اطلاعات اتصال و وضعیت اشتراک در پنل کاربری شما در دسترس قرار می‌گیرد.",faq_1_answer_en:"After purchase, your subscription status and connection details are available in your customer account.",
  faq_2_question:"روی چه دستگاه‌هایی می‌توانم استفاده کنم؟",faq_2_question_en:"Which devices are supported?",faq_2_answer:"سرویس برای ویندوز، اندروید، آیفون، macOS و لینوکس قابل استفاده است؛ محدودیت تعداد دستگاه به پلن انتخابی شما بستگی دارد.",faq_2_answer_en:"The service supports Windows, Android, iPhone, macOS and Linux. The number of allowed devices depends on your selected plan.",
  faq_3_question:"حجم و مدت اشتراک چطور مشخص می‌شود؟",faq_3_question_en:"How are traffic and duration determined?",faq_3_answer:"حجم، مدت و تعداد دستگاه هر پلن قبل از خرید روی همان پلن نمایش داده می‌شود.",faq_3_answer_en:"Traffic, duration and device limits are shown on each plan before purchase.",
  faq_4_question:"برای اتصال چه روش‌هایی وجود دارد؟",faq_4_question_en:"Which connection methods are available?",faq_4_answer:"بسته به پلن، چند روش اتصال در اختیار شما قرار می‌گیرد تا برای دستگاه و شبکه خود گزینه مناسب را انتخاب کنید.",faq_4_answer_en:"Depending on the plan, multiple connection methods are available so you can choose the best option for your device and network.",
  faq_5_question:"اگر در نصب یا اتصال مشکل داشتم چه کار کنم؟",faq_5_question_en:"What if I need help with setup or connection?",faq_5_answer:"از بخش آموزش اتصال یا پشتیبانی آنلاین برای دریافت راهنمایی استفاده کنید.",faq_5_answer_en:"Use the setup guides or live support whenever you need help.",

  final_cta_tag:"آماده اتصال هستید؟",
  final_cta_tag_en:"READY TO CONNECT?",
  final_cta_title:"پلن مناسب را انتخاب کنید و اتصال را شروع کنید.",
  final_cta_title_en:"Choose your plan and get connected.",
  final_cta_description:"اشتراک مناسب خود را بخرید و بعد از فعال‌سازی، اطلاعات اتصال را از پنل کاربری دریافت کنید.",
  final_cta_description_en:"Buy the plan that fits your needs and receive your connection details in your account after activation.",
  final_cta_button:"مشاهده پلن‌ها",
  final_cta_button_en:"View plans",

  contact_tag:"پشتیبانی و ارتباط",
  contact_tag_en:"SUPPORT & CONTACT",
  contact_title:"برای خرید و اتصال، کنار شما هستیم.",
  contact_title_en:"We are here to help with purchasing and setup.",
  contact_description:"برای سوال‌های قبل از خرید، راه‌اندازی سرویس یا مشکلات اتصال از کانال‌های ارتباطی و چت آنلاین استفاده کنید.",
  contact_description_en:"Use the available contact channels or live chat for pre-sales questions, setup help and connection support.",
  footer_tagline:"VPN سریع و پایدار برای همه دستگاه‌های شما.",
  footer_tagline_en:"Fast, reliable VPN access for all your devices.",
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