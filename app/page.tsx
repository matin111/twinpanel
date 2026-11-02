import type {Metadata} from "next";
import {StoreRuntime2027} from "../components/store-runtime";
import {buildStorefrontJsonLd,buildStorefrontMetadata,serializeJsonLd} from "../lib/storefront-seo-server";

export async function generateMetadata():Promise<Metadata>{
  return buildStorefrontMetadata();
}

export default async function Page(){
  const jsonLd=await buildStorefrontJsonLd();
  return <>
    <script type="application/ld+json" dangerouslySetInnerHTML={{__html:serializeJsonLd(jsonLd)}}/>
    <StoreRuntime2027/>
  </>;
}
