"use client";

import {createContext,useContext,useEffect,useMemo,useState} from "react";

export type Lang="fa"|"en";

type I18nValue={
  lang:Lang;
  language:Lang;
  setLang:(lang:Lang)=>void;
  toggle:()=>void;
  pick:(fa:string,en:string)=>string;
  dir:"rtl"|"ltr";
};

const I18nContext=createContext<I18nValue|null>(null);

export function I18nProvider({children}:{children:React.ReactNode}){
  const [lang,setLangState]=useState<Lang>("fa");

  useEffect(()=>{
    const saved=window.localStorage.getItem("twinpanel.lang");
    const initial:Lang=saved==="en"?"en":"fa";
    setLangState(initial);
  },[]);

  useEffect(()=>{
    document.documentElement.lang=lang;
    document.documentElement.dir=lang==="fa"?"rtl":"ltr";
    window.localStorage.setItem("twinpanel.lang",lang);
  },[lang]);

  const value=useMemo<I18nValue>(()=>({
    lang,
    language:lang,
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
