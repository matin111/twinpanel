export const STOREFRONT_SECTION_IDS=[
  "plans",
  "protocols",
  "services",
  "guides",
  "account",
  "faq",
] as const;

export type StorefrontSectionId=(typeof STOREFRONT_SECTION_IDS)[number];
export type StorefrontLocale="fa"|"en";

export type StorefrontSettings={
  active_template:string;

  hero_kicker:string;
  hero_kicker_en:string;
  hero_title:string;
  hero_title_en:string;
  hero_highlight:string;
  hero_highlight_en:string;
  hero_description:string;
  hero_description_en:string;
  hero_primary_button:string;
  hero_primary_button_en:string;
  hero_secondary_button:string;
  hero_secondary_button_en:string;
  hero_proof_1:string;
  hero_proof_1_en:string;
  hero_proof_2:string;
  hero_proof_2_en:string;
  hero_proof_3:string;
  hero_proof_3_en:string;

  plans_tag:string;
  plans_tag_en:string;
  plans_title:string;
  plans_title_en:string;
  plans_description:string;
  plans_description_en:string;
  plan_feature_1:string;
  plan_feature_1_en:string;
  plan_feature_2:string;
  plan_feature_2_en:string;
  plan_feature_3:string;
  plan_feature_3_en:string;

  protocols_tag:string;
  protocols_tag_en:string;
  protocols_title:string;
  protocols_title_en:string;
  protocols_description:string;
  protocols_description_en:string;

  services_tag:string;
  services_tag_en:string;
  services_title:string;
  services_title_en:string;
  services_description:string;
  services_description_en:string;
  service_1_title:string;
  service_1_title_en:string;
  service_1_description:string;
  service_1_description_en:string;
  service_2_title:string;
  service_2_title_en:string;
  service_2_description:string;
  service_2_description_en:string;
  service_3_title:string;
  service_3_title_en:string;
  service_3_description:string;
  service_3_description_en:string;
  service_4_title:string;
  service_4_title_en:string;
  service_4_description:string;
  service_4_description_en:string;
  service_5_title:string;
  service_5_title_en:string;
  service_5_description:string;
  service_5_description_en:string;
  service_6_title:string;
  service_6_title_en:string;
  service_6_description:string;
  service_6_description_en:string;

  guides_tag:string;
  guides_tag_en:string;
  guides_title:string;
  guides_title_en:string;
  guides_description:string;
  guides_description_en:string;

  account_tag:string;
  account_tag_en:string;
  account_title:string;
  account_title_en:string;
  account_description:string;
  account_description_en:string;
  account_primary_button:string;
  account_primary_button_en:string;
  account_secondary_button:string;
  account_secondary_button_en:string;
  account_item_1_title:string;
  account_item_1_title_en:string;
  account_item_1_description:string;
  account_item_1_description_en:string;
  account_item_2_title:string;
  account_item_2_title_en:string;
  account_item_2_description:string;
  account_item_2_description_en:string;
  account_item_3_title:string;
  account_item_3_title_en:string;
  account_item_3_description:string;
  account_item_3_description_en:string;
  account_item_4_title:string;
  account_item_4_title_en:string;
  account_item_4_description:string;
  account_item_4_description_en:string;

  faq_tag:string;
  faq_tag_en:string;
  faq_title:string;
  faq_title_en:string;
  faq_description:string;
  faq_description_en:string;
  faq_1_question:string;
  faq_1_question_en:string;
  faq_1_answer:string;
  faq_1_answer_en:string;
  faq_2_question:string;
  faq_2_question_en:string;
  faq_2_answer:string;
  faq_2_answer_en:string;
  faq_3_question:string;
  faq_3_question_en:string;
  faq_3_answer:string;
  faq_3_answer_en:string;
  faq_4_question:string;
  faq_4_question_en:string;
  faq_4_answer:string;
  faq_4_answer_en:string;
  faq_5_question:string;
  faq_5_question_en:string;
  faq_5_answer:string;
  faq_5_answer_en:string;

  trust_speed_title:string;
  trust_speed_title_en:string;
  trust_speed_description:string;
  trust_speed_description_en:string;
  trust_uptime_value:string;
  trust_uptime_value_en:string;
  trust_uptime_description:string;
  trust_uptime_description_en:string;
  trust_support_title:string;
  trust_support_title_en:string;
  trust_support_description:string;
  trust_support_description_en:string;
  trust_protocols_description:string;
  trust_protocols_description_en:string;
  trust_payment_title:string;
  trust_payment_title_en:string;
  trust_payment_description:string;
  trust_payment_description_en:string;
  trust_activation_title:string;
  trust_activation_title_en:string;
  trust_activation_description:string;
  trust_activation_description_en:string;

  final_cta_tag:string;
  final_cta_tag_en:string;
  final_cta_title:string;
  final_cta_title_en:string;
  final_cta_description:string;
  final_cta_description_en:string;
  final_cta_button:string;
  final_cta_button_en:string;

  contact_tag:string;
  contact_tag_en:string;
  contact_title:string;
  contact_title_en:string;
  contact_description:string;
  contact_description_en:string;
  telegram_url:string;
  telegram_title:string;
  telegram_title_en:string;
  telegram_description:string;
  telegram_description_en:string;
  instagram_url:string;
  instagram_title:string;
  instagram_title_en:string;
  instagram_description:string;
  instagram_description_en:string;
  whatsapp_url:string;
  whatsapp_title:string;
  whatsapp_title_en:string;
  whatsapp_description:string;
  whatsapp_description_en:string;
  chat_title:string;
  chat_title_en:string;
  chat_description:string;
  chat_description_en:string;

  footer_tagline:string;
  footer_tagline_en:string;
  footer_quick_title:string;
  footer_quick_title_en:string;
  footer_support_title:string;
  footer_support_title_en:string;
  footer_social_title:string;
  footer_social_title_en:string;
  footer_rights:string;
  footer_rights_en:string;

  show_plans:boolean;
  show_protocols:boolean;
  show_services:boolean;
  show_guides:boolean;
  show_account:boolean;
  show_faq:boolean;
  show_final_cta:boolean;
  show_contact:boolean;
  show_telegram:boolean;
  show_instagram:boolean;
  show_whatsapp:boolean;
  section_order:StorefrontSectionId[];

  seo_title:string;
  seo_description:string;
  seo_keywords:string;
  canonical_url:string;
  og_title:string;
  og_description:string;
  og_image:string;
  robots_index:boolean;
  robots_follow:boolean;

  updated_at?:string|null;
};

