import {
  STOREFRONT_SECTION_IDS,
  type StorefrontSectionId,
  type StorefrontSettings,
} from "./storefront-config";

export type StoreTemplateOptionValue=string|number|boolean|string[];
export type StoreTemplateOptionMap=Record<string,StoreTemplateOptionValue>;
export type StoreTemplateOptionFieldType="text"|"textarea"|"color"|"toggle"|"select"|"section-order";

export type StoreTemplateOptionChoice={
  value:string;
  fa:string;
  en:string;
};

export type StoreTemplateOptionField={
  key:string;
  type:StoreTemplateOptionFieldType;
  fa:string;
  en:string;
  helpFa?:string;
  helpEn?:string;
  choices?:StoreTemplateOptionChoice[];
};

export type StoreTemplateOptionGroup={
  id:string;
  fa:string;
  en:string;
  descriptionFa?:string;
  descriptionEn?:string;
  fields:StoreTemplateOptionField[];
};

export type StoreTemplateOptionDefinition={
  templateId:string;
  version:number;
  defaults:StoreTemplateOptionMap;
  groups:StoreTemplateOptionGroup[];
};

const text=(key:string,fa:string,en:string):StoreTemplateOptionField=>({key,type:"text",fa,en});
const area=(key:string,fa:string,en:string):StoreTemplateOptionField=>({key,type:"textarea",fa,en});
const toggle=(key:string,fa:string,en:string):StoreTemplateOptionField=>({key,type:"toggle",fa,en});

