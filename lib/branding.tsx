"use client";

import {createContext,useCallback,useContext,useEffect,useMemo,useState} from "react";
import {brandingApi,BrandingRecord} from "./branding-api";

export type BrandingConfig={
  name:string;
  shortName:string;
  tagline:string;
  logoUrl:string;
  faviconUrl:string;
  supportLink:string;
  accent:string;
  secondaryColor:string;
};

export const DEFAULT_BRANDING:BrandingConfig={
  name:"TwinPanel",
  shortName:"TP",
  tagline:"VPN CONTROL 2027",
  logoUrl:"/logo.svg",
  faviconUrl:"/logo.svg",
  supportLink:"https://t.me/support",
  accent:"#7C3AED",
  secondaryColor:"#4F46E5",
};

function validHex(value:unknown,fallback:string){
  const text=String(value||"").trim();
  return /^#[0-9a-fA-F]{6}$/.test(text)?text.toUpperCase():fallback;
}

function shortNameOf(name:string){
  const parts=name.trim().split(/\s+/).filter(Boolean);
  if(parts.length>1)return parts.slice(0,2).map(part=>part[0]).join("").toUpperCase();
  return (parts[0]||DEFAULT_BRANDING.shortName).slice(0,2).toUpperCase();
}

export function configFromBrandingRecord(row:BrandingRecord):BrandingConfig{
  const name=String(row.brand_name||row.site_title||DEFAULT_BRANDING.name).trim()||DEFAULT_BRANDING.name;
  return {
    name,
    shortName:shortNameOf(name),
    tagline:String(row.site_description||DEFAULT_BRANDING.tagline).trim()||DEFAULT_BRANDING.tagline,
    logoUrl:String(row.logo_url||DEFAULT_BRANDING.logoUrl),
    faviconUrl:String(row.favicon_url||DEFAULT_BRANDING.faviconUrl),
    supportLink:String(row.telegram_url||DEFAULT_BRANDING.supportLink),
    accent:validHex(row.primary_color,DEFAULT_BRANDING.accent),
    secondaryColor:validHex(row.secondary_color,DEFAULT_BRANDING.secondaryColor),
  };
}

type BrandingContextValue={
  brand:BrandingConfig;
  ready:boolean;
  updateBrand:(next:Partial<BrandingConfig>)=>void;
  reloadBrand:()=>Promise<BrandingConfig>;
  resetBrand:()=>void;
};

const BrandingContext=createContext<BrandingContextValue|null>(null);

export function BrandingProvider({children}:{children:React.ReactNode}){
  const [brand,setBrand]=useState<BrandingConfig>(DEFAULT_BRANDING);
  const [ready,setReady]=useState(false);

  const reloadBrand=useCallback(async()=>{
    try{
      const next=configFromBrandingRecord(await brandingApi.get());
      setBrand(next);
      return next;
    }finally{
      setReady(true);
    }
  },[]);

  useEffect(()=>{void reloadBrand();},[reloadBrand]);

  useEffect(()=>{
    const root=document.documentElement;
    root.style.setProperty("--brand-primary",brand.accent);
    root.style.setProperty("--brand-secondary",brand.secondaryColor);
    root.style.setProperty("--brand-accent",brand.accent);
    root.style.setProperty("--purple",brand.accent);
    root.style.setProperty("--purple2",brand.secondaryColor);
    document.title=brand.name;

    let favicon=document.querySelector<HTMLLinkElement>('link[rel~="icon"]');
    if(!favicon){
      favicon=document.createElement("link");
      favicon.rel="icon";
      document.head.appendChild(favicon);
    }
    favicon.href=brand.faviconUrl;
  },[brand.name,brand.accent,brand.secondaryColor,brand.faviconUrl]);

  const updateBrand=(next:Partial<BrandingConfig>)=>setBrand(current=>({...current,...next}));
  const resetBrand=()=>setBrand(DEFAULT_BRANDING);

  const value=useMemo<BrandingContextValue>(()=>({brand,ready,updateBrand,reloadBrand,resetBrand}),[brand,ready,reloadBrand]);
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
    <img src={brand.logoUrl} alt={brand.name}/>
    {!compact&&<div className="brand-copy"><b>{brand.name}</b></div>}
  </div>;
}
