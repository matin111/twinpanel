"use client";

import {useEffect} from "react";
import type {StorefrontSettings} from "../lib/storefront-config";

type Cleanup=()=>void;

function absoluteHttpUrl(value:string,fallback:string){
  const source=value.trim()||fallback;
  try{
    const url=new URL(source,window.location.origin);
    return url.protocol==="http:"||url.protocol==="https:"?url.toString():fallback;
  }catch{return fallback;}
}

function setMeta(attribute:"name"|"property",key:string,content:string):Cleanup{
  const selector=`meta[${attribute}="${key}"]`;
  const existing=document.head.querySelector<HTMLMetaElement>(selector);
  if(existing){
    const previous=existing.getAttribute("content");
    existing.setAttribute("content",content);
    return()=>{
      if(previous===null)existing.removeAttribute("content");
      else existing.setAttribute("content",previous);
    };
  }
  const element=document.createElement("meta");
  element.setAttribute(attribute,key);
  element.setAttribute("content",content);
  element.dataset.twinpanelStoreSeo="true";
  document.head.appendChild(element);
  return()=>element.remove();
}

function setLink(rel:string,href:string):Cleanup{
  const existing=document.head.querySelector<HTMLLinkElement>(`link[rel="${rel}"]`);
  if(existing){
    const previous=existing.getAttribute("href");
    existing.setAttribute("href",href);
    return()=>{
      if(previous===null)existing.removeAttribute("href");
      else existing.setAttribute("href",previous);
    };
  }
  const element=document.createElement("link");
  element.rel=rel;
  element.href=href;
  element.dataset.twinpanelStoreSeo="true";
  document.head.appendChild(element);
  return()=>element.remove();
}

export function StorefrontSeoRuntime({settings}:{settings:StorefrontSettings}){
  useEffect(()=>{
    const previousTitle=document.title;
    const currentStoreUrl=`${window.location.origin}${window.location.pathname}`;
    const title=settings.seo_title.trim()||previousTitle||"TwinPanel";
    const description=settings.seo_description.trim();
    const keywords=settings.seo_keywords.trim();
    const canonical=absoluteHttpUrl(settings.canonical_url,currentStoreUrl);
    const ogTitle=settings.og_title.trim()||title;
    const ogDescription=settings.og_description.trim()||description;
    const ogImage=settings.og_image.trim()?absoluteHttpUrl(settings.og_image.trim(),""):"";
    const robots=`${settings.robots_index?"index":"noindex"}, ${settings.robots_follow?"follow":"nofollow"}`;
    const cleanups:Cleanup[]=[];

    document.title=title;
    cleanups.push(()=>{document.title=previousTitle;});
    cleanups.push(setMeta("name","description",description));
    if(keywords)cleanups.push(setMeta("name","keywords",keywords));
    cleanups.push(setMeta("name","robots",robots));
    cleanups.push(setLink("canonical",canonical));

    cleanups.push(setMeta("property","og:type","website"));
    cleanups.push(setMeta("property","og:title",ogTitle));
    cleanups.push(setMeta("property","og:description",ogDescription));
    cleanups.push(setMeta("property","og:url",canonical));
    if(ogImage)cleanups.push(setMeta("property","og:image",ogImage));

    cleanups.push(setMeta("name","twitter:card",ogImage?"summary_large_image":"summary"));
    cleanups.push(setMeta("name","twitter:title",ogTitle));
    cleanups.push(setMeta("name","twitter:description",ogDescription));
    if(ogImage)cleanups.push(setMeta("name","twitter:image",ogImage));

    return()=>{
      for(const cleanup of cleanups.reverse())cleanup();
    };
  },[
    settings.seo_title,
    settings.seo_description,
    settings.seo_keywords,
    settings.canonical_url,
    settings.og_title,
    settings.og_description,
    settings.og_image,
    settings.robots_index,
    settings.robots_follow,
  ]);

  return null;
}
