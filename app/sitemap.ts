import type {MetadataRoute} from "next";
import {getStorefrontSeoContext} from "../lib/storefront-seo-server";
import {NOVA_ARTICLES} from "../lib/nova-articles";

const NOVA_PAGES=["/vpn-services","/vpn-static-ip","/vpn-reseller","/vpn-guides","/vpn-faq","/vpn-about","/vpn-blog"];

export default async function sitemap():Promise<MetadataRoute.Sitemap>{
  const ctx=await getStorefrontSeoContext();
  if(!ctx.canonicalUrl||!ctx.robotsIndex)return [];
  const home={url:ctx.canonicalUrl,lastModified:new Date(),changeFrequency:"daily" as const,priority:1};
  if(ctx.activeTemplate!=="nova-multipage-2027"||!ctx.origin)return [home];
  return [home,
    ...NOVA_PAGES.map(path=>({url:new URL(path,ctx.origin).toString(),lastModified:new Date(),changeFrequency:"weekly" as const,priority:0.7})),
    ...NOVA_ARTICLES.map(article=>({url:new URL("/vpn-blog/"+article.slug,ctx.origin).toString(),lastModified:new Date(article.updated+"T00:00:00Z"),changeFrequency:"monthly" as const,priority:0.6})),
  ];
}
