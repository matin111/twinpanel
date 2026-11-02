import type {Metadata} from "next";
import {headers} from "next/headers";
import {cache} from "react";

const ORBIT_TEMPLATE_ID="orbit-neo-2027";
const LEGACY_SEO_TITLE="اشتراک VPN | اتصال سریع و پایدار";
const LEGACY_SEO_DESCRIPTION="خرید اشتراک VPN برای ویندوز، اندروید، آیفون، مک و لینوکس با چند روش اتصال، پنل کاربری و پشتیبانی آنلاین.";
const LEGACY_OG_TITLE="اشتراک VPN | اتصال سریع و پایدار";
const LEGACY_OG_DESCRIPTION="خرید و مدیریت اشتراک VPN برای همه دستگاه‌ها از یک پنل کاربری.";
const LEGACY_CANONICAL="https://movilineapp.com/";

type JsonRecord=Record<string,unknown>;

export type StorefrontSeoContext={
  origin:string;
  canonicalUrl:string;
  brandName:string;
  brandLogo:string;
  activeTemplate:string;
  values:JsonRecord;
  templateValues:JsonRecord;
  robotsIndex:boolean;
};

function record(value:unknown):JsonRecord{
  return value&&typeof value==="object"&&!Array.isArray(value)?value as JsonRecord:{};
}

function text(value:unknown){
  return typeof value==="string"?value.trim():"";
}

function bool(value:unknown,fallback=true){
  return typeof value==="boolean"?value:fallback;
}

function hasOwn(source:JsonRecord,key:string){
  return Object.prototype.hasOwnProperty.call(source,key);
}

function firstHeader(value:string|null){
  return (value||"").split(",")[0]?.trim()||"";
}

function normalizedOrigin(value:string){
  const raw=value.trim().replace(/\/+$/,"");
  if(!raw)return "";
  try{
    const url=new URL(raw);
    return `${url.protocol}//${url.host}`;
  }catch{return "";}
}

async function requestOrigin(){
  const h=await headers();
  const host=firstHeader(h.get("x-forwarded-host"))||firstHeader(h.get("host"));
  const proto=firstHeader(h.get("x-forwarded-proto"))||(host.startsWith("localhost")||host.startsWith("127.0.0.1")?"http":"https");
  if(host)return `${proto}://${host}`;
  return normalizedOrigin(process.env.NEXT_PUBLIC_SITE_URL||process.env.NEXT_PUBLIC_APP_URL||process.env.NEXT_PUBLIC_API_BASE||"");
}

async function getJson(url:string):Promise<JsonRecord>{
  if(!url)return {};
  try{
    const response=await fetch(url,{cache:"no-store",headers:{Accept:"application/json"}});
    if(!response.ok)return {};
    return record(await response.json());
  }catch{return {};}
}

function absoluteUrl(value:unknown,origin:string){
  const raw=text(value);
  if(!raw)return "";
  try{return new URL(raw,origin||undefined).toString();}catch{return "";}
}

function effectiveValue(template:JsonRecord,global:JsonRecord,key:string){
  return hasOwn(template,key)?template[key]:global[key];
}

function isLegacyCanonical(value:string){
  try{
    const url=new URL(value);
    return url.hostname.toLowerCase()==="movilineapp.com"&&url.pathname==="/";
  }catch{return value===LEGACY_CANONICAL;}
}

export const getStorefrontSeoContext=cache(async():Promise<StorefrontSeoContext>=>{
  const origin=await requestOrigin();
  const [globalRaw,templatesRaw,brandingRaw]=await Promise.all([
    getJson(origin?`${origin}/v1/storefront/settings`:""),
    getJson(origin?`${origin}/v1/storefront/settings/templates`:""),
    getJson(origin?`${origin}/v1/settings/branding`:""),
  ]);

  const global=record(globalRaw.settings||globalRaw);
  const activeTemplate=text(global.active_template)||ORBIT_TEMPLATE_ID;
  const templates=record(templatesRaw.templates);
  const template=record(templates[activeTemplate]);
  const values:{[key:string]:unknown}={...global,...template};
  const brandName=text(brandingRaw.brand_name)||text(brandingRaw.site_title)||"TwinPanel";
  const brandLogo=absoluteUrl(brandingRaw.logo_url,origin);
  const configuredCanonical=text(effectiveValue(template,global,"canonical_url"));
  const ignoreLegacyCanonical=activeTemplate===ORBIT_TEMPLATE_ID&&!hasOwn(template,"canonical_url")&&isLegacyCanonical(configuredCanonical);
  const canonicalUrl=ignoreLegacyCanonical
    ?(origin?`${origin}/`:"")
    :absoluteUrl(configuredCanonical,origin)||(origin?`${origin}/`:"");

  return {
    origin,
    canonicalUrl,
    brandName,
    brandLogo,
    activeTemplate,
    values,
    templateValues:template,
    robotsIndex:bool(effectiveValue(template,global,"robots_index"),true),
  };
});

