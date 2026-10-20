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
    nameFa:"Editorial Pro 2027",
    nameEn:"Editorial Pro 2027",
    descriptionFa:"قالب پریمیوم مستقل با هویت ادیتوریال مدرن، تنظیمات اختصاصی، Hero قابل انتخاب، چیدمان فروش Spotlight/Comparison، تراکم صفحه، کنترل اجزای ادیتوریال و تجربه راهنمای حرفه‌ای؛ کاملاً مستقل از تنظیمات قالب Conversion.",
    descriptionEn:"A premium independent editorial storefront with its own editor, selectable hero compositions, Spotlight/Comparison plan layouts, density controls, editorial modules and a refined guide experience—fully separate from Conversion theme settings.",
    version:"2.0.0",
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
