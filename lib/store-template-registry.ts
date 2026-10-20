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
 * Installed storefront themes ship with TwinPanel updates.
 * A theme is made of three explicit contracts:
 * 1) metadata in this catalog,
 * 2) its isolated option schema/defaults in lib/store-template-options.ts,
 * 3) its renderer registration in components/store-template-runtime-registry.tsx.
 *
 * Per-theme admin settings are persisted under the storefront JSON namespace and
 * survive activation switches and later product updates. No database migration is
 * required when a new built-in theme is added.
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