const COMMON_CONTENT_GROUPS:StoreTemplateOptionGroup[]=[
  {
    id:"hero",
    fa:"Hero و شروع صفحه",
    en:"Hero & opening",
    descriptionFa:"متن و CTA این بخش فقط متعلق به همین قالب است.",
    descriptionEn:"This copy and CTA belong only to this template.",
    fields:[
      text("hero_kicker","متن بالای عنوان","Kicker"),
      text("hero_title","عنوان اصلی","Main title"),
      text("hero_highlight","بخش برجسته عنوان","Highlighted title"),
      area("hero_description","توضیح اصلی","Main description"),
      text("hero_primary_button","دکمه اصلی","Primary button"),
      text("hero_secondary_button","دکمه دوم","Secondary button"),
      text("hero_proof_1","نکته اعتماد ۱","Proof item 1"),
      text("hero_proof_2","نکته اعتماد ۲","Proof item 2"),
      text("hero_proof_3","نکته اعتماد ۳","Proof item 3"),
    ],
  },
  {
    id:"plans",
    fa:"پلن‌ها",
    en:"Plans",
    fields:[
      text("plans_tag","برچسب بخش","Section tag"),
      text("plans_title","عنوان بخش","Section title"),
      area("plans_description","توضیح بخش","Section description"),
      text("plan_feature_1","مزیت پلن ۱","Plan benefit 1"),
      text("plan_feature_2","مزیت پلن ۲","Plan benefit 2"),
      text("plan_feature_3","مزیت پلن ۳","Plan benefit 3"),
    ],
  },
  {
    id:"protocols",
    fa:"پروتکل‌ها",
    en:"Protocols",
    fields:[
      text("protocols_tag","برچسب بخش","Section tag"),
      text("protocols_title","عنوان بخش","Section title"),
      area("protocols_description","توضیح بخش","Section description"),
    ],
  },
  {
    id:"services",
    fa:"خدمات و مزایا",
    en:"Services & benefits",
    fields:[
      text("services_tag","برچسب بخش","Section tag"),
      text("services_title","عنوان بخش","Section title"),
      area("services_description","توضیح بخش","Section description"),
      text("service_1_title","کارت ۱ - عنوان","Card 1 title"),
      area("service_1_description","کارت ۱ - توضیح","Card 1 description"),
      text("service_2_title","کارت ۲ - عنوان","Card 2 title"),
      area("service_2_description","کارت ۲ - توضیح","Card 2 description"),
      text("service_3_title","کارت ۳ - عنوان","Card 3 title"),
      area("service_3_description","کارت ۳ - توضیح","Card 3 description"),
      text("service_4_title","کارت ۴ - عنوان","Card 4 title"),
      area("service_4_description","کارت ۴ - توضیح","Card 4 description"),
      text("service_5_title","کارت ۵ - عنوان","Card 5 title"),
      area("service_5_description","کارت ۵ - توضیح","Card 5 description"),
      text("service_6_title","کارت ۶ - عنوان","Card 6 title"),
      area("service_6_description","کارت ۶ - توضیح","Card 6 description"),
    ],
  },
  {
    id:"guides-account",
    fa:"آموزش و حساب کاربری",
    en:"Guides & account",
    fields:[
      text("guides_tag","آموزش - برچسب","Guides tag"),
      text("guides_title","آموزش - عنوان","Guides title"),
      area("guides_description","آموزش - توضیح","Guides description"),
      text("account_tag","حساب - برچسب","Account tag"),
      text("account_title","حساب - عنوان","Account title"),
      area("account_description","حساب - توضیح","Account description"),
      text("account_primary_button","حساب - دکمه اصلی","Account primary button"),
      text("account_secondary_button","حساب - دکمه پشتیبانی","Account support button"),
      text("account_item_1_title","آیتم حساب ۱ - عنوان","Account item 1 title"),
      text("account_item_1_description","آیتم حساب ۱ - توضیح","Account item 1 description"),
      text("account_item_2_title","آیتم حساب ۲ - عنوان","Account item 2 title"),
      text("account_item_2_description","آیتم حساب ۲ - توضیح","Account item 2 description"),
      text("account_item_3_title","آیتم حساب ۳ - عنوان","Account item 3 title"),
      text("account_item_3_description","آیتم حساب ۳ - توضیح","Account item 3 description"),
      text("account_item_4_title","آیتم حساب ۴ - عنوان","Account item 4 title"),
      text("account_item_4_description","آیتم حساب ۴ - توضیح","Account item 4 description"),
    ],
  },
  {
    id:"faq",
    fa:"سوالات متداول",
    en:"FAQ",
    fields:[
      text("faq_tag","برچسب بخش","Section tag"),
      text("faq_title","عنوان بخش","Section title"),
      area("faq_description","توضیح بخش","Section description"),
      text("faq_1_question","سوال ۱","Question 1"),area("faq_1_answer","پاسخ ۱","Answer 1"),
      text("faq_2_question","سوال ۲","Question 2"),area("faq_2_answer","پاسخ ۲","Answer 2"),
      text("faq_3_question","سوال ۳","Question 3"),area("faq_3_answer","پاسخ ۳","Answer 3"),
      text("faq_4_question","سوال ۴","Question 4"),area("faq_4_answer","پاسخ ۴","Answer 4"),
      text("faq_5_question","سوال ۵","Question 5"),area("faq_5_answer","پاسخ ۵","Answer 5"),
    ],
  },
  {
    id:"trust-cta",
    fa:"اعتماد و CTA نهایی",
    en:"Trust & final CTA",
    fields:[
      text("trust_speed_title","سرعت - عنوان","Speed title"),
      text("trust_speed_description","سرعت - توضیح","Speed description"),
      text("trust_uptime_value","پایداری - مقدار","Uptime value"),
      text("trust_uptime_description","پایداری - توضیح","Uptime description"),
      text("trust_support_title","پشتیبانی - عنوان","Support title"),
      text("trust_support_description","پشتیبانی - توضیح","Support description"),
      text("trust_protocols_description","پروتکل‌ها - توضیح","Protocols description"),
      text("trust_payment_title","پرداخت - عنوان","Payment title"),
      text("trust_payment_description","پرداخت - توضیح","Payment description"),
      text("trust_activation_title","فعال‌سازی - عنوان","Activation title"),
      text("trust_activation_description","فعال‌سازی - توضیح","Activation description"),
      text("final_cta_tag","CTA - برچسب","CTA tag"),
      text("final_cta_title","CTA - عنوان","CTA title"),
      area("final_cta_description","CTA - توضیح","CTA description"),
      text("final_cta_button","CTA - دکمه","CTA button"),
    ],
  },
  {
    id:"contact-footer",
    fa:"ارتباط و فوتر",
    en:"Contact & footer",
    descriptionFa:"آدرس شبکه‌های اجتماعی همچنان از تنظیمات عمومی/یکپارچه‌سازی خوانده می‌شود؛ متن نمایشی مخصوص قالب است.",
    descriptionEn:"Social URLs remain shared integration data; visible copy is template-specific.",
    fields:[
      text("contact_tag","ارتباط - برچسب","Contact tag"),
      text("contact_title","ارتباط - عنوان","Contact title"),
      area("contact_description","ارتباط - توضیح","Contact description"),
      text("telegram_title","تلگرام - عنوان","Telegram title"),
      text("telegram_description","تلگرام - توضیح","Telegram description"),
      text("instagram_title","اینستاگرام - عنوان","Instagram title"),
      text("instagram_description","اینستاگرام - توضیح","Instagram description"),
      text("whatsapp_title","واتس‌اپ - عنوان","WhatsApp title"),
      text("whatsapp_description","واتس‌اپ - توضیح","WhatsApp description"),
      text("chat_title","چت - عنوان","Chat title"),
      area("chat_description","چت - توضیح","Chat description"),
      area("footer_tagline","فوتر - زیرعنوان برند","Footer tagline"),
      text("footer_quick_title","فوتر - لینک‌های سریع","Footer quick links heading"),
      text("footer_support_title","فوتر - خدمات و پشتیبانی","Footer support heading"),
      text("footer_social_title","فوتر - شبکه‌های اجتماعی","Footer social heading"),
      text("footer_rights","فوتر - حقوق","Footer rights"),
    ],
  },
  {
    id:"layout",
    fa:"نمایش و ترتیب بخش‌ها",
    en:"Sections & order",
    fields:[
      toggle("show_plans","نمایش پلن‌ها","Show plans"),
      toggle("show_protocols","نمایش پروتکل‌ها","Show protocols"),
      toggle("show_services","نمایش خدمات","Show services"),
      toggle("show_guides","نمایش آموزش","Show guides"),
      toggle("show_account","نمایش حساب کاربری","Show account"),
      toggle("show_faq","نمایش FAQ","Show FAQ"),
      toggle("show_final_cta","نمایش CTA نهایی","Show final CTA"),
      toggle("show_contact","نمایش ارتباط","Show contact"),
      {key:"section_order",type:"section-order",fa:"ترتیب بخش‌های اصلی",en:"Main section order"},
    ],
  },
];