function orbitText(ctx:StorefrontSeoContext,key:string,legacy:string,fallback:string){
  const configured=text(ctx.values[key]);
  if(hasOwn(ctx.templateValues,key))return configured||fallback;
  if(ctx.activeTemplate===ORBIT_TEMPLATE_ID&&configured===legacy)return fallback;
  return configured||fallback;
}

function resolvedCoreSeo(ctx:StorefrontSeoContext){
  const orbit=ctx.activeTemplate===ORBIT_TEMPLATE_ID;
  const fallbackTitle=orbit
    ?`خرید VPN با IP ثابت | ۱۵ پروتکل | ${ctx.brandName}`
    :`${ctx.brandName} | خرید اشتراک VPN`;
  const fallbackDescription=orbit
    ?`خرید VPN با IP ثابت برای اندروید، آیفون، ویندوز، مک و لینوکس؛ ۱۵ روش اتصال، تحویل سریع، پنل کاربری و پشتیبانی آنلاین از ${ctx.brandName}.`
    :`خرید و مدیریت اشتراک VPN برای همه دستگاه‌ها با تحویل سریع، پنل کاربری و پشتیبانی آنلاین از ${ctx.brandName}.`;
  const title=orbitText(ctx,"seo_title",LEGACY_SEO_TITLE,fallbackTitle);
  const description=orbitText(ctx,"seo_description",LEGACY_SEO_DESCRIPTION,fallbackDescription);
  const ogTitle=orbitText(ctx,"og_title",LEGACY_OG_TITLE,title);
  const ogDescription=orbitText(ctx,"og_description",LEGACY_OG_DESCRIPTION,description);
  return {title,description,ogTitle,ogDescription};
}

export async function buildStorefrontMetadata():Promise<Metadata>{
  const ctx=await getStorefrontSeoContext();
  const values=ctx.values;
  const {title,description,ogTitle,ogDescription}=resolvedCoreSeo(ctx);
  const ogImage=absoluteUrl(values.og_image,ctx.origin)||ctx.brandLogo;
  const keywords=text(values.seo_keywords).split(",").map(item=>item.trim()).filter(Boolean);
  const index=bool(values.robots_index,true);
  const follow=bool(values.robots_follow,true);

  return {
    ...(ctx.origin?{metadataBase:new URL(ctx.origin)}:{}),
    title,
    description,
    ...(keywords.length?{keywords}:{}),
    ...(ctx.canonicalUrl?{alternates:{canonical:ctx.canonicalUrl}}:{}),
    robots:{index,follow,googleBot:{index,follow}},
    openGraph:{
      type:"website",
      locale:"fa_IR",
      title:ogTitle,
      description:ogDescription,
      ...(ctx.canonicalUrl?{url:ctx.canonicalUrl}:{}),
      siteName:ctx.brandName,
      ...(ogImage?{images:[{url:ogImage,alt:ctx.brandName}]}:{}),
    },
    twitter:{
      card:ogImage?"summary_large_image":"summary",
      title:ogTitle,
      description:ogDescription,
      ...(ogImage?{images:[ogImage]}:{}),
    },
  };
}

function faqEntries(values:JsonRecord){
  if(values.show_faq===false)return [];
  const entries=[] as Array<{"@type":"Question";name:string;acceptedAnswer:{"@type":"Answer";text:string}}>;
  for(let index=1;index<=5;index+=1){
    const question=text(values[`faq_${index}_question`]);
    const answer=text(values[`faq_${index}_answer`]);
    if(question&&answer)entries.push({"@type":"Question",name:question,acceptedAnswer:{"@type":"Answer",text:answer}});
  }
  return entries;
}

export async function buildStorefrontJsonLd(){
  const ctx=await getStorefrontSeoContext();
  const {title,description}=resolvedCoreSeo(ctx);
  const graph:Array<JsonRecord>=[
    {
      "@type":"Organization",
      "@id":ctx.canonicalUrl?`${ctx.canonicalUrl}#organization`:"#organization",
      name:ctx.brandName,
      ...(ctx.canonicalUrl?{url:ctx.canonicalUrl}:{}),
      ...(ctx.brandLogo?{logo:ctx.brandLogo}:{}),
    },
    {
      "@type":"WebSite",
      "@id":ctx.canonicalUrl?`${ctx.canonicalUrl}#website`:"#website",
      name:ctx.brandName,
      ...(ctx.canonicalUrl?{url:ctx.canonicalUrl}:{}),
      inLanguage:"fa-IR",
    },
    {
      "@type":"WebPage",
      "@id":ctx.canonicalUrl?`${ctx.canonicalUrl}#webpage`:"#webpage",
      name:title,
      description,
      ...(ctx.canonicalUrl?{url:ctx.canonicalUrl}:{}),
      inLanguage:"fa-IR",
    },
  ];
  const faqs=faqEntries(ctx.values);
  if(faqs.length)graph.push({"@type":"FAQPage",mainEntity:faqs});
  return {"@context":"https://schema.org","@graph":graph};
}

export function serializeJsonLd(value:unknown){
  return JSON.stringify(value).replace(/</g,"\\u003c");
}
