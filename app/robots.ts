import type {MetadataRoute} from "next";
import {getStorefrontSeoContext} from "../lib/storefront-seo-server";

export default async function robots():Promise<MetadataRoute.Robots>{
  const ctx=await getStorefrontSeoContext();
  return {
    rules:{
      userAgent:"*",
      allow:"/",
      disallow:[
        "/admin/",
        "/customer/",
        "/reseller/",
        "/login",
        "/register",
        "/forgot-password",
        "/reset-password",
        "/v1/",
      ],
    },
    ...(ctx.origin?{sitemap:`${ctx.origin}/sitemap.xml`}:{}),
  };
}
