export type StoreTemplateDefinition={
  id:string;
  nameFa:string;
  nameEn:string;
  descriptionFa:string;
  descriptionEn:string;
  version:string;
  author:string;
  builtIn:boolean;
  supportsDark:boolean;
  supportsLight:boolean;
};

export const DEFAULT_STORE_TEMPLATE_ID="conversion-2027";

/**
 * Installed storefront templates ship with TwinPanel updates.
 * Adding a new template does not require a database migration: add its metadata
 * here, register its renderer in components/store-template-renderer.tsx and ship
 * both files with the product update. The admin's selected template id is stored
 * in storefront_settings.content and survives future updates.
 */
export const STORE_TEMPLATE_CATALOG:readonly StoreTemplateDefinition[]=[
  {
    id:"conversion-2027",
    nameFa:"فروش حرفه‌ای 2027",
    nameEn:"Conversion 2027",
    descriptionFa:"قالب فروش نوآورانه و Mobile-first با Hero تصویری، پلن‌های واقعی، پروتکل‌ها، آموزش نصب، امکانات، FAQ، شبکه‌های اجتماعی و چت آنلاین.",
    descriptionEn:"Mobile-first conversion storefront with visual hero, live plans, protocols, setup guides, benefits, FAQ, social contact and live chat.",
    version:"2.0.0",
    author:"TwinPanel",
    builtIn:true,
    supportsDark:true,
    supportsLight:true,
  },
  {
    id:"editorial-grid-2027",
    nameFa:"ادیتوریال گرید 2027",
    nameEn:"Editorial Grid 2027",
    descriptionFa:"قالب دوم با هویت کاملاً متفاوت: طراحی ادیتوریال و مینیمال، تایپوگرافی درشت، Grid ساختاری، پلن‌های تخت، پروتکل‌های شماره‌دار و آموزش Rail/Article؛ با پشتیبانی کامل از RTL، موبایل و Dark/Light.",
    descriptionEn:"A distinctly different editorial storefront with oversized typography, structural grids, flat plan cards, numbered protocol rows and rail/article setup guides, with full RTL, mobile and dark/light support.",
    version:"1.0.0",
    author:"TwinPanel",
    builtIn:true,
    supportsDark:true,
    supportsLight:true,
  },
] as const;

export function installedStoreTemplate(id:unknown){
  const value=String(id||"").trim();
  return STORE_TEMPLATE_CATALOG.find(template=>template.id===value)||null;
}

export function resolveStoreTemplateId(id:unknown){
  return installedStoreTemplate(id)?.id||DEFAULT_STORE_TEMPLATE_ID;
}
