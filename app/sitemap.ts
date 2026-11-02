import type {MetadataRoute} from "next";
import {getStorefrontSeoContext} from "../lib/storefront-seo-server";

export default async function sitemap():Promise<MetadataRoute.Sitemap>{
  const ctx=await getStorefrontSeoContext();
  if(!ctx.canonicalUrl||!ctx.robotsIndex)return [];
  return [{
    url:ctx.canonicalUrl,
    lastModified:new Date(),
    changeFrequency:"daily",
    priority:1,
  }];
}
