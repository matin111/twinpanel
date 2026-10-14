"use client";

import {createContext,useContext,useEffect,useMemo,useState} from "react";
import {usePathname} from "next/navigation";

export type Lang="fa"|"en";
type LangScope="admin"|"reseller"|"customer"|"public";

type I18nValue={
  lang:Lang;
  setLang:(lang:Lang)=>void;
  toggle:()=>void;
  pick:(fa:string,en:string)=>string;
  dir:"rtl"|"ltr";
};

const I18nContext=createContext<I18nValue|null>(null);

function scopeForPath(pathname:string):LangScope{
  if(pathname==="/admin"||pathname.startsWith("/admin/"))return "admin";
  if(pathname==="/reseller"||pathname.startsWith("/reseller/"))return "reseller";
  if(pathname==="/panel"||pathname.startsWith("/panel/"))return "customer";
  return "public";
}

function savedLanguage(scope:LangScope):Lang{
  const scoped=window.localStorage.getItem(`twinpanel.lang.${scope}`);
  if(scoped==="fa"||scoped==="en")return scoped;

  // Reseller is deliberately isolated from the legacy global key. Previously,
  // changing the admin panel to English also forced the reseller portal into
  // English. A reseller with no explicit preference must start in Persian.
  if(scope==="reseller")return "fa";

  const legacy=window.localStorage.getItem("twinpanel.lang");
  return legacy==="en"?"en":"fa";
}

export function I18nProvider({children}:{children:React.ReactNode}){
  const pathname=usePathname()||"/";
  const scope=useMemo(()=>scopeForPath(pathname),[pathname]);
  const [lang,setLangState]=useState<Lang>("fa");
  const [readyScope,setReadyScope]=useState<LangScope|null>(null);

  useEffect(()=>{
    const initial=savedLanguage(scope);
    setLangState(initial);
    setReadyScope(scope);
    document.documentElement.lang=initial;
    document.documentElement.dir=initial==="fa"?"rtl":"ltr";
  },[scope]);

  useEffect(()=>{
    if(readyScope!==scope)return;
    document.documentElement.lang=lang;
    document.documentElement.dir=lang==="fa"?"rtl":"ltr";
    window.localStorage.setItem(`twinpanel.lang.${scope}`,lang);
  },[lang,scope,readyScope]);

  const value=useMemo<I18nValue>(()=>({
    lang,
    setLang:(next)=>setLangState(next),
    toggle:()=>setLangState(v=>v==="fa"?"en":"fa"),
    pick:(fa,en)=>lang==="fa"?fa:en,
    dir:lang==="fa"?"rtl":"ltr"
  }),[lang]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(){
  const ctx=useContext(I18nContext);
  if(!ctx) throw new Error("useI18n must be used inside I18nProvider");
  return ctx;
}

export function LanguageSwitch({compact=false}:{compact?:boolean}){
  const {lang,setLang}=useI18n();
  return <div className={`lang-switch ${compact?"compact":""}`} aria-label="Language selector">
    <button className={lang==="fa"?"active":""} onClick={()=>setLang("fa")} type="button">FA</button>
    <button className={lang==="en"?"active":""} onClick={()=>setLang("en")} type="button">EN</button>
  </div>;
}
