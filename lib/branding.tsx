"use client";

import {createContext,useContext,useEffect,useMemo,useState} from "react";

export type BrandingConfig={
  name:string;
  shortName:string;
  tagline:string;
  logoUrl:string;
  supportLink:string;
  accent:string;
};

export const DEFAULT_BRANDING:BrandingConfig={
  name:"TwinPanel",
  shortName:"TP",
  tagline:"VPN CONTROL 2027",
  logoUrl:"/logo.svg",
  supportLink:"https://t.me/support",
  accent:"#7c3aed"
};

const STORAGE_KEY="twinpanel.branding.preview";

type BrandingContextValue={
  brand:BrandingConfig;
  updateBrand:(next:Partial<BrandingConfig>)=>void;
  resetBrand:()=>void;
};

const BrandingContext=createContext<BrandingContextValue|null>(null);

export function BrandingProvider({children}:{children:React.ReactNode}){
  const [brand,setBrand]=useState<BrandingConfig>(DEFAULT_BRANDING);

  useEffect(()=>{
    try{
      const raw=localStorage.getItem(STORAGE_KEY);
      if(raw) setBrand({...DEFAULT_BRANDING,...JSON.parse(raw)});
    }catch{}
  },[]);

  useEffect(()=>{
    document.title=brand.name;
    document.documentElement.style.setProperty("--brand-accent",brand.accent);
  },[brand.name,brand.accent]);

  const updateBrand=(next:Partial<BrandingConfig>)=>{
    setBrand(prev=>{
      const merged={...prev,...next};
      try{localStorage.setItem(STORAGE_KEY,JSON.stringify(merged));}catch{}
      return merged;
    });
  };

  const resetBrand=()=>{
    setBrand(DEFAULT_BRANDING);
    try{localStorage.removeItem(STORAGE_KEY);}catch{}
  };

  const value=useMemo(()=>({brand,updateBrand,resetBrand}),[brand]);
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