const appearanceGroup=(extra:StoreTemplateOptionField[]=[]):StoreTemplateOptionGroup=>({
  id:"appearance",
  fa:"ظاهر قالب",
  en:"Template appearance",
  descriptionFa:"این گزینه‌ها فقط روی همین قالب اعمال می‌شوند و با تعویض قالب از بین نمی‌روند.",
  descriptionEn:"These options apply only to this template and stay saved when you switch templates.",
  fields:[
    {key:"theme_primary",type:"color",fa:"رنگ اصلی قالب",en:"Template primary color"},
    {key:"theme_secondary",type:"color",fa:"رنگ مکمل قالب",en:"Template secondary color"},
    ...extra,
  ],
});

const commonVisibility={
  show_plans:true,
  show_protocols:true,
  show_services:true,
  show_guides:true,
  show_account:true,
  show_faq:true,
  show_final_cta:true,
  show_contact:true,
  section_order:[...STOREFRONT_SECTION_IDS],
};

const conversionDefaults:StoreTemplateOptionMap={
  theme_primary:"#7c3aed",
  theme_secondary:"#4f46e5",
  hero_kicker:"۵ پروتکل، یک حساب کاربری",
  hero_title:"اشتراک VPN برای چند روش اتصال،",
  hero_highlight:"از یک پنل.",
  hero_description:"پلن مناسب را انتخاب کنید و تمام اطلاعات اتصال را بعد از خرید داخل حساب خود تحویل بگیرید.",
  hero_primary_button:"خرید اشتراک",
  hero_secondary_button:"مشاهده پلن‌ها",
  hero_proof_1:"تحویل داخل پنل",hero_proof_2:"چند پروتکل",hero_proof_3:"پشتیبانی آنلاین",
  plans_tag:"اشتراک‌های VPN",plans_title:"انتخاب اشتراک",plans_description:"حجم، مدت، دستگاه و پروتکل‌ها را قبل از خرید مقایسه کنید.",
  plan_feature_1:"فعال‌سازی سریع بعد از پرداخت",plan_feature_2:"تحویل اطلاعات اتصال داخل پنل",plan_feature_3:"پشتیبانی از پروتکل‌های همان پلن",
  protocols_tag:"پروتکل‌های اتصال",protocols_title:"روش اتصال مناسب شبکه و دستگاهت را انتخاب کن.",protocols_description:"هر پلن می‌تواند چند روش اتصال در اختیار شما قرار دهد.",
  services_tag:"خدمات",services_title:"بعد از خرید همه‌چیز داخل حساب شماست.",services_description:"مدیریت اشتراک، حجم، اتصال و پشتیبانی از یک مسیر واحد.",
  service_1_title:"سرعت بالا",service_1_description:"مسیر بهینه برای استفاده روزمره.",
  service_2_title:"پایداری بالا",service_2_description:"تجربه اتصال پایدار و قابل اتکا.",
  service_3_title:"پروتکل‌های متنوع",service_3_description:"چند روش اتصال برای شبکه‌ها و دستگاه‌های مختلف.",
  service_4_title:"پشتیبانی آنلاین",service_4_description:"دسترسی مستقیم به راهنمایی و پشتیبانی.",
  service_5_title:"پرداخت قابل پیگیری",service_5_description:"وضعیت سفارش و پرداخت داخل حساب ثبت می‌شود.",
  service_6_title:"تحویل سریع",service_6_description:"اطلاعات سرویس پس از تکمیل خرید داخل پنل تحویل می‌شود.",
  guides_tag:"آموزش اتصال",guides_title:"سیستم و پروتکل را انتخاب کن و مرحله‌به‌مرحله جلو برو.",guides_description:"آموزش‌های واقعی، تصاویر مراحل و رفع خطا در همان صفحه در دسترس‌اند.",
  account_tag:"پنل کاربری",account_title:"خرید و مدیریت اشتراک در یک حساب.",account_description:"اشتراک‌ها، حجم، کیف پول و اطلاعات اتصال را از پنل مدیریت کنید.",account_primary_button:"ورود به پنل کاربری",account_secondary_button:"پشتیبانی آنلاین",
  account_item_1_title:"اشتراک‌ها",account_item_1_description:"مدیریت سرویس‌ها",account_item_2_title:"کیف پول",account_item_2_description:"سوابق مالی",account_item_3_title:"اطلاعات اتصال",account_item_3_description:"تحویل امن",account_item_4_title:"پشتیبانی",account_item_4_description:"دسترسی مستقیم",
  faq_tag:"سوالات متداول",faq_title:"قبل از خرید چه چیزهایی باید بدانم؟",faq_description:"پاسخ کوتاه به سوالات اصلی خرید و اتصال.",
  faq_1_question:"بعد از خرید چه اتفاقی می‌افتد؟",faq_1_answer:"سفارش به حساب شما متصل می‌شود و وضعیت ساخت سرویس و اطلاعات اتصال از پنل قابل پیگیری است.",
  faq_2_question:"آیا روی چند دستگاه قابل استفاده است؟",faq_2_answer:"تعداد دستگاه مجاز روی هر پلن مشخص شده است.",
  faq_3_question:"حجم و مدت چطور محاسبه می‌شود؟",faq_3_answer:"حجم و مدت هر پلن مستقیماً از اطلاعات واقعی همان پلن نمایش داده می‌شود.",
  faq_4_question:"چه پروتکل‌هایی ارائه می‌شود؟",faq_4_answer:"پروتکل‌های فعال هر پلن روی کارت همان پلن نمایش داده می‌شوند.",
  faq_5_question:"اگر اتصال مشکل داشت چه کنم؟",faq_5_answer:"از آموزش‌های داخل فروشگاه یا پشتیبانی آنلاین استفاده کنید.",
  trust_speed_title:"سرعت بالا",trust_speed_description:"اتصال سریع و پایدار",trust_uptime_value:"99.9%",trust_uptime_description:"پایداری سرویس",trust_support_title:"پشتیبانی آنلاین",trust_support_description:"دسترسی مستقیم",trust_protocols_description:"روش اتصال",trust_payment_title:"پرداخت امن",trust_payment_description:"قابل پیگیری در حساب",trust_activation_title:"فعال‌سازی سریع",trust_activation_description:"تحویل داخل پنل",
  final_cta_tag:"شروع خرید",final_cta_title:"پلن مناسب خودت را انتخاب کن.",final_cta_description:"خرید را کامل کن و اطلاعات سرویس را داخل پنل تحویل بگیر.",final_cta_button:"خرید اشتراک",
  contact_tag:"ارتباط",contact_title:"پشتیبانی و ارتباط سریع",contact_description:"از کانال‌های ارتباطی فعال برای پشتیبانی و اطلاع‌رسانی استفاده کنید.",telegram_title:"تلگرام",telegram_description:"پشتیبانی و اطلاع‌رسانی",instagram_title:"اینستاگرام",instagram_description:"اخبار و آموزش",whatsapp_title:"واتس‌اپ",whatsapp_description:"ارتباط سریع",chat_title:"پشتیبانی آنلاین",chat_description:"سوال دارید؟ همین حالا گفت‌وگو را شروع کنید.",footer_tagline:"اتصال سریع، پایدار و قابل مدیریت",footer_quick_title:"لینک‌های سریع",footer_support_title:"خدمات و پشتیبانی",footer_social_title:"شبکه‌های اجتماعی",footer_rights:"تمامی حقوق محفوظ است.",
  ...commonVisibility,
};

