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

  hero_kicker:"۱۵ روش اتصال، یک اشتراک",
  hero_kicker_en:"15 connection methods, one subscription",
  hero_title:"VPN پرسرعت برای همه دستگاه‌ها،",
  hero_title_en:"Fast VPN access for all your devices,",
  hero_highlight:"با اتصال پایدار و مطمئن.",
  hero_highlight_en:"with stable and reliable connectivity.",
  hero_description:"اشتراک مناسب خود را انتخاب کنید و روی ویندوز، اندروید، آیفون، مک و لینوکس متصل شوید. اطلاعات اتصال بعد از خرید داخل پنل کاربری شما قرار می‌گیرد.",
  hero_description_en:"Choose the plan that fits your needs and connect on Windows, Android, iPhone, macOS and Linux. Connection details are delivered to your customer account after purchase.",
  hero_primary_button:"خرید اشتراک",
  hero_primary_button_en:"Buy subscription",
  hero_secondary_button:"مشاهده پلن‌ها",
  hero_secondary_button_en:"View plans",
  hero_proof_1:"تحویل داخل پنل",
  hero_proof_1_en:"Delivered in your account",
  hero_proof_2:"۱۵ روش اتصال",
  hero_proof_2_en:"15 connection methods",
  hero_proof_3:"پشتیبانی آنلاین",
  hero_proof_3_en:"Live support",

  plans_tag:"اشتراک‌های VPN",
  plans_tag_en:"VPN PLANS",
  plans_title:"پلن مناسب مصرف خود را انتخاب کنید.",
  plans_title_en:"Choose the VPN plan that fits your usage.",
  plans_description:"حجم، مدت و تعداد دستگاه هر پلن را مقایسه کنید و اشتراک مناسب خود را مستقیم خریداری کنید.",
  plans_description_en:"Compare traffic, duration and device limits, then choose the subscription that fits your needs.",
  plan_feature_1:"فعال‌سازی سریع بعد از پرداخت",
  plan_feature_1_en:"Fast activation after payment",
  plan_feature_2:"تحویل اطلاعات اتصال داخل پنل",
  plan_feature_2_en:"Connection details delivered in your account",
  plan_feature_3:"مناسب ویندوز، اندروید، آیفون، مک و لینوکس",
  plan_feature_3_en:"Works with Windows, Android, iPhone, macOS and Linux",

  protocols_tag:"روش‌های اتصال",
  protocols_tag_en:"CONNECTION METHODS",
  protocols_title:"برای هر دستگاه و شبکه، روش اتصال مناسب دارید.",
  protocols_title_en:"The right connection method for every device and network.",
  protocols_description:"اشتراک‌ها از چند روش اتصال پشتیبانی می‌کنند تا در شرایط مختلف شبکه بتوانید گزینه مناسب را انتخاب کنید.",
  protocols_description_en:"Subscriptions support multiple connection methods so you can choose the best option for your device and network conditions.",

  services_tag:"امکانات سرویس",
  services_tag_en:"SERVICE FEATURES",
  services_title:"همه چیز برای یک اتصال راحت و پایدار آماده است.",
  services_title_en:"Everything you need for a simple and reliable VPN experience.",
  services_description:"سرعت مناسب، پایداری اتصال، پشتیبانی چند دستگاه، تحویل سریع اطلاعات اتصال و پشتیبانی آنلاین در کنار هم قرار گرفته‌اند.",
  services_description_en:"Speed, connection stability, multi-device support, quick delivery and live assistance are all included in one service experience.",
  service_1_title:"سرعت بالا",
  service_1_title_en:"High speed",
  service_1_description:"مسیرهای مناسب برای وب‌گردی، دانلود و استفاده روزمره.",
  service_1_description_en:"Optimized routes for browsing, downloads and everyday use.",
  service_2_title:"پایداری اتصال",
  service_2_title_en:"Reliable connection",
  service_2_description:"اتصال پایدار برای استفاده مداوم در شبکه‌های مختلف.",
  service_2_description_en:"Stable connectivity for everyday use across different networks.",
  service_3_title:"۱۵ روش اتصال",
  service_3_title_en:"15 connection methods",
  service_3_description:"برای دستگاه و شرایط شبکه خود گزینه مناسب را انتخاب کنید.",
  service_3_description_en:"Choose the method that best fits your device and network.",
  service_4_title:"پشتیبانی همه دستگاه‌ها",
  service_4_title_en:"Multi-device support",
  service_4_description:"قابل استفاده روی ویندوز، اندروید، آیفون، مک و لینوکس.",
  service_4_description_en:"Use your service on Windows, Android, iPhone, macOS and Linux.",
  service_5_title:"پشتیبانی آنلاین",
  service_5_title_en:"Live support",
  service_5_description:"برای خرید، نصب و اتصال می‌توانید مستقیم راهنمایی بگیرید.",
  service_5_description_en:"Get direct help with purchasing, setup and connectivity.",
  service_6_title:"مدیریت از پنل",
  service_6_title_en:"Account management",
  service_6_description:"اشتراک، سفارش، پرداخت و اطلاعات اتصال را از یک حساب مدیریت کنید.",
  service_6_description_en:"Manage subscriptions, orders, payments and connection details from one account.",

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
  account_item_1_title:"اشتراک‌ها",
  account_item_1_title_en:"Subscriptions",
  account_item_1_description:"مدیریت سرویس‌ها",
  account_item_1_description_en:"Manage services",
  account_item_2_title:"کیف پول",
  account_item_2_title_en:"Wallet",
  account_item_2_description:"سوابق مالی",
  account_item_2_description_en:"Financial history",
  account_item_3_title:"اطلاعات اتصال",
  account_item_3_title_en:"Connection details",
  account_item_3_description:"دسترسی داخل حساب",
  account_item_3_description_en:"Available in your account",
  account_item_4_title:"پشتیبانی",
  account_item_4_title_en:"Support",
  account_item_4_description:"راهنمای خرید و اتصال",
  account_item_4_description_en:"Purchase and setup help",

  faq_tag:"سوالات متداول",
  faq_tag_en:"FAQ",
  faq_title:"قبل از خرید، جواب سوال‌های مهم را ببینید.",
  faq_title_en:"Answers to common questions before you buy.",
  faq_description:"اطلاعات کوتاه و کاربردی درباره خرید، دستگاه‌ها، حجم، اتصال و پشتیبانی.",
  faq_description_en:"Quick answers about purchasing, devices, traffic, connectivity and support.",
  faq_1_question:"بعد از خرید چه اتفاقی می‌افتد؟",
  faq_1_question_en:"What happens after purchase?",
  faq_1_answer:"بعد از تکمیل خرید، وضعیت اشتراک و اطلاعات اتصال داخل پنل کاربری شما قرار می‌گیرد.",
  faq_1_answer_en:"After purchase, your subscription status and connection details are available in your customer account.",
  faq_2_question:"روی چه دستگاه‌هایی می‌توانم استفاده کنم؟",
  faq_2_question_en:"Which devices are supported?",
  faq_2_answer:"سرویس برای ویندوز، اندروید، آیفون، macOS و لینوکس قابل استفاده است؛ محدودیت تعداد دستگاه به پلن انتخابی شما بستگی دارد.",
  faq_2_answer_en:"The service supports Windows, Android, iPhone, macOS and Linux. The number of allowed devices depends on your selected plan.",
  faq_3_question:"حجم و مدت اشتراک چطور مشخص می‌شود؟",
  faq_3_question_en:"How are traffic and duration determined?",
  faq_3_answer:"حجم، مدت و تعداد دستگاه هر پلن قبل از خرید روی همان پلن نمایش داده می‌شود.",
  faq_3_answer_en:"Traffic, duration and device limits are shown on each plan before purchase.",
  faq_4_question:"برای اتصال چه روش‌هایی وجود دارد؟",
  faq_4_question_en:"Which connection methods are available?",
  faq_4_answer:"بسته به پلن، چند روش اتصال در اختیار شما قرار می‌گیرد تا برای دستگاه و شبکه خود گزینه مناسب را انتخاب کنید.",
  faq_4_answer_en:"Depending on the plan, multiple connection methods are available so you can choose the best option for your device and network.",
  faq_5_question:"اگر در نصب یا اتصال مشکل داشتم چه کار کنم؟",
  faq_5_question_en:"What if I need help with setup or connection?",
  faq_5_answer:"از بخش آموزش اتصال یا پشتیبانی آنلاین برای دریافت راهنمایی استفاده کنید.",
  faq_5_answer_en:"Use the setup guides or live support whenever you need help.",

  trust_speed_title:"سرعت بالا",
  trust_speed_title_en:"High speed",
  trust_speed_description:"مناسب استفاده روزمره",
  trust_speed_description_en:"Built for everyday use",
  trust_uptime_value:"اتصال پایدار",
  trust_uptime_value_en:"Stable connection",
  trust_uptime_description:"برای شبکه‌های مختلف",
  trust_uptime_description_en:"Across different networks",
  trust_support_title:"پشتیبانی آنلاین",
  trust_support_title_en:"Live support",
  trust_support_description:"راهنمای خرید و اتصال",
  trust_support_description_en:"Purchase and setup help",
  trust_protocols_description:"روش اتصال در دسترس",
  trust_protocols_description_en:"available connection methods",
  trust_payment_title:"خرید قابل پیگیری",
  trust_payment_title_en:"Trackable purchase",
  trust_payment_description:"وضعیت سفارش داخل حساب",
  trust_payment_description_en:"Order status in your account",
  trust_activation_title:"فعال‌سازی سریع",
  trust_activation_title_en:"Fast activation",
  trust_activation_description:"تحویل داخل پنل",
  trust_activation_description_en:"Delivered in your account",

  final_cta_tag:"آماده اتصال هستید؟",
  final_cta_tag_en:"READY TO CONNECT?",
  final_cta_title:"پلن مناسب را انتخاب کنید و اتصال را شروع کنید.",
  final_cta_title_en:"Choose your plan and get connected.",
  final_cta_description:"اشتراک مناسب خود را بخرید و بعد از فعال‌سازی، اطلاعات اتصال را از پنل کاربری دریافت کنید.",
  final_cta_description_en:"Buy the plan that fits your needs and receive your connection details in your account after activation.",
  final_cta_button:"خرید اشتراک",
  final_cta_button_en:"Buy subscription",

  contact_tag:"پشتیبانی و ارتباط",
  contact_tag_en:"SUPPORT & CONTACT",
  contact_title:"برای خرید و اتصال، کنار شما هستیم.",
  contact_title_en:"We are here to help with purchasing and setup.",
  contact_description:"برای سوال‌های قبل از خرید، راه‌اندازی سرویس یا مشکلات اتصال از کانال‌های ارتباطی و چت آنلاین استفاده کنید.",
  contact_description_en:"Use the available contact channels or live chat for pre-sales questions, setup help and connection support.",
  telegram_url:"https://t.me/support",
  telegram_title:"تلگرام",
  telegram_title_en:"Telegram",
  telegram_description:"پشتیبانی و اطلاع‌رسانی",
  telegram_description_en:"Support and updates",
  instagram_url:"https://instagram.com/",
  instagram_title:"اینستاگرام",
  instagram_title_en:"Instagram",
  instagram_description:"اخبار و آموزش اتصال",
  instagram_description_en:"Updates and setup tips",
  whatsapp_url:"https://wa.me/",
  whatsapp_title:"واتس‌اپ",
  whatsapp_title_en:"WhatsApp",
  whatsapp_description:"ارتباط سریع با پشتیبانی",
  whatsapp_description_en:"Quick support contact",
  chat_title:"پشتیبانی آنلاین",
  chat_title_en:"Live support",
  chat_description:"برای خرید، نصب یا اتصال سوال دارید؟ با پشتیبانی چت کنید.",
  chat_description_en:"Need help with purchasing, setup or connection? Start a live chat.",

  footer_tagline:"VPN سریع و پایدار برای همه دستگاه‌های شما.",
  footer_tagline_en:"Fast, reliable VPN access for all your devices.",
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

  seo_title:"اشتراک VPN | اتصال سریع و پایدار",
  seo_description:"خرید اشتراک VPN برای ویندوز، اندروید، آیفون، مک و لینوکس با چند روش اتصال، پنل کاربری و پشتیبانی آنلاین.",
  seo_keywords:"VPN, خرید VPN, اشتراک VPN, OpenVPN, WireGuard, Cisco, L2TP, V2Ray, Android VPN, iPhone VPN, Windows VPN",
  canonical_url:"https://movilineapp.com/",
  og_title:"اشتراک VPN | اتصال سریع و پایدار",
  og_description:"خرید و مدیریت اشتراک VPN برای همه دستگاه‌ها از یک پنل کاربری.",
  og_image:"",
  robots_index:true,
  robots_follow:true,
};