export const DEFAULT_STOREFRONT_SETTINGS:StorefrontSettings={
  active_template:"conversion-2027",

  hero_kicker:"۵ پروتکل، یک حساب کاربری",
  hero_kicker_en:"5 protocols, one account",
  hero_title:"اشتراک VPN برای چند روش اتصال،",
  hero_title_en:"VPN plans for multiple connection methods,",
  hero_highlight:"از یک پنل.",
  hero_highlight_en:"from one panel.",
  hero_description:"پلن را بر اساس نیاز انتخاب کنید؛ حجم، مدت، تعداد دستگاه و اطلاعات اتصال بعد از خرید در پنل کاربری در دسترس قرار می‌گیرد.",
  hero_description_en:"Choose a plan for your needs. Traffic, duration, device limits and connection details are available in your customer panel after purchase.",
  hero_primary_button:"خرید اشتراک",
  hero_primary_button_en:"Buy subscription",
  hero_secondary_button:"مشاهده پلن‌ها",
  hero_secondary_button_en:"View plans",
  hero_proof_1:"تحویل داخل پنل",
  hero_proof_1_en:"In-panel delivery",
  hero_proof_2:"چند پروتکل",
  hero_proof_2_en:"Multiple protocols",
  hero_proof_3:"پشتیبانی آنلاین",
  hero_proof_3_en:"Live support",

  plans_tag:"اشتراک‌های VPN",
  plans_tag_en:"VPN PLANS",
  plans_title:"انتخاب اشتراک",
  plans_title_en:"Choose your plan",
  plans_description:"حجم، مدت، تعداد دستگاه و پروتکل‌های هر پلن قبل از خرید نمایش داده می‌شود.",
  plans_description_en:"Compare traffic, duration, device limits and protocols before purchase.",
  plan_feature_1:"فعال‌سازی سریع بعد از پرداخت",
  plan_feature_1_en:"Fast activation after payment",
  plan_feature_2:"تحویل اطلاعات اتصال داخل پنل",
  plan_feature_2_en:"Connection delivery inside your panel",
  plan_feature_3:"پشتیبانی از پروتکل‌های همین پلن",
  plan_feature_3_en:"Support for this plan's protocols",

  protocols_tag:"پروتکل‌های اتصال",
  protocols_tag_en:"PROTOCOLS",
  protocols_title:"روش اتصال مناسب خودت را انتخاب کن.",
  protocols_title_en:"Choose the connection method that fits you.",
  protocols_description:"هر اشتراک می‌تواند چند پروتکل داشته باشد. روی هر گزینه بزن تا کاربرد و ویژگی‌های آن را ببینی.",
  protocols_description_en:"A subscription can include multiple protocols. Review each option to find the best fit.",

  services_tag:"خدمات",
  services_tag_en:"SERVICES",
  services_title:"بعد از خرید، همه‌چیز داخل حساب شماست.",
  services_title_en:"Everything stays inside your account after purchase.",
  services_description:"اطلاعات اتصال، حجم و اعتبار و اشتراک‌های شما از پنل کاربری در دسترس است.",
  services_description_en:"Connection details, traffic, wallet balance and subscriptions are available from the customer panel.",
  service_1_title:"سرعت بالا",
  service_1_title_en:"High speed",
  service_1_description:"اتصال سریع و مسیر بهینه برای استفاده روزمره.",
  service_1_description_en:"Fast connectivity with an optimized route for daily use.",
  service_2_title:"پایداری بالا",
  service_2_title_en:"Reliable uptime",
  service_2_description:"طراحی شده برای اتصال پایدار و تجربه بدون دردسر.",
  service_2_description_en:"Built for a stable, low-friction connection experience.",
  service_3_title:"پروتکل‌های متنوع",
  service_3_title_en:"Multiple protocols",
  service_3_description:"چند روش اتصال از یک حساب، متناسب با دستگاه و شبکه شما.",
  service_3_description_en:"Multiple connection methods from one account for different devices and networks.",
  service_4_title:"پشتیبانی آنلاین",
  service_4_title_en:"Live support",
  service_4_description:"اگر سوالی دارید، از چت آنلاین مستقیم کمک بگیرید.",
  service_4_description_en:"Get help directly from live chat whenever you need it.",
  service_5_title:"پرداخت امن",
  service_5_title_en:"Secure purchase",
  service_5_description:"وضعیت سفارش و پرداخت در حساب شما قابل پیگیری است.",
  service_5_description_en:"Orders and payment status remain traceable inside your account.",
  service_6_title:"فعال‌سازی سریع",
  service_6_title_en:"Quick activation",
  service_6_description:"بعد از تکمیل خرید، اطلاعات سرویس در پنل تحویل می‌شود.",
  service_6_description_en:"Service details are delivered to your panel after purchase completes.",

  guides_tag:"آموزش اتصال",
  guides_tag_en:"SETUP GUIDES",
  guides_title:"سیستم و پروتکل را انتخاب کن؛ مرحله‌به‌مرحله جلو برو.",
  guides_title_en:"Choose your device and protocol, then follow the real steps.",
  guides_description:"آموزش‌های واقعی با برنامه معتبر، اطلاعات لازم، مسیر دقیق منوها، تصاویر مراحل و رفع خطا در همین بخش قرار گرفته‌اند.",
  guides_description_en:"Real guides include verified clients, required credentials, exact menus, step images and troubleshooting.",

  account_tag:"پنل کاربری",
  account_tag_en:"CUSTOMER PANEL",
  account_title:"خرید و مدیریت اشتراک، در یک حساب.",
  account_title_en:"Purchase and manage subscriptions in one account.",
  account_description:"بعد از ورود می‌توانید اشتراک، حجم، اعتبار و اطلاعات اتصال خود را مدیریت کنید.",
  account_description_en:"Sign in to manage subscriptions, traffic, wallet balance and connection details.",
  account_primary_button:"ورود به پنل کاربری",
  account_primary_button_en:"Open customer panel",
  account_secondary_button:"پشتیبانی آنلاین",
  account_secondary_button_en:"Live support",
  account_item_1_title:"اشتراک‌ها",
  account_item_1_title_en:"Subscriptions",
  account_item_1_description:"مدیریت سرویس‌ها",
  account_item_1_description_en:"Manage services",
  account_item_2_title:"کیف پول",
  account_item_2_title_en:"Wallet",
  account_item_2_description:"سوابق مالی",
  account_item_2_description_en:"Financial history",
  account_item_3_title:"اطلاعات اتصال",
  account_item_3_title_en:"Connection",
  account_item_3_description:"تحویل امن",
  account_item_3_description_en:"Secure delivery",
  account_item_4_title:"پشتیبانی",
  account_item_4_title_en:"Support",
  account_item_4_description:"دسترسی مستقیم",
  account_item_4_description_en:"Direct access",

  faq_tag:"سوالات متداول",
  faq_tag_en:"FAQ",
  faq_title:"سوالات متداول",
  faq_title_en:"Frequently asked questions",
  faq_description:"پاسخ سوالات متداول درباره خرید، حجم، دستگاه و اتصال.",
  faq_description_en:"Answers to common questions about purchases, traffic, devices and connectivity.",
  faq_1_question:"بعد از خرید چه اتفاقی می‌افتد؟",
  faq_1_question_en:"What happens after purchase?",
  faq_1_answer:"سفارش داخل حساب شما ثبت می‌شود و وضعیت پرداخت، ساخت سرویس و اطلاعات اتصال را از پنل کاربری پیگیری می‌کنید.",
  faq_1_answer_en:"Your order is attached to your account so payment, provisioning and connection delivery remain trackable from the customer panel.",
  faq_2_question:"آیا روی چند دستگاه می‌توانم استفاده کنم؟",
  faq_2_question_en:"Can I use it on multiple devices?",
  faq_2_answer:"تعداد دستگاه مجاز برای هر پلن قبل از خرید روی همان کارت پلن نمایش داده می‌شود.",
  faq_2_answer_en:"The allowed device count is shown on each plan before purchase.",
  faq_3_question:"آیا محدودیت حجمی وجود دارد؟",
  faq_3_question_en:"Is traffic limited?",
  faq_3_answer:"حجم و مدت هر پلن مستقیماً از Backend نمایش داده می‌شود تا قبل از خرید دقیقاً بدانید چه چیزی دریافت می‌کنید.",
  faq_3_answer_en:"Traffic and duration come directly from the backend so you can see exactly what each plan includes.",
  faq_4_question:"برای اتصال چه پروتکل‌هایی ارائه می‌شود؟",
  faq_4_question_en:"Which protocols are available?",
  faq_4_answer:"پروتکل‌های فعال هر پلن روی همان پلن نمایش داده می‌شوند و می‌توانند شامل Cisco، OpenVPN، WireGuard، L2TP و V2Ray/Xray باشند.",
  faq_4_answer_en:"Each plan lists its active protocols, which can include Cisco, OpenVPN, WireGuard, L2TP and V2Ray/Xray.",
  faq_5_question:"اگر در اتصال مشکل داشتم چه کار کنم؟",
  faq_5_question_en:"What if I need help connecting?",
  faq_5_answer:"از آموزش‌های فروشگاه و پشتیبانی آنلاین برای دریافت راهنمایی استفاده کنید.",
  faq_5_answer_en:"Use the storefront guides and live support for help.",

  trust_speed_title:"سرعت بالا",
  trust_speed_title_en:"High speed",
  trust_speed_description:"اتصال پایدار و سریع",
  trust_speed_description_en:"Fast stable connection",
  trust_uptime_value:"99.9%",
  trust_uptime_value_en:"99.9%",
  trust_uptime_description:"پایداری بالا",
  trust_uptime_description_en:"Reliable uptime",
  trust_support_title:"پشتیبانی آنلاین",
  trust_support_title_en:"Live support",
  trust_support_description:"همیشه در دسترس",
  trust_support_description_en:"Always available",
  trust_protocols_description:"پروتکل اتصال",
  trust_protocols_description_en:"connection protocols",
  trust_payment_title:"پرداخت امن",
  trust_payment_title_en:"Secure payment",
  trust_payment_description:"مسیر خرید قابل پیگیری",
  trust_payment_description_en:"Traceable purchase flow",
  trust_activation_title:"فعال‌سازی سریع",
  trust_activation_title_en:"Fast activation",
  trust_activation_description:"تحویل داخل پنل",
  trust_activation_description_en:"Delivered in panel",

  final_cta_tag:"همین حالا شروع کنید",
  final_cta_tag_en:"Start now",
  final_cta_title:"همین حالا به اینترنت آزاد متصل شوید",
  final_cta_title_en:"Connect with confidence today",
  final_cta_description:"پلن مناسب را انتخاب کنید و مسیر خرید را در چند قدم ساده کامل کنید.",
  final_cta_description_en:"Choose the right plan and complete your purchase in a few simple steps.",
  final_cta_button:"خرید اشتراک",
  final_cta_button_en:"Buy subscription",

  contact_tag:"با ما در ارتباط باشید",
  contact_tag_en:"Stay connected",
  contact_title:"همیشه و همه‌جا کنار شما",
  contact_title_en:"We are always within reach",
  contact_description:"برای پشتیبانی، خبرها و ارتباط سریع از مسیرهای زیر استفاده کنید.",
  contact_description_en:"Use these channels for support, updates and quick contact.",
  telegram_url:"https://t.me/support",
  telegram_title:"تلگرام",
  telegram_title_en:"Telegram",
  telegram_description:"پشتیبانی و اطلاع‌رسانی",
  telegram_description_en:"Support & updates",
  instagram_url:"https://instagram.com/",
  instagram_title:"اینستاگرام",
  instagram_title_en:"Instagram",
  instagram_description:"اخبار و محتوای آموزشی",
  instagram_description_en:"News & learning",
  whatsapp_url:"https://wa.me/",
  whatsapp_title:"واتس‌اپ",
  whatsapp_title_en:"WhatsApp",
  whatsapp_description:"ارتباط سریع",
  whatsapp_description_en:"Quick contact",
  chat_title:"پشتیبانی آنلاین",
  chat_title_en:"Live support",
  chat_description:"سوال دارید؟ همین حالا با ما چت کنید.",
  chat_description_en:"Need help? Start a live chat now.",

  footer_tagline:"اینترنت آزاد، سریع و مطمئن",
  footer_tagline_en:"Fast, reliable connectivity",
  footer_quick_title:"لینک‌های سریع",
  footer_quick_title_en:"Quick links",
  footer_support_title:"خدمات و پشتیبانی",
  footer_support_title_en:"Services & support",
  footer_social_title:"شبکه‌های اجتماعی",
  footer_social_title_en:"Social",
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
  show_telegram:true,
  show_instagram:true,
  show_whatsapp:true,
  section_order:[...STOREFRONT_SECTION_IDS],

  seo_title:"TwinPanel | اشتراک VPN",
  seo_description:"خرید و مدیریت اشتراک VPN با پشتیبانی از چند روش اتصال و پنل کاربری.",
  seo_keywords:"VPN, خرید VPN, OpenVPN, WireGuard, Cisco, L2TP, V2Ray",
  canonical_url:"https://movilineapp.com/",
  og_title:"TwinPanel | اشتراک VPN",
  og_description:"خرید و مدیریت اشتراک VPN از یک پنل.",
  og_image:"",
  robots_index:true,
  robots_follow:true,
};