const editorialDefaults:StoreTemplateOptionMap={
  theme_primary:"#8b5cf6",
  theme_secondary:"#6366f1",
  hero_kicker:"CONNECTIVITY / 2027",
  hero_title:"یک فروشگاه دقیق برای انتخاب سرویس،",
  hero_highlight:"بدون شلوغی.",
  hero_description:"پلن‌ها، روش‌های اتصال و آموزش‌ها در یک ساختار ادیتوریال شفاف کنار هم قرار گرفته‌اند تا تصمیم‌گیری سریع‌تر باشد.",
  hero_primary_button:"مشاهده پلن‌ها",
  hero_secondary_button:"راهنمای اتصال",
  hero_proof_1:"پلن‌های واقعی",hero_proof_2:"۵ روش اتصال",hero_proof_3:"مدیریت از یک حساب",
  plans_tag:"01 / PLANS",plans_title:"پلنی را انتخاب کن که دقیقاً با مصرفت جور است.",plans_description:"قیمت، حجم، مدت و تعداد دستگاه بدون متن اضافه در کنار هم دیده می‌شوند.",
  plan_feature_1:"تحویل اطلاعات اتصال در حساب",plan_feature_2:"نمایش پروتکل‌های فعال همین پلن",plan_feature_3:"قابل پیگیری از سفارش تا سرویس",
  protocols_tag:"02 / PROTOCOLS",protocols_title:"یک حساب؛ چند مسیر برای اتصال.",protocols_description:"بسته به دستگاه و شرایط شبکه، از روش اتصال مناسب همان لحظه استفاده کنید.",
  services_tag:"03 / EXPERIENCE",services_title:"فروشگاه فقط محل خرید نیست؛ نقطه شروع مدیریت سرویس است.",services_description:"هر چیزی که بعد از پرداخت لازم دارید به شکل ساختاریافته در اختیار شماست.",
  service_1_title:"مسیر بهینه",service_1_description:"اتصال با مسیرهای مناسب برای استفاده روزمره.",
  service_2_title:"پایداری عملی",service_2_description:"تمرکز روی تجربه واقعی اتصال، نه فقط عدد و شعار.",
  service_3_title:"انتخاب پروتکل",service_3_description:"امکان استفاده از روش‌های اتصال مختلف متناسب با شبکه.",
  service_4_title:"راهنمای واقعی",service_4_description:"آموزش‌های مرحله‌به‌مرحله برای دستگاه و پروتکل انتخابی.",
  service_5_title:"سفارش شفاف",service_5_description:"وضعیت خرید و پرداخت داخل حساب قابل پیگیری است.",
  service_6_title:"یک حساب مرکزی",service_6_description:"اشتراک‌ها، حجم و اطلاعات اتصال از یک پنل مدیریت می‌شوند.",
  guides_tag:"04 / GUIDES",guides_title:"از انتخاب سیستم‌عامل تا اتصال نهایی، قدم‌به‌قدم.",guides_description:"راهنما را بر اساس دستگاه و پروتکل فیلتر کنید و مراحل واقعی را همان‌جا ببینید.",
  account_tag:"05 / ACCOUNT",account_title:"بعد از خرید، کنترل سرویس دست خودت می‌ماند.",account_description:"اشتراک، کیف پول، حجم و اطلاعات اتصال را بدون خروج از حساب مدیریت کنید.",account_primary_button:"باز کردن حساب",account_secondary_button:"گفت‌وگو با پشتیبانی",
  account_item_1_title:"Subscriptions",account_item_1_description:"سرویس‌های فعال",account_item_2_title:"Wallet",account_item_2_description:"پرداخت‌ها و اعتبار",account_item_3_title:"Connection",account_item_3_description:"اطلاعات اتصال",account_item_4_title:"Support",account_item_4_description:"کمک مستقیم",
  faq_tag:"06 / FAQ",faq_title:"جزئیات قبل از تصمیم.",faq_description:"سوال‌هایی که معمولاً قبل از خرید یا اولین اتصال مطرح می‌شوند.",
  faq_1_question:"سرویس چه زمانی تحویل می‌شود؟",faq_1_answer:"بعد از تکمیل فرآیند خرید، وضعیت سفارش و اطلاعات سرویس از داخل حساب قابل پیگیری است.",
  faq_2_question:"چند دستگاه می‌توانم وصل کنم؟",faq_2_answer:"محدودیت دستگاه روی هر پلن به‌صورت مستقل نمایش داده می‌شود.",
  faq_3_question:"مصرف حجم کجا دیده می‌شود؟",faq_3_answer:"اطلاعات مصرف و وضعیت اشتراک از پنل کاربری قابل مشاهده است.",
  faq_4_question:"پروتکل مناسب را چطور انتخاب کنم؟",faq_4_answer:"پروتکل‌های در دسترس هر پلن و آموزش هر روش اتصال در فروشگاه نمایش داده می‌شوند.",
  faq_5_question:"برای راه‌اندازی کمک می‌گیرم؟",faq_5_answer:"بله؛ آموزش‌های مرحله‌ای و پشتیبانی آنلاین برای همین مسیر در دسترس‌اند.",
  trust_speed_title:"FAST",trust_speed_description:"مسیر اتصال بهینه",trust_uptime_value:"99.9%",trust_uptime_description:"هدف پایداری",trust_support_title:"LIVE",trust_support_description:"پشتیبانی مستقیم",trust_protocols_description:"connection methods",trust_payment_title:"TRACEABLE",trust_payment_description:"سفارش قابل پیگیری",trust_activation_title:"READY",trust_activation_description:"تحویل داخل حساب",
  final_cta_tag:"NEXT STEP",final_cta_title:"انتخاب کن، بخر، وصل شو.",final_cta_description:"مسیر خرید کوتاه می‌ماند و مدیریت سرویس بعد از آن داخل حساب ادامه پیدا می‌کند.",final_cta_button:"انتخاب پلن",
  contact_tag:"CONTACT",contact_title:"وقتی لازم است، مستقیم در دسترسیم.",contact_description:"برای پشتیبانی، آموزش و اطلاع‌رسانی از کانال‌های فعال استفاده کنید.",telegram_title:"Telegram",telegram_description:"Support / Updates",instagram_title:"Instagram",instagram_description:"News / Learning",whatsapp_title:"WhatsApp",whatsapp_description:"Quick contact",chat_title:"Live support",chat_description:"برای سوال‌های قبل یا بعد از خرید، گفت‌وگو را از همین صفحه شروع کنید.",footer_tagline:"A structured storefront for modern connectivity.",footer_quick_title:"Navigate",footer_support_title:"Service",footer_social_title:"Connect",footer_rights:"All rights reserved.",
  ...commonVisibility,
};

