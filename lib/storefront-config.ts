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

  plans_tag:string;
  plans_tag_en:string;
  plans_title:string;
  plans_title_en:string;
  plans_description:string;
  plans_description_en:string;

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

  faq_tag:string;
  faq_tag_en:string;
  faq_title:string;
  faq_title_en:string;
  faq_description:string;
  faq_description_en:string;

  show_plans:boolean;
  show_protocols:boolean;
  show_services:boolean;
  show_guides:boolean;
  show_account:boolean;
  show_faq:boolean;
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
  hero_primary_button:"مشاهده پلن‌ها",
  hero_primary_button_en:"View plans",
  hero_secondary_button:"ورود به پنل کاربری",
  hero_secondary_button_en:"Customer panel",

  plans_tag:"اشتراک‌های VPN",
  plans_tag_en:"VPN PLANS",
  plans_title:"انتخاب اشتراک",
  plans_title_en:"Choose your plan",
  plans_description:"حجم، مدت، تعداد دستگاه و پروتکل‌های هر پلن قبل از خرید نمایش داده می‌شود.",
  plans_description_en:"Compare traffic, duration, device limits and protocols before purchase.",

  protocols_tag:"پروتکل‌های اتصال",
  protocols_tag_en:"PROTOCOLS",
  protocols_title:"روش اتصال مناسب خودت را انتخاب کن.",
  protocols_title_en:"Choose the connection method that fits you.",
  protocols_description:"هر اشتراک می‌تواند چند پروتکل داشته باشد. روی هر گزینه بزن تا کاربرد و ویژگی‌های آن را ببینی.",
  protocols_description_en:"A subscription can include multiple protocols. Review each option to find the best fit.",

  services_tag:"خدمات TwinPanel",
  services_tag_en:"SERVICES",
  services_title:"بعد از خرید، همه‌چیز داخل حساب شماست.",
  services_title_en:"Everything stays inside your account after purchase.",
  services_description:"اطلاعات اتصال، حجم و اعتبار و اشتراک‌های شما از پنل کاربری در دسترس است.",
  services_description_en:"Connection details, traffic, wallet balance and subscriptions are available from the customer panel.",

  guides_tag:"آموزش اتصال",
  guides_tag_en:"SETUP GUIDES",
  guides_title:"راهنمای نصب و اتصال برای همه دستگاه‌ها",
  guides_title_en:"Setup guidance for every device",
  guides_description:"پروتکل و سیستم‌عامل را انتخاب کنید تا مراحل نصب و اتصال نمایش داده شود.",
  guides_description_en:"Choose a protocol and operating system to see the connection flow.",

  account_tag:"پنل کاربری TwinPanel",
  account_tag_en:"CUSTOMER PANEL",
  account_title:"خرید و مدیریت اشتراک، در یک حساب.",
  account_title_en:"Purchase and manage subscriptions in one account.",
  account_description:"بعد از ورود می‌توانید اشتراک، حجم، اعتبار و اطلاعات اتصال خود را مدیریت کنید.",
  account_description_en:"Sign in to manage subscriptions, traffic, wallet balance and connection details.",

  faq_tag:"سوالات متداول",
  faq_tag_en:"FAQ",
  faq_title:"سوالات متداول",
  faq_title_en:"Frequently asked questions",
  faq_description:"پاسخ سوالات متداول درباره خرید، حجم، دستگاه و اتصال.",
  faq_description_en:"Answers to common questions about purchases, traffic, devices and connectivity.",

  show_plans:true,
  show_protocols:true,
  show_services:true,
  show_guides:true,
  show_account:true,
  show_faq:true,
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
