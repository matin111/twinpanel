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

export const STORE_TEMPLATE_CATALOG:readonly StoreTemplateDefinition[]=[
  {
    id:"conversion-2027",
    nameFa:"قالب یک",
    nameEn:"Template 1",
    descriptionFa:"قالب ساده و مدرن برای فروش اشتراک VPN.",
    descriptionEn:"A clean modern storefront for selling VPN subscriptions.",
    version:"2.0.0",
    author:"TwinPanel",
    builtIn:true,
    supportsDark:true,
    supportsLight:true,
  },
  {
    id:"editorial-grid-2027",
    nameFa:"قالب دو",
    nameEn:"Template 2",
    descriptionFa:"قالب حرفه‌ای برای معرفی سرویس، پلن‌ها و امکانات VPN.",
    descriptionEn:"A professional storefront for VPN plans, service details and support.",
    version:"2.0.0",
    author:"TwinPanel",
    builtIn:true,
    supportsDark:true,
    supportsLight:true,
  },
  {
    id:"orbit-neo-2027",
    nameFa:"قالب سه",
    nameEn:"Template 3",
    descriptionFa:"قالب تصویری و فروش‌محور برای اشتراک VPN.",
    descriptionEn:"A visual sales-focused storefront for VPN subscriptions.",
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
