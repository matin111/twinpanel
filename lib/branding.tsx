"use client";

import {createContext,useCallback,useContext,useEffect,useMemo,useState} from "react";
import {BrandingApiRecord,brandingApi,resolveBrandingAssetUrl} from "./branding-api";

export type BrandingConfig={
  name:string;
  shortName:string;
  tagline:string;
  logoUrl:string;
  faviconUrl:string;
  supportLink:string;
  accent:string;
  primaryColor:string;
  secondaryColor:string;
};

export const DEFAULT_BRANDING:BrandingConfig={
  name:"TwinPanel",
  shortName:"TP",
  tagline:"VPN CONTROL 2027",
  logoUrl:"/logo.svg",
  faviconUrl:"",
  supportLink:"https://t.me/support",
  accent:"#7C3AED",
  primaryColor:"#7C3AED",
  secondaryColor:"#4F46E5",
};

function shortNameOf(name:string){
  const parts=name.trim().split(/\s+/).filter(Boolean);
  if(parts.length>=2)return `${parts[0]?.[0]||""}${parts[1]?.[0]||""}`.toUpperCase();
  return (parts[0]||DEFAULT_BRANDING.shortName).slice(0,2).toUpperCase();
}

export function brandingFromApi(value:BrandingApiRecord):BrandingConfig{
  const name=String(value.brand_name||DEFAULT_BRANDING.name).trim()||DEFAULT_BRANDING.name;
  const primary=String(value.primary_color||DEFAULT_BRANDING.primaryColor).trim()||DEFAULT_BRANDING.primaryColor;
  const secondary=String(value.secondary_color||DEFAULT_BRANDING.secondaryColor).trim()||DEFAULT_BRANDING.secondaryColor;
  return {
    name,
    shortName:shortNameOf(name),
    tagline:String(value.site_title||DEFAULT_BRANDING.tagline),
    logoUrl:resolveBrandingAssetUrl(value.logo_url)||DEFAULT_BRANDING.logoUrl,
    faviconUrl:resolveBrandingAssetUrl(value.favicon_url),
    supportLink:String(value.telegram_url||DEFAULT_BRANDING.supportLink),
    accent:primary,
    primaryColor:primary,
    secondaryColor:secondary,
  };
}

type BrandingContextValue={
  brand:BrandingConfig;
  updateBrand:(next:Partial<BrandingConfig>)=>void;
  resetBrand:()=>void;
  reloadBrand:()=>Promise<void>;
  replaceBrand:(record:BrandingApiRecord)=>void;
};

const BrandingContext=createContext<BrandingContextValue|null>(null);

export function BrandingProvider({children}:{children:React.ReactNode}){
  const [brand,setBrand]=useState<BrandingConfig>(DEFAULT_BRANDING);

  const replaceBrand=useCallback((record:BrandingApiRecord)=>{
    setBrand(brandingFromApi(record));
  },[]);

  const reloadBrand=useCallback(async()=>{
    const record=await brandingApi.get();
    replaceBrand(record);
  },[replaceBrand]);

  useEffect(()=>{
    void reloadBrand().catch(()=>{});
  },[reloadBrand]);

  useEffect(()=>{
    document.title=brand.name;
    const root=document.documentElement;
    root.style.setProperty("--brand-primary",brand.primaryColor);
    root.style.setProperty("--brand-secondary",brand.secondaryColor);
    root.style.setProperty("--brand-accent",brand.primaryColor);
    root.style.setProperty("--purple",brand.primaryColor);
    root.style.setProperty("--purple2",brand.secondaryColor);

    const selector='link[data-twinpanel-brand-favicon="1"]';
    let icon=document.head.querySelector<HTMLLinkElement>(selector);
    if(brand.faviconUrl){
      if(!icon){
        icon=document.createElement("link");
        icon.rel="icon";
        icon.dataset.twinpanelBrandFavicon="1";
        document.head.appendChild(icon);
      }
      icon.href=brand.faviconUrl;
    }else if(icon){
      icon.remove();
    }
  },[brand.name,brand.primaryColor,brand.secondaryColor,brand.faviconUrl]);

  const updateBrand=useCallback((next:Partial<BrandingConfig>)=>{
    setBrand(prev=>{
      const merged={...prev,...next};
      if(next.accent&&!next.primaryColor)merged.primaryColor=next.accent;
      if(next.primaryColor)merged.accent=next.primaryColor;
      return merged;
    });
  },[]);

  const resetBrand=useCallback(()=>{
    void reloadBrand().catch(()=>setBrand(DEFAULT_BRANDING));
  },[reloadBrand]);

  const value=useMemo<BrandingContextValue>(()=>({
    brand,
    updateBrand,
    resetBrand,
    reloadBrand,
    replaceBrand,
  }),[brand,reloadBrand,replaceBrand,resetBrand,updateBrand]);

  return <BrandingContext.Provider value={value}>{children}</BrandingContext.Provider>;
}

export function useBranding(){
  const value=useContext(BrandingContext);
  if(!value) throw new Error("useBranding must be used inside BrandingProvider");
  return value;
}

export function BrandMark({compact=false}:{compact?:boolean}){
  const {brand}=useBranding();
  return <div className="brand">
    <img
      src={brand.logoUrl||DEFAULT_BRANDING.logoUrl}
      alt={brand.name}
      onError={event=>{
        if(event.currentTarget.src.endsWith(DEFAULT_BRANDING.logoUrl))return;
        event.currentTarget.src=DEFAULT_BRANDING.logoUrl;
      }}
    />
    {!compact&&<div className="brand-copy"><b>{brand.name}</b></div>}
  </div>;
}