const bool=(value:unknown,fallback:boolean)=>typeof value==="boolean"?value:fallback;
const str=(value:unknown,fallback:string)=>typeof value==="string"&&value.trim()?value:fallback;

const LEGACY_GENERATED_COPY=new Set([
  "۵ پروتکل، یک حساب کاربری","5 protocols, one account",
  "حجم، مدت، تعداد دستگاه و پروتکل‌های هر پلن قبل از خرید نمایش داده می‌شود.","Compare traffic, duration, device limits and protocols before purchase.",
  "پشتیبانی از پروتکل‌های همین پلن","Support for this plan's protocols",
  "حجم و مدت هر پلن مستقیماً از Backend نمایش داده می‌شود تا قبل از خرید دقیقاً بدانید چه چیزی دریافت می‌کنید.","Traffic and duration come directly from the backend so you can see exactly what each plan includes.",
  "پروتکل‌های فعال هر پلن روی همان پلن نمایش داده می‌شوند و می‌توانند شامل Cisco، OpenVPN، WireGuard، L2TP و V2Ray/Xray باشند.","Each plan lists its active protocols, which can include Cisco, OpenVPN, WireGuard, L2TP and V2Ray/Xray.",
]);

export function normalizeStorefrontSettings(raw:unknown):StorefrontSettings{
  const source=raw&&typeof raw==="object"?raw as Record<string,unknown>:{};
  const result={...DEFAULT_STOREFRONT_SETTINGS} as StorefrontSettings;

  for(const [key,defaultValue] of Object.entries(DEFAULT_STOREFRONT_SETTINGS)){
    if(key==="section_order"||key==="updated_at")continue;
    const value=source[key];
    if(typeof defaultValue==="boolean"){
      (result as unknown as Record<string,unknown>)[key]=bool(value,defaultValue);
    }else if(typeof defaultValue==="string"){
      const normalizedValue=typeof value==="string"&&LEGACY_GENERATED_COPY.has(value)?defaultValue:str(value,defaultValue);
      (result as unknown as Record<string,unknown>)[key]=normalizedValue;
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