export const STORE_TEMPLATE_OPTION_DEFINITIONS:Record<string,StoreTemplateOptionDefinition>={
  "conversion-2027":{
    templateId:"conversion-2027",
    version:1,
    defaults:conversionDefaults,
    groups:[appearanceGroup(),...COMMON_CONTENT_GROUPS],
  },
  "editorial-grid-2027":{
    templateId:"editorial-grid-2027",
    version:1,
    defaults:editorialDefaults,
    groups:[appearanceGroup(),...COMMON_CONTENT_GROUPS],
  },
};

export function storeTemplateOptionDefinition(templateId:unknown){
  return STORE_TEMPLATE_OPTION_DEFINITIONS[String(templateId||"")]||null;
}

function normalizeSectionOrder(value:unknown,fallback:string[]):string[]{
  const source=Array.isArray(value)?value:fallback;
  const result:StorefrontSectionId[]=[];
  for(const item of source){
    const section=String(item) as StorefrontSectionId;
    if(STOREFRONT_SECTION_IDS.includes(section)&&!result.includes(section))result.push(section);
  }
  for(const section of STOREFRONT_SECTION_IDS)if(!result.includes(section))result.push(section);
  return result;
}

export function normalizeStoreTemplateOptions(templateId:unknown,raw:unknown):StoreTemplateOptionMap{
  const definition=storeTemplateOptionDefinition(templateId);
  if(!definition)return {};
  const source=raw&&typeof raw==="object"&&!Array.isArray(raw)?raw as Record<string,unknown>:{};
  const result:StoreTemplateOptionMap={};
  for(const [key,fallback] of Object.entries(definition.defaults)){
    const value=source[key];
    if(key==="section_order"){
      result[key]=normalizeSectionOrder(value,Array.isArray(fallback)?fallback.map(String):[...STOREFRONT_SECTION_IDS]);
    }else if(typeof fallback==="boolean"){
      result[key]=typeof value==="boolean"?value:fallback;
    }else if(typeof fallback==="number"){
      const number=Number(value);
      result[key]=Number.isFinite(number)?number:fallback;
    }else{
      result[key]=typeof value==="string"&&value.trim()?value:String(fallback??"");
    }
  }
  return result;
}

export function applyStoreTemplateOptions(settings:StorefrontSettings,templateId:unknown,raw:unknown){
  const options=normalizeStoreTemplateOptions(templateId,raw);
  const next={...settings} as StorefrontSettings;
  const target=next as unknown as Record<string,unknown>;
  for(const [key,value] of Object.entries(options)){
    if(key==="section_order"){
      next.section_order=normalizeSectionOrder(value,[...next.section_order]) as StorefrontSectionId[];
      continue;
    }
    if(key in target)target[key]=value;
  }
  return {settings:next,options};
}

export function storeTemplateCssVariables(options:StoreTemplateOptionMap){
  const primary=typeof options.theme_primary==="string"?options.theme_primary:"";
  const secondary=typeof options.theme_secondary==="string"?options.theme_secondary:"";
  return {
    ...(primary?{"--brand-primary":primary}:{}),
    ...(secondary?{"--brand-secondary":secondary}:{}),
  } as Record<string,string>;
}