const bool=(value:unknown,fallback:boolean)=>typeof value==="boolean"?value:fallback;
const str=(value:unknown,fallback:string)=>typeof value==="string"&&value.trim()?value:fallback;

export function normalizeStorefrontSettings(raw:unknown):StorefrontSettings{
  const source=raw&&typeof raw==="object"?raw as Record<string,unknown>:{};
  const result={...DEFAULT_STOREFRONT_SETTINGS} as StorefrontSettings;

  for(const [key,defaultValue] of Object.entries(DEFAULT_STOREFRONT_SETTINGS)){
    if(key==="section_order"||key==="updated_at")continue;
    const value=source[key];
    if(typeof defaultValue==="boolean"){
      (result as unknown as Record<string,unknown>)[key]=bool(value,defaultValue);
    }else if(typeof defaultValue==="string"){
      (result as unknown as Record<string,unknown>)[key]=str(value,defaultValue);
    }
  }

  const order=Array.isArray(source.section_order)?source.section_order:DEFAULT_STOREFRONT_SETTINGS.section_order;
  const normalized:StorefrontSectionId[]=[];
  for(const item of order){
    const key=String(item) as StorefrontSectionId;
    if(STOREFRONT_SECTION_IDS.includes(key)&&!normalized.includes(key))normalized.push(key);
  }
  for(const key of STOREFRONT_SECTION_IDS)if(!normalized.includes(key))normalized.push(key);
  result.section_order=normalized;
  result.updated_at=typeof source.updated_at==="string"?source.updated_at:null;
  return result;
}

export function storefrontText(settings:StorefrontSettings,key:string,locale:StorefrontLocale){
  const source=settings as unknown as Record<string,unknown>;
  const localizedKey=locale==="en"?`${key}_en`:key;
  const localized=source[localizedKey];
  if(typeof localized==="string"&&localized.trim())return localized;
  const fallback=source[key];
  return typeof fallback==="string"?fallback:"";
}

export function isStorefrontSectionVisible(settings:StorefrontSettings,section:StorefrontSectionId){
  return Boolean((settings as unknown as Record<string,unknown>)[`show_${section}`]);
}
